"""验证逐句 TTS 的预合成与顺序播放。"""

import threading
import time
from types import SimpleNamespace
from unittest import TestCase

from src.ttsreal import BaseTTS


class FakeParent:
    def put_audio_frame(self, *_args, **_kwargs):
        return None


class PrefetchTTS(BaseTTS):
    def __init__(self):
        super().__init__(SimpleNamespace(fps=50), FakeParent())
        self.playback_started = threading.Event()
        self.second_synthesis_started = threading.Event()
        self.second_synthesis_finished = threading.Event()
        self.played = []

    def synthesize(self, text):
        if text == "第二句":
            self.second_synthesis_started.set()
            # 第二句的准备过程与第一句播放重叠，模拟网络 TTS 延迟。
            self.playback_started.wait(timeout=2)
            self.second_synthesis_finished.set()
        return text

    def stream_pcm(self, pcm_stream, msg):
        text, _datainfo = msg
        self.played.append(text)
        if text == "第一句":
            self.playback_started.set()
            if not self.second_synthesis_finished.wait(timeout=2):
                raise AssertionError("第二句没有在第一句播放期间完成预合成")
        return True


class TTSPreflightTests(TestCase):
    def test_next_sentence_is_prepared_while_previous_sentence_plays(self):
        tts = PrefetchTTS()
        quit_event = threading.Event()
        tts.render(quit_event)
        tts.put_msg_txt("第一句")
        tts.put_msg_txt("第二句")

        deadline = time.monotonic() + 3
        while len(tts.played) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)

        quit_event.set()
        self.assertEqual(tts.played, ["第一句", "第二句"])
        self.assertTrue(tts.second_synthesis_started.is_set())
        self.assertTrue(tts.second_synthesis_finished.is_set())


if __name__ == "__main__":
    import unittest

    unittest.main()
