# 超星学习通 自动刷课工具

按课程目录顺序遍历超星学习通（超星尔雅）课程中所有未完成章节，进入每个章节后静音并以 2 倍速依次播放其中的视频任务点。没有视频的未完成章节会被跳过，不再处理文档任务。

## 功能

- 按课程页面当前状态筛选所有未完成章节
- 进入未完成章节后静音并以 2 倍速依次播放其中的全部视频任务点
- 监听正常播放上报接口，收到 `isPassed: true` 后立即进入下一个视频
- 无视频章节自动跳过，不再通过文档访问触发完成
- 浏览器持久登录态：直接在弹出的 Chromium 页面登录，Cookie 自动保存在 `browser-data/`
- 浏览器页面会直接出现“开始自动观看”按钮；你可以先登录、切课程或选择章节，再点击开始
- 可视化进度：实时显示播放位置、完成百分比和停滞状态
- 便携打包：使用 Playwright 自带 Chromium，不依赖 ChromeDriver，也不要求匹配本机 Chrome 版本

## 环境要求

- Python 3.9+
- Playwright Chromium（源码运行时安装；便携包内置）

## 安装

```bash
# 1. 克隆或下载项目
cd chaoxing-auto

# 2. 创建虚拟环境（可选）
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 安装 Playwright Chromium
python -m playwright install chromium
```

## 配置

默认不需要创建 `config.json`。

程序不会保存课程 ID、班级 ID、cpi 或 enc。每次运行时，请先在弹出的浏览器中进入本次要观看的具体课程页面，再点击右上角的“开始自动观看”。程序会从当前课程页面、标签页和 iframe 中临时识别课程参数，只应用于本次运行。

浏览器登录态会保存在 `browser-data/`，下次运行会自动复用。该目录包含用户 Cookie，不要上传到 GitHub，也不要发给别人。

如果同一台电脑需要保存多个账号的登录态，可以使用 `--profile`：

```bash
python main.py --profile account_a
python main.py --profile account_b
```

便携版同理：

```powershell
.\chaoxing-auto.exe --profile account_a
```

## 使用

### Python 版

```bash
python main.py
```

### 首次运行

1. 程序会自动打开 Chromium 浏览器并导航到学习通页面
2. 手动完成登录（扫码或账号密码）
3. Cookie 会自动保存在浏览器用户目录中，下次启动会自动复用
4. 在浏览器里进入本次要观看的具体课程页面或章节页面；如果课程打开了新标签页，按钮也会自动注入到新标签页
5. 点击页面右上角的“开始自动观看”，程序会从当前页、所有标签页和 iframe 里识别课程参数，然后打开章节，检测未完成章节后静音、以 2 倍速依次播放视频

### 后续运行

直接运行 `python main.py`，程序会复用 `browser-data/<profile>` 中的登录态。进入本次目标课程后点击“开始自动观看”，程序会按该课程页面当前完成状态继续检查未完成章节。

### 更换账号/课程

更换账号：使用不同的 `--profile`，例如 `python main.py --profile account_b`，重新运行后在弹出的浏览器里登录新账号。

更换课程：不需要改配置。启动后直接在浏览器里切换到目标课程，再点击“开始自动观看”。

如果没有看到“开始自动观看”按钮：

- 等页面加载完成后再看右上角。
- 如果课程在新标签页打开，切到新标签页，按钮会自动注入。
- 如果仍然没有，刷新当前页面，程序会继续尝试注入按钮。

## 便携打包

项目不使用 Selenium/ChromeDriver。打包后的程序会携带 Playwright Chromium，因此不会遇到 ChromeDriver 与本机 Chrome 版本不匹配的问题。

在 Windows PowerShell 中运行：

```powershell
.\build_portable.ps1
```

首次构建会安装 Python 依赖并下载 Playwright Chromium，确实会比较久。后续再次构建时脚本会自动跳过已存在的依赖和 Chromium，速度会快很多。确认依赖和浏览器都已经存在时，也可以用：

```powershell
$env:SKIP_INSTALL = "1"
.\build_portable.ps1
```

脚本会生成：

```text
dist\chaoxing-auto\
  chaoxing-auto.exe
  ms-playwright\
  README.md
```

把整个 `dist\chaoxing-auto` 文件夹复制到其他 Windows 机器即可运行。不要只复制 exe，否则找不到内置 Chromium。

## 文件说明

| 文件 | 作用 |
|------|------|
| `main.py` | 入口，登录流程，调度章节处理 |
| `config.py` | 通用运行配置和本次运行的临时课程参数 |
| `chapter_parser.py` | 解析章节目录，提取章节信息和完成状态 |
| `video_automator.py` | 核心：进入章节并依次处理视频任务点 |
| `requirements.txt` | Python 依赖 |
| `build_portable.ps1` | 生成便携可执行目录 |
| `browser-data/` | 浏览器登录态和 Cookie（运行后自动生成） |

## 常见问题

**Q: 程序显示完成但课程页面未更新？**
A: 刷新课程页面即可看到最新状态。超星页面不会自动刷新完成状态。

**Q: 提示"未获取到章节列表"？**
A: 确认已经登录，并且点击“开始自动观看”时浏览器停留在具体课程页面或章节页面，而不是课程列表、首页或登录页。

**Q: 登录超时？**
A: 程序等待 5 分钟。请确保在浏览器窗口中完成登录操作（扫码或输入账号密码）。

**Q: 视频播放到一半卡住了？**
A: 网络波动可能导致视频加载慢。程序会等待足够时间，通常不会卡住。如果长时间无反应，可 Ctrl+C 重启程序，程序会重新读取课程页面当前完成状态后继续检查。

**Q: 支持多个课程吗？**
A: 支持。课程参数不会保存，每次进入想看的课程后点击“开始自动观看”即可。
