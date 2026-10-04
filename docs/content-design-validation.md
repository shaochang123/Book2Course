# 真实资料生成修复验证 / Real-source generation repair validation

[中文 README](../README.md) · [English README](../README.en.md)

## 中文

### 资料与运行条件

- 资料：用户上传的九页 [RealDex: Towards Human-like Grasping for Robotic Dexterous Hand](https://www.ijcai.org/proceedings/2024/0758.pdf)，包含机器人抓取、数据采集、学习方法和实验结果。它是研究论文，不是数学专用演示讲义。
- 网页任务：`35f4a9ba2ad64660aa272f788a6bd0f6`。保留完整 PDF，真实 AI / `visual` 模式；唯一教学偏好为“解释时多用生活例子”。没有人工编写分镜或为该论文增加词表。
- 文本模型：本机 Ollama 的 `qwen3:4b-instruct`。原 `qwen3:4b` 出现推理预算问题，本次换模型，不能声称原模型已通过。
- 语音：本机 Kokoro `kokoro-82m-v1.1-zh` / `zf_001`。动画：Manim Cairo。原页定位：PyMuPDF。教材与配音文本没有发送到外部模型。
- 本机 Ollama 0.35.1 的 llama.cpp 提示缓存限制为 512 MiB，以降低 CPU 运行时的内存压力。

### 已复现的失败与修复

| 失败 | 通用修复 |
| --- | --- |
| 原文引文被改写、术语跨句拼接、编号错选 | 模型选择实际原文中的编号与术语，程序填入摘录；保留完整句子与引用括号。 |
| 模型把不同定义接成关系，审稿模型仍批准 | 独立理解原文事实；中文对象名称、原文术语和来源编号以同组契约约束。连线谓词从同一事实的主语与宾语之间提取，保留否定与条件。 |
| 讲解事实正确，但高亮另一条事实的对象 | 程序从当前事实绑定图形焦点和连线，模型只选择讲解顺序。 |
| 强制每步类比，出现截断、重复或遗漏 | 根级 `example` 单独保存一个完整类比，与所选事实绑定；实际口播明确标注。 |
| 类比加入原文未说明的技术行为，审稿仍批准 | 比较和原页讲解优先使用原文明确给出的示例；例子绑定来源事实和焦点。原创类比拒绝保证语句与当前来源实体名，但这类词语检查不能证明语义完全正确。 |
| 独立理解草稿照抄英文，构造中文标签枚举时崩溃 | 理解契约要求完整中文句子；缓存复用时重新验证，旧无效草稿自动重读。空候选在构造枚举前明确报错。 |
| PNG 兼容图采用固定高度，裁掉 SVG 底部字幕 | 读取 SVG 实际宽高生成 PNG，产物核验检查画布尺寸一致。 |
| 短对象含义被要求扩写，返回值混入正则长度片段并损坏 JSON | 简短名称可以忠实表达原文对象；核对理由另行给出，不重复使用正则和字段长度约束。保留实际损坏正文作为本地诊断，不能修剪正文内部来冒充有效审稿。 |
| 初始标定直接跳到效果，遗漏原文明确的后续对齐操作 | 根据紧邻来源摘录中的过程词保留操作事实与顺序；不添加新的因果或运动。 |
| 事实各自有依据，却漏掉当前知识点中的模型作用 | 用标题与独立事实共同包含的具体词语绑定必讲事实；同页邻近内容不能替代主题，词语检查仍不能证明讲解质量。 |
| 把泛化测试类比成“只要步骤正确就能成功” | 拒绝新增充分条件的类比，保留来源事实，重新生成辅助例子；模型审稿批准仍不能取代这项检查。 |
| 聊天接口遇重复 JSON 结束符返回 HTTP 500 | 一次受限原生生成接口重试；只接受完整、满足契约的对象及重复结束符修复，拒绝截断或额外正文。 |
| 后续阶段失败后重复全部规划 | 保留解析、知识点、独立来源理解及结构草稿；未批准草稿仍须含义审查，通过审稿的场景另行缓存。 |
| 将所有资料强行变为坐标移动 | 按内容选择几何、过程、关系、比较或原页讲解。无法忠实简化的关系保留原文图示，不编造连线。 |

自动化回归覆盖上述失败，并保留原有几何、数学、语音和 API 测试。模型的语义批准与确定性来源检查分别记录，批准标志不是领域事实证明。

### 本次来源与教学内容核对

已直接比对最终六段的来源摘录和口播，核对结果如下；这不是对论文实验结论的独立复现。

| 场景 | PDF 页 | 步数 | 核对与范围 |
| --- | --- | --- | --- |
| 多视图与多模态数据融合 | 1 | 4 | 数据、姿态同步与框架用途对应摘要；传球例子明确标为类比。节点“丰富”“无缝”过于笼统，不能据此认为概念图教学质量已达标。 |
| 人类与机器人手部动作的差异 | 1 | 4 | 保留原文杯把与杯内抓取示例；未增加机器人“不会观察”的行为。部分提取标签脱离句子后含义不够清楚，须结合口播与原文阅读。 |
| 强化学习在抓取行为训练中的应用 | 3 | 3 | 强化学习及图像/点云训练对应原文；首步仅为原文对象短语，没有解释完整训练过程。 |
| 手眼标定过程 | 4 | 4 | 保留校准板移动、初始变换、随后 ICP 对齐及来源声称的效果；没有计算或模拟 ICP。 |
| 多模态大语言模型在动作生成中的作用 | 5 | 5 | 保留 cVAE 候选、MLLM 偏好对齐与自回归动作生成；维数符号在提取文本中扁平化为 `θ∈ R22`，不能视为已完成数学公式解释或正确读音验收。原始页仍保留正式公式。 |
| 方法在真实数据集上的泛化能力验证 | 6 | 4 | GRAB 评估对应泛化主题；40 名用户属于相邻用户研究，不能视为 GRAB 实验样本量。类比只说明评估，不承诺成功。 |

本轮六段都选择了 `source_figure`：原页区域高亮、对象焦点与配音同步。它验证跨主题生成链路和来源绑定，尚未证明自动生成机器人动作、研究机制仿真或达到 3Blue1Brown 的讲解质量。上述表达和公式问题保留在验收结果中，不以“模型审稿通过”掩盖。

### 本轮产物与验收

2026-10-04，网页任务达到 `completed` / 100%，错误为空。本机模型规划、24 步本地配音、六段渲染、视频合成和 PPTX 组装均已完成。

产物位于 Git 忽略的 `data/jobs/35f4a9ba2ad64660aa272f788a6bd0f6/`：

| 文件 | 实际结果 |
| --- | --- |
| `lesson.pptx` | 12,228,897 字节；13 页；6 个含配音的内嵌 MP4、6 张 SVG 及 PNG 兼容图；16:9；每页含备注。 |
| `lesson.mp4` | 6,835,139 字节；214.2 秒；1280 × 720 / 30 fps；H.264 + AAC。 |
| `scene-data.json` | 280,967 字节；六段分镜、来源事实、配音时间及渲染检查。 |
| `validation.json` | 自动产物检查通过；保留各段及完整视频的解码、时间和 PPT 检查。 |
| `validation-contact.png`、`web-result.jpg` | 六段起点/中间/终点画面，以及网页实际完成页。 |

- **自动检查**：124 项测试通过，零失败/错误/跳过。实际完整视频解码 6,426 帧，音轨非静音；音视频时长差约 0.026 秒。六段的焦点、布局、状态与实际配音时长一致；SVG/PNG 均为 1200 × 675，没有固定高度裁切。
- **PPT 与下载**：内嵌 MP4 与教学片段的 SHA-256 一致；摘要页和动画页备注均包含实际逐步口播。网页 MP4、PPTX、场景 JSON 三个下载结果与生成文件逐字节一致。
- **来源与视觉检查**：直接比对了六段口播和摘录，并查看 18 张关键帧及摘要图。25 个注释对象中 20 个具有实际文字区域，5 个没有可靠定位；没有补造位置。字幕和来源未裁切，但原页正文在小画幅中不可直接阅读，部分标签和数学符号的问题见上表。专业解释和 3Blue1Brown 级动画质量未全部验收。
- **实际播放**：网页播放器从 0 秒连续播放到 214.2 秒，`ended=true`、无媒体错误。没有人工试听记录，不能据此验收发音、音色或逐句听感。当前工具未提供 Windows 原生应用控制，未在 PowerPoint 放映中点击播放。

源 PDF SHA-256：`4997cd1687cfd938dfe1b2a394e657c0757c3c522f8a883ed7585d3bd2788abd`。

结论：这份非数学研究论文的生成失败链路已经跑通；来源与产物检查通过，教学表达仍有上述问题。本次没有为 RealDex 手写分镜，仍不能由一个成功任务推断任意输入都能得到完整、准确的机制动画。

### 验收边界

学科名称没有白名单。原页讲解与关系追踪是教学示意，不能等同于三维机器人运动或真实物理机制模拟。复杂结构可以保留原文插图；新增动态机制需要相应执行器和核验规则。完整解码、音轨检测和 OOXML 检查不能代替试听或 PowerPoint 放映中实际点击播放。

## English

### Source and runtime

- Source: the user's complete nine-page [RealDex paper](https://www.ijcai.org/proceedings/2024/0758.pdf), covering grasping, data collection, learning methods, and experiments. It is a research paper, not a specialized math fixture.
- Web job: `35f4a9ba2ad64660aa272f788a6bd0f6`, real AI / `visual` mode. The only teaching preference is “use more everyday examples.” No human storyboard or paper-specific vocabulary was supplied.
- Local text model: Ollama `qwen3:4b-instruct`. The original `qwen3:4b` exhausted a reasoning budget; this run changes the model and does not establish success for the original model.
- Local speech: Kokoro `kokoro-82m-v1.1-zh` / `zf_001`; rendering: Manim Cairo; page locations: PyMuPDF. Source and speech text were not sent to an external model.
- The llama.cpp prompt cache in this computer's Ollama 0.35.1 is limited to 512 MiB to reduce memory pressure.

### Reproduced failures and general repairs

Source IDs and original terms replace rewritten quotations and spliced anchors. Independent source readings precede diagram design. Chinese names, source terms, and IDs form one constrained choice. Edge predicates are extracted from the same fact in subject–predicate–object order, retaining qualifiers and negation. The spoken fact determines visual focus and its links.

A separate `example` field attaches one complete analogy to a selected fact. A chat-parser HTTP 500 receives one bounded native-generation retry; only complete schema-valid JSON with duplicated closing tokens can be normalized. Source readings and source-matched structure drafts are resumable but remain unapproved until semantic review. Geometry is not forced on qualitative content; unsupported compact relations use comparisons or original-page guidance.

The source contains a cup-handle example, which is now preferred over an analogy inventing robot behavior. Comparisons and page guidance preserve explicit source examples and bind their fact to speech and focus. Guarantee phrases and current-source entity names are rejected in original analogies, but lexical checks alone cannot establish semantic correctness. Readings require complete Chinese sentences; invalid English or truncated caches are regenerated. Empty catalogs report a design error before enum construction. PNG compatibility images retain the SVG dimensions; artifact verification checks the full canvas.

A captured review response inserted a regex length fragment into JSON after a short object meaning. Reviews now allow concise source object names with a separate supporting reason, without duplicating string-length bounds in regex syntax. Malformed model content remains in local diagnostics; corrupted content inside an object is not trimmed into an apparent approval.

An accepted calibration draft omitted the subsequent alignment operation; another accepted draft omitted the model’s role named in its topic. Guided-source/comparison planning now retains explicit neighboring operations in source order and binds the topic’s most specific sourced phrase to a required spoken fact. These language checks do not establish complete chapter coverage or teaching quality.

A generalization analogy added a sufficient condition for success. That analogy was rejected and regenerated while preserving the source fact; semantic approval did not override the condition check.

Regression tests cover these failures alongside existing geometry, math, speech, and API checks. Semantic approval remains separate from deterministic source checks and is not proof of domain facts.

### Source and teaching-content review

The final six scenes' excerpts and spoken statements were compared directly. This does not reproduce the paper's experiments independently.

| Scene | PDF page | Steps | Review and scope |
| --- | --- | --- | --- |
| Multi-view and multimodal data | 1 | 4 | Data, pose synchronization, and framework use match the abstract. The ball-passing analogy is labeled. Labels such as “enriched” and “seamless” are vague, so concept-diagram teaching quality is not accepted as complete. |
| Human and robotic hand behavior | 1 | 4 | Preserves the source's cup-handle example without inventing a robot's inability to observe. Some extracted labels need narration and source context to remain clear. |
| Reinforcement-learning applications | 3 | 3 | RL and image/point-cloud training match the source. The first step is only a sourced object phrase, not an explanation of the full training process. |
| Hand–eye calibration | 4 | 4 | Retains board movement, initial transform, subsequent ICP alignment, and the source's claimed effect. ICP is neither computed nor simulated. |
| MLLM role in motion generation | 5 | 5 | Retains cVAE candidates, MLLM preference alignment, and autoregressive motion generation. Extracted notation flattens to `θ∈ R22`; mathematical explanation and pronunciation are not accepted. The original page preserves the typeset formula. |
| Generalization evaluation | 6 | 4 | GRAB evaluation matches the topic. The 40 users belong to a neighboring user study, not the GRAB evaluation sample. The analogy explains evaluation without guaranteeing success. |

All six scenes use `source_figure`: source-region highlights and object focus synchronized to speech. This establishes the production path and source bindings across topics, not automatic robot motion, mechanism simulation, or 3Blue1Brown teaching quality. The presentation and formula issues above remain visible in acceptance, irrespective of model approval.

### Artifacts and acceptance

On 2026-10-04, the web job reached `completed` / 100% with no error. Local model planning, 24 spoken steps, six rendered clips, video concatenation, and PPTX assembly completed.

Artifacts remain in Git-ignored `data/jobs/35f4a9ba2ad64660aa272f788a6bd0f6/`:

| File | Actual result |
| --- | --- |
| `lesson.pptx` | 12,228,897 bytes; 13 slides; six narrated MP4s, six SVGs and PNG fallbacks; 16:9; notes on every slide. |
| `lesson.mp4` | 6,835,139 bytes; 214.2 seconds; 1280 × 720 / 30 fps; H.264 + AAC. |
| `scene-data.json` | 280,967 bytes; six storyboards, source facts, speech timing, and rendering checks. |
| `validation.json` | Automated artifact checks passed; retains per-clip/full-video decoding, duration, and PPT checks. |
| `validation-contact.png`, `web-result.jpg` | Start/intermediate/end frames of the six clips and the actual web completion page. |

- **Automated checks:** 124 tests passed, with no failures, errors, or skips. The full video decoded 6,426 frames with non-silent audio; audio/video duration differs by about 0.026 seconds. Six clips retain consistent focus, layout, state, and actual speech timing. SVG/PNG canvases are 1200 × 675, with no fixed-height cropping.
- **PPT and downloads:** Embedded MP4 hashes match the teaching clips. Summary and animation slide notes include the actual spoken steps. The web's MP4, PPTX, and scene-JSON downloads are byte-identical to generated files.
- **Source and visual inspection:** Six sets of statements/excerpts, 18 key frames, and summaries were inspected directly. Twenty of 25 annotations have real text regions; five lack reliable locations, without fabricated coordinates. Captions and source labels remain visible, but full-page text is unreadable at this small size. Label and notation issues remain as recorded above. Professional explanations and 3Blue1Brown animation quality are not fully accepted.
- **Playback:** The web player ran continuously from 0 to 214.2 seconds, reaching `ended=true` with no media error. No human listening record exists; pronunciation, voice quality, and auditory synchronization are not accepted from this check. Native Windows app control was unavailable, so click-to-play in a PowerPoint slideshow was not tested.

Source PDF SHA-256: `4997cd1687cfd938dfe1b2a394e657c0757c3c522f8a883ed7585d3bd2788abd`.

Conclusion: the failed production path for this non-math research paper now completes. Source and artifact checks pass, with the teaching issues listed above. No RealDex storyboard was authored manually; one completed job does not establish complete, accurate mechanism animation for every input.

### Acceptance boundaries

Subject names are unrestricted. Source guidance and relationship tracing are explanatory schematics, not 3-D robot motion or physical simulation. Complex structures can retain source imagery; new mechanisms need corresponding executors and checks. Full decoding, audio-track checks, and OOXML inspection do not replace listening or actual click-to-play testing in a PowerPoint slideshow.
