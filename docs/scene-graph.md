# 通用教学场景 / General teaching scenes

[中文 README](../README.md) · [English README](../README.en.md)

## 中文

### 不以学科名称限制生成

`visual_scene.domain` 是说明性文本，不是执行器白名单。新的学科、交叉主题或专题可以直接使用通用图形和参数步骤，不必先添加学科分支。`auto` 为可识别的二维线性变换选择专用执行器，其余 AI 课程进入通用场景；`visual` 强制通用场景。环境缺失时 auto 明确使用基础回退，分镜无效时尝试修正，仍失败则报错。

通用场景与专用执行器可以共同发展：通用层承接任意学科的二维表达，专用层用于加强某些主题的推理规则、可读性与核验。学科范围开放不证明任意资料的自动讲解质量相同。

### 数据链路

1. 从 PDF 提取带编号的原文依据，模型规划知识点及顺序。来源编号保持稳定，标题可以改写。
2. 为每个片段分两次调用规划对象布局与操作计算。布局阶段确定 3–5 步的 `step_count`，操作阶段的输出契约要求相同步数，避免重复追加；合并为 `visual_scene`：问题、对象、参数、步骤、计算、来源和示意简化。
3. 核验受限表达式、对象引用、坐标、五个插值状态和声明的数值关系。纯淡入要点的场景被拒绝。
4. 新模型分镜将数值口播绑定到已核验参数与计算。自由口播只描述对象、操作和原因，未绑定的字面数字及常见中文数值断言被拒绝；程序补入当前参数和结果，再调用语音 API。新分镜每段规划 3–5 步，每步定性口播 12–100 字符，输出约束也限制文本长度，避免本机模型在单个字符串内用尽输出预算；旧场景契约继续兼容。实际音频长度决定变化与停顿。这个约束不能证明全部定性解释或领域含义。
5. Manim 在连续参数状态中重新计算曲线与对象位置；公式数值随当前状态更新，逐帧执行声明的关系和已注册领域规则。
6. 记录实际图形坐标检查与参数采样。终态生成 SVG 摘要；相同带配音 MP4 用于完整视频和 PPTX。备注保留来源、逐步口播、参数与简化条件。

### 场景契约

| 字段 | 用途 |
| --- | --- |
| `objects` | `dot`、`circle`、`line`、`arrow`、`polygon`、`curve`、`label`；稳定 ID 与颜色 |
| `parameters` | 初始命名数值；步骤只能修改已声明的参数 |
| `position` / `start` / `end` / `vertices` | 点位置、线的两端及多边形顶点；旧 `points` 坐标定义继续兼容 |
| `expression` / `domain` | 曲线函数和定义域，例如 `x**2`、`a*sin(x)` |
| `beats` | 口播、参数变化、显示与隐藏操作、对应计算；对象跨步骤保留身份 |
| `checks` | 全程成立的数值相等、非负、上界及安装规则；单步结果写入 calculations |
| `domain_data` | 字符串形式的领域上下文，例如单位、元素标识、机制条件 |
| `domain_validators` | 可信领域插件名称；插件接收整个场景和当前参数 |
| `evidence` / `simplifications` | 原文依据与示意条件；计算检查不能代替领域事实核查 |
| `narration_binding` | 程序设置 `computed`，数值由参数与计算生成；旧数据默认空值继续兼容 |

表达式只允许数字、已声明参数、`x`（曲线变量）、`pi`、`e`、四则、有限幂及 `sin/cos/tan/sqrt/exp/log/abs/min/max`。模型分镜的数值容差固定为程序控制的 `1e-6`，不能放宽容差绕过错误计算。禁止 Python 代码、属性访问、导入、网络或模型自写 SVG/TeX。LaTeX 由受限数学 AST 转换生成。

### 扩展规则

普通新专题使用现有原语直接规划即可。需要专门核验时，在受信任的 Python 项目中实现数值检查 `checker(value, expected, tolerance) -> bool`，或领域检查 `validator(scene, parameters) -> {"passed": bool, ...}`。通过安装入口让 Web 服务和 Manim 子进程加载相同实现：

```toml
[project.entry-points."book2course.visual_checks"]
my_numeric_rule = "my_course_rules:check_value"

[project.entry-points."book2course.visual_validators"]
my_domain_rule = "my_course_rules:check_scene"
```

模型只选择已安装规则的名称，不能生成或注册 Python 实现。领域插件可以根据 `domain_data`、对象及参数检查物理量纲、化学计量、关系约束或其他条件；未知规则明确报错。也可以在项目初始化代码中注册规则，但须确保服务器与渲染子进程都执行该初始化。

