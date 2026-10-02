"""验证流式 LLM 文本按句子排队，并允许下一句提前准备。"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from src import llm


class FakeNerfReal:
    def __init__(self):
        self.sessionid = 123
        self.tts_messages = []
        self.data_messages = []

    def put_msg_txt(self, text, datainfo=None):
        self.tts_messages.append((text, dict(datainfo or {})))

    def send_data_channel_message(self, message):
        self.data_messages.append(dict(message))


class FakeCompletion:
    def __iter__(self):
        for content in ("这是", "一句完整", "的话。", "请连续播报。"):
            yield SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
            )


class LlmTtsBatchingTests(TestCase):
    def test_system_prompt_requires_language_matching(self):
        self.assertIn("user's latest message", llm.SYSTEM_PROMPT)
        self.assertIn('answer entirely in English', llm.SYSTEM_PROMPT)
        self.assertIn('answer entirely in Chinese', llm.SYSTEM_PROMPT)
        self.assertIn('do not translate it into Chinese', llm.SYSTEM_PROMPT)

    def test_streaming_chunks_are_queued_sentence_by_sentence(self):
        parent = FakeNerfReal()
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: FakeCompletion()
                )
            )
        )

        with patch.object(llm, 'get_llm_client', return_value=fake_client):
            llm.llm_response('测试问题', parent, session_id=parent.sessionid)

        self.assertEqual(len(parent.tts_messages), 2)
        self.assertEqual(
            [item[0] for item in parent.tts_messages],
            ['这是一句完整的话。', '请连续播报。'],
        )
        self.assertTrue(all(item[1] == {'skip_llm_datachannel': True} for item in parent.tts_messages))
        self.assertEqual(
            [item['text'] for item in parent.data_messages if item['type'] == 'llm'],
            ['这是一句完整的话。', '请连续播报。'],
        )


if __name__ == '__main__':
    import unittest

    unittest.main()
