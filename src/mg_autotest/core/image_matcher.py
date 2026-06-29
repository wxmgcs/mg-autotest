"""
图像匹配核心模块

以 OpenCV 模板匹配为主进行元素定位与点击。
提供截图、匹配、点击、等待等基础原子操作。
"""

import time
import os
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import uiautomator2 as u2

from mg_autotest.core.logger import get_logger
from mg_autotest.config import (
    DEFAULT_THRESHOLD,
    DEFAULT_TIMEOUT,
    RETRY_INTERVAL,
    TEMPLATE_DIR,
    SCREENSHOT_DIR,
    SAVE_SCREENSHOT_ON_FAILURE,
)

logger = get_logger(__name__)


# ─── 工具函数 ─────────────────────────────────────────────


def _ensure_dir(path: str) -> None:
    """确保目录存在，不存在则创建"""
    Path(path).mkdir(parents=True, exist_ok=True)


def _load_template(template_path: str) -> Optional[np.ndarray]:
    """
    加载模板图片。

    Args:
        template_path: 模板图片路径

    Returns:
        OpenCV 图像数组，读取失败返回 None
    """
    # 尝试在 TEMPLATE_DIR 下查找
    if not os.path.isfile(template_path):
        alt_path = os.path.join(TEMPLATE_DIR, template_path)
        if os.path.isfile(alt_path):
            template_path = alt_path
        else:
            logger.error(f"模板文件不存在: {template_path}")
            return None

    template = cv2.imread(template_path)
    if template is None:
        logger.error(f"无法读取模板图片: {template_path}")
        return None
    return template


def _screenshot_to_cv(d: u2.Device) -> Optional[np.ndarray]:
    """
    截取当前屏幕并转为 OpenCV BGR 格式。

    Args:
        d: uiautomator2 Device 对象

    Returns:
        BGR 格式的图像数组
    """
    try:
        screenshot = d.screenshot(format="opencv")
        if screenshot is None:
            # fallback: PIL Image → OpenCV
            from PIL import Image
            pil_img = d.screenshot()
            screenshot = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return screenshot
    except Exception as e:
        logger.error(f"截图失败: {e}")
        return None


# ─── 核心 API ─────────────────────────────────────────────


