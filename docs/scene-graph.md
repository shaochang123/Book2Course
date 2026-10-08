# 通用教学场景 / General teaching scenes

[中文 README](../README.md) · [English README](../README.en.md)

## 中文

### 不以学科名称限制生成

`visual_scene.domain` 是说明性文本，不是执行器白名单。新的学科、交叉主题或专题可以直接使用通用图形和参数步骤，不必先添加学科分支。`auto` 保留所有知识点，逐点进入通用场景；专用线性推演由 `math` 显式选择；`visual` 强制通用场景。环境缺失时 auto 明确使用基础回退，分镜无效时尝试修正，仍失败则报错。

通用场景与专用执行器可以共同发展：通用层承接任意学科的二维表达，专用层用于加强某些主题的推理规则、可读性与核验。学科范围开放不证明任意资料的自动讲解质量相同。

### 来源知识图谱

`teaching_graph.py` 在图示设计之前独立提取 `subject/predicate/object/fact_ids` 命题。设计模型只选 `source_proposition_id`，程序填入关系并检查端点全称和角色，不能另造关系。图示设计的对象候选首先使用这些命题中的名称；英文术语、代码字符串和符号可保留原语言，不为凑中文截断名称。命题读取与整页语义审稿分开，二者仍是模型判断。

`TeachingRelation` 扩展字段向后兼容：`binding`、`source_proposition_id`、`supporting_fact_ids`、`source_statements`、`condition`。单句主谓宾可用 `extractive`；新网页任务用 `semantic`，同时要求匹配独立命题，保留最多三条完整来源事实、原文及条件。`TeachingNode.kind` 区分实体、操作与条件。程序按图方向做拓扑分层，分支共享一层，循环保留为环；SVG 和 Manim 使用同一布局。

审稿批准绑定包含节点、关系、条件与口播的 `reviewed_design_digest`；缓存设计变更会失效。`source-propositions-XX.json` 是未批准命题草稿，不能当作已证明关系。`knowledge_graph` 在课程报告与网页中提供页码、命题、事实及摘录，不跨章节自动合并同名实体或推断因果。

匹配知识点原始引文的事实必须进入讲稿，缓存也按此重查。新原页注释以完整摘录定位；只有原文直接出现的名称才绑定单词，不把模型猜测的英文字段当作中文概念译名。关系图保持命题端点的精确角色检查。实际新领域输出与未通过的人工内容项见[教材泛化验证](generalization-validation-2026-10.md)。

### 数据链路

网页先通过 `teaching_design.py` 分析知识点及完整来源页，选择 `geometry`、`process`、`relationship`、`comparison` 或 `source_figure`。后四类使用 `visual_scene.diagram`：模型定义节点、关系、原文依据、教学问题与逐步讲解；程序检查逐字摘录、编号、关系端点、覆盖与状态推进，再共享布局生成图片和关系追踪动画。复杂实体图使用程序从本地 PDF 提取的原始页面，模型不能指定文件路径；可以高亮搜索到的真实原文区域。几何候选多次失败后重新规划表达方式，不伪造变化参数来绕过检查。

以下参数步骤链适用于 `geometry`。关系图允许解释结构和比较而不改变物体坐标，但必须说明真实关系、保留两端对象可见并聚焦至少一个相关端点，推进讲解状态；重复同一组要点不能通过。此检查证明结构和来源摘录匹配，不证明模型对原理的全部理解。

模型通过 `source_id` 选择程序编号的原文片段；节点和关系中的 `source_quote` 由程序填入，避免要求小模型重新抄写原文。教学设计的原始候选及拒绝原因保存在 `teaching-design-XX.json`。这套接口与参数场景共用课程、语音、PPT 和下载链路。

