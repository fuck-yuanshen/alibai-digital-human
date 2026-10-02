"""DashScope 实时 ASR 适配器的离线测试。"""

from unittest import TestCase
from unittest.mock import Mock, patch

from src.dashscope_asr import DashScopeASR, _RecognitionCallback


class FakeResult:
    def __init__(self, sentence):
        self._sentence = sentence

    def get_sentence(self):
        return self._sentence


class DashScopeASRTests(TestCase):
    def test_only_sentence_end_is_delivered(self):
        received = []
        errors = []
        callback = _RecognitionCallback(received.append, errors.append)

        callback.on_event(FakeResult({'text': '你好', 'sentence_end': False}))
        callback.on_event(FakeResult({'text': '你好世界', 'end_time': 1200}))
        callback.on_event(FakeResult({'text': '你好世界', 'end_time': 1200}))

        self.assertEqual(received, ['你好世界'])
        self.assertEqual(errors, [])

    def test_recognition_lifecycle_and_pcm_forwarding(self):
        with (
            patch('src.dashscope_asr.get_dashscope_api_key', return_value='test-key'),
            patch('src.dashscope_asr.get_dashscope_asr_model', return_value='paraformer-realtime-v2'),
            patch('src.dashscope_asr.get_dashscope_asr_format', return_value='pcm'),
            patch('src.dashscope_asr.get_dashscope_asr_sample_rate', return_value=16000),
            patch('src.dashscope_asr.Recognition') as recognition_type,
        ):
            recognition = recognition_type.return_value
            asr = DashScopeASR(Mock(), Mock())
            asr.start()
            recognition_type.assert_called_once()
            recognition.start.assert_called_once_with()

            self.assertTrue(asr.send_audio(b'\x00\x00' * 320))
            recognition.send_audio_frame.assert_called_once_with(b'\x00\x00' * 320)

            asr.stop()
            recognition.stop.assert_called_once_with()
            self.assertFalse(asr.running)

    def test_missing_key_fails_before_network_call(self):
        with (
            patch('src.dashscope_asr.get_dashscope_api_key', return_value=''),
            patch('src.dashscope_asr.get_dashscope_asr_model', return_value='paraformer-realtime-v2'),
            patch('src.dashscope_asr.get_dashscope_asr_format', return_value='pcm'),
            patch('src.dashscope_asr.get_dashscope_asr_sample_rate', return_value=16000),
        ):
            with self.assertRaisesRegex(ValueError, 'DASHSCOPE_API_KEY'):
                DashScopeASR(Mock())

    def test_masked_key_fails_with_actionable_error(self):
        with (
            patch('src.dashscope_asr.get_dashscope_api_key', return_value='sk-test****masked'),
            patch('src.dashscope_asr.get_dashscope_asr_model', return_value='paraformer-realtime-v2'),
            patch('src.dashscope_asr.get_dashscope_asr_format', return_value='pcm'),
            patch('src.dashscope_asr.get_dashscope_asr_sample_rate', return_value=16000),
        ):
            with self.assertRaisesRegex(ValueError, '脱敏'):
                DashScopeASR(Mock())


if __name__ == '__main__':
    import unittest

    unittest.main()
