"""
日志配置模块

统一管理日志输出格式、级别和输出目标。
支持控制台输出和文件输出两种方式，由 config.py 控制。
"""

import logging
import sys

from mg_autotest.config import LOG_LEVEL, LOG_FORMAT, LOG_FILE

# 保存已创建的 logger，避免重复添加 handler
_loggers = {}


def setup_logger(name: str = "autotest") -> logging.Logger:
    """
    创建并返回指定名称的 logger。

    Args:
        name: logger 名称，不同模块可用不同名称便于溯源

    Returns:
        配置好的 Logger 实例
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # 清除已有 handlers，避免重复
    if logger.handlers:
        logger.handlers.clear()

    # ── 控制台 Handler ──
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)

    # ── 文件 Handler（可选） ──
    if LOG_FILE:
        import os
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger


def get_logger(name: str = "autotest") -> logging.Logger:
    """
    获取已创建的 logger，若未创建则调用 setup_logger。

    Args:
        name: logger 名称

    Returns:
        Logger 实例
    """
    if name not in _loggers:
        return setup_logger(name)
    return _loggers[name]
