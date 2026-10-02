###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
# 
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  
#       http://www.apache.org/licenses/LICENSE-2.0
# 
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import numpy as np

import subprocess
import os
import time
import json
import cv2
import glob
import resampy

import queue
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import soundfile as sf

import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from av import AudioFrame, VideoFrame
from av.audio.resampler import AudioResampler

from src.ttsreal import TencentTTS, DoubaoTTS, DoubaoTTS3, AzureTTS, BaiduTTS
from src.dashscope_tts import DashScopeTTS
from src.log import logger
from src.audio_monitor import get_monitor

_ENHANCED_FRAME_CACHE = {}


def enqueue_audio_frame_with_backpressure(
        audio_track,
        frame_item,
        loop,
        stop_event,
        wait_timeout=0.25,
):
    """把音频帧可靠地放入 WebRTC 队列，队列满时等待而不是丢帧。

    TTS 生成速度通常高于实时播放速度。旧实现对 ``Queue.put`` 设置很短的
    超时，超时后继续处理下一帧，导致语音中间出现不可恢复的缺口。这里在
    每次超时后取消挂起的协程并重试，直到队列接收帧、连接关闭或渲染线程退出。
    """
    while not stop_event.is_set():
        if getattr(audio_track, 'readyState', 'live') != 'live':
            return False

        pending = asyncio.run_coroutine_threadsafe(
            audio_track._queue.put(frame_item),
            loop,
        )
        try:
            pending.result(timeout=wait_timeout)
            return True
        except FutureTimeoutError:
            pending.cancel()
            continue
        except (RuntimeError, asyncio.CancelledError):
            pending.cancel()
            return False
        except Exception:
            pending.cancel()
            return False

    return False


