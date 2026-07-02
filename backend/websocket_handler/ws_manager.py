"""
WebSocket 连接管理器

职责：
- 管理所有活跃的 WebSocket 连接（按 session_id 索引）
- 提供消息发送方法（JSON 和二进制）
- 处理连接建立和断开

在 FastAPI 中，每个 WebSocket 连接对应一个会话（session），
前端通过 URL 中的 session_id 来标识自己。

连接生命周期：
    前端打开连接 → connect() → 双向通信 → 断开 → disconnect()
"""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    """WebSocket 连接管理器。

    使用 session_id 作为键来管理所有活跃连接。
    同一时间一个 session_id 只能有一个连接（新连接会替换旧连接）。

    使用示例（在 FastAPI 路由中）：
        manager = ConnectionManager()

        @app.websocket("/ws/{session_id}")
        async def ws_endpoint(websocket: WebSocket, session_id: str):
            await manager.connect(websocket, session_id)
            try:
                while True:
                    data = await websocket.receive_json()
                    # 处理消息...
            except WebSocketDisconnect:
                manager.disconnect(session_id)
    """

    def __init__(self) -> None:
        # session_id -> WebSocket 连接的映射表
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """接受一个新的 WebSocket 连接。

        如果该 session_id 已有旧连接，会先关闭旧连接再替换。

        Args:
            websocket: FastAPI 的 WebSocket 对象
            session_id: 会话标识符（前端生成的唯一 ID）
        """
        # 如果该 session 已有连接，先关闭旧的
        if session_id in self._connections:
            logger.warning(f"会话 {session_id} 已有连接，替换旧连接")
            old_ws = self._connections[session_id]
            try:
                await old_ws.close()
            except Exception:
                pass

        # 接受新连接
        await websocket.accept()
        self._connections[session_id] = websocket
        logger.info(f"客户端已连接: {session_id} (当前活跃: {len(self._connections)})")

    def disconnect(self, session_id: str) -> None:
        """移除一个断开的连接。

        Args:
            session_id: 要移除的会话标识符
        """
        if session_id in self._connections:
            del self._connections[session_id]
            logger.info(f"客户端已断开: {session_id} (当前活跃: {len(self._connections)})")

    def get(self, session_id: str) -> WebSocket | None:
        """获取指定会话的 WebSocket 连接。

        Args:
            session_id: 会话标识符

        Returns:
            WebSocket 对象，不存在时返回 None
        """
        return self._connections.get(session_id)

    def is_connected(self, session_id: str) -> bool:
        """检查指定会话是否在线。"""
        return session_id in self._connections

    async def send_json(self, session_id: str, message: dict[str, Any]) -> bool:
        """向指定会话发送 JSON 消息。

        Args:
            session_id: 目标会话标识符
            message: 要发送的字典（会被自动序列化为 JSON）

        Returns:
            True 发送成功，False 连接不存在
        """
        ws = self._connections.get(session_id)
        if ws is None:
            logger.debug(f"发送失败: 会话 {session_id} 不在线")
            return False

        try:
            await ws.send_json(message)
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {session_id} - {e}")
            # 发送失败说明连接已断开，清理掉
            self.disconnect(session_id)
            return False

    async def send_bytes(self, session_id: str, data: bytes) -> bool:
        """向指定会话发送二进制数据。

        当需要发送原始音频/视频数据（不经过 base64 编码）时使用。
        MVP 阶段所有数据都通过 JSON（base64）传输，此方法备用。

        Args:
            session_id: 目标会话标识符
            data: 原始二进制数据

        Returns:
            True 发送成功，False 连接不存在
        """
        ws = self._connections.get(session_id)
        if ws is None:
            return False

        try:
            await ws.send_bytes(data)
            return True
        except Exception as e:
            logger.error(f"发送二进制数据失败: {session_id} - {e}")
            self.disconnect(session_id)
            return False

    @property
    def active_count(self) -> int:
        """当前活跃连接数。"""
        return len(self._connections)
