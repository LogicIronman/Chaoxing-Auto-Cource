"""章节视频自动化：进入章节后依次播放其中的视频任务点。"""

import asyncio
import json

from playwright.async_api import Page
import config

VIDEO_COMPLETED = "completed"
VIDEO_SKIPPED = "skipped"
VIDEO_FAILED = "failed"
VIDEO_PLAYBACK_RATE = 2.0
VIDEO_POLL_INTERVAL = 2
VIDEO_STALL_LIMIT = 45


async def play_chapter_videos(page: Page, chapter: dict, enc: str = "") -> str:
    """播放单个章节中的所有视频。

    返回值：
    - VIDEO_COMPLETED: 找到视频并全部处理成功
    - VIDEO_SKIPPED: 章节中没有视频
    - VIDEO_FAILED: 进入章节或处理视频失败
    """
    knowledge_id = chapter["knowledgeId"]
    title = chapter.get("title", knowledge_id)

    print(f"\n{'='*50}")
    print(f"[章节] {title} (ID: {knowledge_id})")

    # ── 导航到章节目录，点击目标章节 ──
    chapter_list_url = (
        f"{config.MOOC2_DOMAIN}/mooc2-ans/mycourse/studentcourse"
        f"?courseid={config.COURSE_ID}"
        f"&clazzid={config.CLAZZ_ID}"
        f"&cpi={config.CPI}"
        f"&ut=s"
        f"&enc={enc}"
    )
    await page.goto(chapter_list_url, wait_until="domcontentloaded",
                    timeout=config.PAGE_LOAD_TIMEOUT)

    try:
        await page.wait_for_selector(".chapter_item", timeout=10000)
    except Exception:
        print(f"[章节] 章节目录加载失败")
        return VIDEO_FAILED

    chapter_sel = f"#cur{knowledge_id}"
    try:
        chapter_el = await page.wait_for_selector(chapter_sel, timeout=5000)
    except Exception:
        print(f"[章节] 未找到章节元素 {chapter_sel}")
        return VIDEO_FAILED

    try:
        async with page.expect_navigation(wait_until="domcontentloaded",
                                          timeout=config.PAGE_LOAD_TIMEOUT):
            await chapter_el.click()
        print(f"[章节] 已进入学习页")
        await asyncio.sleep(5)

        # ── 判断章节类型：查找所有 video iframe ──
        video_frames = [f for f in page.frames
                        if "/ananas/modules/video/index.html" in f.url]

        if video_frames:
            return VIDEO_COMPLETED if await _handle_videos(page, video_frames, title) else VIDEO_FAILED

        print(f"[视频] 本章节未找到视频，跳过: {title}")
        return VIDEO_SKIPPED

    except Exception as e:
        print(f"[章节] [ERR] 异常: {e}")
        import traceback
        traceback.print_exc()
        return VIDEO_FAILED


async def complete_video(page: Page, chapter: dict, enc: str = "") -> bool:
    """兼容旧调用：只处理章节视频，没有视频时视为跳过成功。"""
    return await play_chapter_videos(page, chapter, enc) != VIDEO_FAILED


async def _handle_videos(page: Page, video_frames: list, title: str) -> bool:
    """处理所有视频 iframe（支持多任务点章节）。

    每个视频有独立的 jobid/objectId，需逐个完成。
    """
    multi = len(video_frames) > 1
    for idx, vf in enumerate(video_frames):
        label = f"{title} [{idx+1}/{len(video_frames)}]" if multi else title
        if not await _complete_one_video(page, vf, label):
            return False
    return True


