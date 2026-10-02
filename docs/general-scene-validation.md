# 跨学科教学场景验证 / Cross-subject scene validation

[中文 README](../README.md) · [English README](../README.en.md) · [场景架构 / Architecture](scene-graph.md)

## 中文

### 范围与方法

本次改动使学科名称成为描述字段，而不是生成路径的白名单。通用执行器按对象、受限表达式、参数和步骤渲染；数值关系与完整领域规则可以通过可信 Python 安装入口扩展。新学科不需要增加一个学科判断分支。

验证分为开发者分镜回归与真实 PDF 模型规划两类。两者不能相互替代：前者检验表达能力、计算和渲染，后者检验模型是否能从资料设计正确、可执行的教学过程。通用计算通过不代表来源含义或专业机制已得到证明。

### 五组原创回归示例

`scripts/build_general_examples.py` 生成原创依据 PDF 和分镜，调用本机 Kokoro 中文语音 API，再使用与网页相同的通用 Manim Cairo 执行器。没有按学科切换的渲染分支。

| 示例 | 连续过程与检查 | 明确的简化 |
| --- | --- | --- |
| 微积分 | 固定 P，Q 沿 `x²` 移动；h 从 1 到 0.4、0.1；割线斜率从 3 到 2.4、2.1，对照切线斜率 2 | 有限割线不是极限切线 |
| 概率 | 同一矩形的事件和补事件面积随 p=0.2、0.5、0.8 改变；归一化、非负与上界 | 面积份额不是采样频数 |
| 物理 | `x=t, y=2t−t²/2` 的小球连续运动；对应时刻机械能保持 2.5 | 单位质量与示例单位，恒定重力，无空气阻力 |
| 化学 | 六个原子保持身份和颜色，断开旧键、重排、形成两份水的示意；4H、2O 的声明计量条件 | 不是键角、电子机制或真实反应动力学模拟 |
| 生物 | 底物接近活性部位、结合、转换标记、产物释放；同一酶对象保持 | 不指定真实酶结构、反应或速率 |

产物位于 `data/exports/general-examples/`：完整 `lesson.mp4`、`lesson.pptx`、`scene-data.json`、逐段配音、SVG/PNG、场景源文件、渲染几何记录及 `validation.json`。这些分镜由开发者编写，产物通知中明确说明，不能称为模型自动规划验收。

完整视频为 1280×720、30 fps、H.264/AAC，视频流 141.767 秒、音频流约 141.798 秒。全视频逐帧解码 4,253 帧且音频非静音。PPTX 为 11 页，含五个 SVG 和五个带配音的视频；每段视频与完整教学素材的文件字节相同，按 16:9 嵌入。全部页保留讲者备注。脚本重新计算每个声明关系，检查起始数据、实际图形终点、连续参数采样与音频时间线。

讲者备注与实际合成口播逐句核对，包括程序补入的计算结果。验证器还抽取真实视频中间帧，测量颜色唯一的运动点与计算位置的像素距离，并检查运动足够远时旧位置没有残留标记；共享颜色与其他原语由几何记录及人工关键帧检查覆盖，没有声称全部原语完成像素级核验。另一个实际渲染回归验证了零长度箭头展开为非零箭头，三个步骤的坐标误差均为零。

### 视觉检查

已检查五组初态、中间状态和终态关键帧，并使用本机 PowerPoint 打开课件、导出全部 11 页静态预览。检查中修复了动态数值被遮罩隐藏、点标记过大、坐标标签被遮挡、坐标轴覆盖运动点和 SVG 摘要未显示计算值的问题。完整视频统一为恒定 30 fps，避免分段音轨时长产生拼接时间基偏差。

真实微积分片段还暴露了旧 Q 点和旧割线残影：几何记录正确，但 Cairo 在动画开始时展开图形族，保留了后来被替换的子图形。执行器现按帧从当前根容器取得图形族，全部五组回归素材及四个真实 PDF 片段已重新渲染。原片旧位置检测到 136 个残留像素；另一个实际 Cairo/FFmpeg 短回归在修复后为零，中间点误差小于 0.4 像素。短回归使用每步两秒的合成静音，只检验几何与残影，不作为配音质量验收。

静态导出、完整解码不等于 PowerPoint 放映点击或人工试听。**PowerPoint 放映播放与实际听感尚未验收。**打开课件后在第 3、5、7、9、11 页点击视频，可检查声音、操作按钮和投影阅读效果。

完整跨学科视频已在浏览器从头播放到结尾，最终 `ended=true`、`error=null`、`muted=false`，时长 141.798 秒；记录为本地 `browser-playback.json`。这确认浏览器可完整播放，不代表已人工评价听感。

### 真实 PDF 与模型规划

