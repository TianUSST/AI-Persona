"""
日志配置模块

使用 loguru 统一管理日志输出：
- 控制台：实时查看运行状态
- 文件：持久化记录，便于排查问题

使用方式：
    from backend.utils.logger import setup_logger
    setup_logger()  # 在应用启动时调用一次
    from loguru import logger
    logger.info("xxx")  # 之后全局使用
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from backend.config.config_loader import AppConfig


def setup_logger() -> None:
    """初始化 loguru 日志配置。

    读取 app_config.yaml 中的 logging 配置项：
    - level: 日志级别（DEBUG/INFO/WARNING/ERROR）
    - file: 日志文件路径
    - rotation: 文件轮转大小

    调用后，logger 会同时输出到控制台和文件。
    """
    config = AppConfig()

    # 读取配置
    level = config.get("logging.level", "INFO")
    log_file = config.get("logging.file", "logs/app.log")
    rotation = config.get("logging.rotation", "10 MB")

    # 确保日志目录存在
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 移除默认处理器
    logger.remove()

    # 添加控制台输出（带颜色，方便区分级别）
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    # 添加文件输出（详细格式，含完整时间戳）
    logger.add(
        log_file,
        rotation=rotation,       # 文件超过大小后自动轮转
        retention="7 days",      # 保留最近7天的日志
        level="DEBUG",           # 文件记录所有级别（包括 DEBUG）
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}",
    )

    logger.info(f"日志初始化完成 | 级别={level} | 文件={log_file}")
