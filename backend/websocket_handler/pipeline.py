"""
流水线编排器（MVP 版本）

职责：串联 ASR → Persona/LLM 的完整处理流程。
每个阶段作为独立的异步任务运行，通过消息与前端交互。

MVP 流程（纯文本模式）：
    前端发送音频/文字 → ASR识别 → 张雪峰人格处理 → LLM流式生成 → 前端显示

消息协议（参考 OpenAI 风格 JSON）：
    所有消息都通过 WebSocket JSON 帧传输
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

import numpy as np
from loguru import logger

from backend.persona_interface.base_llm import LLMMessage
from backend.persona_interface.conversation import ConversationManager
from backend.persona_interface.openai_llm import OpenAICompatibleLLM
from backend.persona_interface.zhangxuefeng.zhangxuefeng_persona import (
    ZhangXuefengPersona,
)
from backend.speech_interface.sensevoice_asr import SenseVoiceASR
from backend.websocket_handler.protocol import (
    MsgType,
    make_asr_final,
    make_asr_partial,
    make_disclaimer,
    make_error,
    make_llm_chunk,
    make_llm_done,
    make_status,
)
from backend.websocket_handler.ws_manager import ConnectionManager


class PipelineOrchestrator:
    """流水线编排器。

    管理 ASR 和 LLM 模块的生命周期，处理 WebSocket 消息分发。
    MVP 阶段只实现 ASR → LLM 链路。
    """

    def __init__(self) -> None:
        # 模块实例
        self._asr: SenseVoiceASR | None = None
        self._llm: OpenAICompatibleLLM | None = None
        self._persona: ZhangXuefengPersona | None = None

        # 会话管理
        self._conversation = ConversationManager()

        # 每个 session 的音频缓冲区
        self._audio_buffers: dict[str, bytearray] = {}

    async def initialize(self) -> None:
        """初始化所有模块。

        按顺序加载 ASR → LLM → Persona。
        模型加载可能需要较长时间（首次需要下载）。
        """
        logger.info("=== 开始初始化流水线 ===")
        start = time.time()

        # 1. 初始化 ASR
        self._asr = SenseVoiceASR()
        await self._asr.initialize()

        # 2. 初始化 LLM
        self._llm = OpenAICompatibleLLM()
        await self._llm.initialize()

        # 3. 初始化人格（依赖 LLM 实例）
        self._persona = ZhangXuefengPersona(llm=self._llm)
        await self._persona.initialize()

        elapsed = time.time() - start
        logger.info(f"=== 流水线初始化完成 | 耗时 {elapsed:.1f}s ===")

    async def handle_message(
        self,
        session_id: str,
        data: dict[str, Any],
        conn_manager: ConnectionManager,
    ) -> None:
        """处理一条 WebSocket 消息。

        根据消息类型分发到不同的处理逻辑。

        Args:
            session_id: 会话标识符
            data: 前端发来的 JSON 消息
            conn_manager: WebSocket 连接管理器
        """
        msg_type = data.get("type")
        msg_data = data.get("data", {})

        try:
            if msg_type == MsgType.SESSION_START:
                await self._handle_session_start(session_id, msg_data, conn_manager)

            elif msg_type == MsgType.AUDIO_START:
                await self._handle_audio_start(session_id, conn_manager)

            elif msg_type == MsgType.AUDIO_DATA:
                await self._handle_audio_data(session_id, msg_data, conn_manager)

            elif msg_type == MsgType.AUDIO_END:
                await self._handle_audio_end(session_id, conn_manager)

            elif msg_type == MsgType.TEXT_MESSAGE:
                await self._handle_text_message(session_id, msg_data, conn_manager)

            elif msg_type == MsgType.SESSION_END:
                await self._handle_session_end(session_id, conn_manager)

            else:
                logger.warning(f"未知消息类型: {msg_type}")
                await conn_manager.send_json(
                    session_id, make_error(f"未知消息类型: {msg_type}")
                )

        except Exception as e:
            logger.error(f"处理消息异常: {e}", exc_info=True)
            await conn_manager.send_json(
                session_id, make_error(f"服务器内部错误: {str(e)}")
            )

    # ===== 消息处理函数 =====

    async def _handle_session_start(
        self, session_id: str, data: dict, conn_manager: ConnectionManager
    ) -> None:
        """处理会话初始化。"""
        # 清空旧历史（如果有的话）
        self._conversation.clear(session_id)
        self._audio_buffers[session_id] = bytearray()

        logger.info(f"会话开始: {session_id}")
        await conn_manager.send_json(session_id, make_status("ready", "会话已就绪"))

    async def _handle_audio_start(
        self, session_id: str, conn_manager: ConnectionManager
    ) -> None:
        """处理开始录音信号。"""
        self._audio_buffers[session_id] = bytearray()
        logger.debug(f"开始录音: {session_id}")
        await conn_manager.send_json(session_id, make_status("listening", "正在录音"))

    async def _handle_audio_data(
        self, session_id: str, data: dict, conn_manager: ConnectionManager
    ) -> None:
        """处理音频数据块。

        前端每 100ms 发送一个 base64 编码的 PCM 音频块。
        在缓冲区中累积，等待 audio_end 信号后统一识别。
        """
        audio_base64 = data.get("audio", "")
        if not audio_base64:
            return

        # 解码 base64 音频并累积到缓冲区
        audio_bytes = base64.b64decode(audio_base64)
        buffer = self._audio_buffers.get(session_id)
        if buffer is not None:
            buffer.extend(audio_bytes)

    async def _handle_audio_end(
        self, session_id: str, conn_manager: ConnectionManager
    ) -> None:
        """处理录音结束信号。

        核心流程：音频 → ASR识别 → 发送识别结果 → 调用LLM → 流式返回回答
        """
        buffer = self._audio_buffers.get(session_id)
        if buffer is None or len(buffer) == 0:
            await conn_manager.send_json(
                session_id, make_error("未收到音频数据")
            )
            return

        audio_bytes = bytes(buffer)
        buffer.clear()

        logger.info(f"录音结束，音频大小: {len(audio_bytes)} bytes")

        # === 阶段1：ASR 语音识别 ===
        await conn_manager.send_json(session_id, make_status("processing", "正在识别..."))

        asr_result = await self._asr.transcribe(audio_bytes, sample_rate=16000)

        if not asr_result.text.strip():
            await conn_manager.send_json(session_id, make_asr_final("", "zh"))
            await conn_manager.send_json(
                session_id, make_status("idle", "未识别到有效语音")
            )
            return

        # 发送 ASR 最终结果
        logger.info(f"ASR 识别: '{asr_result.text}'")
        await conn_manager.send_json(
            session_id, make_asr_final(asr_result.text, asr_result.language)
        )

        # === 阶段2：Persona + LLM 生成回答 ===
        await self._generate_and_send_response(
            session_id, asr_result.text, conn_manager
        )

    async def _handle_text_message(
        self, session_id: str, data: dict, conn_manager: ConnectionManager
    ) -> None:
        """处理直接文本输入（跳过 ASR，用于调试）。

        前端可以直接发送文字，不需要经过语音识别。
        """
        text = data.get("text", "").strip()
        if not text:
            await conn_manager.send_json(session_id, make_error("消息内容为空"))
            return

        logger.info(f"收到文字消息: '{text}'")

        # 直接进入 LLM 生成
        await self._generate_and_send_response(session_id, text, conn_manager)

    async def _handle_session_end(
        self, session_id: str, conn_manager: ConnectionManager
    ) -> None:
        """处理会话结束。"""
        self._conversation.clear(session_id)
        self._audio_buffers.pop(session_id, None)
        logger.info(f"会话结束: {session_id}")

    # ===== 核心生成逻辑 =====

    async def _generate_and_send_response(
        self, session_id: str, user_text: str, conn_manager: ConnectionManager
    ) -> None:
        """调用张雪峰人格生成回答并流式发送给前端。

        完整流程：
        1. 将用户消息加入历史
        2. 获取对话历史（不含 system prompt）
        3. 调用人格层流式生成回答
        4. 逐 chunk 发送给前端
        5. 将 AI 回答加入历史

        Args:
            session_id: 会话标识符
            user_text: 用户问题（ASR 识别的文字或直接输入的文字）
            conn_manager: WebSocket 连接管理器
        """
        start_time = time.time()

        # 将用户消息加入历史
        self._conversation.add_message(
            session_id, LLMMessage(role="user", content=user_text)
        )

        # 获取历史（不含 system，由 persona 自行构建）
        history = self._conversation.get_history_without_system(session_id)

        # 发送免责声明（如果是新对话的第一轮）
        if len(history) <= 1:  # 只有刚加入的 user 消息
            disclaimer = self._persona._disclaimer
            if disclaimer:
                await conn_manager.send_json(
                    session_id, make_disclaimer(disclaimer)
                )

        # 流式生成回答
        full_response = ""
        chunk_count = 0
        first_chunk_time = None

        try:
            async for chunk in self._persona.generate_response_stream(
                user_text, history
            ):
                # 记录首 chunk 时间（首 token 延迟）
                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    ttft = (first_chunk_time - start_time) * 1000
                    logger.info(f"首 Token 延迟: {ttft:.0f}ms")

                full_response += chunk
                chunk_count += 1

                # 发送文本 chunk 给前端
                await conn_manager.send_json(session_id, make_llm_chunk(chunk))

            # 发送完成信号
            await conn_manager.send_json(
                session_id, make_llm_done(full_response)
            )

            # 将 AI 回答加入历史
            self._conversation.add_message(
                session_id, LLMMessage(role="assistant", content=full_response)
            )

            # 记录性能指标
            total_time = (time.time() - start_time) * 1000
            logger.info(
                f"回答完成 | 会话={session_id} | chunks={chunk_count} | "
                f"长度={len(full_response)} | 总耗时={total_time:.0f}ms"
            )

        except Exception as e:
            logger.error(f"LLM 生成失败: {e}", exc_info=True)
            await conn_manager.send_json(
                session_id, make_error(f"生成回答失败: {str(e)}")
            )

    async def cleanup_session(self, session_id: str) -> None:
        """清理会话资源。"""
        self._conversation.clear(session_id)
        self._audio_buffers.pop(session_id, None)
        logger.debug(f"会话资源清理: {session_id}")

    async def shutdown(self) -> None:
        """释放所有模块资源。"""
        logger.info("正在关闭流水线...")
        if self._asr:
            await self._asr.shutdown()
        if self._llm:
            await self._llm.shutdown()
        if self._persona:
            await self._persona.shutdown()
        logger.info("流水线已关闭")
