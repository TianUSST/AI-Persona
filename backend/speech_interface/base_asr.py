"""
ASR（自动语音识别）抽象接口

定义了语音识别模块必须提供的功能：
- 完整音频转写：接收一段完整音频，返回识别文字
- 流式音频转写：持续接收音频片段，边接收边返回部分识别结果

所有 ASR 引擎（SenseVoice、Whisper 等）都必须实现此接口。

数据流向：
    麦克风音频 → [BaseASR] → 识别文字 → 传给 Persona/LLM
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class ASRResult:
    """语音识别结果。

    Attributes:
        text: 识别出的文字内容
        language: 识别出的语言代码（如 "zh"、"en"），可能为 None
        confidence: 识别置信度（0.0 ~ 1.0），部分引擎可能不提供
        is_final: 是否为最终结果（False 表示中间部分结果，还会继续更新）
        start_ms: 该段语音在原始音频中的起始时间（毫秒）
        end_ms: 该段语音在原始音频中的结束时间（毫秒）
    """

    text: str
    language: str | None = None
    confidence: float = 0.0
    is_final: bool = True
    start_ms: int = 0
    end_ms: int = 0


class BaseASR(ABC):
    """ASR 引擎的抽象基类。

    所有语音识别实现（如 SenseVoiceASR）都必须继承此类
    并实现以下 4 个方法。

    使用示例：
        asr = SenseVoiceASR()       # 创建具体实现
        await asr.initialize()      # 加载模型
        result = await asr.transcribe(audio_bytes)  # 识别
        await asr.shutdown()        # 释放资源
    """

    @abstractmethod
    async def initialize(self) -> None:
        """加载模型并准备推理。

        在应用启动时调用一次，用于：
        - 下载/加载模型权重到内存/GPU
        - 初始化 VAD（语音活动检测）等辅助组件

        Raises:
            RuntimeError: 模型加载失败时抛出
        """
        ...

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> ASRResult:
        """转写一段完整的音频。

        适用于：用户说完话后，一次性发送整段音频进行识别。

        Args:
            audio_bytes: 原始 PCM 音频数据（int16 格式，单声道）
            sample_rate: 采样率（Hz），默认 16000

        Returns:
            ASRResult，is_final=True 的最终识别结果
        """
        ...

    @abstractmethod
    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes], sample_rate: int = 16000
    ) -> AsyncIterator[ASRResult]:
        """流式转写：持续接收音频片段，边接收边返回识别结果。

        适用于：实时场景，用户一边说话一边返回部分识别文字。

        Args:
            audio_chunks: 异步迭代器，每次 yield 一个音频片段（PCM int16）
            sample_rate: 采样率（Hz），默认 16000

        Yields:
            ASRResult 对象：
            - is_final=False 的中间结果（部分识别，后续可能修正）
            - is_final=True 的最终结果（该段识别已确定）
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """释放模型资源。

        在应用关闭时调用，释放 GPU 显存等资源。
        """
        ...
