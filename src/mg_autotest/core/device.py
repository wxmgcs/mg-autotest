"""
设备连接与管理模块

提供统一设备连接接口，支持 USB、ADB 和 WiFi 三种连接方式。
自动检测设备分辨率，用于加载匹配的模板目录。
"""

import uiautomator2 as u2
import subprocess
import re

from mg_autotest.core.logger import get_logger
from mg_autotest.config import (
    DEVICE_CONNECT_METHOD,
    DEVICE_ADDRESS,
    DEVICE_SERIAL,
)

logger = get_logger(__name__)


def get_device() -> u2.Device:
    """
    根据全局配置连接 Android 设备。

    Returns:
        uiautomator2 Device 对象

    Raises:
        RuntimeError: 设备连接失败
    """
    try:
        if DEVICE_CONNECT_METHOD == "usb":
            if DEVICE_SERIAL:
                logger.info(f"通过 USB 连接设备: {DEVICE_SERIAL}")
                d = u2.connect_usb(DEVICE_SERIAL)
            else:
                logger.info("通过 USB 连接设备 (自动)")
                d = u2.connect_usb()
        elif DEVICE_CONNECT_METHOD == "adb":
            logger.info("通过 ADB 连接设备")
            d = u2.connect_adb_wifi()
        elif DEVICE_CONNECT_METHOD == "wifi":
            address = DEVICE_ADDRESS or "192.168.1.100:5555"
            logger.info(f"通过 WiFi 连接设备: {address}")
            d = u2.connect(address)
        else:
            logger.warning(f"未知连接方式 '{DEVICE_CONNECT_METHOD}'，使用默认 usb 连接")
            d = u2.connect_usb()

        # 验证连接
        info = d.info
        logger.info(f"设备已连接: {info.get('productName', 'unknown')}  "
                     f"SDK: {info.get('apiLevel', '?')}  "
                     f"分辨率: {d.window_size()}")
        return d

    except Exception as e:
        logger.error(f"设备连接失败: {e}")
        raise RuntimeError(f"设备连接失败: {e}")


def get_device_resolution(d: u2.Device) -> str:
    """
    获取设备分辨率字符串，用于匹配模板目录。

    Args:
        d: uiautomator2 Device 对象

    Returns:
        分辨率字符串，如 "1080x1920"
    """
    width, height = d.window_size()
    return f"{width}x{height}"


def get_device_serial(d: u2.Device) -> str:
    """
    获取设备序列号。

    Args:
        d: uiautomator2 Device 对象

    Returns:
        设备序列号字符串
    """
    try:
        return d.serial
    except Exception:
        return "unknown_serial"


def is_screen_on(d: u2.Device) -> bool:
    """
    检查设备屏幕是否亮起。

    Args:
        d: uiautomator2 Device 对象

    Returns:
        True 为亮屏，False 为灭屏
    """
    return d.info.get("screenOn", False)


def wake_screen(d: u2.Device) -> None:
    """
    唤醒设备屏幕（若已灭屏则亮屏并解锁）。

    Args:
        d: uiautomator2 Device 对象
    """
    if not is_screen_on(d):
        logger.info("屏幕已灭，正在唤醒...")
        d.screen_on()
        d.unlock()
        import time
        time.sleep(1)
        logger.info("屏幕已唤醒")
    else:
        logger.debug("屏幕已是亮屏状态")


def press_home(d: u2.Device) -> None:
    """按下 Home 键"""
    d.press("home")
    logger.debug("按下 Home 键")


def press_back(d: u2.Device) -> None:
    """按下返回键"""
    d.press("back")
    logger.debug("按下返回键")
