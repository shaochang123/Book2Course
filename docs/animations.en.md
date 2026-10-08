# Teaching diagrams and animations

[简体中文](教学图示与动画.md) | [English](animations.en.md)

Detailed reference moved from the project README. See the [implementation status](实现状态与路线图.md) (Chinese) for current scope. Machine versions and validation results are specific to their linked reports.

### Title scope and source readability (2026-10-08)

Qualitative scenes retrieve assertions from the current and adjacent input pages, then separately review operations, negation, conditions and explicit counts. The original citation stays in diagnostics and does not bias scope selection. One scene uses one source page; missing requirements or necessary joint evidence across pages cause an explicit failure. Every selected required fact must be narrated; this is not full-book coverage.

Complete multiword inline italic examples are extracted from PDF font boundaries. The program fills their exact object names while the model supplies Chinese explanation; no subject-specific examples are built in. OCR lacks reliable typography and does not use this protection. Source annotation scenes retain a page map and zoom into uniquely matched evidence at each step. Lost font-boundary spaces are handled through exact character sequences, not word-bag guesses; ambiguous locations never produce invented crops.

Scope, reading and planning caches use new versions and coverage checks. Foreign-language text PDFs retain source numeric tokens during translation; quantitative OCR remains strict. Token presence does not establish units, roles, conclusions or correct calculations. Semantic and human review are still needed. See the [capability audit](agent-model-capability-2026-10.md) for actual outcomes and failures.

### PPT production skills

The following repository Codex skills help refine PPT content and assets. Web jobs generate a PPTX with built-in templates and do not invoke these skills automatically. Invoke them by name in a Codex task for this project:

