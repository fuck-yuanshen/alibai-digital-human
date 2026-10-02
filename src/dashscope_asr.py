"""DashScope 实时语音识别适配器。

该模块只负责把 PCM 音频送入 DashScope Recognition，并在一句话结束时
通过回调交付最终文本。WebRTC、会话生命周期和 LLM 调用由 BaseReal 管理。
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

from src.config import (
    get_dashscope_api_key,
    get_dashscope_asr_format,
    get_dashscope_asr_model,
    get_dashscope_asr_sample_rate,
)
from src.log import logger


class _RecognitionCallback(RecognitionCallback):
    """把 SDK 回调转换成稳定的最终句子回调。"""

    def __init__(
        self,
        on_text: Callable[[str], None],
        on_error: Callable[[str], None],
    ):
        self.on_text_callback = on_text
        self.on_error_callback = on_error
        self._last_final_key = None

    def on_open(self) -> None:
        logger.info("DashScope ASR connection opened")

    def on_complete(self) -> None:
        logger.info("DashScope ASR recognition completed")

    def on_close(self) -> None:
        logger.info("DashScope ASR connection closed")

    def on_error(self, result: RecognitionResult) -> None:
        message = getattr(result, "message", None) or getattr(result, "code", None) or "unknown error"
        self.on_error_callback(f"DashScope ASR error: {message}")

    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence()
        if isinstance(sentence, list):
            sentences = sentence
        elif sentence:
            sentences = [sentence]
        else:
            sentences = []

        for item in sentences:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue

            # realtime-v2 的句末事件通常带 end_time；部分版本使用
            # sentence_end=true。只交付句末，避免同一句话重复触发 LLM。
            sentence_end = bool(item.get("sentence_end")) or item.get("end_time") is not None
            if sentence_end:
                final_key = (text, item.get("end_time"))
                if final_key == self._last_final_key:
                    continue
                self._last_final_key = final_key
                self.on_text_callback(text)


class DashScopeASR:
    """一个 WebRTC 会话对应一个可反复启动/停止的 DashScope ASR。"""

    def __init__(
        self,
        on_text: Callable[[str], None],
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = get_dashscope_api_key()
        self.model = get_dashscope_asr_model()
        self.audio_format = get_dashscope_asr_format()
        self.sample_rate = get_dashscope_asr_sample_rate()
        self.on_text = on_text
        self.on_error = on_error or (lambda message: logger.error(message))
        self._recognition: Optional[Recognition] = None
        self._lock = threading.RLock()
        self._running = False

        if not self.api_key:
            raise ValueError("DashScope ASR 需要配置 DASHSCOPE_API_KEY")
        if "*" in self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 看起来是脱敏值，请配置完整密钥")

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def start(self) -> None:
        """启动一次实时识别连接。"""
        with self._lock:
            if self._running:
                return

            callback = _RecognitionCallback(self.on_text, self.on_error)
            recognition = Recognition(
                model=self.model,
                callback=callback,
                format=self.audio_format,
                sample_rate=self.sample_rate,
                api_key=self.api_key,
            )
            recognition.start()
            self._recognition = recognition
            self._running = True

    def send_audio(self, pcm_bytes: bytes) -> bool:
        """发送 16-bit little-endian 单声道 PCM 音频。"""
        if not pcm_bytes:
            return False
        with self._lock:
            recognition = self._recognition
            if not self._running or recognition is None:
                return False
            try:
                recognition.send_audio_frame(pcm_bytes)
                return True
            except Exception as exc:
                self._running = False
                self.on_error(f"DashScope ASR 发送音频失败: {exc}")
                return False

    def stop(self) -> None:
        """停止识别并释放 SDK 工作线程。"""
        with self._lock:
            recognition = self._recognition
            self._recognition = None
            was_running = self._running
            self._running = False

        if recognition is not None and was_running:
            try:
                recognition.stop()
            except Exception as exc:
                logger.warning(f"DashScope ASR stop failed: {exc}")