定性设计先独立理解完整来源句子的主语、动作、宾语和条件，调用不接触候选分镜或用户风格。再规划对象与关系，最后用 `source_fact_id` 选择来源事实；程序将当前事实与对应的图形焦点、连线绑定，类比通过独立 `example` 字段选择同一事实，程序填入 `source_statement`，不让口播模型重新改写事实。按实际内容规划 1–5 步，不凑固定条数。`source_term` 的输出契约使用当前原文中的候选短语，不允许拼接或翻译原文术语；可定位的索引误选可以修正并记录。非比较关系的原文及相邻上下文必须包含两端术语，不能把无关的定义拼成因果，过程图与关系图中的节点须参与关系；比较图和原页标注允许不连线，原页标注允许一个对象的多个不同事实。原始与补充摘录分别保留。口播的 `source_statement` 与 `analogy` 分开记录；程序将二者合成实际口播并明确标出生活类比，类比不必出现在原文中，但不得增加技术事实或保证。定性口播不自行断言维数、时间窗口或预测数值。过程和关系图按来源命题主谓宾方向连接，谓词说明其含义；比较和原页注释可不连线。Ollama 读取模型实际支持的推理控制，不依据名称假设开关；非推理模型可完成相同的结构化契约，耗尽输出预算会明确报错。完整来源页和候选送入逐项语义审稿，分别记录对象、关系与每步事实/类比的原文含义、支持判断及理由；遗漏条目或任一拒绝项都不能通过。通过审稿的分镜按资料、模型与提示词缓存，重试时重新检查来源与执行契约；语义审稿与确定性来源检查分别记录，不能将模型审批当成专业事实证明。

1. 从 PDF 提取带编号的原文依据，模型规划知识点及顺序。来源编号保持稳定，标题可以改写。
2. 为每个片段分两次调用规划对象布局与操作计算。布局阶段确定 3–5 步的 `step_count`，操作阶段的输出契约要求相同步数，避免重复追加；合并为 `visual_scene`：问题、对象、参数、步骤、计算、来源和示意简化。
3. 核验受限表达式、对象引用、坐标、五个插值状态和声明的数值关系。纯淡入要点的场景被拒绝。
4. 新模型分镜将数值口播绑定到已核验参数与计算。自由口播只描述对象、操作和原因，未绑定的字面数字及常见中文数值断言被拒绝；程序补入当前参数和结果，再调用语音 API。新分镜每段规划 3–5 步，每步定性口播 12–100 字符，输出约束也限制文本长度，避免本机模型在单个字符串内用尽输出预算；旧场景契约继续兼容。实际音频长度决定变化与停顿。这个约束不能证明全部定性解释或领域含义。
5. Manim 在连续参数状态中重新计算曲线与对象位置；公式数值随当前状态更新，逐帧执行声明的关系和已注册领域规则。
6. 记录实际图形坐标检查与参数采样。终态生成 SVG 摘要；相同带配音 MP4 用于完整视频和 PPTX。备注保留来源、逐步口播、参数与简化条件。

定性图中文节点名称从独立事实中选择。连线只选择事实编号与端点；程序按同一事实的主语→谓词→宾语顺序提取完整谓词，保留否定和限定词，不允许模型另造标签。复杂或被动从句不能直接压缩时使用比较或原页标注。每片段最多一个 12–80 字符、以句号结束的生活类比。

请求生活例子时，比较和原页讲解优先选择原文明确提供的示例；示例作为独立来源事实绑定口播与焦点，不另编类比。原文理解要求完整中文句子，旧缓存中照抄英文或截断的草稿会重新生成；空术语候选以教学设计错误报告，避免构造空枚举。SVG 与 PNG 使用相同画布尺寸，兼容图不能裁掉字幕或来源。

`preserve_source_sequence` 检查当前注释所选事实及其紧邻的明确后续操作，记录 `source_sequence` 并要求口播保留事实和原顺序。它使用原文的过程词，不推断额外因果；对完整章节的教学覆盖仍须另行检查。

`preserve_topic_focus` 将知识点标题与来源事实共同包含的具体词语绑定到必讲事实，记录 `topic_facts`。同页背景不能替代当前主题；词语由当前事实提取，不使用学科词表。缓存复用仍检查这项要求。它不能证明同义表达、全章覆盖或教学质量。

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

