# 智讲 Agent（Book2Course）

将**有使用权的文本型 PDF**转换为一节中文教学课：页面展示课程结构、逐段讲稿、PDF 页码与原文摘录，并生成可播放的 MP4。

本仓库是教育领域 AI Coding 赛事的首版项目。`demo` 模式用确定性规则生成内容，页面和视频均明确标注；`ai` 模式可调用本机 Ollama 或外部兼容接口的真实文本模型。系统语音与可选 AI 配音分别标注。自动引用核验只确认摘录可在相应页找到，不替代人工知识审核。

## 快速运行（Windows）

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765`，选择 [原创演示讲义](examples/binary_search_original.pdf)，确认资料使用权，保持默认的“确定性演示模式 / Windows 中文系统语音”，点击“生成一节课”。完成后可在页面查看引用和视频，并删除本地资料。上传上限为 20 MB、100 页；首版不支持扫描件 OCR。

运行环境：Python 3.11+，已在 Python 3.13 / Windows 验证；系统需要安装中文语音“Microsoft Huihui Desktop”或通过环境变量改用本机其他语音。`imageio-ffmpeg` 的 wheel 提供视频合成所用 FFmpeg，无需预先安装系统 FFmpeg。

## 本机 Ollama 真实 AI 模式

在安装并启动 [Ollama](https://ollama.com/) 后，执行 `ollama list` 确认本机已有 `qwen2.5:7b`；若没有，再执行 `ollama pull qwen2.5:7b`。复制仓库中的配置模板，按实际模型名修改。`.env.local` 已列入 `.gitignore`，不会提交本机地址或密钥。

```powershell
Copy-Item .env.local.example .env.local
.\.venv\Scripts\python scripts\build_ollama_demo.py
```

网页重启后可选“本机 Ollama 真实 AI 模式”。本机模型经原生 `/api/chat` 的 JSON Schema 输出课程，提取的文本留在本机；若改用外部模型，页面会要求额外发送同意。本机 Ollama Demo 为 [视频](demo/zhijiang_ollama_demo.mp4) 和 [讲稿与来源](demo/zhijiang_ollama_lesson.json)，实际生成时长约 2 分 21 秒。此视频的讲稿由模型生成，声音由 Windows 系统语音合成，**不是 AI 配音**。

本机 Ollama 0.34.1 的 `/v1/audio/speech` 实测返回 404，当前版本没有可直接接入本项目 WAV 配音流程的服务，因此没有下载仅能生成文本 token 的所谓 TTS 模型。若将来配置一个真正支持该接口的语音服务，可使用下述可选配置。

## 接入外部兼容模型与可选 AI 配音

在**启动服务前**设置环境变量，不要把密钥写入仓库：

```powershell
$env:ZHIJIANG_LLM_BASE_URL = "https://你的服务地址/v1"
$env:ZHIJIANG_LLM_API_KEY = "你的密钥"
$env:ZHIJIANG_LLM_MODEL = "你的模型名"
$env:ZHIJIANG_LLM_PROVIDER = "openai"
```

文本服务须兼容 `POST /chat/completions` 并返回 `choices[0].message.content`。可选 AI 配音须兼容 `POST /audio/speech`、接受 `response_format: wav`：

```powershell
$env:ZHIJIANG_TTS_BASE_URL = "https://你的语音服务地址/v1"
$env:ZHIJIANG_TTS_API_KEY = "你的语音密钥"
$env:ZHIJIANG_TTS_MODEL = "你的语音模型名"
$env:ZHIJIANG_TTS_VOICE = "alloy"
```

网页会在使用外部文本服务或外部配音时要求额外同意。未配置密钥时，离线演示模式和本机 Ollama 模式仍可使用。真实模型路径已用本机 `qwen2.5:7b` 验证；外部兼容接口通过模拟 HTTP 服务测试。仓库不包含服务密钥。

## 复现、测试与参赛材料

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\generate_sample_pdf.py
.\.venv\Scripts\python scripts\build_demo.py
.\.venv\Scripts\python scripts\build_ollama_demo.py
.\.venv\Scripts\python scripts\build_submission.py
```

- [产品说明书](docs/产品说明书.md)：介绍、设计思路、设计过程、商业价值与创新点。
- [AI Coding 全过程](docs/AI_Coding_全过程.md)：单列工具、交互、开发阶段与测试证据。
- [Demo 操作说明](docs/Demo_操作说明.md)：本地网站与视频演示步骤。
- [第三方来源与许可](docs/第三方来源与许可.md)：依赖、视频工具和示例素材来源。
- [本机 Ollama 演示视频](demo/zhijiang_ollama_demo.mp4) 与 [结构化课程结果](demo/zhijiang_ollama_lesson.json)；另保留 [无需模型的演示视频](demo/zhijiang_demo.mp4)。

`scripts/build_submission.py` 生成 `submission/智讲Agent_参赛材料.zip`，其中包含产品说明书 PDF、独立 AI Coding 全过程 PDF、Demo MP4 和原创演示 PDF。提交前请按照主办方平台实际格式要求核对，并在 **2026 年 10 月 23 日 24:00（中国时间）** 前完成上传。

## 首版边界

单机、单任务顺序处理；一份 PDF 生成一节课，默认从前部可提取内容选取知识点。真实模型分析前 12 个有文字的页面；演示模式选取前 6 个合格文本片段。复杂公式绘图、全书系列课、OCR 和知识事实自动证明属于后续工作。
