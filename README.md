# 智讲 Agent（Book2Course）

**语言 / Language：** [简体中文](README.md) | [English](README.en.md)

将有使用权的教材、讲义和知识型 PDF 转成可溯源的中文教学视频与 PPTX 课件。支持文字提取、本机 OCR、课程规划、讲稿、SVG 图示、配音及视频合成。网页可查看讲稿、PDF 页码、原文摘录和知识关系，并下载 MP4、PPTX 与场景数据。

**真实 AI 模式**使用本机 Ollama 或兼容服务；**确定性演示模式**无需模型和密钥，明确标注为规则生成。来源匹配、模型审稿和计算检查都有各自的范围，教学内容仍需人工复核。

## 快速开始（Windows）

在项目根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765
```

打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)，选择[原创示例 PDF](examples/binary_search_original.pdf)，确认使用权，使用演示模式和 Windows 系统语音体验。完成后查看讲稿、来源、视频与课件。**在启动服务的终端按 `Ctrl+C` 关闭服务**；关闭浏览器不会停止服务。

Python 要求 3.11+，已在 Python 3.13 上验证。系统配音需要 Windows 中文语音；其他环境可配置兼容语音 API。`imageio-ffmpeg` 提供 FFmpeg，无需安装系统 FFmpeg。

## 模型与动画配置

首次配置可复制模板；已有 `.env.local` 时直接编辑，保留现有配置：

```powershell
Copy-Item .env.local.example .env.local
ollama list
```

将 `ZHIJIANG_LLM_MODEL` 改为已安装的模型名，启动 Ollama，再重启 Web 服务。`.env.local`、模型权重、上传资料和生成物均被 Git 忽略。网页也可配置单次任务；外部服务须确认发送文本或讲稿，任务密钥仅在进程内存中保留。

```powershell
.\.venv\Scripts\python -m pip install -e ".[math-animation]"
```

| 动画方式 | 当前行为 |
| --- | --- |
| `auto` | AI 默认；按来源选择关系、流程、比较、原页或几何场景。环境未就绪时使用基础图示并说明原因。 |
| `visual` | 通用场景；未通过来源或执行检查时明确失败。 |
| `math` | 二维线性变换专用推演；需要相应原文和 TeX。 |
| `basic` | 基础要点图示；确定性演示使用此路径。 |

原生关系图与原页讲解无需 TeX；可计算几何和专用数学推演需要 `latex`、`dvisvgm`。系统语音、Kokoro、外部 API 与续跑见[生成配置与恢复](docs/生成配置与恢复.md)，图示和 skills 见[教学图示与动画](docs/教学图示与动画.md)。

## 文档与目录

| 入口 | 内容 |
| --- | --- |
| [文档导航](docs/README.md) | 阅读顺序与目录职责。 |
| [产品说明书](docs/产品说明书.md) | 产品目标、设计、价值与边界。 |
| [使用指南](docs/使用指南.md) | 启停、上传、查看、下载、重试、删除。 |
| [架构与接口](docs/架构与接口.md) | 实际模块、数据契约、API、状态与缓存。 |
| [实现状态与路线图](docs/实现状态与路线图.md) | 参考设计、已实现、部分实现与待开发项。 |
| [验证与验收](docs/验证与验收.md) | 自动测试、媒体检查和教学质量证据。 |
| [AI Coding 过程](docs/AI_Coding_全过程.md) | Codex 的实际用途、反馈、修复与提交。 |
| [来源与许可](docs/第三方来源与许可.md) | 依赖、模型和验证资料。 |

`zhijiang/` 为应用与生成模块，`tests/` 为自动测试，`scripts/` 为示例、验收和文档工具，`examples/` 为原创 PDF 与来源清单，`demo/` 为历史媒体，`data/` 为本机任务和模型数据。历史说明与发布包单独保留，见[历史材料](docs/archive/2026-09/README.md)。

## 流程

[![从 PDF 到视频与课件](docs/workflow.zh.svg)](docs/workflow.zh.svg)

定性图示先独立理解来源，再提取命题，按主语、谓词、宾语及条件构建知识关系。模型选择来源编号，程序绑定引文并共享 SVG/动画布局。参数化几何通过受限表达式与数值检查执行，不执行模型代码。详见[架构与接口](docs/架构与接口.md)。

## 测试与复现

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\build_demo.py
.\.venv\Scripts\python scripts\build_ollama_demo.py
.\.venv\Scripts\python scripts\verify_teaching_artifacts.py --job-dir data\jobs\你的任务ID
.\.venv\Scripts\python scripts\build_documents.py
```

AI 示例需要运行本机模型，确定性示例无需模型。文档导出到 `output/pdf/`，不生成任务或调用模型。完整操作和历史 Demo 版本见[演示操作说明](docs/Demo_操作说明.md)。

语言学、经济学、社会学和数据库设计教材选页已生成 22 段 SVG/有声动画、4 个 MP4 和 4 份 PPTX。媒体检查通过，教学质量部分通过。这些资料参与了调试，不是独立盲测，也不能证明整书覆盖，见[教材验证记录](docs/generalization-validation-2026-10.md)。

## 当前边界

- 单机顺序队列，一份 PDF 生成一节课。上传上限 200 MB，无固定页数或目标时长上限；长教材耗时和产物大小会增加。
- OCR 不保证复杂公式、表格和版面恢复准确；没有人工公式确认界面。
- 网页可查看课程和来源，尚未提供项目列表、知识点选择编辑、讲稿编辑或人工审核发布流程。
- PPTX 标题、来源标签与备注可编辑；SVG 路径不是独立的 PowerPoint 形状。通用/专用动画有配音，基础内嵌动画静音，完整视频有配音。
- 受限二维场景与来源关系追踪已接入；复杂三维机制、跨章推理、事实证明、独立 SRT/VTT 字幕与课程 ZIP 导出尚未实现。

源码使用 [MIT License](LICENSE)；第三方依赖和教材资料有各自许可，见[来源与许可](docs/第三方来源与许可.md)。
