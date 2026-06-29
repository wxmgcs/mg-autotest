"""
弹窗监控器模块

使用 uiautomator2 的 d.watcher 注册通用弹窗处理规则（XPath 选择器）。
支持持久后台监控和手动启停。
"""

import uiautomator2 as u2
from typing import Dict, List, Optional

from mg_autotest.core.logger import get_logger

logger = get_logger(__name__)


def _xpath_by_text(text: str) -> str:
    """
    将文本转为 XPath 选择器。

    Args:
        text: 文本内容，如 "允许"

    Returns:
        XPath 字符串，如 "//*[@text='允许']"
    """
    # 转义单引号
    safe_text = text.replace("'", "\\'")
    return f"//*[@text='{safe_text}']"


def setup_watchers(
    d: u2.Device,
    custom_rules: Optional[Dict[str, List[str]]] = None,
) -> None:
    """
    注册通用的弹窗点击规则（持久后台监控）。

    内置基础规则集，可通过 custom_rules 扩展自定义规则。
    使用 XPath 选择器匹配文本，注册后自动在后台运行。

    注意：watch_context 的 when() 和 click() 均不接收 text= 关键字，
    需使用 XPath 字符串，如 "//*[@text='允许']"。

    Args:
        d: uiautomator2 Device 对象
        custom_rules: 自定义规则字典
            { "规则名称": ["文本1", "文本2", ...] }
            每个名称注册为一个 watcher，当 文本1 出现时点击它。
    """
    # ── 内置基础规则 ──
    base_rules = {
        "允许权限":    ["允许", "Allow", "允许权限"],
        "确定":        ["确定", "确认", "OK", "好的"],
        "同意":        ["同意", "Agree", "Accept"],
        "取消":        ["取消", "Cancel", "关闭"],
        "知道了":      ["知道了", "我知道了", "明白"],
        "拒绝":        ["拒绝", "Deny", "不允许"],
        "以后再说":    ["以后再说", "稍后", "稍后再说"],
        "升级提示":    ["稍后更新", "以后再说", "跳过"],
    }

    # 合并自定义规则
    if custom_rules:
        base_rules.update(custom_rules)

    # 注册规则
    registered_count = 0
    for name, texts in base_rules.items():
        if not texts:
            continue

        # 每条规则是一个持久 watcher
        # 点击列表中第一个文本对应的元素
        watcher = d.watcher(name)
        watcher.when(_xpath_by_text(texts[0])).click()

        # 如果规则有多个文本变体，用相同名称注册多个 when 条件
        for text in texts[1:]:
            watcher.when(_xpath_by_text(text)).click()

        registered_count += 1
        logger.debug(f"弹窗规则已注册: [{name}] -> 点击 '{texts[0]}'")

    logger.info(f"弹窗监控已启动，共 {registered_count} 条规则")


def setup_watchers_stop(d: u2.Device) -> None:
    """
    停止所有弹窗监控。

    Args:
        d: uiautomator2 Device 对象
    """
    try:
        d.watchers.stop()
        logger.info("弹窗监控已停止")
    except Exception as e:
        logger.warning(f"停止弹窗监控时发生异常: {e}")


def setup_watchers_remove(d: u2.Device) -> None:
    """
    移除所有已注册的弹窗规则。

    Args:
        d: uiautomator2 Device 对象
    """
    try:
        d.watchers.remove()
        logger.info("所有弹窗规则已移除")
    except Exception as e:
        logger.warning(f"移除弹窗规则时发生异常: {e}")
