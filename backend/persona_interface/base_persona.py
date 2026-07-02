"""
Persona（人格）抽象接口

人格层是整个系统的"灵魂"，负责：
- 定义 AI 的角色身份（如张雪峰、HR面试官、医生等）
- 管理系统提示词（告诉 LLM "你是谁、怎么说话"）
- 在 LLM 回答前后附加处理（注入免责声明、敏感内容过滤等）
- 构建完整的对话消息列表

数据流向：
    用户文字 → [BasePersona 构建消息] → BaseLLM → [BasePersona 后处理] → 最终回答

每个人格是一个独立文件夹，包含：
    persona.yaml  - 人格元数据（名称、描述、免责声明）
    prompt.txt    - 系统提示词（角色设定和行为规范）
    skills.py     - 技能函数（可选，如查学校、分析专业）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from backend.persona_interface.base_llm import LLMMessage


class BasePersona(ABC):
    """人格的抽象基类。

    每个人格实现必须继承此类，提供：
    - 系统提示词（定义角色）
    - 回答生成（调用 LLM + 后处理）

    使用示例：
        persona = ZhangXuefengPersona(llm=llm)
        await persona.initialize()
        answer = await persona.generate_response("620分能报计算机吗", history)
        await persona.shutdown()
    """

    # 人格名称（如 "zhangxuefeng"），子类必须设置
    name: str

    @abstractmethod
    async def initialize(self) -> None:
        """加载人格配置。

        读取 persona.yaml 和 prompt.txt，准备好人格的所有设置。
        在应用启动时调用一次。
        """
        ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """返回系统提示词。

        系统提示词告诉 LLM 它扮演什么角色、怎么说话、有什么限制。
        每次调用 LLM 时都会把这段话放在对话最前面。

        Returns:
            系统提示词文本
        """
        ...

    @abstractmethod
    async def generate_response(
        self, user_text: str, history: list[LLMMessage]
    ) -> str:
        """生成完整回答（非流式）。

        完整流程：
        1. 调用 build_messages() 构建消息列表
        2. 调用 LLM 生成回答
        3. 后处理：注入免责声明、内容过滤等

        Args:
            user_text: 用户当前的问题
            history: 之前的对话历史（不含 system prompt）

        Returns:
            经过后处理的最终回答文本
        """
        ...

    @abstractmethod
    async def generate_response_stream(
        self, user_text: str, history: list[LLMMessage]
    ) -> AsyncIterator[str]:
        """流式生成回答。

        与 generate_response 相同的流程，但以流式方式返回。
        免责声明通常作为第一个 chunk 预先返回。

        Args:
            user_text: 用户当前的问题
            history: 之前的对话历史

        Yields:
            逐个返回的文字片段
        """
        ...

    def build_messages(
        self, user_text: str, history: list[LLMMessage]
    ) -> list[LLMMessage]:
        """构建发送给 LLM 的完整消息列表。

        默认实现：
        1. 放入 system prompt（角色设定）
        2. 追加历史对话
        3. 追加当前用户问题

        子类可以重写此方法，例如：
        - 注入额外的技能提示词
        - 添加 RAG 检索到的知识片段
        - 压缩过长的历史对话

        Args:
            user_text: 用户当前的问题
            history: 之前的对话历史

        Returns:
            完整的消息列表，可直接传给 BaseLLM.generate()
        """
        messages: list[LLMMessage] = []

        # 1. 系统提示词（放在最前面，定义角色）
        messages.append(LLMMessage(role="system", content=self.get_system_prompt()))

        # 2. 历史对话
        messages.extend(history)

        # 3. 当前用户问题
        messages.append(LLMMessage(role="user", content=user_text))

        return messages

    @abstractmethod
    async def shutdown(self) -> None:
        """释放资源。"""
        ...