新图形原语扩展 `SceneObject` 契约、`visual_planning.object_geometry`、`visual_renderer` 构造及 SVG 导出，并同时增加起点、中间状态、终点和源含义验收。复杂三维、真实分子动力学等需要对应执行器，不能用二维插值冒充真实机制。

### 核验与示例

`scripts/build_general_examples.py` 提供原创开发者分镜：割线逼近、概率面积分配、抛体运动与机械能、原子重排及酶催化流程。它们使用同一执行器，无学科渲染分支。这些回归素材与真实模型自动规划的 PDF 任务分别验收。

```powershell
.\.venv\Scripts\python scripts\build_general_examples.py
.\.venv\Scripts\python scripts\verify_teaching_artifacts.py --job-dir data\exports\general-examples
```

报告分别记录计算与几何、来源、关键帧、完整媒体播放、人工听感和 PowerPoint 放映。缺少相应检查时不能标为全部通过。

## English

### Subject-independent generation

`visual_scene.domain` is descriptive text, not an executor whitelist. New subjects and interdisciplinary topics use the same primitives and parameter steps without adding a subject branch. Auto mode selects the specialized executor for recognized 2-D linear transformations and general scenes for other AI lessons. Visual mode requires general scenes. Missing dependencies produce an explained auto fallback; invalid storyboards are revised or rejected.

The general layer handles parameterized 2-D teaching across subjects. Specialized executors can add stronger reasoning, presentation, and checks for particular topics. Open subject scope does not establish equal automatic teaching quality for every source.

### Contract and execution

Stable source IDs connect PDF excerpts to course order. Separate calls draft object layout and operation/calculation steps. Layout chooses a `step_count` of 3–5, and the sequence contract requires that exact count to prevent repeated tails. Merge questions, persistent objects, parameters, narration, calculations, source evidence, and simplifications. Primitive types are dots, circles, lines, arrows, polygons, curves, and labels. Named parameters drive coordinates or curve expressions, and steps show/hide objects or change values. Points use `position`, lines use `start/end`, polygons use `vertices`; legacy `points` remains readable. `checks` must hold throughout all frames; step-specific results belong to `calculations`. Scenes with only progressive bullet reveals are rejected.

Restricted expression and geometry checks include five interpolation states. Actual speech durations control animation and holds. Manim recomputes geometry and numeric formulas as parameters change and executes declared numeric/domain checks on rendered frames. The report records parameter paths and actual coordinate checks. SVG summaries, full lesson MP4s, PPTX clips, and speaker notes share the same scene data. Clips retain narration and 16:9 proportions.

The program sets `narration_binding=computed` for new model scenes: qualitative prose describes objects and operations, while verified parameters/calculations generate numeric speech. Unbound literal digits and common Chinese numeric assertions are rejected before audio synthesis. New storyboards draft 3–5 steps with 12–100 characters of qualitative speech per step; the output constraint also bounds prose length to avoid exhausting the local model's token budget within one string. The older scene contract remains readable. This is not a proof of all qualitative meanings.

Expressions allow numbers, declared parameters, the curve variable `x`, constants `pi/e`, arithmetic, bounded powers, and `sin/cos/tan/sqrt/exp/log/abs/min/max`. Model-drafted checks use a program-controlled `1e-6` tolerance; a model cannot loosen it to approve wrong calculations. Python code, attribute access, imports, networking, and model-authored SVG/TeX are rejected. Trusted AST conversion generates LaTeX.

### Extensions

Use existing primitives for ordinary new topics. Add trusted numeric rules with `checker(value, expected, tolerance) -> bool` or full-context rules with `validator(scene, parameters) -> {"passed": bool, ...}`. The Python entry points shown above load matching implementations in the server and Manim child process. The model can name installed rules but cannot implement or register code. `domain_data` holds string-valued context for units, elements, relationships, or mechanism conditions. Unknown rules fail explicitly. Direct registration must run in both processes.

Extend the object contract, geometry computation, Manim construction, and SVG export together for new primitives. Add source, initial-state, intermediate-state, and endpoint validation. Complex 3-D or molecular dynamics requires a corresponding executor; a 2-D parameter interpolation is not a physical mechanism simulation.

### Validation

`build_general_examples.py` provides authored regression models for secant limits, probability partitions, projectile motion and energy, atom rearrangement, and enzyme processes, all using one executor. These exercise rendering and declared relations; real model planning is tested separately with PDF uploads. Use `verify_teaching_artifacts.py` for generic or specialized job artifacts. Keep calculation/geometry, source review, key frames, playback, listening, and PowerPoint slideshow results separate.
