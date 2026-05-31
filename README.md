# 超星学习通 未完成章节视频顺序播放工具

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
playwright install chromium
```

## 配置

修改 `config.json` 中的默认课程参数。参数从课程页面的 URL 和 Cookie 中获取。

程序启动后也可以直接在浏览器里切换课程；程序会从当前课程 URL 自动读取 `courseid`、`clazzid`、`cpi` 并应用到本次运行。

### 快速获取参数

1. 用浏览器打开课程页面（课程首页）
2. 查看地址栏 URL，提取参数：
   - `COURSE_ID` — URL 中的 `courseid=xxx`
   - `CLAZZ_ID` — URL 中的 `clazzid=xxx`
   - `CPI` — URL 中的 `cpi=xxx`
3. 打开浏览器开发者工具（F12）→ Application → Cookies → `mooc2-ans.chaoxing.com`
   - `ENC` — Cookie 中名为 `{courseId}enc` 的值（如 `261791158enc`）

示例：
```
课程 URL:
https://mooc2-ans.chaoxing.com/mooc2-ans/mycourse/stu?courseid=261791158&clazzid=142798268&cpi=412884755
                                  课程 ID ^^^^^^^^        班级 ID ^^^^^^^^      cpi ^^^^^^^^

Cookie: 261791158enc = fce9e004fc2fb027cb8452d3ce629bf2
           ENC ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

### 配置内容

在 `config.json` 中修改对应的值：

```json
{
  "COURSE_ID": "你的课程ID",
  "CLAZZ_ID": "你的班级ID",
  "CPI": "你的cpi",
  "ENC": "你的enc",
  "PROFILE_NAME": "default"
}
```

`PROFILE_NAME` 对应一个浏览器用户目录。不同账号可以使用不同目录名，例如 `account_a`、`account_b`。如果只用一个账号，保持 `default` 即可。

## 使用

```bash
python main.py
```

### 首次运行

1. 程序会自动打开 Chromium 浏览器并导航到学习通登录页
2. 手动完成登录（扫码或账号密码）
3. Cookie 会自动保存在浏览器用户目录中，下次启动会自动复用
4. 你可以在浏览器里切课程或选择章节；如果登录后打开了新标签页，按钮也会自动注入到新标签页
5. 点击页面右上角的“开始自动观看”，程序会从当前页、所有标签页和 iframe 里识别课程参数，然后打开章节，检测未完成章节后静音、以 2 倍速依次播放视频

### 后续运行

直接运行 `python main.py`，程序会复用 `browser-data/<PROFILE_NAME>` 中的登录态。程序会按课程页面当前完成状态继续检查未完成章节。

### 更换账号/课程

更换账号：修改 `config.json` 里的 `PROFILE_NAME`，例如从 `default` 改成 `account_b`，重新运行后在弹出的浏览器里登录新账号。

更换课程：可以修改 `config.json` 中的课程参数，也可以启动后直接在浏览器里切换到目标课程，再点击“开始自动观看”。

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
  config.json
  ms-playwright\
  README.md
```

把整个 `dist\chaoxing-auto` 文件夹复制到其他 Windows 机器即可运行。不要只复制 exe，否则找不到内置 Chromium。

## 文件说明

| 文件 | 作用 |
|------|------|
| `main.py` | 入口，登录流程，调度章节处理 |
| `config.py` | 读取配置并提供运行常量 |
| `config.json` | 可编辑课程参数配置 |
| `chapter_parser.py` | 解析章节目录，提取章节信息和完成状态 |
| `video_automator.py` | 核心：进入章节并依次处理视频任务点 |
| `requirements.txt` | Python 依赖 |
| `build_portable.ps1` | 生成便携可执行目录 |
| `browser-data/` | 浏览器登录态和 Cookie（运行后自动生成） |

## 常见问题

**Q: 程序显示完成但课程页面未更新？**
A: 刷新课程页面即可看到最新状态。超星页面不会自动刷新完成状态。

**Q: 提示"未获取到章节列表"？**
A: 检查 `config.json` 中的参数是否正确，尤其是 `ENC`（不是登录 Password，而是 Cookie 中的 enc 值）。

**Q: 登录超时？**
A: 程序等待 5 分钟。请确保在浏览器窗口中完成登录操作（扫码或输入账号密码）。

**Q: 视频播放到一半卡住了？**
A: 网络波动可能导致视频加载慢。程序会等待足够时间，通常不会卡住。如果长时间无反应，可 Ctrl+C 重启程序，程序会重新读取课程页面当前完成状态后继续检查。

**Q: 支持多个课程吗？**
A: 目前需要为每个课程分别修改 `config.json` 并运行。也可以复制多份便携目录，分别配置不同课程。
