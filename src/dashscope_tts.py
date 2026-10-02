"""DashScope Qwen-TTS/CosyVoice 适配器。"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from http import HTTPStatus
from urllib.parse import urlparse

import dashscope
import requests

from src.config import (
    get_dashscope_api_key,
    get_dashscope_base_url,
    get_dashscope_instructions,
    get_dashscope_language_type,
    get_dashscope_model,
    get_dashscope_optimize_instructions,
    get_dashscope_voice,
)
from src.log import logger
from src.tts_audio import decode_audio_bytes
from src.ttsreal import BaseTTS


def _read_field(value, name: str, default=None):
    """同时兼容 DashScope SDK 的对象响应和字典响应。"""
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


class DashScopeTTS(BaseTTS):
    """调用 DashScope 语音模型并转换为数字人的 PCM 帧。"""

    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.api_key = get_dashscope_api_key()
        self.base_url = get_dashscope_base_url()
        self.model = get_dashscope_model()
        self.voice = str(getattr(opt, "REF_FILE", "") or get_dashscope_voice())
        self.language_type = get_dashscope_language_type()
        self.instructions = get_dashscope_instructions()
        self.optimize_instructions = get_dashscope_optimize_instructions()
        self.http = requests.Session()

        if not self.api_key:
            raise ValueError("DashScopeTTS 需要配置 DASHSCOPE_API_KEY")
        if "*" in self.api_key:
            raise ValueError("DASHSCOPE_API_KEY 看起来是脱敏值，请配置完整密钥")

    def _call_api(self, text: str):
        """按模型调用官方 Qwen-TTS 或 CosyVoice 非流式接口。"""
        if self.model.startswith("cosyvoice-"):
            return self._call_cosyvoice(text)

        dashscope.base_http_api_url = self.base_url
        request = {
            "model": self.model,
            "api_key": self.api_key,
            "text": text,
            "voice": self.voice,
            "language_type": self.language_type,
            "stream": False,
        }
        # instructions/optimize_instructions 仅适用于 Qwen3-TTS-Instruct-Flash。
        if self.model.startswith("qwen3-tts-instruct-") and self.instructions:
            request["instructions"] = self.instructions
            request["optimize_instructions"] = self.optimize_instructions
        return dashscope.MultiModalConversation.call(**request)

    def _call_cosyvoice(self, text: str):
        """调用 CosyVoice 的 SpeechSynthesizer HTTP 接口。"""
        endpoint = f"{self.base_url.rstrip('/')}/services/audio/tts/SpeechSynthesizer"
        payload = {
            "model": self.model,
            "input": {
                "text": text,
                "voice": self.voice,
                "format": "wav",
                "sample_rate": 24000,
            },
        }
        response = self.http.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=(5, 30),
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text[:500]
            raise RuntimeError(f"CosyVoice TTS 请求失败: {detail}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("CosyVoice TTS 返回了无效 JSON") from exc

    @staticmethod
    def _decode_inline_audio(data) -> bytes:
        if isinstance(data, bytes):
            return data
        if not isinstance(data, str) or not data.strip():
            raise ValueError("DashScope 返回了无效的内嵌音频")

        encoded = data.strip()
        if encoded.startswith("data:"):
            if "," not in encoded:
                raise ValueError("DashScope 返回的音频 data URL 无效")
            encoded = encoded.split(",", 1)[1]
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("DashScope 返回的音频不是有效 Base64") from exc

    def _download_audio(self, url: str) -> bytes:
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("DashScope 返回了无效的音频 URL")

        response = self.http.get(url, timeout=(5, 30))
        response.raise_for_status()
        if not response.content:
            raise ValueError("DashScope 音频下载结果为空")
        return response.content

    def _extract_audio_bytes(self, response) -> bytes:
        status_code = _read_field(
            response,
            "status_code",
            HTTPStatus.OK if isinstance(response, Mapping) else None,
        )
        if status_code != HTTPStatus.OK:
            code = _read_field(response, "code", "unknown_error")
            message = _read_field(response, "message", "unknown error")
            request_id = _read_field(response, "request_id", "unknown")
            raise RuntimeError(
                f"DashScope TTS 请求失败: code={code}, message={message}, "
                f"request_id={request_id}"
            )

        output = _read_field(response, "output")
        audio = _read_field(output, "audio")
        if audio is None:
            raise RuntimeError("DashScope TTS 响应中缺少 output.audio")

        inline_data = _read_field(audio, "data")
        if inline_data:
            return self._decode_inline_audio(inline_data)

        audio_url = _read_field(audio, "url")
        if not audio_url:
            raise RuntimeError("DashScope TTS 响应中缺少音频 data 或 url")
        return self._download_audio(str(audio_url))

    def synthesize(self, text: str):
        """合成文本并返回 16 kHz 单声道 float32 PCM。"""
        response = self._call_api(text)
        if not self.is_current_request_active():
            return None
        audio_bytes = self._extract_audio_bytes(response)
        if not self.is_current_request_active():
            return None
        return decode_audio_bytes(
            audio_bytes,
            self.sample_rate,
            compress_internal_pauses=self.model.startswith("cosyvoice-"),
        )

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, _ = msg
        try:
            pcm_stream = self.synthesize(text)
            if pcm_stream is not None:
                self.stream_pcm(pcm_stream, msg)
        except Exception as exc:
            logger.exception(f"DashScopeTTS txt_to_audio error: {exc}")
            self.notify_tts_error("DashScope TTS生成失败，请检查模型、音色和API Key配置")
