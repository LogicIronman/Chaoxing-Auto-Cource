"""解析课程章节目录，提取知识点 ID 和完成状态"""

import asyncio
from playwright.async_api import Page
import config


async def _extract_enc_from_page(page: Page) -> str:
    """从页面 JavaScript 上下文中尝试提取 enc 参数。"""
    try:
        enc = await page.evaluate("() => window._openc || window.openc || ''")
        if enc:
            return enc
    except Exception:
        pass
    # 回退到 config 中的 ENC（来自 Cookie 中 {courseId}enc 的值）
    return config.ENC


async def get_chapters(page: Page) -> tuple[list[dict], str]:
    """从 studentcourse 页面提取所有章节信息和 enc 参数。

    先导航到课程主页并主动打开章节区域；如果当前页解析不到，再加载章节目录页。
    返回 (章节列表, enc)。
    """
    main_url = (
        f"{config.MOOC2_DOMAIN}/mooc2-ans/mycourse/stu"
        f"?courseid={config.COURSE_ID}"
        f"&clazzid={config.CLAZZ_ID}"
        f"&cpi={config.CPI}"
        f"&pageHeader=1"
    )
    print(f"[章节解析] 正在进入课程主页...")
    await page.goto(main_url, wait_until="domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT)
    await asyncio.sleep(2)  # 等待 JS 初始化，设置 window._openc 等变量

    enc = await _extract_enc_from_page(page)
    print(f"[章节解析] enc = {enc[:20]}...")

    print("[章节解析] 正在自动打开章节...")
    chapters = await _open_chapters_from_course_page(page)
    if chapters:
        return chapters, enc

    print("[章节解析] 当前课程页未解析到章节，改用章节目录页...")
    chapter_url = (
        f"{config.MOOC2_DOMAIN}/mooc2-ans/mycourse/studentcourse"
        f"?courseid={config.COURSE_ID}"
        f"&clazzid={config.CLAZZ_ID}"
        f"&cpi={config.CPI}"
        f"&ut=s"
        f"&enc={enc}"
    )
    print(f"[章节解析] 正在加载章节目录...")
    await page.goto(chapter_url, wait_until="domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT)

    # 等待章节容器出现
    try:
        await page.wait_for_selector(".chapter_item", timeout=10000)
    except Exception:
        print("[章节解析] 未找到 .chapter_item，尝试直接从主页 iframe 获取...")
        chapters, fallback_enc = await _get_chapters_from_main_page(page)
        return chapters, fallback_enc or enc

    chapters = await _parse_chapter_items(page)
    return chapters, enc


async def _open_chapters_from_course_page(page: Page) -> list[dict]:
    """在课程主页主动打开章节区域，并从页面或 iframe 中解析章节。"""
    try:
        await page.evaluate("""() => {
            const candidates = [
                ...document.querySelectorAll('.nav-item, .tab, [data-url], a, li, span, div')
            ];
            for (const item of candidates) {
                const text = (item.textContent || '').trim();
                if (text === '章节' || text.includes('章节')) {
                    item.click();
                    break;
                }
            }
            if (typeof window.loadModule === 'function') {
                window.loadModule('zj');
            }
        }""")
    except Exception:
        pass

    await asyncio.sleep(3)
    return await _parse_chapters_from_page_and_frames(page)


async def _parse_chapters_from_page_and_frames(page: Page) -> list[dict]:
    """从当前页面和所有 iframe 中寻找章节列表。"""
    contexts = [page, *page.frames]
    for context in contexts:
        try:
            count = await context.evaluate(
                "() => document.querySelectorAll('.chapter_item').length"
            )
        except Exception:
            continue

        if count > 0:
            print("[章节解析] 已在课程界面找到章节列表")
            return await _parse_chapter_items(context)

    return []


async def _get_chapters_from_main_page(page: Page) -> tuple[list[dict], str]:
    """备用方案：从课程主页的章节 iframe 中获取数据。
    返回 (章节列表, enc)。"""
    # 回到主页
    main_url = (
        f"{config.MOOC2_DOMAIN}/mooc2-ans/mycourse/stu"
        f"?courseid={config.COURSE_ID}"
        f"&clazzid={config.CLAZZ_ID}"
        f"&cpi={config.CPI}"
        f"&pageHeader=1"
    )
    await page.goto(main_url, wait_until="domcontentloaded", timeout=config.PAGE_LOAD_TIMEOUT)
    await asyncio.sleep(3)

    enc = await _extract_enc_from_page(page)

    chapters = await _open_chapters_from_course_page(page)
    if chapters:
        return chapters, enc

    # 最后兜底：打印页面信息供调试
    text = await page.evaluate("() => document.body.innerText.substring(0, 500)")
    print(f"[章节解析] 主页面片段: {text}")
    return [], enc


async def _parse_chapter_items(page_or_frame) -> list[dict]:
    """从已加载的页面/iframe 中解析 .chapter_item 元素。

    完成状态仅由 span.catalog_state.icon_yiwanc 判定：
    - 有 icon_yiwanc → 已完成（跳过）
    - 无 icon_yiwanc 但有 knowledgeJobCount → 待处理
    - section 标题行（无 knowledgeId）→ 跳过
    """
    chapters = await page_or_frame.evaluate("""() => {
        const items = document.querySelectorAll('.chapter_item');
        const result = [];
        for (const item of items) {
            const idMatch = item.id.match(/^cur(\\d+)$/);
            const knowledgeId = idMatch ? idMatch[1] : null;
            if (!knowledgeId) continue;  // 跳过 section 标题行

            const onclick = item.getAttribute('onclick') || '';
            const toOldMatch = onclick.match(/toOld\\('(\\d+)',\\s*'(\\d+)',\\s*'(\\d+)'/);
            const title = item.getAttribute('title') || '';

            // 完成状态：看是否有 icon_yiwanc 类
            const stateEl = item.querySelector('.catalog_state');
            const isCompleted = stateEl && stateEl.classList.contains('icon_yiwanc');

            // 任务点数：从 knowledgeJobCount 取，没有则默认 1
            const jobCountEl = item.querySelector('.knowledgeJobCount');
            const totalTasks = jobCountEl
                ? (parseInt(jobCountEl.value) || 1)
                : (isCompleted ? 1 : 0);

            // 已完成数：icon_yiwanc 说明全部完成，否则设为 0
            const completedTasks = isCompleted ? totalTasks : 0;

            result.push({
                knowledgeId: knowledgeId,
                title: title,
                courseId: toOldMatch ? toOldMatch[1] : null,
                clazzId: toOldMatch ? toOldMatch[2] : null,
                totalTasks: totalTasks,
                completedTasks: completedTasks,
                isCompleted: isCompleted
            });
        }
        return result;
    }""")

    print(f"[章节解析] 共找到 {len(chapters)} 个章节")
    for ch in chapters:
        status = "[DONE]" if ch["isCompleted"] else "[..]"
        tasks_info = f"({ch['completedTasks']}/{ch['totalTasks']})" if ch["totalTasks"] > 0 else "(无任务点)"
        print(f"  [{status}] {ch['knowledgeId']} - {ch['title'][:50]}  {tasks_info}")

    return chapters


def filter_unfinished(chapters: list[dict], force: bool = False) -> list[dict]:
    """过滤出需要检查视频的章节。

    force=False: 按课程页面状态，仅检查未完成章节。
    force=True:  检查所有章节（忽略课程完成状态）。
    """
    pending = []
    for ch in chapters:
        if not force:
            if ch["isCompleted"]:
                continue
        pending.append(ch)

    already_completed = sum(1 for c in chapters if c["isCompleted"])
    has_no_tasks = sum(1 for c in chapters if c["totalTasks"] == 0)
    label = "[强制模式]" if force else ""
    print(f"[章节解析] {label}待检查视频: {len(pending)} 个章节"
          f"（课程已完成: {already_completed}, 无任务点: {has_no_tasks}）")
    return pending
