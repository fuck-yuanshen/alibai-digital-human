"""DashScope TTS 适配器的离线行为测试。"""

import base64
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import threading
import wave

import numpy as np

from src.dashscope_tts import DashScopeTTS
from src.tts_audio import decode_audio_bytes, compress_long_internal_pauses


class FakeParent:
    def __init__(self):
        self.frames = []
        self.messages = []

    def put_audio_frame(self, frame, event):
        self.frames.append((np.array(frame, copy=True), dict(event)))

    def send_data_channel_message(self, message):
        self.messages.append(dict(message))


def make_wav(sample_rate=24000, channels=2, frame_count=2400):
    time_axis = np.arange(frame_count, dtype=np.float32) / sample_rate
    left = 0.4 * np.sin(2 * np.pi * 440 * time_axis)
    right = 0.2 * np.sin(2 * np.pi * 440 * time_axis)
    samples = np.column_stack((left, right)) if channels == 2 else left[:, None]
    pcm16 = (samples * 32767).astype('<i2')

    output = BytesIO()
    with wave.open(output, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())
    return output.getvalue()


def make_tts(parent=None):
    parent = parent or FakeParent()
    opt = SimpleNamespace(fps=50, REF_FILE='Cherry')
    with (
        patch('src.dashscope_tts.get_dashscope_api_key', return_value='test-key'),
        patch(
            'src.dashscope_tts.get_dashscope_base_url',
            return_value='https://dashscope.aliyuncs.com/api/v1',
        ),
        patch(
            'src.dashscope_tts.get_dashscope_model',
            return_value='qwen3-tts-instruct-flash',
        ),
        patch(
            'src.dashscope_tts.get_dashscope_language_type',
            return_value='Chinese',
        ),
        patch('src.dashscope_tts.get_dashscope_voice', return_value='Cherry'),
        patch(
            'src.dashscope_tts.get_dashscope_instructions',
            return_value='Speak quickly.',
        ),
        patch(
            'src.dashscope_tts.get_dashscope_optimize_instructions',
            return_value=True,
        ),
    ):
        return DashScopeTTS(opt, parent)


class AudioDecodeTests(TestCase):
    def test_decode_downmixes_and_resamples_to_16khz(self):
        pcm = decode_audio_bytes(make_wav(), target_sample_rate=16000)

        self.assertEqual(pcm.dtype, np.float32)
        self.assertEqual(pcm.ndim, 1)
        self.assertEqual(pcm.shape, (1600,))
        self.assertTrue(np.isfinite(pcm).all())
        self.assertLessEqual(float(np.max(np.abs(pcm))), 1.0)

    def test_decode_rejects_invalid_audio(self):
        with self.assertRaisesRegex(ValueError, '无法解析'):
            decode_audio_bytes(b'not-an-audio-file')

    def test_compresses_only_long_internal_pause(self):
        tone = np.full(1600, 0.2, dtype=np.float32)
        long_pause = np.zeros(8000, dtype=np.float32)
        samples = np.concatenate((tone, long_pause, tone))

        compressed = compress_long_internal_pauses(samples, 16000)

        self.assertLess(len(compressed), len(samples) - 5000)
        self.assertGreater(len(compressed), len(samples) - 8000)
        self.assertGreater(float(np.max(compressed[:1600])), 0.1)
        self.assertGreater(float(np.max(compressed[-1600:])), 0.1)


