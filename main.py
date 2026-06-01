"""超星学习通 未完成章节视频顺序播放工具

按顺序遍历课程中所有未完成章节，并静音、以 2 倍速依次播放章节内的视频。
使用持久化浏览器用户目录保存登录态，打包后优先使用内置 Chromium。
"""

import asyncio
import sys
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

RUNTIME_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BUNDLED_BROWSER_DIRS = [
    RUNTIME_DIR / "ms-playwright",
    Path(getattr(sys, "_MEIPASS", RUNTIME_DIR)) / "ms-playwright",
]
for browser_dir in BUNDLED_BROWSER_DIRS:
    if browser_dir.exists():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browser_dir))
        break

from playwright.async_api import async_playwright

import config
from chapter_parser import get_chapters, filter_unfinished
from video_automator import (
    VIDEO_COMPLETED,
    VIDEO_FAILED,
    VIDEO_SKIPPED,
    play_chapter_videos,
)


async def main():
    force = "--force" in sys.argv
    _apply_cli_options()
    print("=" * 50)
    print("超星学习通 未完成章节视频静音 2 倍速播放工具")
    if force:
        print("[强制模式] 将忽略完成状态，重新检查所有章节")
    print("=" * 50)

    async with async_playwright() as p:
        profile_dir = _profile_dir()
        print(f"[启动] 正在启动浏览器，用户目录: {profile_dir}")
        context = await p.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled"],
        )

        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await _open_course_or_login(page)

            page, detected = await _wait_for_browser_start(context, page)
            _apply_detected_course_params(detected)

            # 第一步：获取章节目录
            chapters, enc = await get_chapters(page)
            if not chapters:
                print("[错误] 未获取到章节列表，请检查：")
                print("  1. 账号已登录成功")
                print("  2. 点击开始时浏览器位于具体课程页面或章节页面")
                return

            # 打印课程完成状况
            _print_summary(chapters)

            pending = filter_unfinished(chapters, force=force)
            if not pending:
                print("[完成] 没有需要检查的视频章节！")
                return

            total = len(pending)
            success = 0
            skipped = 0
            fail = 0

            for i, chapter in enumerate(pending):
                print(f"\n{'#'*50}")
                print(f"# 进度: {i+1}/{total}  (播放完成: {success}, 无视频跳过: {skipped}, 失败: {fail})")
                print(f"{'#'*50}")

                result = await play_chapter_videos(page, chapter, enc)

                if result == VIDEO_COMPLETED:
                    success += 1
                elif result == VIDEO_SKIPPED:
                    skipped += 1
                elif result == VIDEO_FAILED:
                    fail += 1

                if i < total - 1:
                    print(f"\n[休息] {config.CHAPTER_INTERVAL} 秒后继续下一章...")
                    await asyncio.sleep(config.CHAPTER_INTERVAL)

            print(f"\n{'='*50}")
            print(f"处理完毕: 播放完成 {success}, 无视频跳过 {skipped}, 失败 {fail}, 共检查 {total}")
            print(f"{'='*50}")

        finally:
            await context.close()

    print("\n提示: 请手动刷新课程页面确认章节完成状态")


def _profile_dir() -> Path:
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in config.PROFILE_NAME).strip("._-")
    if not safe_name:
        safe_name = "default"
    path = RUNTIME_DIR / "browser-data" / safe_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _apply_cli_options() -> None:
    """处理简单命令行参数。"""
    profile = _arg_value("--profile")
    if profile:
        config.PROFILE_NAME = profile


def _arg_value(name: str) -> str:
    for index, arg in enumerate(sys.argv):
        if arg == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        prefix = f"{name}="
        if arg.startswith(prefix):
            return arg[len(prefix):]
    return ""


