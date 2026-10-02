"""运行时用户设置，包含可持久化的系统提示词。"""

import json
import sys
from pathlib import Path


DEFAULT_SYSTEM_PROMPT = (
    "You are Li Bai, the ancient Chinese poet and a friendly technology guide. "
    "Always determine the response language from the user's latest message, not "
    "from earlier conversation turns. If the latest question is in English, answer "
    "entirely in English; do not translate it into Chinese or add a Chinese translation "
    "unless the user explicitly asks for one. If the latest question is in Chinese, "
    "answer entirely in Chinese. For mixed-language questions, use the dominant language. "
    "Keep answers concise, plain text only, without Markdown."
)


def _settings_path() -> Path:
    # 源码模式写入项目根目录，打包模式写入 Alibai.exe 所在目录。
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "settings.json"
    return Path(__file__).resolve().parent.parent / "settings.json"


def _write_settings_file(path: Path, prompt: str) -> None:
    """以原子替换方式写入提示词配置，避免程序中断留下半个 JSON 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps({"system_prompt": prompt}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def get_system_prompt() -> str:
    path = _settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("system_prompt")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except (OSError, ValueError, TypeError):
        pass

    # 首次启动时生成可直接编辑的配置文件；只读安装目录下仍允许使用内置默认值。
    try:
        _write_settings_file(path, DEFAULT_SYSTEM_PROMPT)
    except OSError:
        pass
    return DEFAULT_SYSTEM_PROMPT


def set_system_prompt(value: str) -> str:
    prompt = str(value or "").strip()
    if not prompt:
        raise ValueError("系统提示词不能为空")
    if len(prompt) > 12000:
        raise ValueError("系统提示词不能超过 12000 个字符")

    _write_settings_file(_settings_path(), prompt)
    return prompt
