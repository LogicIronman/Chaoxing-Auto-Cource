"""超星学习通 - 运行配置。

课程参数不写入配置文件，运行时从用户当前打开的课程页面临时识别。
可选的 config.json 仅用于通用运行参数，例如浏览器用户目录名称和超时。
"""

import json
import sys
from pathlib import Path

DEFAULT_CONFIG = {
    "PROFILE_NAME": "default",
    "MOOC1_DOMAIN": "https://mooc1.chaoxing.com",
    "MOOC2_DOMAIN": "https://mooc2-ans.chaoxing.com",
    "PAGE_LOAD_TIMEOUT": 30000,
    "CHAPTER_INTERVAL": 2,
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _load_external_config() -> dict:
    config_path = app_dir() / "config.json"
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


_CONFIG = {**DEFAULT_CONFIG, **_load_external_config()}

# ═══════════════════════════════════════════════════════
# 课程参数（运行时从当前课程页识别，不持久化保存）
# ═══════════════════════════════════════════════════════
COURSE_ID = ""     # 课程 ID
CLAZZ_ID = ""      # 班级 ID
CPI = ""           # 课程参数 cpi
ENC = ""           # 课程级 enc
PROFILE_NAME = str(_CONFIG["PROFILE_NAME"])  # 浏览器用户目录名称

# ═══════════════════════════════════════════════════════
# 域名（除非超星改域名，否则不需修改）
# ═══════════════════════════════════════════════════════
MOOC1_DOMAIN = str(_CONFIG["MOOC1_DOMAIN"])
MOOC2_DOMAIN = str(_CONFIG["MOOC2_DOMAIN"])

# ═══════════════════════════════════════════════════════
# 超时与间隔（一般不需修改）
# ═══════════════════════════════════════════════════════
PAGE_LOAD_TIMEOUT = int(_CONFIG["PAGE_LOAD_TIMEOUT"])  # 页面加载超时（毫秒）
CHAPTER_INTERVAL = int(_CONFIG["CHAPTER_INTERVAL"])    # 章节间休息间隔（秒）
