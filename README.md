# 以太李白（AI 数字人）

基于静态数字人头像、WebRTC、DeepSeek 与阿里云百炼语音服务构建的实时数字人项目。浏览器负责采集语音和播放音视频，服务端完成语音识别、对话生成和语音合成。当前版本已移除 Wav2Lip 权重，头像视频轨道重复首帧，因此嘴部不会随语音变化。

## 功能特性

- 静态头像视频输出，嘴部保持不动
- WebRTC 实时音视频传输
- DeepSeek 多轮对话
- DashScope Paraformer 实时语音识别
- DashScope CosyVoice 语音合成，默认使用 `libai_v2` 李白音色
- 支持文字对话、语音对话、音频文件驱动和随时打断
- 支持多数字人配置与启动时预加载
- 不依赖本地 GPU 或唇形模型
- 首次启动时自动检查并下载默认数字人头像资源

## 运行流程

```text
浏览器麦克风
    -> WebRTC 音频轨道
    -> DashScope ASR
    -> DeepSeek LLM
    -> DashScope TTS
    -> 静态头像帧输出
    -> WebRTC 音视频播放
```

## 环境要求

- Windows 10/11 或 Linux
- Python 3.10
- FFmpeg，并已加入 `PATH`
- Chrome 或 Edge 浏览器
- DeepSeek API Key
- 阿里云百炼 DashScope API Key

静态头像模式使用 CPU 即可运行，不再需要 CUDA、PyTorch 或 Wav2Lip 权重。FFmpeg 仅在使用服务端录制功能时需要。

## 安装

创建 Python 环境：

```bash
conda create -n alibai python=3.10
conda activate alibai
```

安装 PyTorch CUDA 版本：

```bash
conda install pytorch==2.5.0 torchvision==0.20.0 torchaudio==2.5.0 pytorch-cuda=12.4 -c pytorch -c nvidia
```

安装项目依赖：

```bash
pip install -r requirements.txt
```

确认 FFmpeg 可用：

```bash
ffmpeg -version
```

## 配置

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

Linux/macOS 可使用：

```bash
cp .env.example .env
```

填写 `.env`：

```dotenv
DEEPSEEK_API_KEY=your-deepseek-api-key
DASHSCOPE_API_KEY=your-dashscope-api-key
```

系统环境变量的优先级高于 `.env`。`.env` 已被 Git 忽略，不要把真实密钥写入 README、提交记录或公开配置文件。

主要配置位于 [`config.yml`](config.yml)：

- `LLM`：DeepSeek 地址、模型、推理强度和 thinking 模式
- `ASR`：DashScope 实时识别模型、采样率和音频格式
- `TTS`：DashScope 模型、音色和语言
- `DOWNLOAD`：数字人资源的下载地址
- `AVATARS`：前端可选数字人、资源目录和对应音色

当前默认数字人为 `ai_libai`，资源目录为 `data/wav2lip_avatar_wzj2cjl`。

## 快速启动

### Windows 启动脚本

双击项目根目录中的 `start.bat`，或执行：

```powershell
.\start.bat
```

脚本会检查服务是否已经启动，等待服务可用后自动打开浏览器。若脚本内指定的 Python 路径不存在，会回退到 `py -3.10`。

### 命令行启动

```bash
python main.py
```

服务启动后访问：

- 首页：<http://127.0.0.1:8010/index.html>
- 对话页：<http://127.0.0.1:8010/talk.html?avatar=ai_libai>
- 测试页：<http://127.0.0.1:8010/test.html>

进入对话页后，右上角的“日志”按钮可以打开运行日志窗口。连接失败时窗口会自动打开，显示浏览器端 WebRTC 错误、服务端 `/offer` 错误、模型加载和 TTS 错误。日志文件同时保存到 `%LOCALAPPDATA%\\Alibai\\launcher.log` 和 `%LOCALAPPDATA%\\Alibai\\server.log`。

首次运行会检查默认数字人资源，缺失时自动下载：

- `data/wav2lip_avatar_wzj2cjl`：默认“以太李白”数字人资源

### 打包版 EXE

执行 `build_exe.bat` 后，打包目录位于 `dist/Alibai/`。双击 [`dist/Alibai/Alibai.exe`](dist/Alibai/Alibai.exe) 会启动本地服务，并在独立的内置浏览器窗口中打开首页。窗口右上角的“系统提示词”面板可以编辑并保存角色设定、语气和回答规则。

