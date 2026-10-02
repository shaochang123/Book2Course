# 数学动画验证报告 / Math animation validation report

[中文](#中文验证记录) · [English](#english-validation-record) · [中文 README](../README.md) · [English README](../README.en.md)

## 中文验证记录

本轮验证覆盖二维线性变换，不代表任意数学或其他学科已经支持同等推演。计算、来源位置、视觉检查、浏览器播放和 PowerPoint 放映分别记录。程序解码成功不等于人工试听合格。

### 资料与环境

采用 MIT OCW 五页讲义 [Linear transformations and their matrices](https://ocw.mit.edu/courses/18-06sc-linear-algebra-fall-2011/resources/mit18_06scf11_ses3-6sum/)。已阅读全部五页并检查对应引文。原理引文保留页码，以下矩阵、向量、平移与伸缩数值算例，以及面积讲解，均标注为补充教学示例。讲义中的三维和函数空间内容不纳入本轮课程。课件封面与讲者备注记录 MIT 来源及其 [CC BY-NC-SA 4.0 许可](https://ocw.mit.edu/pages/privacy-and-terms-of-use/)。

本机实际生成使用 Python 3.13、Ollama `qwen3:4b`、Kokoro `kokoro-82m-v1.1-zh` / `zf_001`、Manim Community 0.21.0、SymPy 1.14.0、Cairo 和已有 TeX Live 2026。文字规划、逐句配音和动画渲染均在本机完成。

| 场景 | 原理来源 | 已检查的过程与结论 |
| --- | --- | --- |
| 线性与平移反例 | 第 1 页 | 平行四边形、两种加法路径、齐次性、平移使原点不再固定 |
| 基向量与矩阵列 | 第 3 页 | 基向量去向、矩阵的两列、向量分解及重新合成 |
| 平面变换 | 第 2 页的矩阵映射原理 | 网格、向量与单位正方形共同变化；面积为原创补充 |
| 45° 投影 | 第 4 页 | 沿法线投影、幂等性、平行与垂直特征方向、换基后的对角矩阵 |
| 复合顺序 | 第 4 页的复合原理 | 先旋转后伸缩与反序的中间状态及不同终点 |

### 两组真实任务

第一组通过网页上传讲义、选择严格数学模式并调用本机模型；第二组再次上传相同 PDF，通过 `auto` 模式指定另一矩阵。两组都经过模型规划、真实配音、Manim 渲染和 PPTX 导出。第一组最终文件还经过网页下载及 SHA-256 一致性检查。

| 检查项 | 第一组 | 矩阵对照组 |
| --- | --- | --- |
| 任务 ID | `6a1faecd1dd44f6fbec91c9ece9fe22f` | `b3e25f18b3154ee483a3b9c6fef3cdc4` |
| 矩阵 A，输入 v=(1,2) | `[[2,1],[0,1]]` | `[[1,0],[2,1]]` |
| 计算 Av | `(4,2)` | `(1,4)` |
| 单位正方形变换后的面积 | `2` | `1` |
| 完整视频时长（视频流） | 315.733 秒 | 315.833 秒 |
| PPTX | 11 页、5 个 SVG、5 个带配音视频 | 11 页、5 个 SVG、5 个带配音视频 |

前三类场景的矩阵列、终点、公式、网格及 SVG 按新矩阵重新生成。投影和旋转/伸缩使用各自独立参数，其核验结果保持一致；模型生成的问题措辞可以不同。

### 计算、连续过程与媒体检查

- SymPy 核验加法与齐次关系、矩阵列、向量终点、投影幂等性、特征方向、换基与复合。面积另用顶点鞋带公式核对，避免只重复同一面积表达式。
- 实际渲染记录起点、中间状态与终点的对象坐标。第一组投影记录 113 个连续采样；两次旋转分别记录 101、85 个采样。法线投影路径、旋转长度误差均小于 `1e-6` 验收阈值。
- 数学口播绑定已计算状态，保留模型分镜草稿供查阅。本机小模型曾在自由口播中混淆方向或中间值，因此最终采用参数化的事实说明；正确计算声明不能单独证明自由口播正确。
- 两组全部分段和完整 MP4 均完成逐帧视频、逐帧音频解码，音频非静音；1280×720、30 fps、H.264/AAC。第一组完整视频的音视频时长差约 0.014 秒，对照组约 0.003 秒。
- PPT 中视频的 SHA-256 与对应教学分段一致，均保持 16:9。全部页有讲者备注，保存口播、参数条件和来源；SVG 含 PNG 兼容图。
- 全套自动测试 **71 项通过**，包含错误计算、错误步骤顺序、被篡改口播、非有限参数、三维矩阵与歧义输入拒绝，旧数据兼容，以及严格数学失败与自动基础回退。

### 来源与视觉检查的实际状态

已逐页检查五页讲义及引文含义；两组检查脚本再次校验原文摘录位置。已检查各场景关键初态、中间态和终态，以及矩阵对照画面。第一组 PPTX 由本机 PowerPoint 打开并导出全部 11 页静态预览，逐页检查文字、公式、颜色、比例和遮挡。检查发现并修正了 Office 中 SVG 箭头颜色及投影线进入文字区的问题，重新生成最终文件后复查。

最终第一组视频在网页从头播放到结尾：播放器记录 `ended=true`，时间 315.754 秒，未静音，无媒体错误。浏览器播放与完整解码只证明播放链路及技术时间线，不代替用耳朵判断发音、停顿和教学节奏。

**尚未完成的人工验收：PowerPoint 放映中的点击播放与实际听感。**当前自动化环境没有可操作的 PowerPoint 界面或连接会话，静态导出与 OOXML 检查不能作为该项通过。可打开第一组 `lesson.pptx`，进入放映，在第 3、5、7、9、11 页点击视频，确认声音、播放按钮、公式可读性、比例与遮挡，并试听全部课程。此项未标为通过。

### 本地产物与复现

两组原始产物位于 `data/test-runs/linear-transformations/web/jobs/<任务 ID>/`。交付副本位于 `data/exports/linear-transformations/default/` 与 `changed-matrix/`，包含 `lesson.pptx`、`lesson.mp4`、`math-scenes.json`、`validation.json` 和场景素材。另有 `matrix-comparison.json`、对照画面、网页播放记录及静态预览。`data/` 在 Git 中忽略，二进制教材与媒体不随代码推送。

安装与复核：

```powershell
.\.venv\Scripts\python -m pip install -e ".[math-animation,test]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\verify_math_artifacts.py --job-dir data\jobs\你的任务ID
```

复核脚本生成 `validation.json` 与关键帧拼图，只记录其实际完成的计算、引文和媒体检查。跨学科通用场景已另外实现，使用参数化对象与可扩展领域规则；详见[通用场景架构](scene-graph.md)和[跨学科验证记录](general-scene-validation.md)。本报告只证明这里列出的线性变换任务。

## English validation record

This validation covers 2-D linear transformations. It does not establish equivalent reasoning quality for arbitrary mathematics or other subjects. Calculation checks, source review, visual inspection, browser playback, and PowerPoint slideshow playback are separate checks.

### Source and runtime

The source is MIT OCW's five-page [Linear transformations and their matrices](https://ocw.mit.edu/courses/18-06sc-linear-algebra-fall-2011/resources/mit18_06scf11_ses3-6sum/). All five pages were reviewed. Principle excerpts retain page numbers; numeric matrices, vectors, translations, stretches, and area explanations are labeled supplemental teaching examples. The source's 3-D and function-space material is outside this lesson. The cover and notes retain MIT attribution and the [CC BY-NC-SA 4.0 license](https://ocw.mit.edu/pages/privacy-and-terms-of-use/).

Actual local generation used Python 3.13, Ollama `qwen3:4b`, Kokoro `kokoro-82m-v1.1-zh` / `zf_001`, Manim Community 0.21.0, SymPy 1.14.0, Cairo, and the existing TeX Live 2026. Planning, phrase-level speech, and rendering ran locally. Source pages are 1 for linearity, 3 for basis columns, 2 for the plane's matrix mapping, and 4 for projection and composition. Area is supplemental.

### Actual generation and results

The first job (`6a1faecd1dd44f6fbec91c9ece9fe22f`) was uploaded through the web interface in strict math mode. The second (`b3e25f18b3154ee483a3b9c6fef3cdc4`) uploaded the same PDF in auto mode with a different matrix. Both used the real local model and speech service, then rendered and exported all five scenes.

For `v=(1,2)`, changing A from `[[2,1],[0,1]]` to `[[1,0],[2,1]]` changed Av from `(4,2)` to `(1,4)` and the unit square's transformed area from 2 to 1. The first three scenes' columns, endpoints, formulas, grids, and SVGs changed accordingly. Independent projection and rotation/stretch calculations stayed consistent.

The full videos contain 315.733 and 315.833 seconds of video. Each PPTX contains 11 slides, five SVG summaries, five narrated MP4 clips, and speaker notes. All clips use 1280×720 at 30 fps, H.264/AAC, with non-silent audio. Full-video audio/video duration differences are approximately 0.014 and 0.003 seconds. Every embedded clip matches the corresponding rendered lesson clip by SHA-256 and preserves its original 16:9 ratio. The final first PPTX's web download also matches the generated file by SHA-256.

### Checks and review status

- SymPy checks linearity, columns, endpoints, projection idempotence, eigendirections, basis changes, and composition. An independent polygon shoelace calculation checks area.
- Rendered positions and continuous paths are recorded. The first job's projection has 113 samples; rotations have 101 and 85. Normal-path and length errors meet the `1e-6` threshold.
- Fact-bearing narration is bound to computed states; original model storyboard drafts remain available. This addresses incorrect free-form explanations observed with the small local model.
- **71 automated tests pass**, including rejection of wrong calculations, operation order, altered narration, non-finite values, 3-D matrices, and ambiguous input, plus compatibility and mode behavior.
- All source pages and excerpt meanings were reviewed. Critical initial, intermediate, and final frames from both jobs and matrix comparison frames were inspected. The first deck was opened by local PowerPoint and all 11 slides exported for static inspection. Office SVG arrow colors and projection/text overlap were corrected and the final deck reviewed again.
- The final first video played from beginning to end in the browser: `ended=true`, 315.754 seconds, unmuted, no media error. This and full decoding verify the playback path and technical timing, not pronunciation or teaching rhythm by listening.

**PowerPoint slideshow clicks and listening quality remain unverified.** The automation environment provides no operable PowerPoint UI or connected document session. Static exports and OOXML checks do not satisfy this check. Open the first `lesson.pptx`, start the slideshow, click videos on slides 3, 5, 7, 9, and 11, and check sound, controls, readable formulas, aspect ratio, and overlap. Listen to the full course. This gate is not reported as passed.

### Local deliverables and reproduction

Original jobs are under `data/test-runs/linear-transformations/web/jobs/<job ID>/`. Delivery copies are under `data/exports/linear-transformations/default/` and `changed-matrix/`, containing `lesson.pptx`, `lesson.mp4`, `math-scenes.json`, `validation.json`, and scene assets. Comparison data, frames, browser playback evidence, and static previews are also included. Git ignores `data/`; source PDFs and generated binary media are not pushed with code.

Install `.[math-animation,test]`, run `python -m pytest`, and use `python scripts/verify_math_artifacts.py --job-dir data/jobs/JOB_ID`. The script emits `validation.json` and a key-frame contact sheet, without claiming human listening or slideshow checks. A subject-independent scene graph is implemented separately; see [the architecture](scene-graph.md) and [cross-subject validation](general-scene-validation.md). This report establishes only the linear transformation jobs listed here.