def pcm_to_webrtc_audio_frame(frame):
    """把 16 kHz 单声道浮点 PCM 转为 aiortc 的 20 ms 音频帧。"""
    samples = np.asarray(frame, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        raise ValueError("音频帧不能为空")

    max_val = np.max(np.abs(samples))
    if max_val > 1.0:
        logger.warning(
            f"Audio clipping detected before conversion: max={max_val:.3f}, applying normalization"
        )
        samples = np.clip(samples, -1.0, 1.0)

    pcm16 = (samples * 32767).astype(np.int16)
    audio_frame = AudioFrame(
        format='s16',
        layout='mono',
        samples=pcm16.shape[0],
    )
    audio_frame.planes[0].update(pcm16.tobytes())
    audio_frame.sample_rate = 16000
    return audio_frame, pcm16


def build_sharpen_kernel(sharpen_strength):
    strength = max(0.0, float(sharpen_strength or 0.0))
    if strength <= 0:
        return None
    return np.array([
        [0.0, -strength, 0.0],
        [-strength, 1.0 + 4.0 * strength, -strength],
        [0.0, -strength, 0.0],
    ], dtype=np.float32)


def enhance_frame_quality_with_kernel(image, kernel):
    if kernel is None:
        return image.copy()
    return cv2.filter2D(image, ddepth=-1, kernel=kernel)


def prepare_enhanced_frame_cache_for_frames(
        frame_list,
        cache_name="avatar",
        sharpen_strength=0.0,
        preload=True
):
    if not preload or not frame_list:
        return None

    kernel = build_sharpen_kernel(sharpen_strength)
    cache_key = (id(frame_list), round(max(0.0, float(sharpen_strength or 0.0)), 4))
    if cache_key in _ENHANCED_FRAME_CACHE:
        logger.info(f'Using pre-enhanced frame cache: {cache_name}')
        return _ENHANCED_FRAME_CACHE[cache_key]

    logger.info(f'Pre-enhancing {len(frame_list)} frames in memory: {cache_name}')
    start_time = time.perf_counter()
    enhanced_frames = [
        np.ascontiguousarray(enhance_frame_quality_with_kernel(frame, kernel))
        for frame in frame_list
    ]

    _ENHANCED_FRAME_CACHE[cache_key] = enhanced_frames
    elapsed = time.perf_counter() - start_time
    memory_mb = sum(frame.nbytes for frame in enhanced_frames) / 1024 / 1024
    logger.info(
        f'Pre-enhanced frame cache ready: {cache_name}, '
        f'{memory_mb:.1f} MB, {elapsed:.2f}s'
    )
    return enhanced_frames


def read_imgs(img_list, max_workers=8):
    """并发读取图像列表，提升加载速度
    
    Args:
        img_list: 图像文件路径列表
        max_workers: 最大并发线程数，默认8
        
    Returns:
        成功读取的图像帧列表（保持原始顺序）
    """

    def load_single_image(img_path):
        """加载单张图像"""
        try:
            # cv2.imread 不支持含中文的路径，改用 imdecode 读取
            frame = cv2.imdecode(np.fromfile(img_path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                logger.warning(f"Failed to load image: {img_path}")
                return None
            return frame
        except Exception as e:
            logger.error(f"Error loading image {img_path}: {e}")
            return None

    frames = [None] * len(img_list)
    failed_count = 0

    logger.info(f'Reading {len(img_list)} images with {max_workers} workers...')
    start_time = time.perf_counter()

    # 使用线程池并发读取图像
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务，保存索引
        future_to_index = {
            executor.submit(load_single_image, img_path): idx
            for idx, img_path in enumerate(img_list)
        }

        # 使用tqdm显示进度
        with tqdm(total=len(img_list), desc="Loading images") as pbar:
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    frame = future.result()
                    if frame is not None:
                        frames[idx] = frame
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error(f"Unexpected error for image {idx}: {e}")
                    failed_count += 1
                pbar.update(1)

    # 过滤掉失败的图像
    frames = [f for f in frames if f is not None]

    elapsed = time.perf_counter() - start_time
    logger.info(f'Loaded {len(frames)} images in {elapsed:.2f}s ({len(frames) / elapsed:.1f} imgs/s)')

    if failed_count > 0:
        logger.warning(f'Failed to load {failed_count} images')

    if len(frames) == 0:
        raise ValueError("No images were successfully loaded")

    return frames


def play_audio(quit_event, queue):
    import pyaudio
    p = pyaudio.PyAudio()
    stream = p.open(
        rate=16000,
        channels=1,
        format=8,
        output=True,
        output_device_index=1,
    )
    stream.start_stream()
    # while queue.qsize() <= 0:
    #     time.sleep(0.1)
    while not quit_event.is_set():
        stream.write(queue.get(block=True))
    stream.close()


class BaseReal:
    def __init__(self, opt):
        self.opt = opt
        self.sample_rate = 16000
        self.chunk = self.sample_rate // opt.fps  # 320 samples per chunk (20ms * 16000 / 1000)
        self.sessionid = self.opt.sessionid

        if opt.tts == "tencent":
            self.tts = TencentTTS(opt, self)
        elif opt.tts == "doubao":
            self.tts = DoubaoTTS(opt, self)
        elif opt.tts == "doubao3":
            self.tts = DoubaoTTS3(opt, self)
        elif opt.tts == "azuretts":
            self.tts = AzureTTS(opt, self)
        elif opt.tts == "baidu":
            self.tts = BaiduTTS(opt, self)
        elif opt.tts == "dashscope":
            self.tts = DashScopeTTS(opt, self)
        else:
            raise ValueError(f"不支持的 TTS 服务类型: {opt.tts}")

        self.speaking = False

        self.recording = False
        self._record_video_pipe = None
        self._record_audio_pipe = None
        self.data_channel = None
        self.data_channel_loop = None
        self.client_audio_track = None
        self.client_audio_task = None
        self.client_asr = None
        self.client_voice_active = False
        self._client_voice_generation = 0
        self._client_voice_stopping_generation = None
        self._audio_play_queue = queue.Queue(maxsize=500)
        self._audio_delivery_thread = None
        self._audio_delivery_stop = threading.Event()
        self._audio_delivery_track = None
        self._audio_delivery_loop = None
        self.width = self.height = 0

        self.curr_state = 0
        self.custom_img_cycle = {}
        self.custom_audio_cycle = {}
        self.custom_audio_index = {}
        self.custom_index = {}
        self.custom_opt = {}
        self.__loadcustom()

        # 初始化音频监控 (可通过环境变量AUDIO_MONITOR=0关闭，=1开启)
        enable_monitor = os.getenv('AUDIO_MONITOR', '0') == '1'
        self.audio_monitor = get_monitor(enable=enable_monitor)

        self.preload_enhanced_frames = bool(int(getattr(opt, 'preload_enhanced_frames', 1) or 0))
        self.enhanced_frame_list_cycle = None
        self.sharpen_strength = max(0.0, float(getattr(opt, 'sharpen_strength', 0.0) or 0.0))
        self._sharpen_kernel = build_sharpen_kernel(self.sharpen_strength)
        if self.sharpen_strength > 0:
            logger.info(f'Frame sharpening enabled, strength={self.sharpen_strength:.2f}')

    def put_msg_txt(self, msg, datainfo: dict = {}):
        self.tts.put_msg_txt(msg, datainfo)

    def set_data_channel(self, data_channel, loop=None):
        self.data_channel = data_channel
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
        self.data_channel_loop = loop

    def set_client_audio_track(self, audio_track):
        """保存客户端音频轨道并启动持续消费任务。

        音频轨道必须持续消费，即使用户没有按下语音输入按钮；否则 WebRTC
        接收缓冲会反压并最终断开。未激活语音会话的帧只会被丢弃，不会送入 ASR。
        """
        self.client_audio_track = audio_track
        logger.info(f"Client audio track set for session {self.sessionid}")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = self.data_channel_loop

        if loop and (self.client_audio_task is None or self.client_audio_task.done()):
            self.data_channel_loop = self.data_channel_loop or loop
            self.client_audio_task = loop.create_task(self._process_client_audio())
            logger.info("Client audio processing task started")

    def start_client_voice(self) -> tuple[bool, str]:
        """开始当前 WebRTC 会话的 DashScope 实时识别。"""
        if self.client_audio_track is None:
            return False, "客户端麦克风音频轨道尚未建立，请重新连接页面"
        if self.client_voice_active:
            return True, ""

        try:
            from src.dashscope_asr import DashScopeASR

            self._client_voice_generation += 1
            generation = self._client_voice_generation
            self._client_voice_stopping_generation = None
            self.client_asr = DashScopeASR(
                on_text=lambda text: self._on_client_asr_result(text, generation),
                on_error=lambda message: self._on_client_asr_error(message, generation),
            )
            self.client_asr.start()
            self.client_voice_active = True
            self.send_data_channel_message({'type': 'voice_status', 'status': 'started'})
            logger.info(f"Client voice ASR started for session {self.sessionid}")
            return True, ""
        except Exception as exc:
            self.client_asr = None
            self.client_voice_active = False
            logger.exception(f"Failed to start client voice ASR: {exc}")
            return False, str(exc)

    def stop_client_voice(self) -> None:
        """停止当前语音识别，避免旧句末结果触发新一轮对话。"""
        self.client_voice_active = False
        stopping_generation = self._client_voice_generation
        self._client_voice_stopping_generation = stopping_generation
        asr_service = self.client_asr
        self.client_asr = None
        if asr_service is not None:
            def stop_service():
                try:
                    asr_service.stop()
                finally:
                    # Recognition.stop() 会等待 SDK 发出最后的句末事件；
                    # 该事件完成后才使本代回调失效，避免松开按钮丢掉最后一句。
                    if self._client_voice_generation == stopping_generation:
                        self._client_voice_generation += 1
                    if self._client_voice_stopping_generation == stopping_generation:
                        self._client_voice_stopping_generation = None

            threading.Thread(
                target=stop_service,
                name=f"asr-stop-{self.sessionid}",
                daemon=True,
            ).start()
        else:
            self._client_voice_generation += 1
            self._client_voice_stopping_generation = None
        self.send_data_channel_message({'type': 'voice_status', 'status': 'stopped'})

    def _on_client_asr_result(self, text: str, generation: int) -> None:
        """处理 ASR 句末文本，并在事件循环中提交一次 LLM。"""
        text = str(text or '').strip()
        accepted_generation = (
            generation == self._client_voice_generation
            or generation == self._client_voice_stopping_generation
        )
        if not text or not accepted_generation:
            return

        self.send_data_channel_message({'type': 'asr', 'text': text})
        loop = self.data_channel_loop
        if loop is None or loop.is_closed():
            logger.error("Cannot submit voice text: session event loop is unavailable")
            return

        def submit_llm():
            accepted = (
                generation == self._client_voice_generation
                or generation == self._client_voice_stopping_generation
            )
            if not accepted:
                return
            from src.llm import llm_response
            loop.run_in_executor(None, llm_response, text, self, self.sessionid)

        loop.call_soon_threadsafe(submit_llm)

    def _on_client_asr_error(self, message: str, generation: int) -> None:
        """向前端报告 ASR 错误并终止当前识别会话。"""
        if (
            generation != self._client_voice_generation
            and generation != self._client_voice_stopping_generation
        ):
            return
        logger.error(message)
        self.client_voice_active = False
        self._client_voice_generation += 1
        self._client_voice_stopping_generation = None
        self.client_asr = None
        self.send_data_channel_message({'type': 'voice_error', 'message': message})

    async def _process_client_audio(self):
        """把任意 WebRTC 音频格式统一成 16 kHz PCM 后送入实时 ASR。"""
        import numpy as np

        logger.info(f"Starting client audio processing for session {self.sessionid}")
        resampler = AudioResampler(format='s16', layout='mono', rate=16000)
        try:
            while True:
                frame = await self.client_audio_track.recv()

                # 未按下语音按钮时仍然消费帧，但不发送到云端。
                if not self.client_voice_active or self.client_asr is None:
                    continue

                output_frames = resampler.resample(frame)
                if not isinstance(output_frames, list):
                    output_frames = [output_frames]
                asr_service = self.client_asr
                for output_frame in output_frames:
                    if not self.client_voice_active or asr_service is not self.client_asr:
                        break
                    pcm = np.asarray(output_frame.to_ndarray()).reshape(-1)
                    if pcm.dtype != np.int16:
                        pcm = np.clip(pcm, -32768, 32767).astype(np.int16)
                    asr_service.send_audio(pcm.astype('<i2', copy=False).tobytes())

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Client audio processing error for session {self.sessionid}: {exc}")
        finally:
            logger.info(f"Client audio processing stopped for session {self.sessionid}")

    def send_data_channel_message(self, message: dict) -> bool:
        if self.data_channel is None or self.data_channel.readyState != 'open':
            return False
        payload = json.dumps(message, ensure_ascii=False)

        def _send():
            if self.data_channel is not None and self.data_channel.readyState == 'open':
                self.data_channel.send(payload)

        try:
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                current_loop = None

            if self.data_channel_loop is not None and self.data_channel_loop is not current_loop:
                self.data_channel_loop.call_soon_threadsafe(_send)
            else:
                _send()
            return True
        except Exception as e:
            logger.error(f"Failed to send data channel message from BaseReal: {e}")
            return False

    def put_audio_frame(self, audio_chunk, datainfo: dict = {}):  # 16khz 20ms pcm
        self.asr.put_audio_frame(audio_chunk, datainfo)
        # 音频播放队列与唇形推理解耦，避免视频推理延迟直接变成听感卡顿。
        self._audio_play_queue.put((audio_chunk, dict(datainfo or {})))

    def start_audio_delivery(self, loop, audio_track, quit_event):
        """启动独立音频发送线程，保证 TTS 音频不等待视频推理。"""
        if audio_track is None or loop is None:
            return

        self._audio_delivery_track = audio_track
        self._audio_delivery_loop = loop
        self._audio_delivery_stop.clear()
        if self._audio_delivery_thread and self._audio_delivery_thread.is_alive():
            return

        self._audio_delivery_thread = threading.Thread(
            target=self._audio_delivery_worker,
            args=(quit_event,),
            name=f"audio-delivery-{self.sessionid}",
            daemon=True,
        )
        self._audio_delivery_thread.start()

    def _audio_delivery_worker(self, quit_event):
        """把 TTS PCM 独立转换并投递到 WebRTC 音频轨道。"""
        while not self._audio_delivery_stop.is_set() and not quit_event.is_set():
            try:
                pcm, eventpoint = self._audio_play_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                audio_frame, pcm16 = pcm_to_webrtc_audio_frame(pcm)
                self.audio_monitor.record_frame_produced()
                delivered = enqueue_audio_frame_with_backpressure(
                    self._audio_delivery_track,
                    (audio_frame, eventpoint),
                    self._audio_delivery_loop,
                    quit_event,
                )
                if not delivered:
                    return
                self.record_audio_data(pcm16)
            finally:
                self._audio_play_queue.task_done()

    def stop_audio_delivery(self):
        """停止独立音频发送线程并清理残留的待播帧。"""
        self._audio_delivery_stop.set()
        thread = self._audio_delivery_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._audio_delivery_thread = None
        self._audio_delivery_track = None
        self._audio_delivery_loop = None
        with self._audio_play_queue.mutex:
            self._audio_play_queue.queue.clear()

    def clear_audio_play_queue(self):
        """丢弃被打断回答的待播音频，避免旧回答继续播放。"""
        with self._audio_play_queue.mutex:
            self._audio_play_queue.queue.clear()

    def put_audio_file(self, filebyte, datainfo: dict = {}):
        input_stream = BytesIO(filebyte)
        stream = self.__create_bytes_stream(input_stream)
        streamlen = stream.shape[0]
        idx = 0
        while streamlen >= self.chunk:  # and self.state==State.RUNNING
            self.put_audio_frame(stream[idx:idx + self.chunk], datainfo)
            streamlen -= self.chunk
            idx += self.chunk

    def __create_bytes_stream(self, byte_stream):
        # byte_stream=BytesIO(buffer)
        stream, sample_rate = sf.read(byte_stream)  # [T*sample_rate,] float64
        logger.info(f'[INFO]put audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.info(f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0] > 0:
            logger.info(f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    def flush_talk(self):
        self.stop_client_voice()
        self.tts.flush_talk()
        self.asr.flush_talk()
        self.clear_audio_play_queue()

    def is_speaking(self) -> bool:
        return self.speaking

    def enhance_frame_quality(self, image):
        return enhance_frame_quality_with_kernel(image, self._sharpen_kernel)

    def prepare_enhanced_frame_cache(self, frame_list, cache_name="avatar"):
        self.enhanced_frame_list_cycle = prepare_enhanced_frame_cache_for_frames(
            frame_list,
            cache_name,
            self.sharpen_strength,
            self.preload_enhanced_frames,
        )

    def __loadcustom(self):
        for item in self.opt.customopt:
            logger.info(item)
            input_img_list = glob.glob(os.path.join(item['imgpath'], '*.[jpJP][pnPN]*[gG]'))
            input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
            self.custom_img_cycle[item['audiotype']] = read_imgs(input_img_list)
            self.custom_audio_cycle[item['audiotype']], sample_rate = sf.read(item['audiopath'], dtype='float32')
            self.custom_audio_index[item['audiotype']] = 0
            self.custom_index[item['audiotype']] = 0
            self.custom_opt[item['audiotype']] = item

    def init_customindex(self):
        self.curr_state = 0
        for key in self.custom_audio_index:
            self.custom_audio_index[key] = 0
        for key in self.custom_index:
            self.custom_index[key] = 0

    def notify(self, eventpoint):
        # logger.debug(f"{eventpoint}") 
        pass

    def start_recording(self):
        """开始录制视频"""
        if self.recording:
            return

        command = ['ffmpeg',
                   '-y', '-an',
                   '-f', 'rawvideo',
                   '-vcodec', 'rawvideo',
                   '-pix_fmt', 'bgr24',  # 像素格式
                   '-s', "{}x{}".format(self.width, self.height),
                   '-r', str(25),
                   '-i', '-',
                   '-pix_fmt', 'yuv420p',
                   '-vcodec', "h264",
                   # '-f' , 'flv',
                   f'temp{self.opt.sessionid}.mp4']
        self._record_video_pipe = subprocess.Popen(command, shell=False, stdin=subprocess.PIPE)

        acommand = ['ffmpeg',
                    '-y', '-vn',
                    '-f', 's16le',
                    # '-acodec','pcm_s16le',
                    '-ac', '1',
                    '-ar', '16000',
                    '-i', '-',
                    '-acodec', 'aac',
                    # '-f' , 'wav',
                    f'temp{self.opt.sessionid}.aac']
        self._record_audio_pipe = subprocess.Popen(acommand, shell=False, stdin=subprocess.PIPE)

        self.recording = True
        # self.recordq_video.queue.clear()
        # self.recordq_audio.queue.clear()
        # self.container = av.open(path, mode="w")

        # process_thread = Thread(target=self.record_frame, args=())
        # process_thread.start()

    def record_video_data(self, image):
        if self.width == 0:
            # print("image.shape:", image.shape)
            self.height, self.width, _ = image.shape
        if self.recording:
            self._record_video_pipe.stdin.write(image.tostring())

    def record_audio_data(self, frame):
        if self.recording:
            self._record_audio_pipe.stdin.write(frame.tostring())

    def stop_recording(self):
        """停止录制视频"""
        if not self.recording:
            return
        self.recording = False
        self._record_video_pipe.stdin.close()  # wait()
        self._record_video_pipe.wait()
        self._record_audio_pipe.stdin.close()
        self._record_audio_pipe.wait()
        cmd_combine_audio = f"ffmpeg -y -i temp{self.opt.sessionid}.aac -i temp{self.opt.sessionid}.mp4 -c:v copy -c:a copy data/record.mp4"
        os.system(cmd_combine_audio)
        # os.remove(output_path)

    def mirror_index(self, size, index):
        # size = len(self.coord_list_cycle)
        turn = index // size
        res = index % size
        if turn % 2 == 0:
            return res
        else:
            return size - res - 1

    def get_audio_stream(self, audiotype):
        idx = self.custom_audio_index[audiotype]
        stream = self.custom_audio_cycle[audiotype][idx:idx + self.chunk]
        self.custom_audio_index[audiotype] += self.chunk
        if self.custom_audio_index[audiotype] >= self.custom_audio_cycle[audiotype].shape[0]:
            self.curr_state = 1  # 当前视频不循环播放，切换到静音状态
        return stream

    def set_custom_state(self, audiotype, reinit=True):
        print('set_custom_state:', audiotype)
        if self.custom_audio_index.get(audiotype) is None:
            return
        self.curr_state = audiotype
        if reinit:
            self.custom_audio_index[audiotype] = 0
            self.custom_index[audiotype] = 0

    def process_frames(self, quit_event, loop=None, audio_track=None, video_track=None):
        enable_transition = False  # 设置为False禁用过渡效果，True启用

        if enable_transition:
            _last_speaking = False
            _transition_start = time.time()
            _transition_duration = 0.1  # 过渡时间
            _last_silent_frame = None  # 静音帧缓存
            _last_speaking_frame = None  # 说话帧缓存

        while not quit_event.is_set():
            try:
                res_frame, idx, audio_frames = self.res_frame_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue

            if enable_transition:
                # 检测状态变化
                current_speaking = not (audio_frames[0][1] != 0 and audio_frames[1][1] != 0)
                if current_speaking != _last_speaking:
                    logger.info(
                        f"状态切换：{'说话' if _last_speaking else '静音'} → {'说话' if current_speaking else '静音'}")
                    _transition_start = time.time()
                _last_speaking = current_speaking

            frame_already_enhanced = False
            if audio_frames[0][1] != 0 and audio_frames[1][1] != 0:  # 全为静音数据，只需要取fullimg
                self.speaking = False
                audiotype = audio_frames[0][1]
                if self.custom_index.get(audiotype) is not None:  # 有自定义视频
                    mirindex = self.mirror_index(len(self.custom_img_cycle[audiotype]), self.custom_index[audiotype])
                    target_frame = self.custom_img_cycle[audiotype][mirindex].copy()
                    self.custom_index[audiotype] += 1
                else:
                    if self.enhanced_frame_list_cycle is not None:
                        target_frame = self.enhanced_frame_list_cycle[idx].copy()
                        frame_already_enhanced = True
                    else:
                        target_frame = self.frame_list_cycle[idx].copy()

                if enable_transition:
                    # 说话→静音过渡
                    if time.time() - _transition_start < _transition_duration and _last_speaking_frame is not None:
                        alpha = min(1.0, (time.time() - _transition_start) / _transition_duration)
                        combine_frame = cv2.addWeighted(_last_speaking_frame, 1 - alpha, target_frame, alpha, 0)
                    else:
                        combine_frame = target_frame
                    # 缓存静音帧
                    _last_silent_frame = combine_frame.copy()
                else:
                    combine_frame = target_frame
            else:
                self.speaking = True
                try:
                    current_frame = self.paste_back_frame(res_frame, idx)
                except Exception as e:
                    logger.warning(f"paste_back_frame error: {e}")
                    continue
                if enable_transition:
                    # 静音→说话过渡
                    if time.time() - _transition_start < _transition_duration and _last_silent_frame is not None:
                        alpha = min(1.0, (time.time() - _transition_start) / _transition_duration)
                        combine_frame = cv2.addWeighted(_last_silent_frame, 1 - alpha, current_frame, alpha, 0)
                    else:
                        combine_frame = current_frame
                    # 缓存说话帧
                    _last_speaking_frame = combine_frame.copy()
                else:
                    combine_frame = current_frame

            # 添加logo：如CCTV5, 默认是“”
            cv2.putText(combine_frame, "", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (128, 128, 128), 1)
            image = combine_frame.copy() if self.speaking or frame_already_enhanced else self.enhance_frame_quality(combine_frame)
            new_frame = VideoFrame.from_ndarray(image, format="bgr24")
            asyncio.run_coroutine_threadsafe(video_track._queue.put((new_frame, None)), loop)
            self.record_video_data(image)
        logger.info('basereal process_frames thread stop')
