"""
常用辅助功能模块

提供元素等待、文本输入、滑动、手势等常用操作的封装。
整合 uiautomator2 原生定位与图像匹配两种方式。
"""

import time
from typing import Optional

import uiautomator2 as u2

from mg_autotest.core.logger import get_logger
from mg_autotest.config import (
    DEFAULT_TIMEOUT,
    WAIT_ELEMENT_INTERVAL,
)

logger = get_logger(__name__)


# ─── 元素等待 ─────────────────────────────────────────────


def wait_for_text(d: u2.Device, text: str, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """
    等待包含特定文本的元素出现。

    基于 uiautomator2 原生定位，适合 UI 树可读的 H5 页面或原生页面。

    Args:
        d: uiautomator2 Device 对象
        text: 要等待的文本内容
        timeout: 超时时间 (秒)

    Returns:
        文本是否在超时前出现
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        if d(text=text).exists:
            logger.info(f"文本已出现: '{text}'")
            return True
        time.sleep(WAIT_ELEMENT_INTERVAL)
    logger.warning(f"超时: 在 {timeout}s 内未找到文本 '{text}'")
    return False


def wait_for_element_by_id(
    d: u2.Device,
    resource_id: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """
    等待具有指定 resourceId 的元素出现。

    Args:
        d: uiautomator2 Device 对象
        resource_id: 元素的 resource-id
        timeout: 超时时间 (秒)

    Returns:
        元素是否在超时前出现
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        if d(resourceId=resource_id).exists:
            logger.info(f"元素已出现: id='{resource_id}'")
            return True
        time.sleep(WAIT_ELEMENT_INTERVAL)
    logger.warning(f"超时: 在 {timeout}s 内未找到元素 id='{resource_id}'")
    return False


def wait_for_text_gone(
    d: u2.Device,
    text: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """
    等待指定文本从屏幕上消失。

    Args:
        d: uiautomator2 Device 对象
        text: 要等待消失的文本
        timeout: 超时时间 (秒)

    Returns:
        文本是否在超时前消失
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        if not d(text=text).exists:
            logger.info(f"文本已消失: '{text}'")
            return True
        time.sleep(WAIT_ELEMENT_INTERVAL)
    logger.warning(f"超时: 文本 '{text}' 未在 {timeout}s 内消失")
    return False


# ─── 文本输入 ─────────────────────────────────────────────


def input_text(
    d: u2.Device,
    resource_id: str,
    text: str,
    clear_first: bool = True,
    timeout: float = 5,
) -> bool:
    """
    向指定 resourceId 的输入框输入文本。

    Args:
        d: uiautomator2 Device 对象
        resource_id: 输入框的 resource-id
        text: 要输入的文本
        clear_first: 输入前是否先清空
        timeout: 等待超时 (秒)

    Returns:
        是否输入成功
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        elem = d(resourceId=resource_id)
        if elem.exists:
            try:
                elem.click()
                time.sleep(0.3)
                if clear_first:
                    elem.clear_text()
                    time.sleep(0.2)
                elem.set_text(text)
                logger.info(f"已输入文本: '{text}' -> id='{resource_id}'")
                return True
            except Exception as e:
                logger.warning(f"输入文本到 id='{resource_id}' 失败: {e}")
                time.sleep(WAIT_ELEMENT_INTERVAL)
        else:
            time.sleep(WAIT_ELEMENT_INTERVAL)

    logger.warning(f"超时: 未找到输入框 id='{resource_id}'")
    return False


def input_text_by_selector(
    d: u2.Device,
    selector_kwargs: dict,
    text: str,
    clear_first: bool = True,
    timeout: float = 5,
) -> bool:
    """
    使用自定义选择器定位输入框并输入文本。

    Args:
        d: uiautomator2 Device 对象
        selector_kwargs: 选择器参数，如 {"className": "android.widget.EditText"}
        text: 要输入的文本
        clear_first: 输入前是否先清空
        timeout: 等待超时 (秒)

    Returns:
        是否输入成功
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        elem = d(**selector_kwargs)
        if elem.exists:
            try:
                elem.click()
                time.sleep(0.3)
                if clear_first:
                    elem.clear_text()
                    time.sleep(0.2)
                elem.set_text(text)
                logger.info(f"已输入文本: '{text}' -> {selector_kwargs}")
                return True
            except Exception as e:
                logger.warning(f"输入文本失败 {selector_kwargs}: {e}")
                time.sleep(WAIT_ELEMENT_INTERVAL)
        else:
            time.sleep(WAIT_ELEMENT_INTERVAL)

    logger.warning(f"超时: 未找到输入框 {selector_kwargs}")
    return False


# ─── 滑动操作 ─────────────────────────────────────────────


def swipe_up(d: u2.Device, duration: float = 0.2, scale: float = 0.8) -> None:
    """
    从屏幕底部向上滑动。

    Args:
        d: uiautomator2 Device 对象
        duration: 滑动持续时间 (秒)
        scale: 滑动距离占屏幕高度的比例
    """
    width, height = d.window_size()
    start_x = width // 2
    start_y = int(height * 0.8)
    end_y = int(height * (1 - scale))
    d.swipe(start_x, start_y, start_x, end_y, duration=duration)
    logger.debug(f"上滑: ({start_x}, {start_y}) -> ({start_x}, {end_y})")


def swipe_down(d: u2.Device, duration: float = 0.2, scale: float = 0.8) -> None:
    """
    从屏幕顶部向下滑动。

    Args:
        d: uiautomator2 Device 对象
        duration: 滑动持续时间 (秒)
        scale: 滑动距离占屏幕高度的比例
    """
    width, height = d.window_size()
    start_x = width // 2
    start_y = int(height * 0.2)
    end_y = int(height * scale)
    d.swipe(start_x, start_y, start_x, end_y, duration=duration)
    logger.debug(f"下滑: ({start_x}, {start_y}) -> ({start_x}, {end_y})")


def swipe_left(d: u2.Device, duration: float = 0.2, scale: float = 0.8) -> None:
    """
    从屏幕右侧向左滑动。

    Args:
        d: uiautomator2 Device 对象
        duration: 滑动持续时间 (秒)
        scale: 滑动距离占屏幕宽度的比例
    """
    width, height = d.window_size()
    start_x = int(width * 0.8)
    end_x = int(width * (1 - scale))
    start_y = height // 2
    d.swipe(start_x, start_y, end_x, start_y, duration=duration)
    logger.debug(f"左滑: ({start_x}, {start_y}) -> ({end_x}, {start_y})")


def swipe_right(d: u2.Device, duration: float = 0.2, scale: float = 0.8) -> None:
    """
    从屏幕左侧向右滑动。

    Args:
        d: uiautomator2 Device 对象
        duration: 滑动持续时间 (秒)
        scale: 滑动距离占屏幕宽度的比例
    """
    width, height = d.window_size()
    start_x = int(width * 0.2)
    end_x = int(width * scale)
    start_y = height // 2
    d.swipe(start_x, start_y, end_x, start_y, duration=duration)
    logger.debug(f"右滑: ({start_x}, {start_y}) -> ({end_x}, {start_y})")


# ─── 坐标点击 ─────────────────────────────────────────────


def click_coordinate(d: u2.Device, x: int, y: int) -> None:
    """
    点击屏幕指定坐标。

    Args:
        d: uiautomator2 Device 对象
        x: X 坐标
        y: Y 坐标
    """
    d.click(x, y)
    logger.info(f"坐标点击: ({x}, {y})")


# ─── 页面文本获取 ─────────────────────────────────────────


def get_text(d: u2.Device, resource_id: str, timeout: float = 5) -> Optional[str]:
    """
    获取指定元素的文本内容。

    Args:
        d: uiautomator2 Device 对象
        resource_id: 元素的 resource-id
        timeout: 等待超时 (秒)

    Returns:
        元素文本内容，未找到返回 None
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        elem = d(resourceId=resource_id)
        if elem.exists:
            text = elem.get_text()
            logger.info(f"获取文本: '{text}' -> id='{resource_id}'")
            return text
        time.sleep(WAIT_ELEMENT_INTERVAL)
    logger.warning(f"超时: 未找到元素 id='{resource_id}'")
    return None
