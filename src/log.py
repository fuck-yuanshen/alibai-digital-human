# -*- coding: utf-8 -*-
"""
@author:XuMing(xuming624@qq.com)
@description: Unified logging configuration for AI Avatar.

This module provides a centralized logger configuration that can be controlled
via environment variables or programmatically.
"""

import os
import sys
from pathlib import Path
from loguru import logger as _logger

# Windows 打包版可能将 stderr 绑定到 GBK 输出流；替换不可编码字符，
# 避免原始网络/文件错误被 UnicodeEncodeError 覆盖。
try:
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(errors="replace")
except (AttributeError, OSError):
    pass

# Remove default handler
_logger.remove()

# Get log level from environment variable, default to DEBUG
LOG_LEVEL = os.getenv("AI_AVATAR_LOG_LEVEL", "DEBUG").upper()

# Add custom handler with configurable level
_logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,
)


def get_log_file_path() -> Path:
    """返回桌面程序和服务端共用的持久化日志文件路径。"""
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Alibai"
    root.mkdir(parents=True, exist_ok=True)
    return root / "server.log"


# 桌面版没有控制台窗口，服务端日志必须落盘，供网页调试窗口读取。
try:
    _logger.add(
        str(get_log_file_path()),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=LOG_LEVEL,
        encoding="utf-8",
        rotation="10 MB",
        retention="7 days",
    )
except OSError:
    # 只读或受限环境仍可使用 stderr 日志，不影响服务启动。
    pass


def set_log_level(level: str):
    """
    Set the log level for the entire AI Avatar package.
    
    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Example:
        >>> from src.log import set_log_level
        >>> set_log_level("DEBUG")
    """
    _logger.remove()
    _logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=level.upper(),
        colorize=True,
    )


def add_file_logger(log_file: str, level: str = "DEBUG"):
    """
    Add a file handler to the logger.
    
    Args:
        log_file: Path to the log file
        level: Log level for the file handler (default: DEBUG)
    
    Example:
        >>> from src.log import add_file_logger
        >>> add_file_logger("ai_avatar.log", "INFO")
    """
    _logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=level.upper(),
        rotation="10 MB",
        retention="7 days",
        compression="zip",
    )


# Export the configured logger
logger = _logger

__all__ = ["logger", "set_log_level", "add_file_logger", "get_log_file_path", "LOG_LEVEL"]

