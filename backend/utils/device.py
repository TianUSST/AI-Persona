"""
计算设备管理器

职责：
- 自动检测 Intel XPU (ARC B580) 是否可用
- 根据配置返回最优计算设备
- XPU 不可用时自动回退到 CPU

使用方式：
    from backend.utils.device import get_device
    device = get_device()           # 返回 torch.device("xpu:0") 或 torch.device("cpu")
    model = model.to(device)        # 将模型移到目标设备
"""

from __future__ import annotations

import torch
from loguru import logger

from backend.config.config_loader import AppConfig


def get_device() -> torch.device:
    """获取最优计算设备。

    选择优先级：
    1. 如果配置 preferred="xpu"，强制使用 XPU（不可用则报错回退）
    2. 如果配置 preferred="auto"，自动检测 XPU → 回退 CPU
    3. 如果配置 preferred="cpu"，强制使用 CPU

    Returns:
        torch.device 对象，用于 model.to(device) 和 tensor.to(device)

    Examples:
        >>> device = get_device()
        >>> model = MyModel().to(device)
        >>> tensor = torch.zeros(10).to(device)
    """
    config = AppConfig()
    preferred = config.get("device.preferred", "auto")

    # 情况1：用户强制指定 XPU
    if preferred == "xpu":
        if _is_xpu_available():
            return _create_xpu_device(config)
        else:
            logger.warning("配置要求 XPU 但设备不可用，回退到 CPU")
            return torch.device("cpu")

    # 情况2：自动检测（推荐）
    if preferred == "auto":
        if _is_xpu_available():
            return _create_xpu_device(config)
        else:
            logger.info("XPU 不可用，使用 CPU 设备")
            return torch.device("cpu")

    # 情况3：强制 CPU
    if preferred == "cpu":
        logger.info("配置指定使用 CPU 设备")
        return torch.device("cpu")

    # 未知配置值，回退 CPU
    logger.warning(f"未知的设备配置 '{preferred}'，回退到 CPU")
    return torch.device("cpu")


def _is_xpu_available() -> bool:
    """检测 Intel XPU 设备是否可用。

    检查逻辑：
    1. PyTorch 是否编译了 XPU 支持（torch.xpu 模块是否存在）
    2. 是否有可用的 XPU 设备

    Returns:
        True 表示 XPU 可用
    """
    try:
        # torch.xpu 在 PyTorch XPU 版本中才存在
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return True
    except Exception as e:
        logger.debug(f"XPU 检测异常: {e}")
    return False


def _create_xpu_device(config: AppConfig) -> torch.device:
    """创建 XPU 设备对象并记录设备信息。

    Args:
        config: 应用配置实例

    Returns:
        torch.device("xpu:N") 对象
    """
    device_id = config.get("device.xpu_device_id", 0)
    device = torch.device(f"xpu:{device_id}")

    # 记录设备信息，方便排查问题
    try:
        device_name = torch.xpu.get_device_name(device_id)
        logger.info(f"使用 XPU 设备 {device_id}: {device_name}")
    except Exception:
        logger.info(f"使用 XPU 设备 {device_id}")

    return device