def find_image(
    d: u2.Device,
    template_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[Tuple[int, int, float]]:
    """
    在屏幕中查找模板图片。

    这是纯查找函数，不执行点击操作。

    Args:
        d: uiautomator2 Device 对象
        template_path: 模板图片路径
        threshold: 匹配阈值 (0~1)，建议 0.8
        timeout: 超时时间 (秒)

    Returns:
        (center_x, center_y, confidence) 或 None（未找到）
    """
    template = _load_template(template_path)
    if template is None:
        return None

    h, w = template.shape[:2]
    start_time = time.time()

    while time.time() - start_time < timeout:
        screenshot_cv = _screenshot_to_cv(d)
        if screenshot_cv is None:
            time.sleep(RETRY_INTERVAL)
            continue

        # 模板匹配
        result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            logger.info(f"找到图像 '{Path(template_path).name}'  "
                         f"坐标: ({center_x}, {center_y}) 置信度: {max_val:.3f}")
            return (center_x, center_y, max_val)
        else:
            logger.debug(f"未找到匹配 (当前最佳: {max_val:.3f})，延时 {RETRY_INTERVAL}s 重试...")
            time.sleep(RETRY_INTERVAL)

    logger.warning(f"超时: 在 {timeout}s 内未找到 '{Path(template_path).name}'")
    _save_failure_screenshot(d, f"not_found_{Path(template_path).stem}")
    return None


def find_and_click(
    d: u2.Device,
    template_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    timeout: float = DEFAULT_TIMEOUT,
    offset_x: int = 0,
    offset_y: int = 0,
) -> bool:
    """
    在屏幕上查找模板图片并点击其中心位置。

    Args:
        d: uiautomator2 Device 对象
        template_path: 模板图片路径
        threshold: 匹配阈值 (0~1)，建议 0.8
        timeout: 超时时间 (秒)
        offset_x: 点击位置 X 偏移（相对于中心点，可为负数）
        offset_y: 点击位置 Y 偏移（相对于中心点，可为负数）

    Returns:
        是否点击成功
    """
    result = find_image(d, template_path, threshold, timeout)
    if result is None:
        return False

    center_x, center_y, confidence = result
    click_x = center_x + offset_x
    click_y = center_y + offset_y

    try:
        d.click(click_x, click_y)
        logger.info(f"点击成功: ({click_x}, {click_y}) 置信度: {confidence:.3f}")
        return True
    except Exception as e:
        logger.error(f"点击失败 ({click_x}, {click_y}): {e}")
        _save_failure_screenshot(d, f"click_failed_{Path(template_path).stem}")
        return False


def wait_for_image(
    d: u2.Device,
    template_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """
    等待模板图片出现在屏幕上。不执行点击，只判断是否存在。

    Args:
        d: uiautomator2 Device 对象
        template_path: 模板图片路径
        threshold: 匹配阈值
        timeout: 超时时间 (秒)

    Returns:
        图片是否在超时前出现
    """
    return find_image(d, template_path, threshold, timeout) is not None


def wait_for_image_gone(
    d: u2.Device,
    template_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """
    等待模板图片从屏幕上消失。

    Args:
        d: uiautomator2 Device 对象
        template_path: 模板图片路径
        threshold: 匹配阈值
        timeout: 超时时间 (秒)

    Returns:
        图片是否在超时前消失
    """
    template = _load_template(template_path)
    if template is None:
        return True

    start_time = time.time()
    while time.time() - start_time < timeout:
        screenshot_cv = _screenshot_to_cv(d)
        if screenshot_cv is None:
            time.sleep(RETRY_INTERVAL)
            continue

        result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)

        if max_val < threshold:
            logger.info(f"图片 '{Path(template_path).name}' 已消失")
            return True
        time.sleep(RETRY_INTERVAL)

    logger.warning(f"超时: 图片 '{Path(template_path).name}' 未在 {timeout}s 内消失")
    return False


def click_if_exists(
    d: u2.Device,
    template_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    timeout: float = 3.0,
) -> bool:
    """
    快速点击：如果图片存在则点击并返回 True，否则快速返回 False。
    适用于弹窗等"有则点，无则过"的场景。

    Args:
        d: uiautomator2 Device 对象
        template_path: 模板图片路径
        threshold: 匹配阈值
        timeout: 超时时间 (可设较短)

    Returns:
        是否点击成功
    """
    return find_and_click(d, template_path, threshold, timeout)


# ─── 截屏辅助 ─────────────────────────────────────────────


def save_screenshot(d: u2.Device, name: str = None) -> Optional[str]:
    """
    保存当前屏幕截图。

    Args:
        d: uiautomator2 Device 对象
        name: 文件名（不含后缀），默认使用时间戳

    Returns:
        截图文件路径，失败返回 None
    """
    _ensure_dir(SCREENSHOT_DIR)
    filename = name or time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(SCREENSHOT_DIR, f"{filename}.png")

    try:
        screenshot_cv = _screenshot_to_cv(d)
        if screenshot_cv is not None:
            cv2.imwrite(filepath, screenshot_cv)
            logger.info(f"截图已保存: {filepath}")
            return filepath
        else:
            # fallback: PIL save
            pil_img = d.screenshot()
            pil_img.save(filepath)
            logger.info(f"截图已保存 (PIL): {filepath}")
            return filepath
    except Exception as e:
        logger.error(f"保存截图失败: {e}")
        return None


def _save_failure_screenshot(d: u2.Device, tag: str) -> None:
    """操作失败时自动截图（按配置决定是否保存）"""
    if SAVE_SCREENSHOT_ON_FAILURE:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_screenshot(d, f"FAIL_{tag}_{timestamp}")