使用 MIT OCW 的两页 [Geometric definition of the derivative](https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/resources/mit18_01scf10_ses1c/)，保留来源摘录与页码。页面中的 P、Q、割线与切线图已检查；`x²` 的具体数值作为原创教学示例。许可参见 [MIT OCW 条款](https://ocw.mit.edu/pages/privacy-and-terms-of-use/)。

本机 `qwen3:4b` 的真实尝试暴露了自由变量、割线结果、对象坐标和恒成立检查混淆的问题。程序拒绝错误分镜，保存草稿，并尝试修正；不会把失败任务称为正确动画。人工补查还发现：模型审稿曾批准包含错误斜率的自由口播，虽然 calculations 正确。因此新增 `narration_binding=computed`：未绑定的字面数字及常见中文数值断言被拒绝，参数和计算结果由程序生成口播。科学名称中已声明的对象标识（如 H2O）继续允许，不把名称数字当成计算结果。定性解释仍需要来源和人工核对。

用户教学偏好和计算修正指令已从教材数据中分离，原文和模型旧稿仍作为数据处理。真实输出还暴露了无限延长口播耗尽输出预算，以及重复 LaTeX 转义串被审稿模型批准的问题。新分镜的解码约束限制每步定性口播长度，并拒绝方程符号与转义串；配音前再次核查。重试接口已修复为使用当前网页设置；旧媒体目录清理也有回归检查。失败草稿与被人工拒绝的口播保存在本地 `data/exports/general-pdf-validation/`。

最终网页任务 `0b9f829792524bb79278866f665384b3` 使用真实 MIT PDF、本机 `qwen3:4b` 和 Kokoro。开发者在提示词中明确提供对象、公式、h 的变化及三步自然语言讲解指引；模型在四个知识点中重复使用同一示例。因此这次结果不能作为无引导课程设计能力的证明。模型审稿未发现三处割线颜色与口播不一致，人工将第 1、3、4 个场景的割线由蓝色改为橙色，再用同一执行器重新渲染全部四个场景。网页通知明确披露指引与人工修正，原始自动产物保存在 `original-auto/`，修正记录为 `human-review.json`。

最终交付位于 `data/exports/general-pdf-validation/completed/`。独立 SymPy 计算确认割线斜率为 `2a+h`，a=1、h=1、0.2、0.1 时为 3、2.2、2.1，切线斜率为 2；有限割线与极限切线分别说明。完整视频长 139.900 秒，1280×720、30 fps、H.264/AAC，4,197 帧全部解码且音频非静音。9 页 PPTX 包含四个 SVG、四个与场景素材字节相同的配音视频，保持 16:9，讲者备注匹配实际口播。

已核对来源图示与摘录，检查四场的初态、中间状态、终态及全部九页本机 PowerPoint 静态导出。最终视频在网页完整播放，`ended=true`、`error=null`、`muted=false`；网页下载的 PPTX 和场景 JSON 与交付文件 SHA-256 相同。计算核验、来源核对和人工视觉检查分别记录；**人工试听和 PowerPoint 放映点击播放尚未验收。**

### 自动测试与复现

全套自动测试 71 项通过，通用场景测试包括任意新领域路由、六类主题的同一参数契约、错误计算与中间状态拒绝、代码/未声明表达式拒绝、领域插件、旧坐标兼容、明确点/线坐标、程序字段不由模型生成、闭合运动，以及视频旧位置残留标记拒绝。

```powershell
.\.venv\Scripts\python -m pip install -e ".[math-animation,test]"
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\build_general_examples.py
.\.venv\Scripts\python scripts\verify_teaching_artifacts.py --job-dir data\exports\general-examples
```

场景原语和领域插件扩展方法见[架构文档](scene-graph.md)。教材与生成媒体保存在 Git 忽略的 `data/` 中；代码、验证工具及文档提交到仓库。

## English

### Scope

Subject names are descriptive rather than a generation whitelist. One interpreter renders persistent objects, restricted expressions, parameter changes, and narrated steps. Trusted numeric and full-context domain plugins extend validation. New subjects do not require a subject routing branch.

Authored regression fixtures and real PDF/model planning are separate tests. Rendering and declared numeric checks do not establish correct interpretation of sources or scientific mechanisms.

### Authored fixture results

`build_general_examples.py` supplies an original reference PDF and five developer-authored storyboards, explicitly labeled as such. The same generic executor and local Kokoro speech API render all of them:

- Calculus: fixed P, Q moving along `x²`, h=1, 0.4, 0.1, computed secant slopes 3, 2.4, 2.1 versus tangent slope 2. Finite secants are not claimed to equal the limit.
- Probability: complementary area partitions for p=0.2, 0.5, 0.8 with normalization and bounds; area shares are not sample frequencies.
- Physics: a projectile follows `x=t, y=2t−t²/2` with constant energy 2.5 under stated ideal assumptions.
- Chemistry: six persistent atoms, old bonds hidden, rearrangement, and two schematic water molecules, retaining declared 4H/2O counts. No real kinetics or electronic mechanism is claimed.
- Biology: schematic binding, conversion, and release with an unchanged enzyme object; no real molecular structure or rate model is claimed.

Local output is under `data/exports/general-examples/`, with a PPTX, full MP4, scene JSON, speech, SVG/PNG, source files, rendered geometry, and verification report. The full movie is 1280×720 at 30 fps with H.264/AAC: 141.767 seconds of video and approximately 141.798 seconds of audio, 4,253 decoded video frames, and non-silent audio. The 11-slide deck contains five SVGs, five narrated clips matching the scene media byte-for-byte, original 16:9 proportions, and notes on every slide.

Notes are checked against the actual synthesized step text, including computed results. Real intermediate movie frames are measured against calculated positions for uniquely colored moving dots, with old-position absence checks when movement is sufficiently large. Shared colors and other primitives use geometry logs and manual keyframes, without claiming pixel checks for every primitive. A separate actual render regression expands a zero-length arrow into a nonzero arrow, with zero coordinate error in all three steps.

Initial, intermediate, and final frames and all 11 native PowerPoint static exports were inspected. Hidden dynamic numbers, oversized markers, masked axis labels, axes covering moving points, missing SVG numeric summaries, and concat time-base discrepancies were corrected. **Human listening and PowerPoint slideshow click playback remain unverified.** Static exports and media decoding do not satisfy those checks.

The real calculus clip also exposed stale Q points and secants despite correct geometry logs. Cairo flattened families at animation start and retained children later replaced by the interpreter. Rendering now captures the current root families each frame; all five fixtures and four real-PDF clips were rebuilt. The original clip had 136 residual pixels at an old position. A separate actual Cairo/FFmpeg regression has zero after repair and intermediate point errors below 0.4 pixels. Its synthetic two-second silent steps test geometry and stale shapes, not speech quality.

The full cross-subject movie was played from start to end in the browser, with `ended=true`, `error=null`, `muted=false`, and a 141.798-second duration, recorded in local `browser-playback.json`. This confirms complete browser playback, not a human evaluation of listening quality.

### Real source and model planning

The real upload source is MIT OCW's two-page [Geometric definition of the derivative](https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/resources/mit18_01scf10_ses1c/). Its P/Q, secant, and tangent diagram and excerpts were reviewed; numeric `x²` examples are supplemental. Retain [MIT attribution and licensing](https://ocw.mit.edu/pages/privacy-and-terms-of-use/).

Actual local `qwen3:4b` attempts exposed undefined variables, incorrect slopes, confused object coordinates, and final values incorrectly declared as all-frame invariants. Invalid storyboards are rejected, saved, and revised. Manual inspection also found that model review approved false spoken slopes despite correct calculations. New `narration_binding=computed` rejects unbound literal digits and common Chinese numeric assertions, then generates numeric speech from verified parameters/results. Declared scientific object identifiers such as H2O remain permitted. Qualitative meanings still require source and human review.

Human teaching preferences and computed repair instructions are separated from untrusted source/draft data. Actual output also exposed unbounded prose exhausting the output budget, and repeated LaTeX escape strings approved by model review. New decoding constraints bound qualitative prose and reject equation symbols/escape strings, with another check before speech synthesis. Retry now adopts current page settings, and obsolete media-directory cleanup has regression coverage. Rejected drafts and manually rejected speech are retained under local `data/exports/general-pdf-validation/`.

Final web job `0b9f829792524bb79278866f665384b3` used the real MIT PDF, local `qwen3:4b`, and Kokoro. A developer explicitly supplied objects, formulas, the h sequence, and three natural-language teaching cues in the prompt. The model reused the same example across four knowledge points, so this does not establish unguided course-design capability. Model review missed three secant colors inconsistent with the narration. Human review changed the secants in scenes 1, 3, and 4 from blue to orange, then rebuilt all four scenes using the same executor. The web notice discloses guidance and corrections, original automatic output remains in `original-auto/`, and `human-review.json` records repairs.

Final delivery is under `data/exports/general-pdf-validation/completed/`. Independent SymPy calculations confirm slope `2a+h`: for a=1 and h=1, 0.2, 0.1, the secant slopes are 3, 2.2, 2.1 versus tangent slope 2. Finite secants and the limiting tangent are explained separately. The complete movie is 139.900 seconds, 1280×720, 30 fps, H.264/AAC, with all 4,197 frames decoded and non-silent audio. The nine-slide PPTX contains four SVGs and four narrated clips matching scene media byte-for-byte, at 16:9, with notes matching actual speech.

Source diagrams and excerpts, all four initial/intermediate/final states, and all nine native PowerPoint static exports were inspected. Final browser playback reached `ended=true`, `error=null`, `muted=false`; downloaded PPTX and scene JSON matched delivery SHA-256 hashes. Computation, source meaning, and human visual inspection are reported separately. **Human listening and PowerPoint slideshow click playback remain unverified.**

### Reproduction

Install `.[math-animation,test]`, run `python -m pytest`, then `build_general_examples.py` and `verify_teaching_artifacts.py --job-dir data/exports/general-examples`. All 71 automated tests pass. Tests cover arbitrary subject routing, six domains using one contract, wrong calculations/intermediate states, prohibited code, custom domain rules, legacy coordinates, explicit point/line contracts, program-owned fields, closed-loop motion, and stale movie markers. See [the architecture](scene-graph.md) for primitive and plugin extensions. Generated sources and media remain in ignored `data/`; source code, verification tools, and documentation are committed.