async def _open_course_or_login(page) -> None:
    """打开目标课程；未登录时让用户直接在浏览器里登录。"""
    course_url="https://i.chaoxing.com/base?"
    print("[浏览器] 正在打开课程页；如跳转登录，请直接在浏览器中完成登录")
    await page.goto(course_url, wait_until="domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT)


async def _wait_for_browser_start(context, first_page):
    """在浏览器页面注入开始按钮，避免命令行确认。"""
    start_event = asyncio.Event()
    clicked_page = {"page": first_page}

    def on_start(source):
        clicked_page["page"] = source["page"]
        start_event.set()

    try:
        await context.expose_binding("__chaoxingStartAutoWatch", on_start)
    except Exception:
        pass

    print("[浏览器] 你可以在打开的浏览器里登录、切换课程或选择章节。")
    print("[浏览器] 请在目标课程页面点击右上角“开始自动观看”。")
    print("[浏览器] 如果登录后打开了新标签页，按钮也会自动注入到新标签页。")

    while not start_event.is_set():
        for page in context.pages:
            await _inject_start_button(page)
        try:
            await asyncio.wait_for(start_event.wait(), timeout=2)
        except asyncio.TimeoutError:
            pass

    page = clicked_page["page"]
    detected_page, params = await _wait_for_course_params(context, page)
    print(f"[浏览器] 检测到课程页: courseid={params.get('courseid')}, clazzid={params.get('clazzid')}")
    return detected_page, params


async def _wait_for_course_params(context, preferred_page):
    """点击开始后，从当前页、所有标签页和 iframe 中寻找课程参数。"""
    print("[浏览器] 正在从当前页面/标签页/iframe 中识别课程参数...")

    for _ in range(120):
        page, params = await _find_course_page_and_params(context, preferred_page)
        if params:
            return page, params

        for page in context.pages:
            await _inject_start_button(page)
        await asyncio.sleep(1)

    print("[错误] 未识别到课程参数。请确认当前页已经进入具体课程，而不是课程列表或登录页。")
    sys.exit(1)


async def _find_course_page_and_params(context, preferred_page):
    pages = []
    if preferred_page in context.pages:
        pages.append(preferred_page)
    pages.extend(page for page in context.pages if page not in pages)

    for page in pages:
        params = _course_params_from_url(page.url)
        if _has_required_course_params(params):
            return page, params

        params = await _course_params_from_dom(page)
        if _has_required_course_params(params):
            return page, params

        for frame in page.frames:
            params = _course_params_from_url(frame.url)
            if _has_required_course_params(params):
                return page, params
            params = await _course_params_from_dom(frame)
            if _has_required_course_params(params):
                return page, params

    return preferred_page, {}


async def _inject_start_button(page) -> None:
    try:
        await page.evaluate("""() => {
            if (document.getElementById('chaoxing-auto-start')) {
                return;
            }
            const button = document.createElement('button');
            button.id = 'chaoxing-auto-start';
            button.textContent = '开始自动观看';
            button.style.cssText = [
                'position:fixed',
                'top:16px',
                'right:16px',
                'z-index:2147483647',
                'padding:10px 14px',
                'border:0',
                'border-radius:6px',
                'background:#1677ff',
                'color:#fff',
                'font-size:14px',
                'font-weight:600',
                'cursor:pointer',
                'box-shadow:0 4px 14px rgba(0,0,0,.18)'
            ].join(';');
            button.onclick = () => window.__chaoxingStartAutoWatch();
            document.body.appendChild(button);
        }""")
    except Exception:
        pass


def _course_params_from_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.netloc and "chaoxing.com" not in parsed.netloc:
        return {}

    query = parse_qs(parsed.query)
    course_id = _first(query, "courseid") or _first(query, "courseId")
    clazz_id = (
        _first(query, "clazzid")
        or _first(query, "clazzId")
        or _first(query, "classid")
        or _first(query, "classId")
    )
    cpi = _first(query, "cpi")
    if not course_id:
        return {}

    return {"courseid": course_id, "clazzid": clazz_id, "cpi": cpi}


async def _course_params_from_dom(page_or_frame) -> dict[str, str]:
    """从页面中的链接、iframe src、onclick、data-url 中提取课程参数。"""
    try:
        candidates = await page_or_frame.evaluate("""() => {
            const values = [];
            const nodes = document.querySelectorAll('a[href], iframe[src], [onclick], [data-url]');
            for (const node of nodes) {
                for (const attr of ['href', 'src', 'onclick', 'data-url']) {
                    const value = node.getAttribute(attr);
                    if (value && /courseid|courseId/i.test(value)) {
                        values.push(value);
                    }
                }
            }
            return values.slice(0, 200);
        }""")
    except Exception:
        return {}

    for value in candidates:
        value = value.replace("&amp;", "&")
        params = _course_params_from_url(value)
        if _has_required_course_params(params):
            return params
    return {}


def _apply_detected_course_params(params: dict[str, str]) -> None:
    """把用户当前打开的课程参数应用到本次运行。"""
    required = {
        "courseid": "courseid",
        "clazzid": "clazzid/classid",
        "cpi": "cpi",
    }
    missing = [label for key, label in required.items() if not params.get(key)]
    if missing:
        print("[错误] 当前页面缺少课程参数: " + ", ".join(missing))
        print("[提示] 请进入具体课程的章节/课程主页，再点击“开始自动观看”。")
        sys.exit(1)

    config.COURSE_ID = params["courseid"]
    config.CLAZZ_ID = params["clazzid"]
    config.CPI = params["cpi"]


def _has_required_course_params(params: dict[str, str]) -> bool:
    invalid = {"", "undefined", "null", "none"}
    return all(str(params.get(key, "")).strip().lower() not in invalid for key in ("courseid", "clazzid", "cpi"))


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return values[0] if values else ""


def _print_summary(chapters: list[dict]) -> None:
    """打印课程章节完成状况。"""
    total = len(chapters)
    done = sum(1 for c in chapters if c["isCompleted"])
    pending = total - done

    # 统计任务点
    total_tasks = sum(c["totalTasks"] for c in chapters)
    done_tasks = sum(c["completedTasks"] for c in chapters)

    print(f"\n{'='*50}")
    print(f"课程完成状况")
    print(f"{'='*50}")
    print(f"  总章节数:     {total}")
    print(f"  已完成:       {done}")
    print(f"  待处理:       {pending}")
    print(f"  任务点进度:   {done_tasks}/{total_tasks}")
    print(f"{'='*50}")

    if pending == 0:
        print("所有章节已完成！")
        return

    print(f"\n未完成章节列表:")
    for c in chapters:
        if not c["isCompleted"]:
            tasks_info = f"({c['completedTasks']}/{c['totalTasks']} 任务点)" if c["totalTasks"] > 0 else ""
            print(f"  [{c['knowledgeId']}] {c['title'][:50]} {tasks_info}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
