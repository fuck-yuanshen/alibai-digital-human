"""TTS 音频容器解码和项目播放格式归一化。"""

from io import BytesIO

import numpy as np
import resampy
import soundfile as sf


TARGET_SAMPLE_RATE = 16000


def compress_long_internal_pauses(
    samples: np.ndarray,
    sample_rate: int,
    threshold_db: float = -42.0,
    max_pause_seconds: float = 0.16,
) -> np.ndarray:
    """压缩语音中异常过长的内部静音，保留自然短停顿。

    部分非实时 TTS 音频会在词语之间插入 300~500 ms 的近零振幅区间。
    这些区间不是网络丢包，而是音频内容本身；保留过长时会产生明显的
    “说一个词、停一下、再说下一个词”的听感。检测使用 10 ms RMS 窗口，
    只处理位于语音中间且超过上限的静音段，不裁剪开头和结尾。
    """
    pcm = np.asarray(samples, dtype=np.float32).reshape(-1)
    if pcm.size == 0 or sample_rate <= 0 or max_pause_seconds <= 0:
        return np.ascontiguousarray(pcm, dtype=np.float32)

    window = max(1, int(round(sample_rate * 0.01)))
    frame_count = (pcm.size + window - 1) // window
    padded = np.pad(pcm, (0, frame_count * window - pcm.size))
    frames = padded.reshape(frame_count, window)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    quiet = rms < (10.0 ** (threshold_db / 20.0))

    max_quiet_frames = max(1, int(round(max_pause_seconds / 0.01)))
    output_parts = []
    start = 0
    frame_index = 0
    while frame_index < frame_count:
        if not quiet[frame_index]:
            frame_index += 1
            continue

        quiet_start = frame_index
        while frame_index < frame_count and quiet[frame_index]:
            frame_index += 1
        quiet_end = frame_index

        # 句首/句尾静音保留，避免改变播放器起止时序。
        if quiet_start == 0 or quiet_end == frame_count:
            continue

        quiet_length = quiet_end - quiet_start
        if quiet_length <= max_quiet_frames:
            continue

        keep_left = max_quiet_frames // 2
        keep_right = max_quiet_frames - keep_left
        cut_start = quiet_start * window + keep_left * window
        cut_end = quiet_end * window - keep_right * window
        cut_start = min(max(cut_start, start), pcm.size)
        cut_end = min(max(cut_end, cut_start), pcm.size)

        output_parts.append(pcm[start:cut_start])
        start = cut_end

    output_parts.append(pcm[start:])
    if len(output_parts) == 1:
        return np.ascontiguousarray(pcm, dtype=np.float32)
    return np.ascontiguousarray(np.concatenate(output_parts), dtype=np.float32)


def decode_audio_bytes(
    audio_bytes: bytes,
    target_sample_rate: int = TARGET_SAMPLE_RATE,
    compress_internal_pauses: bool = False,
) -> np.ndarray:
    """把常见音频容器转换为指定采样率的单声道 float32 PCM。"""
    if not audio_bytes:
        raise ValueError("TTS 返回了空音频数据")

    try:
        samples, sample_rate = sf.read(
            BytesIO(audio_bytes),
            dtype="float32",
            always_2d=True,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("无法解析 TTS 返回的音频格式") from exc

    if samples.size == 0 or sample_rate <= 0:
        raise ValueError("TTS 返回的音频没有有效采样")

    mono = samples.mean(axis=1, dtype=np.float32)
    if sample_rate != target_sample_rate:
        mono = resampy.resample(mono, sample_rate, target_sample_rate)

    mono = np.nan_to_num(mono, nan=0.0, posinf=1.0, neginf=-1.0)
    mono = np.ascontiguousarray(np.clip(mono, -1.0, 1.0), dtype=np.float32)
    if compress_internal_pauses:
        mono = compress_long_internal_pauses(mono, target_sample_rate)
    return mono
