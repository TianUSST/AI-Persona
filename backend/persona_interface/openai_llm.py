"""
OpenAI 兼容 LLM 实现

使用 OpenAI SDK 调用大语言模型，支持所有兼容 OpenAI API 的服务：
- DeepSeek（国内推荐，便宜快速）
- OpenAI GPT-4（效果最好）
- 本地 Ollama（免费，需本地部署）
- 阿里 Qwen API
- 其他任何 OpenAI 兼容接口

配置来源：app_config.yaml 中的 llm.openai_compatible 部分
API Key：通过环境变量读取（不在配置文件中明文存储）
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from loguru import logger

from backend.config.config_loader import AppConfig
from backend.persona_interface.base_llm import BaseLLM, LLMConfig, LLMMessage


class OpenAICompatibleLLM(BaseLLM):
    """OpenAI 兼容的 LLM 后端。

    通过 openai SDK 的 AsyncClient 调用远程/本地 LLM。
    流式模式下逐 token 返回，首 token 延迟通常 0.5~2 秒。

    使用示例：
        llm = OpenAICompatibleLLM()
        await llm.initialize(LLMConfig(model="deepseek-chat"))
        async for chunk in llm.generate_stream(messages):
            print(chunk, end="")
        await llm.shutdown()
    """

    def __init__(self) -> None:
        self._client = None         # openai.AsyncClient 实例
        self._config = AppConfig()
        self._default_config: LLMConfig | None = None

    async def initialize(self, config: LLMConfig | None = None) -> None:
        """初始化 LLM 客户端。

        从配置文件读取 API 地址和模型信息，从环境变量读取 API Key。

        Args:
            config: 可选的 LLM 配置覆盖。为 None 时从 app_config.yaml 读取。
        """
        # 读取配置
        llm_config = self._config.get("llm.openai_compatible", {})
        base_url = llm_config.get("base_url", "https://api.deepseek.com/v1")
        api_key_env = llm_config.get("api_key_env", "LLM_API_KEY")
        model = llm_config.get("model", "deepseek-chat")
        max_tokens = llm_config.get("max_tokens", 1024)
        temperature = llm_config.get("temperature", 0.7)

        # 从环境变量读取 API Key
        api_key = self._config.resolve_env(api_key_env)
        if api_key is None:
            logger.error(
                f"LLM API Key 未设置！请设置环境变量 {api_key_env}\n"
                f"  Windows: set {api_key_env}=your-api-key\n"
                f"  Linux:   export {api_key_env}=your-api-key"
            )
            raise RuntimeError(f"环境变量 {api_key_env} 未设置")

        # 构建默认配置
        self._default_config = config or LLMConfig(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        # 创建异步客户端
        def _create_client():
            from openai import AsyncClient
            return AsyncClient(
                base_url=base_url,
                api_key=api_key,
            )

        self._client = await asyncio.to_thread(_create_client)
        logger.info(f"LLM 客户端初始化完成 | base_url={base_url} | model={model}")

    async def generate(
        self, messages: list[LLMMessage], config: LLMConfig | None = None
    ) -> str:
        """生成完整回答（非流式）。

        Args:
            messages: 对话历史
            config: 可选的运行时配置覆盖

        Returns:
            完整的回答文本
        """
        if self._client is None:
            raise RuntimeError("LLM 客户端未初始化，请先调用 initialize()")

        cfg = config or self._default_config

        # 转换消息格式（LLMMessage → OpenAI 格式）
        openai_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        logger.debug(f"LLM 请求 | model={cfg.model} | messages={len(messages)}")

        # 调用 API
        response = await self._client.chat.completions.create(
            model=cfg.model,
            messages=openai_messages,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            stream=False,
        )

        content = response.choices[0].message.content or ""
        logger.debug(f"LLM 响应 | length={len(content)}")
        return content

    async def generate_stream(
        self, messages: list[LLMMessage], config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        """流式生成回答。

        逐 token 返回文本片段，前端可以边收边显示。
        首 token 到达后，后续 token 通常以 30-100ms/个 的速度生成。

        Args:
            messages: 对话历史
            config: 可选的运行时配置覆盖

        Yields:
            文本片段（如 "你好"、"，我是"、"张老师"）
        """
        if self._client is None:
            raise RuntimeError("LLM 客户端未初始化，请先调用 initialize()")

        cfg = config or self._default_config

        openai_messages = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]

        logger.debug(f"LLM 流式请求 | model={cfg.model} | messages={len(messages)}")

        # 流式调用 API
        stream = await self._client.chat.completions.create(
            model=cfg.model,
            messages=openai_messages,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            stream=True,
        )

        # 逐 chunk 返回文本
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def shutdown(self) -> None:
        """释放 LLM 客户端资源。"""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("LLM 客户端资源已释放")
