"""头像资源加载器。

静态数字人模式只需要完整头像帧，不依赖 Wav2Lip 模型或人脸裁剪帧。
"""

import glob
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np

from src.log import logger


_avatar_cache = {}
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_imgs(img_list, max_workers=8):
    """并发读取头像完整帧，保留文件名排序后的顺序。"""
    frames = [None] * len(img_list)

    def load_one(path):
        try:
            return cv2.imdecode(
                np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR
            )
        except Exception as exc:
            logger.warning(f"读取头像帧失败 {path}: {exc}")
            return None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {
            executor.submit(load_one, path): index
            for index, path in enumerate(img_list)
        }
        for future in as_completed(future_to_index):
            frames[future_to_index[future]] = future.result()

    frames = [frame for frame in frames if frame is not None]
    if not frames:
        raise ValueError("头像目录中没有可读取的完整帧")
    return frames


def load_avatar(avatar_id):
    """只加载首张完整帧，避免静态模式占用数 GB 内存。"""
    if avatar_id in _avatar_cache:
        return _avatar_cache[avatar_id]

    avatar_path = os.path.join(_root_dir, "data", avatar_id)
    full_imgs_path = os.path.join(avatar_path, "full_imgs")
    if not os.path.isdir(full_imgs_path):
        raise FileNotFoundError(f"头像目录不存在: {full_imgs_path}")

    input_img_list = sorted(
        glob.glob(os.path.join(full_imgs_path, "*.[jpJP][pnPN]*[gG]")),
        key=lambda path: int(os.path.splitext(os.path.basename(path))[0]),
    )
    frame_list = read_imgs(input_img_list[:1])
    avatar = (frame_list, [], [])
    _avatar_cache[avatar_id] = avatar
    logger.info(f'静态头像 "{avatar_id}" 已加载，共 {len(frame_list)} 帧')
    return avatar


def preload_avatars(avatar_ids):
    """预加载配置中的头像，减少首次 WebRTC 协商等待。"""
    for avatar_id in avatar_ids:
        try:
            load_avatar(avatar_id)
        except Exception as exc:
            logger.error(f'预加载头像 "{avatar_id}" 失败: {exc}')
