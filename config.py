"""
全局配置文件
"""

# ─── 设备连接配置 ──────────────────────────────────────────
DEVICE_CONNECT_METHOD = "usb"       # "usb" | "adb" | "wifi"
DEVICE_ADDRESS = None               # None=自动, 或 "192.168.1.x:5555"
# 多设备时指定序列号，如 "ABCDEF123456"
DEVICE_SERIAL = "FPP0222225010815"

# ─── 图像匹配全局默认参数 ─────────────────────────────────
DEFAULT_THRESHOLD = 0.8             # 模板匹配置信度阈值 (0~1)
DEFAULT_TIMEOUT = 10                # 单次查找超时 (秒)
RETRY_INTERVAL = 0.5                # 匹配失败重试间隔 (秒)
WAIT_ELEMENT_INTERVAL = 1.0         # 等待元素轮询间隔 (秒)

# ─── 日志配置 ──────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_FILE = None                     # None=只输出控制台, 或路径如 "logs/autotest.log"

# ─── 模板路径 ──────────────────────────────────────────────
TEMPLATE_DIR = "templates"
# 多分辨率模板目录，设备初始化时自动选择
RESOLUTION_TEMPLATE_DIRS = {
    "1080x1920": "templates/1080x1920",
    "1440x2560": "templates/1440x2560",
}

# ─── 截图配置 ──────────────────────────────────────────────
SCREENSHOT_DIR = "screenshots"      # 截图保存目录
SAVE_SCREENSHOT_ON_FAILURE = True   # 操作失败时自动截图
STATUS_BAR_HEIGHT = 120             # 屏幕录制时裁剪顶部状态栏（像素）

# ─── 屏幕录制 GIF 优化 ─────────────────────────────────────
RECORD_INTERVAL = 0.5               # 截帧间隔（秒），越大帧数越少体积越小
RECORD_RESIZE_RATIO = 0.5           # 缩放比例（<1 缩小体积），如 0.5 = 缩小到 50%
RECORD_GIF_COLORS = 128             # GIF 调色板颜色数（≤256），越小体积越小
