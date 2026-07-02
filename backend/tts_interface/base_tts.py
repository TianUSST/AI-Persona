"""
TTS（文本转语音）抽象接口

定义了语音合成模块必须提供的功能：
- 完整合成：接收一段文字，返回完整音频
- 流式合成：接收一段文字，逐块返回音频片段（实时播放用）

所有 TTS 引擎（Fish Speech、CosyVoice 等）都必须实现此接口。

数据流向：
    LLM 回答文字 → [BaseTTS] → 语音音频 → 传给 Avatar + 传给前端播放
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class TTSChunk:
    """TTS 输出的一个音频数据块。

    流式合成时，音频被分成多个小块依次返回，前端可以边收边播放，
    用户不需要等全部合成完就能开始听到声音。

    Attributes:
        audio_bytes: 原始 PCM 音频数据（int16 或 float32 格式）
        sample_rate: 采样率（Hz），如 44100
        is_last: 是否为最后一个块（True 表示这段文字的音频已全部返回）
        duration_ms: 本块音频的时长（毫秒），用于前端同步
    """

    audio_bytes: bytes
    sample_rate: int = 44100
    is_last: bool = False
    duration_ms: float = 0.0


class BaseTTS(ABC):
    """TTS 引擎的抽象基类。

    所有语音合成实现（如 FishSpeechTTS）都必须继承此类
    并实现以下 4 个方法。

    使用示例：
        tts = FishSpeechTTS()
        await tts.initialize()
        # 完整合成
        audio = await tts.synthesize("你好，我是张老师")
        # 流式合成
        async for chunk in tts.synthesize_stream("你好，我是张老师"):
            play_audio(chunk.audio_bytes)
        await tts.shutdown()
    """

    @abstractmethod
    async def initialize(self) -> None:
        """加载 TTS 模型并准备合成。

        在应用启动时调用一次，用于：
        - 加载声学模型和声码器
        - 加载声音克隆的参考音频（如有）
        - 预热模型（跑一次空推理）

        Raises:
            RuntimeError: 模型加载失败时抛出
        """
        ...

    @abstractmethod
    async def synthesize(
        self, text: str, voice: str | None = None
    ) -> TTSChunk:
        """将文字合成为完整音频（非流式）。

        等待全部合成完成后一次性返回。
        适用于对实时性要求不高的场景。

        Args:
            text: 要合成的文字
            voice: 可选的声音标识（如参考音频路径、预设音色名），
                   为 None 时使用默认音色

        Returns:
            包含完整音频的 TTSChunk，is_last=True
        """
        ...

    @abstractmethod
    async def synthesize_stream(
        self, text: str, voice: str | None = None
    ) -> AsyncIterator[TTSChunk]:
        """流式合成：边合成边返回音频块。

        这是实时交互的核心方法。合成引擎把文字分成小段，
        每合成一段就立即返回，前端可以马上播放。

        典型的分段策略：
        - 按句子分段（遇到句号/问号/感叹号就返回一块）
        - 按固定时长分段（每 200ms 返回一块）

        Args:
            text: 要合成的文字
            voice: 可选的声音标识

        Yields:
            TTSChunk 对象，最后一块的 is_last=True
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """释放 TTS 模型资源。

        释放 GPU 显存、关闭推理引擎等。
        """
        ...