打包版不包含 Wav2Lip 权重，只携带一张默认头像首帧，产物约 410 MB。构建脚本会在项目根目录存在 `.env` 时将它复制到 EXE 同目录；手动部署时也可以将 `.env.example` 复制为 `.env` 并填写 API Key，或使用系统环境变量。缺少 `DASHSCOPE_API_KEY` 会导致建立对话时 `/offer` 返回错误，缺少 `DEEPSEEK_API_KEY` 会导致文字回答失败。提示词设置保存到当前程序目录的 `settings.json`：源码运行时是项目根目录，EXE 运行时是 `Alibai.exe` 所在目录。`.env` 包含真实密钥，不应公开上传或发送给不可信的人。

LLM 流式回答会按句末标点拆分为独立消息。每条消息只发起一次 TTS 合成，播放线程按原顺序输出；默认 DashScope TTS 会在第一条消息播放时预合成下一条消息，减少句子之间的等待。

内置浏览器窗口使用 Microsoft Edge WebView2 Runtime。新装 Windows 10 如果没有该运行时，请先安装 WebView2 Evergreen Runtime；EXE 目录必须整体复制，不能只复制 `Alibai.exe`。

EXE 会从自身 `_internal` 资源目录加载 `static` 和 `data`，不依赖快捷方式的“起始位置”或当前工作目录；因此可以从桌面、其它磁盘目录或命令行任意位置启动。

重新构建 EXE：

```powershell
.\\build_exe.bat
```

常用启动参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--port` | `8010` | Web 服务监听端口 |
| `--avatar_id` | `wav2lip_avatar_wzj2cjl` | `data` 下的默认数字人目录 |
| `--max_session` | `1` | 最大会话数配置（当前版本保留参数，主服务未执行上限校验） |
| `--tts` | `dashscope` | TTS 服务类型 |
| `--REF_FILE` | `libai_v2` | DashScope 音色名称 |
| `--video_bitrate` | `8000` | 视频带宽提示，单位 kbps；`0` 表示禁用 |
| `--keyframe_interval` | `5.0` | 强制关键帧间隔，单位秒；`0` 表示禁用 |
| `--sharpen_strength` | `0.12` | 输出帧锐化强度；`0` 表示禁用 |
| `--preload_enhanced_frames` | `1` | 是否预加载增强帧缓存 |

示例：

```bash
python main.py --port 8010 --avatar_id wav2lip_avatar_wzj2cjl
```

## 浏览器使用

1. 打开首页并点击“开始对话”。
2. 首次使用语音输入时允许浏览器访问麦克风。
3. 等待 WebRTC 连接成功后输入文字，或开启语音对话。
4. 数字人说话时可以使用打断功能停止当前回复。

浏览器与服务端不在同一台机器时，麦克风权限通常要求 HTTPS；`localhost` 和 `127.0.0.1` 不受此限制。

## HTTP 接口

这些接口服务于数字人前端，不是 PulseRing Mock API。

| 方法 | 路径 | 作用 | 主要参数 |
|---|---|---|---|
| POST | `/offer` | 创建 WebRTC 会话并返回 SDP Answer | `sdp`, `type`, `avatar_id` |
| POST | `/human` | 发送文字或触发 LLM 对话 | `sessionid`, `type`, `text`, `interrupt` |
| POST | `/voice/start` | 启动当前会话的实时 ASR | `sessionid` |
| POST | `/voice/stop` | 停止当前会话的实时 ASR | `sessionid` |
| POST | `/humanaudio` | 上传音频并驱动数字人 | `multipart/form-data`: `sessionid`, `file` |
| POST | `/set_audiotype` | 切换自定义音频/动作状态 | `sessionid`, `audiotype`, `reinit` |
| POST | `/record` | 开始或停止服务端录制 | `sessionid`, `type` |
| POST | `/interrupt_talk` | 打断当前数字人语音 | `sessionid` |
| POST | `/is_speaking` | 查询数字人是否正在说话 | `sessionid` |
| GET | `/api/avatars` | 获取 `config.yml` 中配置的数字人列表 | - |

`/human` 的 `type` 支持：

- `echo`：直接将 `text` 送入 TTS
- `chat`：先由 DeepSeek 生成回复，再送入 TTS

除 `/offer` 外，业务接口通常返回：

```json
{
  "code": 0,
  "msg": "ok"
}
```

## GPU 服务分离部署（旧版兼容）

静态头像模式不会调用 GPU 推理服务。以下接口和脚本仅用于保留旧版 Wav2Lip 部署兼容性，当前 `main.py` 会忽略 `--gpu_server_url`：

```bash
python src/gpu_wav2lip_service.py --host 0.0.0.0 --port 8080 --batch_size 32 --fp16
```

应用服务器连接远程 GPU 服务：

```bash
python main.py --gpu_server_url http://192.168.1.100:8080 --port 8010
```

GPU 服务提供以下内部接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查及设备信息 |
| POST | `/session/init` | 初始化推理会话 |
| POST | `/inference/batch` | 批量唇形推理 |
| POST | `/session/close` | 关闭推理会话 |

远程部署时需要同时放行应用端口（默认 `8010`）、GPU 服务端口（默认 `8080`）以及 WebRTC 所需 UDP 流量。GPU 服务应部署在受信网络内，不建议直接暴露到公网。

## 创建自定义静态数字人

准备一个人物面部清晰、正面且嘴部状态稳定的视频，然后执行：

```bash
python src/wav2lip/genavatar.py --video_path your_video.mp4 --img_size 256 --avatar_id wav2lip_avatar_custom
```

生成结果位于 `results/avatars/wav2lip_avatar_custom`，包含：

- `full_imgs/`：完整视频帧
- `face_imgs/`：裁剪后的人脸图像
- `coords.pkl`：人脸坐标数据

将生成目录复制到 `data/`，再把对应条目加入 `config.yml` 的 `AVATARS.avatars`，即可由前端选择该数字人。静态模式只读取该目录的第一张 `full_imgs` 图片，后续帧不会驱动嘴部变化。

## 项目结构

```text
alibai/
├─ main.py                     # aiohttp/WebRTC 主服务
├─ config.yml                  # LLM、ASR、TTS、下载与数字人配置
├─ start.bat                   # Windows 一键启动脚本
├─ requirements.txt            # Python 依赖
├─ models/                     # 兼容旧版的模型目录，当前为空
├─ data/                       # 数字人资源
├─ static/                     # 浏览器页面及交互脚本
├─ src/
│  ├─ basereal.py              # 数字人会话、音频和对话编排
│  ├─ staticreal.py            # 静态头像视频和音频输出
│  ├─ avatar.py                # 首帧头像加载器
│  ├─ dashscope_asr.py         # DashScope 实时 ASR
│  ├─ dashscope_tts.py         # DashScope TTS
│  ├─ llm.py                   # DeepSeek/OpenAI 兼容 LLM 客户端
│  ├─ webrtc.py                # WebRTC 音视频轨道
│  └─ gpu_wav2lip_service.py   # 独立 GPU 推理服务
├─ tests/                      # 离线单元测试
└─ docs/                       # 补充说明
```

## 测试

运行离线单元测试：

```bash
python -m unittest discover -s tests -v
```

测试覆盖 WebRTC 音频队列、DashScope ASR 生命周期及 DashScope TTS 音频处理。需要真实 API 的端到端能力应在本机配置 `.env` 后单独验证。

## 常见问题

### 页面可以打开，但数字人没有声音

- 检查 `DASHSCOPE_API_KEY` 是否有效。
- 检查浏览器标签页是否静音，并确认页面已经经过一次用户点击。
- 查看服务端日志中的 TTS 或音频解码错误。
- 参见 [`docs/TTS_AUDIO_FIX.md`](docs/TTS_AUDIO_FIX.md)。

### 语音输入不可用

- 确认已授予麦克风权限。
- 确认 `DASHSCOPE_API_KEY` 可调用 `paraformer-realtime-v2`。
- 远程访问时使用 HTTPS。
- 参见 [`docs/语音输入问题说明.md`](docs/语音输入问题说明.md)。

### 首次启动长时间没有响应

首次运行可能正在下载数字人资源。请检查控制台下载进度、磁盘空间和 Hugging Face 网络连接。需要镜像时可在启动前设置：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

PowerShell：

```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

