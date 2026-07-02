"""
会话历史管理器

负责管理每个 WebSocket 会话的对话历史：
- 按 session_id 隔离不同用户的对话
- 滑动窗口裁剪（保留最近 N 轮，避免 token 超限）
- 支持清空和查询历史

数据结构：
    {
        "session_abc": [system_msg, user_msg, ai_msg, user_msg, ai_msg, ...],
        "session_xyz": [system_msg, user_msg, ai_msg, ...],
    }
"""

from __future__ import annotations

from collections import defaultdict

from loguru import logger

from backend.config.config_loader import AppConfig
from backend.persona_interface.base_llm import LLMMessage


class ConversationManager:
    """对话历史管理器。

    每个 session_id 维护独立的对话历史列表。
    历史超出最大轮数时，自动裁剪最早的对话（保留系统提示词）。

    使用示例：
        manager = ConversationManager()
        manager.add_message("session1", LLMMessage(role="user", content="你好"))
        history = manager.get_history("session1")
        manager.clear("session1")
    """

    def __init__(self) -> None:
        # session_id → 消息列表的映射
        self._histories: dict[str, list[LLMMessage]] = defaultdict(list)
        # 从配置读取最大保留轮数
        self._max_turns = AppConfig().get("persona.max_history_turns", 10)

    def add_message(self, session_id: str, message: LLMMessage) -> None:
        """向指定会话添加一条消息。

        添加后自动检查是否超出最大轮数，超出时裁剪最早的消息。

        Args:
            session_id: 会话标识符
            message: 要添加的消息
        """
        history = self._histories[session_id]
        history.append(message)

        # 裁剪逻辑：保留 system prompt + 最近 N 轮对话
        # 每轮 = 1条 user + 1条 assistant = 2条消息
        max_messages = self._max_turns * 2  # 不含 system prompt

        if len(history) > max_messages + 10:  # 留一些缓冲
            # 找到第一条非 system 消息的位置
            system_msgs = [m for m in history if m.role == "system"]
            non_system_msgs = [m for m in history if m.role != "system"]

            # 保留最近的 max_messages 条非 system 消息
            trimmed_non_system = non_system_msgs[-max_messages:]

            # 重建历史：system 消息 + 裁剪后的对话
            self._histories[session_id] = system_msgs + trimmed_non_system
            logger.debug(
                f"会话 {session_id} 历史裁剪: "
                f"{len(history)} → {len(self._histories[session_id])}"
            )

    def get_history(self, session_id: str) -> list[LLMMessage]:
        """获取指定会话的对话历史。

        Args:
            session_id: 会话标识符

        Returns:
            消息列表的副本（避免外部修改内部状态）
        """
        return list(self._histories.get(session_id, []))

    def get_history_without_system(self, session_id: str) -> list[LLMMessage]:
        """获取不含 system prompt 的对话历史。

        用于传给 Persona.build_messages()，由人格层自行添加 system prompt。

        Args:
            session_id: 会话标识符

        Returns:
            不包含 role="system" 的消息列表
        """
        history = self._histories.get(session_id, [])
        return [m for m in history if m.role != "system"]

    def clear(self, session_id: str) -> None:
        """清空指定会话的对话历史。

        Args:
            session_id: 会话标识符
        """
        if session_id in self._histories:
            del self._histories[session_id]
            logger.info(f"会话 {session_id} 历史已清空")

    def has_history(self, session_id: str) -> bool:
        """检查指定会话是否有对话历史。"""
        return session_id in self._histories and len(self._histories[session_id]) > 0

    @property
    def active_sessions(self) -> int:
        """当前活跃会话数。"""
        return len(self._histories)
