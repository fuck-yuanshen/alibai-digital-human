"""桌面启动器：启动 aiohttp 服务并用 pywebview 打开内置浏览器窗口。"""

import argparse
import os
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path

import webview


_server_error = None


def _log_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Alibai"
    root.mkdir(parents=True, exist_ok=True)
    return root / "launcher.log"


def _write_log(message: str):
    with _log_path().open("a", encoding="utf-8") as file:
        file.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def _load_external_env():
    """读取 EXE 同目录的 .env，系统环境变量优先。"""
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    env_path = base_dir / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _log_configuration_status():
    """记录会导致对话协商失败的关键配置状态，但不写入密钥内容。"""
    for key in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        value = os.environ.get(key, "").strip()
        if not value or value == "your-api-key" or "*" in value:
            _write_log(f"配置警告：{key} 未配置完整值；对应功能可能在 /offer 阶段失败")
        else:
            _write_log(f"配置已加载：{key}（长度 {len(value)}）")


def _server_worker(port: int, avatar_id: str):
    global _server_error
    try:
        _write_log(f"正在加载服务模块，端口 {port}")
        import main

        _write_log("服务模块加载完成")
        main.main(["--port", str(port), "--avatar_id", avatar_id])
    except Exception:
        _server_error = traceback.format_exc()
        _write_log(_server_error)


def _wait_for_server(port: int, timeout: float = 120.0):
    url = f"http://127.0.0.1:{port}/index.html"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _server_error:
            raise RuntimeError(_server_error)
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="以太李白桌面启动器")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--avatar_id", default="wav2lip_avatar_wzj2cjl")
    args = parser.parse_args(argv)

    try:
        _write_log("桌面启动器启动")
        _load_external_env()
        _log_configuration_status()
        server_thread = threading.Thread(
            target=_server_worker,
            args=(args.port, args.avatar_id),
            name="alibai-server",
            daemon=True,
        )
        server_thread.start()
        if not _wait_for_server(args.port):
            raise RuntimeError("服务启动超时，请查看 launcher.log")

        _write_log("服务就绪，正在创建内置浏览器窗口")
        webview.create_window(
            "以太李白 - AI 数字人",
            f"http://127.0.0.1:{args.port}/index.html",
            width=1280,
            height=820,
            min_size=(960, 640),
            resizable=True,
        )
        webview.start(debug=False)
    except Exception as exc:
        message = f"启动失败：{exc}\n\n日志：{_log_path()}"
        _write_log(message)
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "以太李白启动失败", 0x10)
        raise


if __name__ == "__main__":
    main()
