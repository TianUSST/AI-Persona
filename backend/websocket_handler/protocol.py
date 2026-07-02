"""
WebSocket 消息协议定义

定义了前端（浏览器）和后端（服务器）之间所有消息的格式。

协议设计原则（参考 OpenAI Realtime API 风格）：
- 所有消息都是 JSON 文本帧（不用二进制帧，调试方便）
- 音频和图片数据用 base64 编码放在 JSON 的 data 字段中
- 每条消息都有 type 字段标识消息类型

消息流向：
    前端 → 后端：session_start / audio_data / audio_end / text_message / session_end
    后端 → 前端：status / asr_partial / asr_final / llm_chunk / llm_done
                / tts_audio / tts_done / avatar_frame / avatar_done
                / error / disclaimer
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class MsgType(str, Enum):
    """WebSocket 消息类型枚举。

    所有消息类型的完整列表，按方向分组：

    【前端 → 后端】
    - SESSION_START: 初始化会话（选择人格）
    - AUDIO_START: 开始录音（前端开始发送音频数据）
    - AUDIO_DATA: 音频数据块（base64 编码的 PCM 音频）
    - AUDIO_END: 录音结束（触发 ASR 最终识别）
    - TEXT_MESSAGE: 直接发送文字（跳过 ASR，用于调试）
    - SESSION_END: 结束会话

    【后端 → 前端】
    - STATUS: 系统状态通知（如 "ready"、"processing"）
    - ASR_PARTIAL: ASR 部分识别结果（可能还会修正）
    - ASR_FINAL: ASR 最终识别结果（确定不会再变）
    - LLM_CHUNK: LLM 流式文本片段
    - LLM_DONE: LLM 生成完毕
    - TTS_AUDIO: TTS 音频数据块（base64 编码的 PCM）
    - TTS_DONE: TTS 合成完毕
    - AVATAR_FRAME: 数字人视频帧（base64 编码的 JPEG）
    - AVATAR_DONE: 数字人生成完毕
    - ERROR: 错误信息
    - DISCLAIMER: AI 身份免责声明
    """

    # ===== 前端 → 后端 =====
    SESSION_START = "session_start"
    AUDIO_START = "audio_start"
    AUDIO_DATA = "audio_data"
    AUDIO_END = "audio_end"
    TEXT_MESSAGE = "text_message"
    SESSION_END = "session_end"

    # ===== 后端 → 前端 =====
    STATUS = "status"
    ASR_PARTIAL = "asr_partial"
    ASR_FINAL = "asr_final"
    LLM_CHUNK = "llm_chunk"
    LLM_DONE = "llm_done"
    TTS_AUDIO = "tts_audio"
    TTS_DONE = "tts_done"
    AVATAR_FRAME = "avatar_frame"
    AVATAR_DONE = "avatar_done"
    ERROR = "error"
    DISCLAIMER = "disclaimer"


class WSMessage(BaseModel):
    """WebSocket 消息的标准格式。

    所有前后端通信都使用此格式，确保一致性。

    Examples:
        # 前端发送音频
        {"type": "audio_data", "data": {"audio": "UklGRiQ..."}}

        # 后端返回 ASR 结果
        {"type": "asr_final", "data": {"text": "你好", "language": "zh"}}

        # 后端返回 LLM 文本块
        {"type": "llm_chunk", "data": {"text": "计算机专业"}}

        # 后端返回 TTS 音频
        {"type": "tts_audio", "data": {"audio": "UklGRiQ...", "sample_rate": 44100}}

        # 后端返回错误
        {"type": "error", "data": {"message": "ASR 模型未加载"}}
    """

    type: MsgType
    data: dict[str, Any] = {}
    session_id: str | None = None
    timestamp_ms: float = 0.0


# ============================================================
# 以下是一些常用消息的便捷构造函数
# 方便在 pipeline.py 中快速创建标准消息
# ============================================================

def make_status(status: str, message: str = "") -> dict[str, Any]:
    """构造状态消息。

    Args:
        status: 状态码，如 "ready"、"processing"、"idle"
        message: 可选的状态描述

    Returns:
        可直接通过 WebSocket 发送的字典
    """
    return {
        "type": MsgType.STATUS,
        "data": {"status": status, "message": message},
    }


def make_asr_partial(text: str) -> dict[str, Any]:
    """构造 ASR 部分结果消息。"""
    return {
        "type": MsgType.ASR_PARTIAL,
        "data": {"text": text, "is_final": False},
    }


def make_asr_final(text: str, language: str | None = None) -> dict[str, Any]:
    """构造 ASR 最终结果消息。"""
    return {
        "type": MsgType.ASR_FINAL,
        "data": {"text": text, "language": language, "is_final": True},
    }


def make_llm_chunk(text: str) -> dict[str, Any]:
    """构造 LLM 文本片段消息。"""
    return {
        "type": MsgType.LLM_CHUNK,
        "data": {"text": text},
    }


def make_llm_done(full_text: str) -> dict[str, Any]:
    """构造 LLM 完成消息（包含完整回答文本）。"""
    return {
        "type": MsgType.LLM_DONE,
        "data": {"text": full_text},
    }


def make_tts_audio(audio_base64: str, sample_rate: int = 44100) -> dict[str, Any]:
    """构造 TTS 音频数据消息。"""
    return {
        "type": MsgType.TTS_AUDIO,
        "data": {"audio": audio_base64, "sample_rate": sample_rate},
    }


def make_tts_done() -> dict[str, Any]:
    """构造 TTS 完成消息。"""
    return {"type": MsgType.TTS_DONE, "data": {}}


def make_avatar_frame(frame_base64: str, timestamp_ms: float = 0.0) -> dict[str, Any]:
    """构造 Avatar 视频帧消息。"""
    return {
        "type": MsgType.AVATAR_FRAME,
        "data": {"frame": frame_base64, "timestamp_ms": timestamp_ms},
    }


def make_avatar_done() -> dict[str, Any]:
    """构造 Avatar 完成消息。"""
    return {"type": MsgType.AVATAR_DONE, "data": {}}


def make_error(message: str, code: str = "unknown") -> dict[str, Any]:
    """构造错误消息。"""
    return {
        "type": MsgType.ERROR,
        "data": {"message": message, "code": code},
    }


def make_disclaimer(text: str) -> dict[str, Any]:
    """构造 AI 身份免责声明消息。"""
    return {
        "type": MsgType.DISCLAIMER,
        "data": {"text": text},
    }