表达式只允许数字、已声明参数、`x`（曲线变量）、`pi`、`e`、四则、有限幂及 `sin/cos/tan/asin/acos/atan/atan2/sqrt/exp/log/abs/min/max`。模型分镜的数值容差固定为程序控制的 `1e-6`，不能放宽容差绕过错误计算。禁止 Python 代码、属性访问、导入、网络或模型自写 SVG/TeX。LaTeX 由受限数学 AST 转换生成。

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


### 数学对象模式与坐标

`geometry` 显式要求通用数学对象，不允许图示回退。图形规划读取完整引用页；知识点与引文仍来自自动提取。公式或图形信息丢失时需要对照 PDF，不能把计算检查当作原文读取成功。

`parametric_curve` 使用两个受限 `parametric_expression` 和 `domain`；其中 `x` 是路径参数，区别于 `curve` 的横坐标。SVG 与 Manim 共用 `EuclideanViewport`，保持同等单位的长度与角度。一般坐标轴仍使用原文或例子的变量范围。

规划器在对象阶段检查是否引用声明参数，必要时请求 `MotionParameterBindings` 对已有字段作符号绑定。`VisualSequenceDraft.parameter_changes` 使用声明名称的变更列表，程序恢复执行字段 `parameters`；旧课程 JSON 仍兼容。点的显示半径属于标记样式，不算数学运动；实际位置、圆半径或曲线变化才算。

每步记录可见对象实际位移与方向是否改变，提供给审稿。没有方向变化的伸缩不能配“旋转”口播。这是部分动作一致性检查，不能证明旋转中心、角度、极限、面积关系及全部数学解释正确。相关回归见 `tests/test_geometry_contract.py`，实际教材见[数学验证](math-level-validation-2026-10.md)。



严格数学场景的 `geometry_constraints` 从来源编号绑定现有对象：测量曲线/圆周归属、相等距离/长度/面积及垂直、平行、共起点。规划采样与渲染每帧都执行，并拒绝窗口外的可见点及标签锚点；曲线可裁切，标签尺寸尚未全面检查。缓存包含规范化场景摘要，修改对象或约束使旧批准失效。关系绑定仍可漏项或误判，不等于全部数学证明。

## English

### Source knowledge graph

Before diagram design, `teaching_graph.py` independently reads `subject/predicate/object/fact_ids` propositions. The designer chooses `source_proposition_id`; trusted code copies the relation and requires matching endpoint names and roles. Graph node candidates come from those propositions. Original-language terms and strings remain intact. Proposition reading and full-page semantic review are separate model judgements, not formal proofs.

Backward-compatible relation fields include `binding`, `source_proposition_id`, `supporting_fact_ids`, `source_statements`, and `condition`; node `kind` distinguishes entities, operations, and conditions. New semantic relations must match independent propositions and retain up to three complete source facts. Directed topology, branches, and cycles determine shared SVG/Manim layouts. Review approval binds to `reviewed_design_digest`, including nodes, edges, conditions, and speech. Proposition caches remain unapproved drafts. The exported `knowledge_graph` includes pages, propositions, facts, and quotes, without merging homonyms across chapters or inferring causation.

Facts matching the topic's original citation must appear in speech, including on cache reuse. New source-page notes anchor full quotes; only literal names receive exact word anchors, avoiding guessed English fields for translated concepts. Graph endpoints retain their strict proposition-role checks. See [textbook validation](generalization-validation-2026-10.md) for actual new-domain outputs and unaccepted human content checks.


### Choose the representation before geometry

Web jobs use `teaching_design.py` to analyze each topic and its full source page, selecting `geometry`, `process`, `relationship`, `comparison`, or `source_figure`. The last four use `visual_scene.diagram`: model-designed nodes, relations, literal source excerpts, a question, and explanatory steps. Trusted code checks excerpts, IDs, relation endpoints, coverage, and progression, then uses shared layouts for SVG images and narrated relation tracing. Local PDF page extraction preserves complex original artwork; model output cannot choose file paths. Searchable source regions can be highlighted. Repeated geometry failures trigger representation redesign rather than invented parameter changes.

