# 智讲 Agent（Book2Course）

智讲 Agent 将有使用权的 PDF 转换为中文教学视频。文字版 PDF 直接提取内容，扫描页在本机 OCR。上传资料后，页面展示课程结构、逐段讲稿、PDF 页码与原文摘录，并提供可播放、可下载的 MP4。

系统提供两种生成方式：**真实 AI 模式**调用本机 Ollama 或外部兼容模型；**确定性演示模式**无需模型或密钥，使用固定规则生成内容，并在页面与视频中标明。网页可为单次任务调整模型提供方、API 地址、模型名称、密钥和讲解提示词。配音可使用 Windows 中文系统语音；配置兼容语音服务后也可选择 AI 配音。来源核验只确认摘录与对应提取/OCR 文字匹配，知识解释和 OCR 准确性仍需人工复核。

## 快速开始（Windows）

在项目目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765
```

打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)，上传有使用权的 PDF，确认资料使用权后开始生成。可用[示例讲义](examples/binary_search_original.pdf)体验。生成完成后可查看来源、播放或下载视频，也可删除本地任务和资料。失败任务可用原 PDF 重新生成。按 `Ctrl+C` 关闭 Web 服务。

运行环境为 Python 3.11+ 与 Windows 中文系统语音；已在 Python 3.13 上验证。`rapidocr` 和 `onnxruntime` 在本机执行 OCR，`pypdfium2` 负责扫描页渲染。`imageio-ffmpeg` 提供视频合成所需的 FFmpeg，无需单独安装系统 FFmpeg。

## 使用本机 Ollama

安装并启动 [Ollama](https://ollama.com/)，通过 `ollama list` 检查模型。默认模板使用 `qwen2.5:7b`；如果本机没有该模型，可运行 `ollama pull qwen2.5:7b`。复制配置模板后重启 Web 服务：

```powershell
Copy-Item .env.local.example .env.local
```

`.env.local` 已加入 `.gitignore`。可在其中修改 Ollama 地址和模型名。真实 AI 模式通过本机 `/api/chat` 生成知识点、课程规划和讲稿；PDF 提取文本不会发送到外部文本模型。模型先选择带页码的原文片段编号，程序再填入并核验引文，减少模型改写原文造成的错误。

也可以不创建 `.env.local`，直接在网页选择真实 AI 模式并填写本次任务的 API 配置。API 密钥仅在任务运行期间留在服务进程内存，不写入 SQLite、课程 JSON 或网页响应；刷新页面或服务重启后重试外部模型任务，需要重新输入密钥。自定义提示词作用于课程规划和讲稿风格，不能绕过来源核验。

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
- 支持文字版和扫描版 PDF；上传大小上限 200 MB，没有固定页数上限。扫描页在后台逐页 OCR，处理时间会随页数增加。
- AI 模式从全部有文字的页面分批选取依据并生成课程，不限制目标视频时长；实际时长取决于资料、模型输出和配音速度。长文档会产生更多模型调用。
- 演示模式也不限制页数或片段数；两页以内的示例仍选前 6 个片段，较长资料从每页选取最多 3 个片段。
- 支持概念卡片、公式步骤和流程画面。复杂动画、跨章节连续性与知识事实自动证明尚未实现。
