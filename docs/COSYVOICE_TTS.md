# CosyVoice 李白音色配置

项目默认使用阿里云百炼 CosyVoice 的 `libai_v2` 音色。官方音色列表中该音色名称为“李白”，特质为“古代诗仙男”，适合当前数字人形象。

## 官方资料

- [CosyVoice 音色列表](https://help.aliyun.com/zh/model-studio/cosyvoice-voice-list)
- [非实时语音合成](https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide)

官方参数对应关系：

```text
model: cosyvoice-v2
voice: libai_v2
endpoint: https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer
```

CosyVoice v2 的 `libai_v2` 不支持 Instruct 参数，因此项目不会发送 `instructions` 或 `optimize_instructions`。接口返回音频 URL 后，项目会立即下载并转换为数字人需要的 16 kHz 单声道 PCM。

## 文本提交策略

LLM 的流式 token 用于实时更新字幕，并在句末标点处组成独立消息提交 TTS。每条消息只请求一次 TTS；默认实现会在当前句播放期间预合成下一句，并按原顺序播放，避免等完整回答结束后才开始语音，也避免多个请求乱序。

## 配置

只需要在项目根目录 `.env` 中填写 DashScope API Key：

```dotenv
DASHSCOPE_API_KEY=你的百炼API-Key
```

当前默认配置位于 `config.yml`：

```yaml
TTS:
  DASHSCOPE_API_KEY_ENV: "DASHSCOPE_API_KEY"
  DASHSCOPE_BASE_URL: "https://dashscope.aliyuncs.com/api/v1"
  DASHSCOPE_MODEL: "cosyvoice-v2"
  DASHSCOPE_VOICE: "libai_v2"
```

## 启动

```powershell
python main.py --port 8010
```

默认 `--tts` 已经是 `dashscope`，无需再配置豆包、百度或腾讯 TTS 凭据。访问：<http://127.0.0.1:8010/talk.html>
