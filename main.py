"""
OpenCV + uiautomator2 图像识别自动化测试

主入口脚本：提供命令行交互和示例流程。
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

import time
import argparse

from core.logger import get_logger, setup_logger
from core.device import get_device, wake_screen, get_device_resolution
from core.image_matcher import (
    find_and_click,
    wait_for_image,
    click_if_exists,
    save_screenshot,
)
from core.watchers import setup_watchers
from core.helpers import wait_for_text

logger = get_logger(__name__)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="OpenCV + uiautomator2 图像识别自动化测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
    python main.py                         # 运行示例流程
    python main.py --screenshot-only       # 仅截图
    python main.py --flow my_flow          # 运行自定义流程
        """,
    )
    parser.add_argument("--screenshot-only", action="store_true",
                        help="仅截图，不执行自动化流程")
    parser.add_argument("--flow", type=str, default=None,
                        help="运行指定名称的自动化流程")
    parser.add_argument("--device-info", action="store_true",
                        help="显示设备信息")
    return parser.parse_args()


def show_device_info(d):
    """显示设备详细信息"""
    width, height = d.window_size()
    info = d.info
    print("=" * 40)
    print("设备信息")
    print("=" * 40)
    print(f"  产品名称:    {info.get('productName', 'N/A')}")
    print(f"  品牌:        {info.get('brand', 'N/A')}")
    print(f"  型号:        {info.get('productModel', 'N/A')}")
    print(f"  分辨率:      {width}x{height}")
    print(f"  API 级别:    {info.get('apiLevel', 'N/A')}")
    print(f"  Android 版本: {info.get('androidVersion', 'N/A')}")
    print(f"  序列号:      {d.serial}")
    print(f"  屏幕亮:      {info.get('screenOn', 'N/A')}")
    print(f"  当前包名:    {d.app_current().get('package', 'N/A')}")
    print("=" * 40)


def example_flow():
    """
    示例自动化流程。

    演示如何使用图像匹配 + 原生定位完成一个典型的 H5/小程序自动化场景。
    实际使用时请替换模板路径为您的真实模板文件。
    """
    logger.info("=" * 50)
    logger.info("开始示例自动化流程")
    logger.info("=" * 50)

    # 1. 连接设备
    d = get_device()

    # 2. 唤醒屏幕
    wake_screen(d)

    # 3. 启动弹窗监控
    setup_watchers(d)

    # 4. 按 Home 键回到桌面，确保起始状态干净
    # d.press("home")
    time.sleep(1)

    # ── 以下为示例步骤，请根据实际应用修改 ──
    # （将下面的模板路径替换为您自己的模板文件）

    # 示例步骤 1: 点击 "打开应用" 按钮 (图像匹配)
    logger.info("步骤 1: 查找并点击目标按钮...")
    if not find_and_click(d, "templates/goto_get_coupon.png", timeout=15):
        logger.warning("步骤 1 跳过：未找到目标按钮（首次运行属于正常现象，请先截取模板）")
        logger.info("提示：请先运行 python scripts/get_template.py 生成模板图片")
        return False

    # 示例步骤 2: 等待页面加载（等待特定文本出现）
    logger.info("步骤 2: 等待页面加载...")
    if not wait_for_text(d, "首页", timeout=20):
        logger.warning("步骤 2 跳过：页面可能未正常加载")
        return False

    # 示例步骤 3: 点击 "我的" 标签 (图像匹配)
    logger.info("步骤 3: 点击导航标签...")
    if not find_and_click(d, "templates/my_tab.png", timeout=10):
        logger.warning("步骤 3 跳过：未找到导航标签")

    # 示例步骤 4: 处理可能的弹窗 (有则关闭，无则继续)
    logger.info("步骤 4: 检查弹窗...")
    click_if_exists(d, "templates/close_popup.png", timeout=2)

    # 示例步骤 5: 截图保存
    save_screenshot(d, "example_flow_result")

    logger.info("示例流程执行完毕")
    return True


def main():
    """主入口"""
    setup_logger()

    args = parse_args()

    try:
        d = get_device()

        if args.screenshot_only:
            save_screenshot(d)
            return

        if args.device_info:
            show_device_info(d)
            return

        if args.flow:
            flow_name = args.flow
            logger.info(f"运行自定义流程: {flow_name}")
            # TODO: 根据 flow_name 动态加载对应的流程模块
            logger.info(f"自定义流程 '{flow_name}' 暂未实现，请扩展此功能")
            return

        # 默认：运行示例流程
        example_flow()

    except RuntimeError as e:
        logger.error(f"运行失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("用户中断运行")
        sys.exit(0)
    except Exception as e:
        logger.error(f"未预期的异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