### 视频播放卡顿

静态模式没有唇形推理开销。若视频仍卡顿，请检查 CPU 占用、浏览器 WebRTC 状态和本机网络；服务端日志中的 `finalfps` 建议保持在 25 以上。

## 外部 Mock API 参考

项目目录中包含一份从 PulseRing OpenAPI 文档整理的接口清单：[`PulseRing-API-接口清单.md`](PulseRing-API-接口清单.md)。该 API 当前未在数字人代码中调用，接入前需要单独实现客户端和业务映射。

- Swagger UI：<https://apimock.feypower.com/docs/>
- Base URL：`https://apimock.feypower.com`
- 共 73 个路径、85 个操作

## 安全注意事项

- 真实 API Key 只存放在 `.env` 或系统环境变量中。
- 不要提交 `.env`、运行日志、录音录像和用户对话内容。
- 生产环境应限制 CORS 来源、增加接口鉴权，并为 WebRTC 和 HTTP 配置 HTTPS。
- GPU 推理服务没有面向公网的鉴权能力，应限制为内网访问。

## 许可证与致谢

本项目使用 [Apache License 2.0](LICENSE)。

项目基于或参考以下开源工作：

- [AIAvatar](https://github.com/shibing624/AIAvatar)
- [LiveTalking](https://github.com/lipku/LiveTalking)
- [Wav2Lip](https://github.com/Rudrabha/Wav2Lip)
- [MuseTalk](https://github.com/TMElyralab/MuseTalk)
