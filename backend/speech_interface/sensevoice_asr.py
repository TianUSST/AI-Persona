"""
SenseVoice ASR 实现

基于 FunASR 框架的 SenseVoice 语音识别引擎。
支持中文、英文、日文、韩文、粤语等多语言识别。

技术要点：
- SenseVoiceSmall 模型：阿里达摩院开源，中文识别效果优于 Whisper
- fsmn-vad：语音活动检测，用于检测用户是否说完
- FunASR 的 generate() 是同步方法，需要 asyncio.to_thread() 包装为异步

数据流：
    浏览器 PCM 音频 → base64 解码 → numpy float32 → FunASR → 文字
"""

from __future__ import annotations

import asyncio
import base64
from typing import AsyncIterator

import numpy as np
from loguru import logger

from backend.config.config_loader import AppConfig
from backend.speech_interface.base_asr import ASRResult, BaseASR


class SenseVoiceASR(BaseASR):
    """SenseVoice 语音识别实现。

    使用 FunASR 框架加载 SenseVoiceSmall 模型。
    支持批量转写和 VAD 分段流式转写。

    使用示例：
        asr = SenseVoiceASR()
        await asr.initialize()
        result = await asr.transcribe(audio_bytes)
        print(result.text)
        await asr.shutdown()
    """

    def __init__(self) -> None:
        # FunASR 模型实例（在 initialize 中加载）
        self._model = None
        self._config = AppConfig()

    async def initialize(self) -> None:
        """加载 SenseVoice 模型。

        从 ModelScope 下载模型（首次运行），后续从缓存加载。
        模型加载到 CPU（FunASR 对 XPU 支持需验证，先用 CPU 保证稳定）。
        """
        logger.info("正在加载 SenseVoice ASR 模型...")

        # 读取配置
        model_name = self._config.get(
            "asr.sensevoice.model", "iic/SenseVoiceSmall"
        )
        vad_model = self._config.get(
            "asr.sensevoice.vad_model", "fsmn-vad"
        )
        language = self._config.get(
            "asr.sensevoice.language", "auto"
        )
        use_itn = self._config.get(
            "asr.sensevoice.use_itn", True
        )

        # 在线程中加载模型（避免阻塞事件循环）
        def _load():
            from funasr import AutoModel

            # SenseVoice 模型配置
            model_kwargs = {
                "model": model_name,
                "vad_model": vad_model,         # VAD 语音活动检测
                "vad_kwargs": {"max_single_segment_time": 30000},  # 单段最大30秒
                "trust_remote_code": True,
            }

            # 指定设备（FunASR 支持 device 参数）
            # Intel XPU 兼容性待验证，先用 CPU
            model_kwargs["device"] = "cpu"

            model = AutoModel(**model_kwargs)
            logger.info(f"SenseVoice 模型加载完成: {model_name}")
            return model

        self._model = await asyncio.to_thread(_load)
        logger.info("SenseVoice ASR 就绪")

    async def transcribe(
        self, audio_bytes: bytes, sample_rate: int = 16000
    ) -> ASRResult:
        """转写一段完整的音频。

        Args:
            audio_bytes: 原始 PCM 音频数据（int16 格式，单声道）
            sample_rate: 采样率，默认 16000Hz

        Returns:
            ASRResult 包含识别文字
        """
        if self._model is None:
            raise RuntimeError("ASR 模型未初始化，请先调用 initialize()")

        # 将 bytes 转为 numpy 数组（int16 → float32）
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # 在线程中执行同步推理
        def _infer():
            results = self._model.generate(
                input=audio_array,
                cache={},
                language="auto",    # 自动检测语言
                use_itn=True,       # 数字/日期标准化
                batch_size_s=30,    # 批处理
            )
            return results

        results = await asyncio.to_thread(_infer)

        # 解析结果
        text = ""
        language = None
        if results and len(results) > 0:
            result = results[0]
            text = result.get("text", "")
            # SenseVoice 返回的语言标签格式如 <|zh|>
            raw_lang = result.get("language", "")
            if raw_lang:
                language = raw_lang.strip("<|>")

        logger.debug(f"ASR 识别结果: text='{text}', lang={language}")
        return ASRResult(text=text, language=language, is_final=True)

    async def transcribe_stream(
        self, audio_chunks: AsyncIterator[bytes], sample_rate: int = 16000
    ) -> AsyncIterator[ASRResult]:
        """流式转写：累积音频后分段识别。

        策略：累积音频数据，当检测到静音（VAD）或缓冲区满时进行识别。
        由于 SenseVoice 不原生支持流式，采用"缓冲-识别"模式。

        Args:
            audio_chunks: 异步迭代器，每次 yield 一个 PCM 音频片段
            sample_rate: 采样率

        Yields:
            ASRResult 对象
        """
        if self._model is None:
            raise RuntimeError("ASR 模型未初始化，请先调用 initialize()")

        # 音频缓冲区
        buffer = bytearray()
        # 缓冲区大小阈值（约 2 秒的 16kHz int16 音频）
        buffer_threshold = sample_rate * 2 * 2  # 16bit = 2 bytes/sample, 2 seconds

        async for chunk in audio_chunks:
            buffer.extend(chunk)

            # 缓冲区达到阈值时进行一次识别
            if len(buffer) >= buffer_threshold:
                audio_bytes = bytes(buffer)
                buffer.clear()

                result = await self.transcribe(audio_bytes, sample_rate)
                # 标记为部分结果（后续可能还有更多音频）
                result.is_final = False
                yield result

        # 缓冲区中剩余的音频（最后一段）
        if len(buffer) > 0:
            result = await self.transcribe(bytes(buffer), sample_rate)
            result.is_final = True
            yield result

    @staticmethod
    def decode_audio_base64(audio_base64: str) -> bytes:
        """解码 base64 编码的音频数据。

        前端通过 WebSocket 发送的音频是 base64 编码的 PCM 数据。

        Args:
            audio_base64: base64 编码的字符串

        Returns:
            原始 PCM 字节数据
        """
        return base64.b64decode(audio_base64)

    async def shutdown(self) -> None:
        """释放模型资源。"""
        if self._model is not None:
            # FunASR 没有显式的 shutdown，置空让 GC 回收
            self._model = None
            logger.info("SenseVoice ASR 资源已释放")
