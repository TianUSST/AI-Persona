"""
LLM（大语言模型）抽象接口

定义了语言模型模块必须提供的功能：
- 完整生成：发送问题，等待完整回答
- 流式生成：发送问题，逐 token 返回回答片段（实时显示用）

所有 LLM 后端（OpenAI API、DeepSeek、本地 Ollama 等）都必须实现此接口。

数据流向：
    用户文字 + 人格提示词 → [BaseLLM] → AI 回答文字 → 传给 TTS
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from pydantic import BaseModel


class LLMMessage(BaseModel):
    """对话中的一条消息。

    对话历史由多条消息组成，每条消息有角色和内容。
    标准的对话格式：
        [
            {"role": "system", "content": "你是一个高考志愿专家..."},
            {"role": "user", "content": "我620分能报计算机吗"},
            {"role": "assistant", "content": "620分想冲计算机？..."},
        ]

    Attributes:
        role: 消息角色
            - "system": 系统提示词（定义 AI 行为）
            - "user": 用户输入
            - "assistant": AI 回复
        content: 消息文本内容
    """

    role: str
    content: str


class LLMConfig(BaseModel):
    """LLM 调用的运行时配置。

    可以在全局配置基础上针对单次调用做微调。

    Attributes:
        model: 模型名称（如 "deepseek-chat"、"qwen-7b"）
        temperature: 生成温度（0.0=完全确定，1.0=更随机），默认 0.7
        max_tokens: 单次回复最大 token 数，默认 1024
        stream: 是否流式生成，默认 True
    """

    model: str
    temperature: float = 0.7
    max_tokens: int = 1024
    stream: bool = True


class BaseLLM(ABC):
    """LLM 后端的抽象基类。

    所有语言模型实现（如 OpenAICompatibleLLM）都必须继承此类
    并实现以下 4 个方法。

    使用示例：
        llm = OpenAICompatibleLLM()
        await llm.initialize(config)
        # 完整生成
        answer = await llm.generate(messages)
        # 流式生成
        async for chunk in llm.generate_stream(messages):
            print(chunk, end="")
        await llm.shutdown()
    """

    @abstractmethod
    async def initialize(self, config: LLMConfig) -> None:
        """初始化 LLM 客户端。

        在应用启动时调用一次，用于：
        - 创建 API 客户端实例
        - 验证 API Key 和连接可用性
        - 如果是本地模型，加载权重到 GPU

        Args:
            config: LLM 配置（模型名、温度等）
        """
        ...

    @abstractmethod
    async def generate(
        self, messages: list[LLMMessage], config: LLMConfig | None = None
    ) -> str:
        """生成完整回答（非流式）。

        发送完整对话历史，等待 LLM 生成完整回答后一次性返回。
        适用于对实时性要求不高的场景。

        Args:
            messages: 对话历史列表（包含 system prompt + 用户/AI 交替消息）
            config: 可选的运行时配置覆盖（为 None 时使用初始化时的配置）

        Returns:
            完整的回答文本
        """
        ...

    @abstractmethod
    async def generate_stream(
        self, messages: list[LLMMessage], config: LLMConfig | None = None
    ) -> AsyncIterator[str]:
        """流式生成回答。

        发送完整对话历史，逐 token 返回回答片段。
        这是实时交互的核心方法——前端可以边收到文字边显示，
        同时也可以边收到句子边送给 TTS 合成语音。

        Args:
            messages: 对话历史列表
            config: 可选的运行时配置覆盖

        Yields:
            逐个返回的文字片段（如 "你好"、"，我是"、"张老师"）
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """释放 LLM 客户端资源。

        关闭 HTTP 连接池、释放本地模型显存等。
        """
        ...