async def _complete_one_video(page: Page, video_frame, title: str) -> bool:
    """自然播放单个视频，并保持 2 倍速直到结束。"""
    passed_event = asyncio.Event()
    response_tasks = set()

    def on_response(response):
        if "/multimedia/log/a/" not in response.url:
            return
        task = asyncio.create_task(_mark_passed_from_response(response, passed_event))
        response_tasks.add(task)
        task.add_done_callback(response_tasks.discard)

    page.on("response", on_response)

    try:
        await video_frame.wait_for_selector("video", timeout=15000)
        meta = await _start_video_playback(video_frame)
        duration = meta.get("duration") or 0
        current_time = meta.get("currentTime") or 0
        duration_text = f"{duration:.0f}s" if duration > 0 else "未知"
        print(f"[视频] 开始播放: {title}")
        print(f"[视频] 倍速={VIDEO_PLAYBACK_RATE:g}x, duration={duration_text}, current={current_time:.0f}s")

        return await _wait_for_video_end(video_frame, title, passed_event)

    except Exception as e:
        print(f"[视频] [ERR] {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        page.remove_listener("response", on_response)
        for task in response_tasks:
            task.cancel()


async def _start_video_playback(video_frame) -> dict:
    """设置 2 倍速并触发播放。"""
    try:
        await video_frame.click("video", timeout=5000)
    except Exception:
        pass

    return await video_frame.evaluate(
        """async (rate) => {
            const video = document.querySelector('video');
            if (!video) {
                throw new Error('video element not found');
            }

            video.defaultPlaybackRate = rate;
            video.playbackRate = rate;
            video.muted = true;
            video.volume = 0;
            video.onratechange = () => {
                if (video.playbackRate !== rate) {
                    video.playbackRate = rate;
                }
            };

            if (Number.isFinite(video.duration) && video.currentTime >= video.duration - 0.5) {
                return {
                    duration: video.duration || 0,
                    currentTime: video.currentTime || 0,
                    ended: true,
                };
            }

            try {
                await video.play();
            } catch (err) {
                const playButton = document.querySelector(
                    '.vjs-play-control, .vjs-big-play-button, button[title*="播放"], button[aria-label*="Play"]'
                );
                if (playButton) {
                    playButton.click();
                    await video.play().catch(() => {});
                } else {
                    throw err;
                }
            }

            video.playbackRate = rate;
            video.muted = true;
            video.volume = 0;
            return {
                duration: Number.isFinite(video.duration) ? video.duration : 0,
                currentTime: video.currentTime || 0,
                ended: Boolean(video.ended),
            };
        }""",
        VIDEO_PLAYBACK_RATE,
    )


async def _wait_for_video_end(video_frame, title: str, passed_event: asyncio.Event) -> bool:
    """轮询视频状态，直到接口确认通过或自然播放结束。"""
    last_time = -1.0
    stalled_seconds = 0
    last_logged_progress = -1

    while True:
        try:
            await asyncio.wait_for(passed_event.wait(), timeout=VIDEO_POLL_INTERVAL)
            await _pause_video(video_frame)
            print(f"[接口] isPassed=true，跳到下一个视频: {title}")
            return True
        except asyncio.TimeoutError:
            pass

        state = await video_frame.evaluate(
            """(rate) => {
                const video = document.querySelector('video');
                if (!video) {
                    return { missing: true };
                }

                if (video.playbackRate !== rate) {
                    video.playbackRate = rate;
                }
                if (!video.muted) {
                    video.muted = true;
                    video.volume = 0;
                }
                if (video.paused && !video.ended) {
                    video.play().catch(() => {});
                }

                return {
                    missing: false,
                    ended: Boolean(video.ended),
                    paused: Boolean(video.paused),
                    currentTime: video.currentTime || 0,
                    duration: Number.isFinite(video.duration) ? video.duration : 0,
                    readyState: video.readyState,
                    playbackRate: video.playbackRate,
                };
            }""",
            VIDEO_PLAYBACK_RATE,
        )

        if state.get("missing"):
            print(f"[视频] [WARN] 视频元素丢失: {title}")
            return False

        current_time = float(state.get("currentTime") or 0)
        duration = float(state.get("duration") or 0)
        ended = bool(state.get("ended"))

        if ended or (duration > 0 and current_time >= duration - 0.5):
            print(f"[视频] [OK] 播放完成: {title}")
            return True

        if current_time > last_time + 0.2:
            stalled_seconds = 0
            last_time = current_time
        else:
            stalled_seconds += VIDEO_POLL_INTERVAL

        if duration > 0:
            progress = int(current_time / duration * 100)
            if progress >= last_logged_progress + 10:
                last_logged_progress = progress
                print(f"[视频] 播放中 {progress}%: {current_time:.0f}/{duration:.0f}s")
        else:
            print(f"[视频] 播放中: current={current_time:.0f}s, readyState={state.get('readyState')}")

        if stalled_seconds >= VIDEO_STALL_LIMIT:
            print(f"[视频] [WARN] 播放停滞超过 {VIDEO_STALL_LIMIT} 秒: {title}")
            return False


async def _mark_passed_from_response(response, passed_event: asyncio.Event) -> None:
    """监听正常播放上报接口，发现 isPassed=true 即通知播放循环。"""
    if passed_event.is_set():
        return

    try:
        body = await response.text()
    except Exception:
        return

    if not _response_has_passed(body):
        return

    passed_event.set()


def _response_has_passed(body: str) -> bool:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        normalized = body.replace(" ", "").replace("\n", "").lower()
        return '"ispassed":true' in normalized

    if not isinstance(data, dict):
        return False

    for key, value in data.items():
        if key.lower() == "ispassed":
            return value is True or str(value).lower() == "true"
    return False


async def _pause_video(video_frame) -> None:
    try:
        await video_frame.evaluate(
            """() => {
                const video = document.querySelector('video');
                if (video) {
                    video.pause();
                }
            }"""
        )
    except Exception:
        pass
