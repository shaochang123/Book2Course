# 智讲 Agent（Book2Course）

**语言 / Language：** [简体中文](README.md) | [English](README.en.md)

智讲 Agent 将有使用权的 PDF 转换为中文教学视频和演示用 PPT 课件。文字版 PDF 直接提取内容，扫描页在本机 OCR。上传资料后，页面展示课程结构、逐段讲稿、PDF 页码与原文摘录，并提供可下载的 MP4 和 PPTX。PPTX 内含 SVG 教学图示、逐段可播放的讲解动画及讲者备注。

系统提供两种生成方式：**真实 AI 模式**调用本机 Ollama 或外部兼容模型；**确定性演示模式**无需模型或密钥，使用固定规则生成内容，并在页面与视频中标明。网页可为单次任务调整文本模型提供方、API 地址、模型名称、密钥和讲解提示词，也可单独设置语音 API 地址、模型、音色和密钥。配音可使用 Windows 中文系统语音、本机 Kokoro 中文 AI 语音模型或外部兼容语音服务。来源核验只确认摘录与对应提取/OCR 文字匹配，知识解释和 OCR 准确性仍需人工复核。

## 从书籍到课程的流程

草稿中的“书籍 → OCR／排版 → 页面”和“主画面 → 配音／动画 → 合成”在这里整理为同一条可溯源的制作链。**绿色实线表示当前已实现的 MP4 与 PPTX 流程；图注将 LaTeX 排版和 Manim 场景标为规划能力**。来源核验能检查引文位置，不能保证知识覆盖完整或讲解正确，正式使用前仍要人工核对。

[![从书籍 PDF 到教学视频的流程图](docs/workflow.zh.svg)](docs/workflow.zh.svg)

视频画面由 Pillow 绘制为临时帧并随任务清理。PPTX 自动生成封面及每个知识点的图示页、动画页：标题等文字可在 PowerPoint 中编辑，SVG 作为矢量图片嵌入并附 PNG 兼容图，分段 MP4 可在放映时点击播放；讲者备注包含口播稿、原文页码与摘录。自动图示和动画使用受限模板，复杂的连续数学变换、LaTeX 公式排版与 Manim 场景仍需人工专项制作。

### PPT 内容制作 skills

仓库内的以下 Codex skills 可用于改进 PPT 内容和素材；网页使用内置模板自动生成 PPTX，不会自动调用这些 skills。可以在本项目的 Codex 任务中按名称调用：