The existing numeric scene path remains for computable geometry. Qualitative diagrams explain real relations and comparisons without claiming physical movement; both endpoints remain visible while at least one is emphasized, and steps cannot repeat an identical state. These checks establish structure and excerpt matching, not complete semantic understanding.

Models select numbered excerpts through `source_id`; the program fills literal `source_quote` fields on nodes and relations, avoiding unreliable copying by small models. Candidate designs and rejection reasons remain in `teaching-design-XX.json`. Both contracts share course, speech, PPT, and download infrastructure.

Qualitative node names select phrases from independent source facts. Links select a fact and endpoint IDs; trusted code extracts the complete predicate in subject–predicate–object order, retaining negation and qualifiers. The model cannot invent edge labels. Complex or passive clauses use comparisons or source-page annotations when they cannot be faithfully shortened. Each segment includes at most one complete everyday analogy of 12–80 characters, ending with sentence punctuation.

When everyday examples are requested, comparisons and source-page guidance prefer explicit source examples. Each example binds speech and focus to an independent source fact without another invented analogy. Readings require complete Chinese statements; older untranslated or truncated drafts are regenerated. Empty term catalogs report a teaching-design error rather than constructing an empty enum. SVG and PNG use the same canvas dimensions, preserving captions and source labels.

`preserve_source_sequence` checks selected annotations and explicitly subsequent neighboring operations. It records `source_sequence` and requires speech to retain those facts in source order. Temporal source cues do not infer additional causation; full chapter coverage still requires separate review.

`preserve_topic_focus` binds a specific phrase shared by the topic and its source facts to required spoken facts, recorded as `topic_facts`. Background on the same page cannot replace the topic. Phrases come from the current facts, without a subject glossary, and reused caches undergo the same check. This does not establish synonym coverage, chapter completeness, or teaching quality.

An isolated call first reads source sentence subjects, actions, objects, and conditions without candidate storyboards or style prompts. Later calls design objects/relations and choose source facts through `source_fact_id`; trusted code inserts `source_statement` without narration-model rewriting. Qualitative diagrams use 1–5 steps based on the material, without filling a fixed count. `source_term` selects actual phrases from the current source, preventing concatenated or translated anchors. Determinate index mistakes can be repaired and logged. Non-comparison relation evidence and adjacent context must contain both endpoint terms, and isolated nodes are rejected in process/relationship diagrams. Comparisons and source-page annotations can omit relations; source annotations can explain several distinct facts about one object. Primary and supporting excerpts remain separate; neighboring definitions do not establish causation. `source_statement` and `analogy` are stored separately, and the program labels analogies in the composed speech. Original analogies need not appear in the source, but cannot add technical facts or guarantees. Qualitative narration does not assert dimensions, time windows, or predicted values. Process and relationship links follow sourced subject–predicate–object roles; comparisons and page guidance can omit links. Ollama reads advertised thinking controls rather than inferring switches from names. Non-thinking models use the same structured contracts; output-budget exhaustion is reported explicitly. Itemized semantic reviews use the full source page and record source meanings, decisions, and reasons for every object, relation, and spoken step. Missing or rejected items fail validation. Accepted storyboards are cached by source, model, and prompt and rechecked on retries. Reviews remain separate from deterministic source checks; approval is not proof of domain facts.

### Subject-independent generation

`visual_scene.domain` is descriptive text, not an executor whitelist. New subjects and interdisciplinary topics use the same primitives and parameter steps without adding a subject branch. Auto mode preserves all extracted topics and selects a general representation per topic; math mode explicitly chooses specialized linear transformations. Visual mode requires general scenes. Missing dependencies produce an explained auto fallback; invalid storyboards are revised or rejected.

The general layer handles parameterized 2-D teaching across subjects. Specialized executors can add stronger reasoning, presentation, and checks for particular topics. Open subject scope does not establish equal automatic teaching quality for every source.

### Contract and execution