class DashScopeTTSTests(TestCase):
    def test_call_uses_requested_model_voice_and_instructions(self):
        tts = make_tts()
        response = object()
        with patch(
            'src.dashscope_tts.dashscope.MultiModalConversation.call',
            return_value=response,
        ) as call:
            self.assertIs(tts._call_api('你好'), response)

        call.assert_called_once_with(
            model='qwen3-tts-instruct-flash',
            api_key='test-key',
            text='你好',
            voice='Cherry',
            language_type='Chinese',
            instructions='Speak quickly.',
            optimize_instructions=True,
            stream=False,
        )

    def test_plain_qwen_model_does_not_receive_instruction_only_options(self):
        tts = make_tts()
        tts.model = 'qwen3-tts-flash'
        with patch(
            'src.dashscope_tts.dashscope.MultiModalConversation.call',
            return_value=object(),
        ) as call:
            tts._call_api('你好')

        self.assertEqual(
            call.call_args.kwargs,
            {
                'model': 'qwen3-tts-flash',
                'api_key': 'test-key',
                'text': '你好',
                'voice': 'Cherry',
                'language_type': 'Chinese',
                'stream': False,
            },
        )

    def test_cosyvoice_uses_speech_synthesizer_endpoint(self):
        tts = make_tts()
        tts.model = 'cosyvoice-v2'
        tts.voice = 'libai_v2'
        response = Mock()
        response.json.return_value = {
            'output': {'audio': {'url': 'https://example.invalid/libai.wav'}},
        }
        with patch.object(tts.http, 'post', return_value=response) as post:
            result = tts._call_api('举杯邀明月')

        self.assertEqual(result, response.json.return_value)
        response.raise_for_status.assert_called_once_with()
        post.assert_called_once_with(
            'https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer',
            headers={
                'Authorization': 'Bearer test-key',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'cosyvoice-v2',
                'input': {
                    'text': '举杯邀明月',
                    'voice': 'libai_v2',
                    'format': 'wav',
                    'sample_rate': 24000,
                },
            },
            timeout=(5, 30),
        )

    def test_cosyvoice_response_without_status_code_is_accepted(self):
        tts = make_tts()
        response = {
            'output': {'audio': {'data': base64.b64encode(b'wav').decode()}},
        }
        self.assertEqual(tts._extract_audio_bytes(response), b'wav')

    def test_masked_api_key_is_rejected(self):
        parent = FakeParent()
        opt = SimpleNamespace(fps=50, REF_FILE='Cherry')
        with (
            patch('src.dashscope_tts.get_dashscope_api_key', return_value='sk-test****masked'),
            patch('src.dashscope_tts.get_dashscope_base_url', return_value='https://dashscope.aliyuncs.com/api/v1'),
            patch('src.dashscope_tts.get_dashscope_model', return_value='qwen3-tts-flash'),
            patch('src.dashscope_tts.get_dashscope_language_type', return_value='Chinese'),
            patch('src.dashscope_tts.get_dashscope_voice', return_value='Cherry'),
            patch('src.dashscope_tts.get_dashscope_instructions', return_value=''),
            patch('src.dashscope_tts.get_dashscope_optimize_instructions', return_value=True),
        ):
            with self.assertRaisesRegex(ValueError, '脱敏'):
                DashScopeTTS(opt, parent)

    def test_extracts_inline_and_url_audio(self):
        tts = make_tts()
        wav_bytes = make_wav(sample_rate=16000, channels=1, frame_count=320)
        inline_response = {
            'status_code': 200,
            'output': {'audio': {'data': base64.b64encode(wav_bytes).decode()}},
        }
        self.assertEqual(tts._extract_audio_bytes(inline_response), wav_bytes)

        download = Mock()
        download.content = wav_bytes
        download.raise_for_status = Mock()
        tts.http.get = Mock(return_value=download)
        url_response = {
            'status_code': 200,
            'output': {'audio': {'url': 'https://example.invalid/audio.wav'}},
        }
        self.assertEqual(tts._extract_audio_bytes(url_response), wav_bytes)
        tts.http.get.assert_called_once_with(
            'https://example.invalid/audio.wav',
            timeout=(5, 30),
        )

    def test_stream_pcm_preserves_frame_and_event_protocol(self):
        parent = FakeParent()
        tts = make_tts(parent)
        tts._active_generation = tts._generation

        delivered = tts.stream_pcm(
            np.linspace(-0.5, 0.5, 641, dtype=np.float32),
            ('测试', {'source': 'unit-test'}),
        )

        self.assertTrue(delivered)
        self.assertEqual(len(parent.frames), 4)
        self.assertTrue(all(frame.shape == (320,) for frame, _ in parent.frames))
        self.assertEqual(parent.frames[0][1]['status'], 'start')
        self.assertEqual(parent.frames[0][1]['source'], 'unit-test')
        self.assertEqual(parent.frames[1][1], {})
        self.assertEqual(parent.frames[2][1], {})
        self.assertTrue(np.all(parent.frames[2][0][1:] == 0))
        self.assertEqual(parent.frames[3][1]['status'], 'end')
        self.assertTrue(np.all(parent.frames[3][0] == 0))

    def test_interrupt_discards_inflight_audio(self):
        parent = FakeParent()
        tts = make_tts(parent)
        request_started = threading.Event()
        release_request = threading.Event()
        quit_event = threading.Event()
        wav_bytes = make_wav(sample_rate=16000, channels=1, frame_count=320)
        response = {
            'status_code': 200,
            'output': {'audio': {'data': base64.b64encode(wav_bytes).decode()}},
        }

        def delayed_call(_text):
            request_started.set()
            release_request.wait(timeout=2)
            return response

        tts._call_api = delayed_call
        worker = threading.Thread(target=tts.process_tts, args=(quit_event,))
        worker.start()
        tts.put_msg_txt('已经取消的回答')
        self.assertTrue(request_started.wait(timeout=2))
        tts.flush_talk()
        release_request.set()
        quit_event.set()
        worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(parent.frames, [])


if __name__ == '__main__':
    import unittest

    unittest.main()