| Skill | Purpose |
| --- | --- |
| [`$book2course-ppt-outline`](../.agents/skills/book2course-ppt-outline/SKILL.md) | Plan slides from learning dependencies and source pages; check for missing key concepts. |
| [`$book2course-ppt-script`](../.agents/skills/book2course-ppt-script/SKILL.md) | Write a page-aligned speaker script, notes, narration, and visual cues. |
| [`$book2course-svg-diagrams`](../.agents/skills/book2course-svg-diagrams/SKILL.md) | Create editable SVG flowcharts, concept diagrams, and formula step diagrams. |
| [`$book2course-explainer-animation`](../.agents/skills/book2course-explainer-animation/SKILL.md) | Design explanatory visual transformations and check visuals against narration and timing; use [Manim Community](https://docs.manim.community/en/stable/) when needed. |

For custom teaching beyond the automatic deck, use Codex's Presentations skill to assemble outlines, scripts, SVGs, and clips, then inspect layout and notes. The web pipeline now includes a general scene interpreter and specialized 2-D linear transformations; Manim is installed as an optional dependency.

## Teaching process animations and subject extensions (optional)

Install in the existing environment:

```powershell
.\.venv\Scripts\python -m pip install -e ".[math-animation]"
latex --version
dvisvgm --version
```

Source-backed relationship, process, comparison, and page-guidance diagrams use native Manim text and do not require TeX. Computable geometry and specialized math scenes additionally require TeX Live or another LaTeX distribution providing `latex`, `dvisvgm`, and the `standalone` package on PATH. Restart the web server after installation. This computer uses its existing TeX Live installation and needs no GPU. Animation renders on the local CPU; text and speech use the APIs configured in the page.

Select real AI mode and choose an animation mode:

| Mode | Behavior |
| --- | --- |
| `auto` (default for new AI jobs) | Retain all extracted textbook topics and select source-backed diagrams or parameterized scenes per topic. Choose `math` explicitly for specialized reasoning. Missing general dependencies produce an explained basic fallback. |
| `visual` | Require general teaching scenes without a subject restriction; invalid storyboards or declared numeric relations fail explicitly. |
| `math` | Require source-backed 2-D linear transformation material and a complete math environment. Unsupported content, invalid parameters, and failed computation checks produce explicit errors. |
| `basic` | Use the existing concept, formula, and process templates; embedded basic clips remain silent. |

The specialized executor covers linearity and translation counterexamples, basis images and matrix columns, grids and unit squares, orthogonal projections and eigendirections, and rotation/stretch composition order. Set teaching parameters in the prompt, such as `A=[[2,1],[0,1]]` and `v=[1,2]`. Supplemental examples are labeled. Math jobs focus on this supported thread and do not imply that 3-D or function-space material in the source has been animated.

The general `visual_scene` contract has no subject-name whitelist. The model can use curves, points, circles, lines, arrows, polygons, and labels with stable identities, parameters, and successive changes for calculus, probability, physics, chemistry, biology, or other fields. The same data produces SVG summaries, narrated animations, and speaker notes. Restricted expressions generate LaTeX formulas; numeric results and geometry update together as parameters change.

General jobs first select a teaching representation for each topic: computable geometry, a process diagram, a relationship diagram, a comparison, or guided source imagery. For qualitative material, the model designs nodes, relations, questions, and explanatory steps; shared program layouts produce SVG images and narrated relation-tracing animations. Each node and relation has a checked source excerpt. Complex original artwork can use locally extracted PDF pages, preserving embedded images and vector drawings. Repeated geometry failures trigger representation redesign rather than forcing every topic into coordinate movement. Selection reasons and verification scope remain in scene data and PPT notes.

Teaching design first reads source facts in a call isolated from candidate storyboards and style prompts, retaining sentence subjects, actions, and conditions. It then plans objects/relations. Narration selects `source_fact_id`; trusted code inserts `source_statement` and binds the same fact to visual focus and links. A separate `example` field attaches one analogy to a selected fact. The model cannot rewrite the spoken fact or swap visual focus. Qualitative diagrams use 1–5 steps according to the material, avoiding invented facts to fill a fixed count. Original everyday analogies (`analogy`) are recorded separately and explicitly labeled in speech. Comparisons and source-page annotations may omit links, avoiding invented causation; page annotations can explain different sourced facts about a single object. The program numbers source excerpts, builds selectable terms from original phrases, and checks both relation endpoints with adjacent source context. Models cannot translate source anchors or infer causation from unrelated excerpts. Different concepts can share one excerpt; duplicate topic titles are still rejected. Determinate source-index errors are repaired and logged. Bibliography entries are excluded from topic selection. Process and relationship arrows follow source proposition roles; a directed predicate does not automatically assert causation. Comparisons and source-page annotations can omit links. Qualitative relation tracing is not a simulation of a 3-D hand, physics, or biological mechanisms. Itemized reviews record the original meaning and the reason for each object, relation, and spoken step, rejecting invented causation, guarantees, or necessary conditions. Quantity checks distinguish technical measurements from indefinite articles and explicitly labeled analogies; they do not replace meaning checks. Approval by the same model does not prove all domain facts.

The optional installation includes PyMuPDF for source-page extraction and real text-region locations, plus Jieba for Chinese phrase candidates without a fixed subject glossary. Ollama calls read the model’s advertised [thinking controls](https://docs.ollama.com/capabilities/thinking), rather than forcing settings from its name. Hybrid models enable thinking during design and review; thinking-only models follow the server default, and non-thinking models receive no switch. For switchable models that exhaust the structured-output budget, set `ZHIJIANG_OLLAMA_SEMANTIC_THINKING=false` in Git-ignored `.env.local` and restart. Non-switchable services keep their advertised defaults. Output-budget exhaustion produces a specific error; call durations and token counts are saved in local diagnostics. Local CPU inference may take longer, and the page shows the active planning stage.

Before designing a diagram, an isolated call extracts source propositions (subject, predicate, object, and fact IDs). The designer selects proposition IDs, while trusted code constructs nodes, copies relations, and requires matching endpoints; co-occurrence cannot create a new edge. Passive and multi-sentence relations retain multiple facts, negation, qualifications, and full conditions in scene data, narration, and SVG condition legends. Names and predicates can retain their original language while narration uses Chinese source facts. Phrase candidates include objects, operations, and conditions from the current source, without subject-specific drawing branches. Directed graph structure, branches, and cycles determine layout; the same graph and spoken facts drive animated tracing. Expand “知识关系与来源” in the page to inspect propositions and evidence. Basic mode shows source bullet content without choosing probability or other subject diagrams from keywords.

Source propositions are still model-reading drafts and require itemized full-page meaning review. Review approval binds to a digest of the design; changed edges, directions, conditions, nodes, or speech cannot reuse an old approval. Unsupported relations trigger comparison or source-page redesign. Geometry contract and computation failures receive bounded repair before representation redesign. Position-based PDF extraction retains spaces across font changes and example lines where possible; the updated parser invalidates older extraction caches. Position extraction, semantic review, and knowledge graphs do not prove textbook facts.

Graph labels can retain complete short names without truncating clauses or lists. English wrapping preserves whole words, and text scales to each card. Unresolved pronouns, dangling phrases, and ellipsis predicates cannot become graph endpoints or links. Direct identity relations also check the source's subject–copula–object order, avoiding confusing an activity with its cost or an object with its property. Complex prose can use source-page annotations. These conservative language checks are not proof of domain facts.

When the topic's original citation matches an independently read fact, that fact must appear in the explanation. A neighboring rule cannot replace the current counterexample or condition. Graphs omitting core facts are redesigned or use source-page annotations; cached scenes undergo the same check. Unmatched citations still require semantic review, so this is not a guarantee of complete coverage.

New source-page notes locate the complete source quote. Only names literally present in the source receive exact name anchors. A translated concept cannot be attached to an unrelated English field through a guessed locator. Every note still requires meaning review against the full quote.

A segment can include at most one complete everyday analogy (12–80 characters), enabled only on request. It cannot add technical behavior or guarantees. Display headings derive from the checked topic and selected representation; original model headings, repairs, and rejection reasons remain in local diagnostics.

See the [real-source generation repair validation](content-design-validation.md) for reproduced failures, runtime conditions, and actual acceptance of the user PDF.

The nine-page RealDex paper produced a 13-slide PPTX, six SVGs, and a 3-minute-34-second narrated video through local text and speech models. Web playback and downloads were checked. All six clips use source-page guidance; label clarity, flattened mathematical notation, and mechanism animation remain unaccepted teaching-quality items, recorded in that report.

When everyday examples are requested, comparisons and source-page guidance prefer explicit examples already in the source, binding them to the same fact without inventing another analogy. Source readings must contain complete Chinese sentences; untranslated or truncated older caches are regenerated. PNG compatibility images retain the SVG canvas dimensions, avoiding cropped captions and sources.

Itemized reviews allow concise source object names and explain support separately, avoiding invented padding. Invalid model content remains in the local job’s `model-format-errors.json`, outside web error messages. It does not record request headers, credentials, or reasoning fields.

Diagrams check explicit neighboring operations. When an initial operation is followed by a stated next operation, the diagram retains those source facts and their order, avoiding a skipped intermediate step. This uses source sequencing cues, without a subject-specific process template.

Guided-source and comparison explanations also bind the topic’s most specific sourced phrase to a required spoken fact. Other facts on the same page cannot replace the current topic. This local text check does not establish synonym coverage, chapter completeness, or teaching quality.

Cross-subject regression fixtures cover approaching secants, probability areas, projectile motion, atom rearrangement, and schematic enzyme catalysis, using the same executor for narrated PPTX and video. These developer-authored storyboards test expression, computation, and rendering; real PDF/model planning is evaluated separately. See the [general scene validation report](general-scene-validation.md) for actual results and scientific simplifications.

A real MIT calculus PDF has produced a deck and animations through the web page, local model, and speech API. This run used explicit teaching guidance and human corrections to three secant colors that disagreed with the narration. It validates that production path, without establishing unguided quality from the small local model for arbitrary textbooks. The report separates original output, corrections, and acceptance scope.

Built-in checks cover expressions, geometry, interpolation, equality, non-negativity, and declared upper bounds. Trusted project code or Python entry points `book2course.visual_checks` / `book2course.visual_validators` can add domain rules. The latter receives the full scene and `domain_data` for units, atoms, or relationships. Models cannot execute code or register rules. Extend the executor for new primitives or complex mechanisms; see the [general scene architecture](scene-graph.md). Open subject scope still requires source-specific teaching validation.

The model chooses parameters and questions and drafts a structured storyboard. The program executes a finite set of supported operations, never model-generated code. SymPy checks matrix products, vector endpoints, area, projection idempotence, eigen relations, and composition order, rejecting incorrect calculations. Fact-bearing narration uses parameterized explanations bound to computed states; model drafts remain available for review. This prevents spoken claims from contradicting correct claim arrays. Phrase-level speech durations control intermediate holds. Rotation interpolates angles while preserving length; projection moves along the normal. SVG summaries use the same verified data.

`GET /api/config` returns `math_animation` and `visual_animation` environment status. The upload field `animation_mode=auto|visual|geometry|math|basic` selects the mode. Completed jobs display scene/check scope and offer `GET /api/jobs/{id}/scenes` with parameters, storyboards, speech cues, calculations, and rendered geometry checks. Specialized jobs retain `/math-scenes`. Optional `math_scene` and `visual_scene` fields preserve older lesson data.

Validation uses MIT's five-page [Linear transformations and their matrices](https://ocw.mit.edu/courses/18-06sc-linear-algebra-fall-2011/resources/mit18_06scf11_ses3-6sum/). Principle excerpts retain source pages; numeric examples, area explanations, and Chinese animation scripts are supplemental. See the [math animation validation report](math-animation-validation.md) for methods and actual results. MIT material is credited under its [CC BY-NC-SA 4.0 license](https://ocw.mit.edu/pages/privacy-and-terms-of-use/). Local test files stay in Git-ignored `data/`.

## General mathematical object demonstrations

`geometry` requires actual 2-D mathematical objects, reads the complete cited page and fails explicitly without qualitative diagram fallback. Restricted function and `parametric_curve` expressions support arcs, closed curves and parameterized paths without executing model code.

SVG and Manim share equal coordinate units, preserving length ratios and angles. Planning checks parameter dependencies; symbolic repairs select existing fields. `parameter_changes` bind operations to declared variables. Review receives measured motion, and rotation claims without directional change are rejected. Unbound worded numeric quantities are also rejected.

This does not prove mathematical truth, complete reasoning or teaching quality. Inspect sources, SVGs and real intermediate frames. See [four-level textbook validation](math-level-validation-2026-10.md). Mixed PDFs may omit graphical formulas despite readable prose; current OCR does not supplement all such formulas.

Strict mathematical scenes use `geometry_constraints`: the model selects existing object IDs, relation types and source IDs; the program binds quotations and measures actual objects. Supported relations include function/circle membership, equal distances/lengths/areas, perpendicular/parallel lines and common origins. Five states per step are checked during planning, then every rendered frame is checked again. Visible point and label anchors must stay in the coordinate window; curves and lines may be clipped at its boundary. This does not check every label extent or ensure all core conditions were bound. Cached numeric scenes require matching scene digests and renewed checks.

Local mathematical calls use simple JSON decoding while the prompt and program retain the full contract. Undeclared parameters and invalid expressions still fail. Runtime stalls were observed under local service and GPU-memory load; decoder cost was not isolated causally, so no speedup or model ranking is established.

Format retries extract allowed types, enums, lengths, patterns and numeric bounds from the existing schema without echoing invalid values or source text. More specific feedback does not guarantee model compliance: the 7B Taylor extraction still failed after this change.
