"""
配置加载器 - 单例模式

职责：
- 从 app_config.yaml 加载所有配置
- 提供点分隔键访问（如 "asr.sensevoice.model"）
- 支持环境变量解析（API Key 等敏感信息不写入配置文件）

使用方式：
    from backend.config.config_loader import AppConfig
    config = AppConfig()
    model_name = config.get("asr.sensevoice.model")
    api_key = config.resolve_env(config.get("llm.openai_compatible.api_key_env"))
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


class AppConfig:
    """单例配置管理器。

    整个应用生命周期内只加载一次配置文件，后续所有调用
    返回同一个实例，避免重复读取磁盘。
    """

    # 类变量：单例实例引用
    _instance: AppConfig | None = None
    # 存储解析后的配置数据（嵌套字典）
    _data: dict[str, Any]

    def __new__(cls) -> AppConfig:
        """单例模式：首次调用时创建实例并加载配置，后续调用直接返回已有实例。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """从 YAML 文件加载配置。

        配置文件路径固定为本文件同目录下的 app_config.yaml。
        """
        # 获取配置文件的绝对路径（config_loader.py 同级目录）
        config_path = Path(__file__).parent / "app_config.yaml"

        if not config_path.exists():
            logger.error(f"配置文件不存在: {config_path}")
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        # 读取并解析 YAML
        with open(config_path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

        logger.info(f"配置加载成功: {config_path}")

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """通过点分隔键获取配置值。

        Args:
            dotted_key: 点分隔的配置键路径，如 "asr.sensevoice.model"
            default: 键不存在时的默认值

        Returns:
            配置值，如果键不存在则返回 default

        Examples:
            >>> config = AppConfig()
            >>> config.get("server.port")
            8000
            >>> config.get("asr.sensevoice.model")
            'iic/SenseVoiceSmall'
            >>> config.get("not.exist", "fallback")
            'fallback'
        """
        # 按 "." 分割键路径，逐层查找
        keys = dotted_key.split(".")
        node = self._data

        for key in keys:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default

        return node

    def resolve_env(self, env_key_name: str | None) -> str | None:
        """从环境变量中获取值。

        用于解析 API Key 等敏感信息——配置文件中只存储环境变量名，
        实际密钥通过此方法从系统环境变量中读取。

        Args:
            env_key_name: 环境变量名称，如 "LLM_API_KEY"

        Returns:
            环境变量的值，未设置时返回 None

        Examples:
            >>> config = AppConfig()
            >>> # 假设配置中 api_key_env 为 "LLM_API_KEY"
            >>> api_key_name = config.get("llm.openai_compatible.api_key_env")
            >>> api_key = config.resolve_env(api_key_name)
        """
        if env_key_name is None:
            return None
        value = os.environ.get(env_key_name)
        if value is None:
            logger.warning(f"环境变量 {env_key_name} 未设置")
        return value

    def reload(self) -> None:
        """重新加载配置文件。

        调试模式下可热更新配置，无需重启应用。
        """
        logger.info("重新加载配置文件...")
        self._load()

    def __repr__(self) -> str:
        return f"AppConfig(loaded={self._data is not None})"
