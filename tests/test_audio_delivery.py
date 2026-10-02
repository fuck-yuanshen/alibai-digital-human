"""WebRTC 音频队列背压行为测试。"""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest import TestCase

from av import AudioFrame

from src.basereal import enqueue_audio_frame_with_backpressure, pcm_to_webrtc_audio_frame


class AudioDeliveryTests(TestCase):
    def test_pcm_conversion_creates_16khz_mono_frame(self):
        frame, pcm16 = pcm_to_webrtc_audio_frame([0.0] * 320)

        self.assertIsInstance(frame, AudioFrame)
        self.assertEqual(frame.sample_rate, 16000)
        self.assertEqual(frame.samples, 320)
        self.assertEqual(frame.format.name, 's16')
        self.assertEqual(frame.layout.name, 'mono')
        self.assertEqual(pcm16.dtype.name, 'int16')

    def test_full_queue_waits_and_preserves_frame(self):
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever, daemon=True)
        thread.start()
        stop_event = threading.Event()

        async def scenario():
            queue = asyncio.Queue(maxsize=1)
            await queue.put(('already-buffered', None))
            return SimpleNamespace(_queue=queue, readyState='live')

        track = asyncio.run_coroutine_threadsafe(scenario(), loop).result(timeout=1)

        def consume_later():
            time.sleep(0.08)
            asyncio.run_coroutine_threadsafe(track._queue.get(), loop).result(timeout=1)

        consumer = threading.Thread(target=consume_later, daemon=True)
        consumer.start()
        delivered = enqueue_audio_frame_with_backpressure(
            track,
            ('next-frame', None),
            loop,
            stop_event,
            wait_timeout=0.02,
        )

        self.assertTrue(delivered)
        self.assertEqual(
            asyncio.run_coroutine_threadsafe(track._queue.get(), loop).result(timeout=1),
            ('next-frame', None),
        )
        consumer.join(timeout=1)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())
        loop.close()


if __name__ == '__main__':
    import unittest

    unittest.main()