Stable source IDs connect PDF excerpts to course order. Separate calls draft object layout and operation/calculation steps. Layout chooses a `step_count` of 3–5, and the sequence contract requires that exact count to prevent repeated tails. Merge questions, persistent objects, parameters, narration, calculations, source evidence, and simplifications. Primitive types are dots, circles, lines, arrows, polygons, curves, and labels. Named parameters drive coordinates or curve expressions, and steps show/hide objects or change values. Points use `position`, lines use `start/end`, polygons use `vertices`; legacy `points` remains readable. `checks` must hold throughout all frames; step-specific results belong to `calculations`. Scenes with only progressive bullet reveals are rejected.

Restricted expression and geometry checks include five interpolation states. Actual speech durations control animation and holds. Manim recomputes geometry and numeric formulas as parameters change and executes declared numeric/domain checks on rendered frames. The report records parameter paths and actual coordinate checks. SVG summaries, full lesson MP4s, PPTX clips, and speaker notes share the same scene data. Clips retain narration and 16:9 proportions.

The program sets `narration_binding=computed` for new model scenes: qualitative prose describes objects and operations, while verified parameters/calculations generate numeric speech. Unbound literal digits and common Chinese numeric assertions are rejected before audio synthesis. New storyboards draft 3–5 steps with 12–100 characters of qualitative speech per step; the output constraint also bounds prose length to avoid exhausting the local model's token budget within one string. The older scene contract remains readable. This is not a proof of all qualitative meanings.

Expressions allow numbers, declared parameters, the curve variable `x`, constants `pi/e`, arithmetic, bounded powers, and `sin/cos/tan/asin/acos/atan/atan2/sqrt/exp/log/abs/min/max`. Model-drafted checks use a program-controlled `1e-6` tolerance; a model cannot loosen it to approve wrong calculations. Python code, attribute access, imports, networking, and model-authored SVG/TeX are rejected. Trusted AST conversion generates LaTeX.

### Extensions

Use existing primitives for ordinary new topics. Add trusted numeric rules with `checker(value, expected, tolerance) -> bool` or full-context rules with `validator(scene, parameters) -> {"passed": bool, ...}`. The Python entry points shown above load matching implementations in the server and Manim child process. The model can name installed rules but cannot implement or register code. `domain_data` holds string-valued context for units, elements, relationships, or mechanism conditions. Unknown rules fail explicitly. Direct registration must run in both processes.

Extend the object contract, geometry computation, Manim construction, and SVG export together for new primitives. Add source, initial-state, intermediate-state, and endpoint validation. Complex 3-D or molecular dynamics requires a corresponding executor; a 2-D parameter interpolation is not a physical mechanism simulation.

### Validation

`build_general_examples.py` provides authored regression models for secant limits, probability partitions, projectile motion and energy, atom rearrangement, and enzyme processes, all using one executor. These exercise rendering and declared relations; real model planning is tested separately with PDF uploads. Use `verify_teaching_artifacts.py` for generic or specialized job artifacts. Keep calculation/geometry, source review, key frames, playback, listening, and PowerPoint slideshow results separate.

### Mathematical objects and coordinates

`geometry` explicitly requires mathematical objects and rejects diagram fallbacks. Planning reads the complete cited page; extracted topics and citations still require review, especially when vector formulas are missing from PDF text. `parametric_curve` takes two restricted `parametric_expression` strings and a `domain`; its `x` is the path parameter. Both renderers use the same equal-unit `EuclideanViewport`.

Layout checks require a declared parameter to drive geometry; constrained `MotionParameterBindings` can bind existing object fields. Step `parameter_changes` use declared names and are converted to execution parameters. Cosmetic marker size is not mathematical motion. Review receives measured displacement and direction changes; stretching cannot be narrated as rotation. These partial checks do not prove rotation centers, angles, areas, limits, or all mathematical claims. See [textbook validation](math-level-validation-2026-10.md).

Strict mathematical scenes bind `geometry_constraints` from source IDs to existing objects: function/circle membership, equal distances/lengths/areas, perpendicular/parallel lines and common origins. Planning samples and every rendered frame are measured; visible point and label anchors outside the coordinate window are rejected. Curves may be clipped and label extents are not fully checked. Canonical scene digests invalidate approval when objects or constraints change. Relation binding can still be incomplete or wrong; this is not a universal mathematical proof.
