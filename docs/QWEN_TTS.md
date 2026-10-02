# Qwen-TTS 配置说明（历史参考）

项目当前默认使用匹配数字人形象的 CosyVoice `libai_v2` 音色，Qwen-TTS 配置仍保留在本文件中作为备用方案。当前方案请参见 [COSYVOICE_TTS.md](COSYVOICE_TTS.md)。

## 官方接口

- 非实时语音合成说明：<https://help.aliyun.com/zh/model-studio/non-realtime-tts-user-guide>
- Qwen-TTS API 参考：<https://help.aliyun.com/zh/model-studio/qwen-tts-api>

北京地域使用以下服务地址：

```text
https://dashscope.aliyuncs.com/api/v1
```

Qwen-TTS 的官方 Python 调用方式是 `dashscope.MultiModalConversation.call`。非流式调用会返回音频 URL，URL 有效期为 24 小时；项目会自动下载、解码并重采样为数字人使用的 16 kHz 单声道 PCM。

## 配置

在项目根目录 `.env` 中填写完整密钥：

```dotenv
DASHSCOPE_API_KEY=你的百炼API-Key
```

不要把密钥写入 `config.yml` 或提交到代码仓库。项目会自动从 `.env` 读取 `DASHSCOPE_API_KEY`。

历史 Qwen-TTS 配置示例（当前默认配置请参见 `docs/COSYVOICE_TTS.md`）：

```yaml
TTS:
  DASHSCOPE_BASE_URL: "https://dashscope.aliyuncs.com/api/v1"
  DASHSCOPE_MODEL: "qwen3-tts-instruct-flash"
  DASHSCOPE_VOICE: "Cherry"
  DASHSCOPE_LANGUAGE_TYPE: "Chinese"
```

`qwen3-tts-instruct-flash` 支持 `instructions` 和 `optimize_instructions`；如果切换到普通的 `qwen3-tts-flash`，项目会自动省略这两个仅指令模型支持的参数。

## 启动

```powershell
python main.py --port 8010
```

如需切回 Qwen-TTS，请将 `config.yml` 中的模型和音色改回上述值。当前默认音色为 CosyVoice `libai_v2`。
