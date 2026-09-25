# 智讲 Agent（Book2Course）

智讲 Agent 将有使用权的文本型 PDF 转换为一节中文教学视频。上传资料后，页面展示课程结构、逐段讲稿、PDF 页码与原文摘录，并提供可播放、可下载的 MP4。

系统提供两种生成方式：**真实 AI 模式**调用本机 Ollama 或外部兼容模型；**确定性演示模式**无需模型或密钥，使用固定规则生成内容，并在页面与视频中标明。配音可使用 Windows 中文系统语音；配置兼容语音服务后也可选择 AI 配音。来源核验只确认摘录与对应 PDF 页面匹配，知识解释仍需人工复核。

## 快速开始（Windows）

在项目目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765
```

打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)，上传有使用权的文本型 PDF，确认资料使用权后开始生成。可用[示例讲义](examples/binary_search_original.pdf)体验。生成完成后可查看来源、播放或下载视频，也可删除本地任务和资料。失败任务可用原 PDF 重新生成。按 `Ctrl+C` 关闭 Web 服务。

运行环境为 Python 3.11+ 与 Windows 中文系统语音；已在 Python 3.13 上验证。`imageio-ffmpeg` 提供视频合成所需的 FFmpeg，无需单独安装系统 FFmpeg。

## 使用本机 Ollama

安装并启动 [Ollama](https://ollama.com/)，通过 `ollama list` 检查模型。默认模板使用 `qwen2.5:7b`；如果本机没有该模型，可运行 `ollama pull qwen2.5:7b`。复制配置模板后重启 Web 服务：

```powershell
Copy-Item .env.local.example .env.local
```

`.env.local` 已加入 `.gitignore`。可在其中修改 Ollama 地址和模型名。真实 AI 模式通过本机 `/api/chat` 生成知识点、课程规划和讲稿；PDF 提取文本不会发送到外部文本模型。模型先选择带页码的原文片段编号，程序再填入并核验引文，减少模型改写原文造成的错误。

已生成的[示例视频](demo/zhijiang_ollama_demo.mp4)与[讲稿及来源](demo/zhijiang_ollama_lesson.json)可直接查看。示例视频的讲稿由本机模型生成，声音来自 Windows 系统语音。

## 外部模型与语音服务

如需使用外部文本模型，在启动服务前设置兼容 `POST /chat/completions` 的服务地址、模型名和密钥：

```powershell
$env:ZHIJIANG_LLM_PROVIDER = "openai"
$env:ZHIJIANG_LLM_BASE_URL = "https://你的服务地址/v1"
$env:ZHIJIANG_LLM_API_KEY = "你的密钥"
$env:ZHIJIANG_LLM_MODEL = "你的模型名"
```

可选 AI 配音需要兼容 `POST /audio/speech` 并能返回 WAV：

```powershell
$env:ZHIJIANG_TTS_BASE_URL = "https://你的语音服务地址/v1"
$env:ZHIJIANG_TTS_API_KEY = "你的语音密钥"
$env:ZHIJIANG_TTS_MODEL = "你的语音模型名"
$env:ZHIJIANG_TTS_VOICE = "alloy"
```

使用外部服务时，网页会要求额外确认发送提取文本或讲稿。不要将密钥提交到仓库。

## 测试与示例

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\generate_sample_pdf.py
.\.venv\Scripts\python scripts\build_demo.py
.\.venv\Scripts\python scripts\build_ollama_demo.py
```

`build_ollama_demo.py` 需要先配置本机 Ollama。项目还提供[无需模型的示例视频](demo/zhijiang_demo.mp4)。

## 当前支持范围

- 单机顺序处理任务；一份 PDF 生成一节课。
- 支持可提取文字的 PDF，最多 20 MB、100 页；暂不支持扫描件 OCR。
- AI 模式分析前 12 个有文字的页面；演示模式选取前 6 个合格文本片段。
- 支持概念卡片、公式步骤和流程画面。复杂动画、全书系列课与知识事实自动证明尚未实现。
