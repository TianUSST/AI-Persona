"""
Avatar（数字人）抽象接口

定义了数字人驱动模块必须提供的功能：
- 接收音频数据，生成与语音同步的口型视频帧
- 支持流式处理：音频边到边生成视频帧

所有 Avatar 引擎（LivePortrait、Hallo、Wav2Lip 等）都必须实现此接口。

数据流向：
    TTS 音频 → [BaseAvatar] → 视频帧 → 传给前端显示

注意：LivePortrait 本身是视频驱动（需要一个驱动视频来驱动静态图片），
不是原生音频驱动。实现时可能需要：
- 方案 A：用 Hallo/Hallo2（音频直接驱动）
- 方案 B：用 Wav2Lip 做口型同步
- 方案 C：音频 → 面部关键点 → LivePortrait 驱动
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

from backend.tts_interface.base_tts import TTSChunk


@dataclass
class VideoFrame:
    """一帧视频画面。

    Avatar 生成的每一帧视频都封装为 VideoFrame，
    前端收到后直接渲染到 Canvas 或 Video 元素上。

    Attributes:
        frame_bytes: 编码后的图片数据（通常为 JPEG 格式，体积小适合网络传输）
        format: 图片格式，"jpeg" / "png" / "raw_rgb"
        width: 画面宽度（像素）
        height: 画面高度（像素）
        timestamp_ms: 该帧的呈现时间戳（毫秒），用于音视频同步
        audio_chunk: 可选的配套音频块（音视频打包在一起发送时使用）
    """

    frame_bytes: bytes
    format: str = "jpeg"
    width: int = 512
    height: int = 512
    timestamp_ms: float = 0.0
    audio_chunk: TTSChunk | None = None


class BaseAvatar(ABC):
    """Avatar 引擎的抽象基类。

    所有数字人实现（如 LivePortraitAvatar）都必须继承此类
    并实现以下 5 个方法。

    使用示例：
        avatar = LivePortraitAvatar()
        await avatar.initialize()
        await avatar.set_source_image("assets/avatar.jpg")
        # 逐块生成视频帧
        async for frame in avatar.generate_frames_stream(audio_stream):
            send_to_client(frame)
        await avatar.shutdown()
    """

    @abstractmethod
    async def initialize(self) -> None:
        """加载 Avatar 模型并准备推理。

        在应用启动时调用一次，用于：
        - 加载人脸检测/关键点模型
        - 加载驱动模型（LivePortrait/Hallo 等）
        - 加载默认的数字人形象图片

        Raises:
            RuntimeError: 模型加载失败时抛出
        """
        ...

    @abstractmethod
    async def set_source_image(self, image_path: str) -> None:
        """设置或更换数字人的静态形象图片。

        这是数字人的"底图"——一张正面人脸照片，
        模型会根据音频驱动这张图片的口型和表情。

        Args:
            image_path: 图片文件路径（jpg/png）
        """
        ...

    @abstractmethod
    async def generate_frames(
        self, audio_chunk: TTSChunk
    ) -> list[VideoFrame]:
        """为一个音频块生成对应的视频帧。

        非流式方式：接收一个音频块，返回该音频对应的所有视频帧。
        适用于简单的同步处理。

        Args:
            audio_chunk: TTS 输出的音频数据块

        Returns:
            该音频对应的视频帧列表（按时间顺序）
        """
        ...

    @abstractmethod
    async def generate_frames_stream(
        self, audio_stream: AsyncIterator[TTSChunk]
    ) -> AsyncIterator[VideoFrame]:
        """流式生成视频帧：音频边到边出帧。

        这是实时交互的核心方法。接收 TTS 的音频流，
        每收到一个音频块就立即生成对应的视频帧并返回。

        前端收到帧后可以立即渲染，用户看到的画面与语音保持同步。

        Args:
            audio_stream: TTS 输出的音频流

        Yields:
            VideoFrame 对象，每帧附带时间戳用于同步
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """释放 Avatar 模型资源。

        释放 GPU 显存、关闭推理引擎等。
        """
        ...
