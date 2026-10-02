# -*- coding: utf-8 -*-
"""
@author:XuMing(xuming624@qq.com)
@description: config module
"""
import os

import yaml
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_local_env(env_path: str = None) -> None:
    """加载项目本机密钥；系统环境变量具有更高优先级。"""
    path = Path(env_path) if env_path else PROJECT_ROOT / ".env"
    if not path.exists():
        return

    with open(path, 'r', encoding='utf-8') as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


def load_config(config_path: str = None) -> dict:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径，默认为项目根目录下的 config.yml
        
    Returns:
        配置字典
    """
    if config_path is None:
        # 获取项目根目录（src 的父目录）
        current_dir = Path(__file__).parent
        config_path = current_dir.parent / "config.yml"
    
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config or {}


# 全局配置对象
_config = None


def get_config() -> dict:
    """
    获取配置（单例模式）
    
    Returns:
        配置字典
    """
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_llm_config() -> dict:
    """
    获取 LLM 配置
    
    Returns:
        LLM 配置字典
    """
    config = get_config()
    return config.get('LLM', {})


def get_tts_config() -> dict:
    """
    获取 TTS 配置
    
    Returns:
        TTS 配置字典
    """
    config = get_config()
    return config.get('TTS', {})


# 便捷函数
def get_llm_api_key() -> str:
    """从配置指定的环境变量读取 LLM API Key。"""
    load_local_env()
    return os.environ.get(get_llm_api_key_env(), '')


def get_llm_api_key_env() -> str:
    """获取保存 LLM API Key 的环境变量名。"""
    return get_llm_config().get('LLM_API_KEY_ENV', 'DEEPSEEK_API_KEY')


def get_llm_base_url() -> str:
    """获取 LLM Base URL"""
    return get_llm_config().get('LLM_BASE_URL', '')


def get_llm_model_name() -> str:
    """获取 LLM 模型名称"""
    return get_llm_config().get('LLM_MODEL_NAME', 'deepseek-flash')


def get_llm_reasoning_effort() -> str:
    """获取 DeepSeek 推理强度配置。"""
    return get_llm_config().get('LLM_REASONING_EFFORT', 'high')


def get_llm_thinking_enabled() -> bool:
    """获取是否启用 DeepSeek 思考模式。"""
    value = get_llm_config().get('LLM_THINKING_ENABLED', True)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_doubao_appid() -> str:
    """获取豆包 TTS AppID"""
    return get_tts_config().get('DOUBAO_APPID', '')


def get_doubao_token() -> str:
    """获取豆包 TTS Token"""
    return get_tts_config().get('DOUBAO_TOKEN', '')

def get_doubao_voice() -> str:
    """获取豆包 TTS Voice"""
    return get_tts_config().get('DOUBAO_VOICE', 'zh_female_meilinvyou_saturn_bigtts')

def get_baidu_api_key() -> str:
    """获取百度 TTS API Key"""
    return get_tts_config().get('BAIDU_API_KEY', '')

def get_baidu_secret_key() -> str:
    """获取百度 TTS Secret Key"""
    return get_tts_config().get('BAIDU_SECRET_KEY', '')


def get_dashscope_api_key() -> str:
    """从配置指定的环境变量读取 DashScope API Key。"""
    load_local_env()
    env_name = get_tts_config().get('DASHSCOPE_API_KEY_ENV', 'DASHSCOPE_API_KEY')
    return os.environ.get(env_name, '')


def get_dashscope_base_url() -> str:
    """获取 DashScope HTTP API 地址。"""
    return get_tts_config().get(
        'DASHSCOPE_BASE_URL',
        'https://dashscope.aliyuncs.com/api/v1',
    )


def get_dashscope_model() -> str:
    """获取 DashScope TTS 模型名称。"""
    return get_tts_config().get('DASHSCOPE_MODEL', 'qwen3-tts-instruct-flash')


def get_dashscope_voice() -> str:
    """获取 DashScope TTS 默认音色。"""
    return get_tts_config().get('DASHSCOPE_VOICE', 'Cherry')


def get_dashscope_language_type() -> str:
    """获取 Qwen-TTS 的文本语言类型。"""
    return get_tts_config().get('DASHSCOPE_LANGUAGE_TYPE', 'Chinese')


def get_dashscope_instructions() -> str:
    """获取 DashScope TTS 音色指令。"""
    return get_tts_config().get('DASHSCOPE_INSTRUCTIONS', '')


def get_dashscope_optimize_instructions() -> bool:
    """获取是否让 DashScope 自动优化音色指令。"""
    value = get_tts_config().get('DASHSCOPE_OPTIMIZE_INSTRUCTIONS', True)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def get_asr_config() -> dict:
    """获取实时语音识别配置。"""
    config = get_config()
    return config.get('ASR', {})


def get_dashscope_asr_model() -> str:
    """获取 DashScope 实时 ASR 模型。"""
    return get_asr_config().get('DASHSCOPE_ASR_MODEL', 'paraformer-realtime-v2')


def get_dashscope_asr_format() -> str:
    """获取 DashScope 实时 ASR 输入格式。"""
    return get_asr_config().get('DASHSCOPE_ASR_FORMAT', 'pcm')


def get_dashscope_asr_sample_rate() -> int:
    """获取 DashScope 实时 ASR 采样率。"""
    return int(get_asr_config().get('DASHSCOPE_ASR_SAMPLE_RATE', 16000))

def get_download_config() -> dict:
    """
    获取下载配置
    
    Returns:
        下载配置字典
    """
    config = get_config()
    return config.get('DOWNLOAD', {})


def get_model_download_config() -> dict:
    """
    获取模型下载配置
    
    Returns:
        模型配置字典，格式: {model_name: {url: ..., path: ..., size: ..., description: ...}}
    """
    download_config = get_download_config()
    base_url = download_config.get('BASE_URL', '')
    models = download_config.get('MODELS', {})
    
    # 为每个模型添加完整的URL
    result = {}
    for model_name, model_info in models.items():
        result[model_name] = {
            'url': f"{base_url}/{model_name}",
            'path': model_info.get('path', ''),
            'size': model_info.get('size', ''),
            'description': model_info.get('description', '')
        }
    
    return result


def get_avatar_download_config() -> dict:
    """
    获取形象下载配置
    
    Returns:
        形象配置字典，格式: {avatar_name: {url: ..., path: ..., size: ..., description: ...}}
    """
    download_config = get_download_config()
    base_url = download_config.get('BASE_URL', '')
    avatars = download_config.get('AVATARS', {})
    
    # 为每个形象添加完整的URL
    result = {}
    for avatar_name, avatar_info in avatars.items():
        url_suffix = avatar_info.get('url_suffix', f"{avatar_name}.zip")
        result[avatar_name] = {
            'url': f"{base_url}/{url_suffix}",
            'path': avatar_info.get('path', ''),
            'size': avatar_info.get('size', ''),
            'description': avatar_info.get('description', '')
        }
    
    return result


def get_avatars_config() -> dict:
    """
    获取数字人配置
    
    Returns:
        数字人配置字典，包含 avatars 列表和 default_avatar
    """
    config = get_config()
    avatars_config = config.get('AVATARS', {})
    return {
        'avatars': avatars_config.get('avatars', []),
        'default_avatar': avatars_config.get('default_avatar', 'ai_model')
    }


def get_avatar_config(avatar_id: str) -> dict:
    """
    根据avatar_id获取单个数字人配置（支持通过 id 或 avatar_dir 查找）
    
    Args:
        avatar_id: 数字人ID（可以是 id 或 avatar_dir）
        
    Returns:
        数字人配置字典，如果未找到返回None
    """
    avatars_config = get_avatars_config()
    
    # 首先尝试通过 id 查找
    for avatar in avatars_config.get('avatars', []):
        if avatar.get('id') == avatar_id:
            return avatar
    
    # 如果没找到，尝试通过 avatar_dir 查找（向后兼容）
    for avatar in avatars_config.get('avatars', []):
        if avatar.get('avatar_dir') == avatar_id:
            return avatar
    
    return None

