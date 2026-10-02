"""静态头像数字人渲染器。

视频轨道始终重复一张完整头像帧，因此语音合成不会触发嘴部或人脸区域变化。
音频、ASR、LLM 和 WebRTC 会话管理仍复用 BaseReal。
"""

import asyncio
import time
from threading import Event

from av import VideoFrame

from src.basereal import BaseReal
from src.log import logger


class StaticASR:
    """静态模式下的占位 ASR，避免音频帧进入唇形特征队列。"""

    def put_audio_frame(self, *_args, **_kwargs):
        return None

    def flush_talk(self):
        return None


class StaticAvatarReal(BaseReal):
    """使用固定头像帧输出视频、使用真实 TTS 输出音频。"""

    def __init__(self, opt, avatar):
        super().__init__(opt)
        self.frame_list_cycle = avatar[0]
        if not self.frame_list_cycle:
            raise ValueError("静态头像至少需要一张完整帧")
        self.asr = StaticASR()
        self.static_frame = self.enhance_frame_quality(self.frame_list_cycle[0])

    def _enqueue_video_frame(self, loop, video_track):
        frame = VideoFrame.from_ndarray(self.static_frame.copy(), format="bgr24")
        future = asyncio.run_coroutine_threadsafe(
            video_track._queue.put((frame, None)), loop
        )
        future.result(timeout=2)
        self.record_video_data(self.static_frame)

    def render(self, quit_event, loop=None, audio_track=None, video_track=None):
        if loop is None or audio_track is None or video_track is None:
            logger.error("静态数字人渲染缺少 WebRTC 轨道")
            return

        self.init_customindex()
        self.start_audio_delivery(loop, audio_track, quit_event)
        self.tts.render(quit_event)
        next_frame_at = time.monotonic()
        try:
            while not quit_event.is_set():
                self._enqueue_video_frame(loop, video_track)
                next_frame_at += 0.04
                delay = next_frame_at - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_frame_at = time.monotonic()
        except (asyncio.CancelledError, RuntimeError, TimeoutError) as exc:
            if not quit_event.is_set():
                logger.warning(f"静态视频轨道停止: {exc}")
        finally:
            self.stop_audio_delivery()
            logger.info("static avatar render thread stop")

