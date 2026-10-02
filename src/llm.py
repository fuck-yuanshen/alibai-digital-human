import time
from collections import deque
from openai import OpenAI
from src.basereal import BaseReal
from src.log import logger
from src.config import (
    get_llm_api_key,
    get_llm_api_key_env,
    get_llm_base_url,
    get_llm_model_name,
    get_llm_reasoning_effort,
    get_llm_thinking_enabled,
)
from src.settings import DEFAULT_SYSTEM_PROMPT, get_system_prompt


base_url = get_llm_base_url()
model_name = get_llm_model_name()
client = None
logger.debug(f"LLM configured: base_url={base_url}, model={model_name}")

# 全局对话历史管理
# key: session_id, value: deque of messages (最多保留10轮，即20条消息)
_conversation_history = {}
MAX_HISTORY_ROUNDS = 10  # 最多保留10轮对话
MAX_HISTORY_MESSAGES = MAX_HISTORY_ROUNDS * 2  # 每轮2条消息（user + assistant）

# 保留常量供现有调用方和测试读取；实际请求使用可持久化的 get_system_prompt()。
SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT

# 系统提示词：要求模型根据最新用户消息的语言回答，避免历史对话或固定人格导致语言漂移。
def get_llm_client() -> OpenAI:
    """按需创建 DeepSeek 客户端，避免在模块加载时读取或记录密钥。"""
    global client
    if client is not None:
        return client

    api_key = get_llm_api_key()
    if not api_key:
        key_env = get_llm_api_key_env()
        raise RuntimeError(f"未设置 DeepSeek API Key，请先设置环境变量 {key_env}")

    client = OpenAI(api_key=api_key, base_url=base_url)
    return client


def get_conversation_history(session_id):
    """获取指定session的对话历史"""
    if session_id not in _conversation_history:
        _conversation_history[session_id] = deque(maxlen=MAX_HISTORY_MESSAGES)
    return _conversation_history[session_id]


def add_to_history(session_id, role, content):
    """添加消息到对话历史
    
    Args:
        session_id: 会话ID
        role: 'user' 或 'assistant'
        content: 消息内容
    """
    history = get_conversation_history(session_id)
    history.append({'role': role, 'content': content})


def clear_conversation_history(session_id=None):
    """清除对话历史
    
    Args:
        session_id: 指定session_id清除特定会话，None则清除所有
    """
    global _conversation_history
    if session_id is None:
        _conversation_history.clear()
        logger.info("All conversation history cleared")
    elif session_id in _conversation_history:
        del _conversation_history[session_id]
        logger.info(f"Session {session_id} conversation history cleared")


def build_messages(session_id, current_message):
    """构建完整的消息列表（系统提示词 + 历史 + 当前消息）
    
    Args:
        session_id: 会话ID
        current_message: 当前用户消息
    
    Returns:
        完整的消息列表
    """
    messages = [{'role': 'system', 'content': get_system_prompt()}]
    
    # 添加历史消息
    history = get_conversation_history(session_id)
    messages.extend(list(history))
    
    # 添加当前消息
    messages.append({'role': 'user', 'content': current_message})
    
    return messages


def emit_llm_text(nerfreal: BaseReal, text: str):
    """把流式回答片段发送到前端字幕，不触发语音合成。"""
    if hasattr(nerfreal, 'send_data_channel_message'):
        nerfreal.send_data_channel_message({'type': 'llm', 'text': text})


def queue_tts_response(nerfreal: BaseReal, text: str):
    """按句子加入 TTS 队列，让下一句可以在上一句播放时提前合成。"""
    if text and text.strip():
        nerfreal.put_msg_txt(text.strip(), {'skip_llm_datachannel': True})


def emit_llm_error(nerfreal: BaseReal, message: str):
    if hasattr(nerfreal, 'send_data_channel_message'):
        nerfreal.send_data_channel_message({'type': 'error', 'message': message})


def llm_response(message, nerfreal: BaseReal, session_id=None):
    """生成LLM响应（支持多轮对话）
    
    Args:
        message: 用户输入消息
        nerfreal: BaseReal实例
        session_id: 会话ID，用于区分不同用户/会话的对话历史
    """
    try:
        # 如果没有提供session_id，使用nerfreal的sessionid
        if session_id is None:
            session_id = getattr(nerfreal, 'sessionid', 'default')
        
        logger.debug(f"Session {session_id}: User message: {message}")
        
        # 构建包含历史的消息列表
        messages = build_messages(session_id, message)
        
        start = time.perf_counter()
        request_options = {
            'model': model_name,
            'messages': messages,
            'stream': True,
            'reasoning_effort': get_llm_reasoning_effort(),
        }
        if get_llm_thinking_enabled():
            request_options['extra_body'] = {'thinking': {'type': 'enabled'}}

        completion = get_llm_client().chat.completions.create(
            **request_options,
        )
        
        result = ""
        assistant_response = ""  # 完整的助手响应
        first = True
        
        # 只在大标点处分割（句号、问号、感叹号、分号）
        major_punctuation = "。！？；.!?;"
        
        for chunk in completion:
            if len(chunk.choices) > 0:
                if first:
                    end = time.perf_counter()
                    logger.debug(f"llm Time to first chunk: {end - start}s")
                    first = False
                msg = chunk.choices[0].delta.content
                if msg:
                    assistant_response += msg  # 累积完整响应
                    lastpos = 0
                    for i, char in enumerate(msg):
                        # 只在大标点处分割
                        if char in major_punctuation:
                            result = result + msg[lastpos:i + 1]
                            lastpos = i + 1
                            # 句子完成后同时发送字幕并排入 TTS；后续句子继续流式准备。
                            if len(result.strip()) > 0:
                                emit_llm_text(nerfreal, result)
                                queue_tts_response(nerfreal, result)
                                result = ""
                    result = result + msg[lastpos:]
        
        # 处理最后剩余的文本（如果没有以大标点结尾）
        if result.strip():
            emit_llm_text(nerfreal, result)

        # 没有句末标点的尾部也要独立入队。
        if result.strip():
            queue_tts_response(nerfreal, result)
        
        # 保存到对话历史
        add_to_history(session_id, 'user', message)
        add_to_history(session_id, 'assistant', assistant_response)
    except Exception as e:
        logger.exception(f"LLM response failed: {e}")
        emit_llm_error(nerfreal, "大模型响应失败，请查看后端日志")
    