| Skill | 用途 |
| --- | --- |
| [`$book2course-ppt-outline`](.agents/skills/book2course-ppt-outline/SKILL.md) | 按知识依赖和来源页码规划逐页大纲，检查重要知识点是否遗漏。 |
| [`$book2course-ppt-script`](.agents/skills/book2course-ppt-script/SKILL.md) | 为每页写演讲稿、讲者备注、配音文案和画面播放提示。 |
| [`$book2course-svg-diagrams`](.agents/skills/book2course-svg-diagrams/SKILL.md) | 制作可编辑的 SVG 流程图、概念关系图和公式步骤图。 |
| [`$book2course-explainer-animation`](.agents/skills/book2course-explainer-animation/SKILL.md) | 设计连续变换式讲解动画，并核对画面、口播和时间线；可按需使用 [Manim Community](https://docs.manim.community/en/stable/)。 |

需要定制自动课件之外的复杂讲解时，可用 Codex 的 Presentations skill 组装大纲、讲稿、SVG 与动画素材，并检查幻灯片版式和讲者备注。Manim 是按需安装的动画制作工具，不属于本项目 Web 服务的基础依赖。

## 快速开始（Windows）

在项目目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765
```

打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)，上传有使用权的 PDF，确认资料使用权后开始生成。可用[示例讲义](examples/binary_search_original.pdf)体验。生成完成后可查看来源、播放或下载视频、下载 PPTX，也可删除本地任务和资料。旧任务若没有 PPTX，重新上传原 PDF 即可生成。失败任务可用原 PDF 重新生成。按 `Ctrl+C` 关闭 Web 服务。

运行环境为 Python 3.11+；选择系统配音时需要 Windows 中文系统语音。已在 Python 3.13 上验证。`rapidocr` 和 `onnxruntime` 在本机执行 OCR，`pypdfium2` 负责扫描页渲染。`python-pptx` 生成课件，`imageio-ffmpeg` 提供视频与内嵌动画合成所需的 FFmpeg，无需单独安装系统 FFmpeg。

## 使用本机 Ollama

安装并启动 [Ollama](https://ollama.com/)，通过 `ollama list` 检查模型。默认模板使用 `qwen3:4b`；如果本机没有该模型，可运行 `ollama pull qwen3:4b`。复制配置模板后重启 Web 服务：

```powershell
Copy-Item .env.local.example .env.local
```

`.env.local` 已加入 `.gitignore`。可在其中修改 Ollama 地址和模型名。真实 AI 模式通过本机 `/api/chat` 生成知识点、课程规划和讲稿；PDF 提取文本不会发送到外部文本模型。模型先选择带页码的原文片段编号，程序再填入并核验引文，减少模型改写原文造成的错误。

讲稿中的具体数字须出现在对应原文摘录中；若模型加入无来源的数值，程序会要求重写一次，仍不符合时删去相关句子或要点，并在结果中提示人工重点检查。这个检查不能证明全部知识解释正确；缺少算例的资料可能产生更偏概念说明的讲稿，正式教学前仍需人工核对。

也可以不创建 `.env.local`，直接在网页选择真实 AI 模式并填写本次任务的 API 配置。API 密钥仅在任务运行期间留在服务进程内存，不写入 SQLite、课程 JSON 或网页响应；刷新页面或服务重启后重试外部模型任务，需要重新输入密钥。自定义提示词作用于课程规划和讲稿风格，不能绕过来源核验。

已生成的[示例视频](demo/zhijiang_ollama_demo.mp4)与[讲稿及来源](demo/zhijiang_ollama_lesson.json)可直接查看。示例视频的讲稿由本机模型生成，声音来自 Windows 系统语音。

## 使用本机 AI 配音

本机无 NVIDIA 显卡时，可通过 CPU 运行支持中文的 [Kokoro-82M v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)。在项目目录安装可选依赖并下载 [ONNX Community 的量化模型](https://modelscope.cn/models/onnx-community/Kokoro-82M-v1.1-zh-ONNX)及 4 种中文音色（约 130 MB，保存在忽略提交的 `data/models/kokoro/`，下载脚本会校验 SHA-256）：

```powershell
.\.venv\Scripts\python -m pip install -e ".[local-tts]"
.\.venv\Scripts\python scripts\download_local_tts.py
```

在一个终端启动本机语音 API，并保持运行：

```powershell
.\.venv\Scripts\python -m uvicorn zhijiang.local_tts:app --host 127.0.0.1 --port 8766
```

在另一个终端启动主 Web 服务。复制 `.env.local.example` 为 `.env.local` 后，网页会默认填入 `http://127.0.0.1:8766/v1`、模型 `kokoro-82m-v1.1-zh` 和中文音色 `zf_001`。还可选择 `zf_002`、`zm_009`、`zm_010`。也可不创建配置文件，直接在网页选择“AI 语音配音”并填写这些值。本机接口无需 API 密钥，语音合成在本机进行；首次请求需加载模型，长讲稿在 CPU 上需要更多时间。可打开 [语音服务健康检查](http://127.0.0.1:8766/health)确认模型文件已安装。

## 外部模型与语音服务

如需使用外部文本模型，在启动服务前设置兼容 `POST /chat/completions` 的服务地址、模型名和密钥：

```powershell
$env:ZHIJIANG_LLM_PROVIDER = "openai"
$env:ZHIJIANG_LLM_BASE_URL = "https://你的服务地址/v1"
$env:ZHIJIANG_LLM_API_KEY = "你的密钥"
$env:ZHIJIANG_LLM_MODEL = "你的模型名"
```

外部 AI 配音需要兼容 `POST /audio/speech` 并能返回 WAV。以下变量可替换 `.env.local` 中的本机语音配置；也可在网页为单次任务填写：

```powershell
$env:ZHIJIANG_TTS_BASE_URL = "https://你的语音服务地址/v1"
$env:ZHIJIANG_TTS_API_KEY = "你的语音密钥"
$env:ZHIJIANG_TTS_MODEL = "你的语音模型名"
$env:ZHIJIANG_TTS_VOICE = "alloy"
```

使用外部服务时，网页会要求额外确认发送提取文本或讲稿。语音和文本 API 密钥仅在任务运行期间保留在服务进程内存；失败后重试外部语音任务需要重新输入语音密钥。不要将密钥提交到仓库。

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
- PPTX 为每个片段生成一张 SVG 图示页和一张内嵌静音 MP4 的动画页；放映时点击播放，讲者可按备注讲解。课件大小和制作时间随片段数量增加。PowerPoint 可编辑标题、来源标签等原生文字；SVG 是矢量图片对象，不能直接逐个编辑其中的线条与文字。
- 支持概念卡片、公式步骤和流程画面。自动动画以数字、关系和步骤的逐步呈现为主，复杂 Manim 动画、跨章节连续性与知识事实自动证明尚未实现。
