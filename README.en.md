# Zhijiang Agent (Book2Course)

**Language / 语言:** [简体中文](README.md) | [English](README.en.md)

Zhijiang Agent turns PDFs that you have the right to use into Chinese educational videos and presentation decks. It uses position-based extraction for text-based PDFs and runs OCR locally for scanned pages. After you upload a document, the web page shows the course outline, narration for each segment, PDF page numbers, and source excerpts. It also provides downloadable MP4 and PPTX files. The PPTX contains SVG teaching diagrams, playable explanatory clips, and speaker notes.

There are two generation modes: **real AI mode** uses local Ollama or an external compatible model; **deterministic demo mode** uses fixed rules and needs no model or API key. The demo is labeled in the page and video. For each job, the web page lets you set the text model provider, API URL, model name, API key, and an instruction prompt. You can configure the speech API URL, model, voice, and key separately. Narration can use a Chinese Windows system voice, a local Chinese Kokoro AI speech model, or an external compatible speech service. Source verification checks that excerpts match the corresponding extracted or OCR text; the accuracy of explanations and OCR still needs human review.

## From book to course

The sketch's “book → OCR/typesetting → pages” and “main slides → narration/animation → assembly” paths form one workflow with source references. There are three routes: basic diagrams, general scenes across subjects, and specialized 2-D linear transformations. Scenes receive their corresponding checks and use actual speech durations for Manim/LaTeX rendering. Citation checks locate excerpts; teaching quality still needs human review.

[![Workflow from PDF to lesson video](docs/workflow.en.svg)](docs/workflow.en.svg)

Basic videos use Pillow. General teaching scenes and specialized math videos use local Manim Cairo with LaTeX formulas. The PPTX has a cover and two slides per topic: an SVG summary and an animation. Native text is editable; each SVG has a PNG fallback. Summary images are centered at their original aspect ratio, and SVGs specify a Chinese font and fallback fonts. Click a segment's MP4 during a slideshow. Notes contain step-by-step narration, source pages, and excerpts. General and specialized clips include narration and reuse the full lesson video's assets, embedded at their original 16:9 aspect ratio.

### PPT production skills

The following repository Codex skills help refine PPT content and assets. Web jobs generate a PPTX with built-in templates and do not invoke these skills automatically. Invoke them by name in a Codex task for this project:

| Skill | Purpose |
| --- | --- |
| [`$book2course-ppt-outline`](.agents/skills/book2course-ppt-outline/SKILL.md) | Plan slides from learning dependencies and source pages; check for missing key concepts. |
| [`$book2course-ppt-script`](.agents/skills/book2course-ppt-script/SKILL.md) | Write a page-aligned speaker script, notes, narration, and visual cues. |
| [`$book2course-svg-diagrams`](.agents/skills/book2course-svg-diagrams/SKILL.md) | Create editable SVG flowcharts, concept diagrams, and formula step diagrams. |
| [`$book2course-explainer-animation`](.agents/skills/book2course-explainer-animation/SKILL.md) | Design explanatory visual transformations and check visuals against narration and timing; use [Manim Community](https://docs.manim.community/en/stable/) when needed. |

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

See the [real-source generation repair validation](docs/content-design-validation.md) for reproduced failures, runtime conditions, and actual acceptance of the user PDF.

The nine-page RealDex paper produced a 13-slide PPTX, six SVGs, and a 3-minute-34-second narrated video through local text and speech models. Web playback and downloads were checked. All six clips use source-page guidance; label clarity, flattened mathematical notation, and mechanism animation remain unaccepted teaching-quality items, recorded in that report.

When everyday examples are requested, comparisons and source-page guidance prefer explicit examples already in the source, binding them to the same fact without inventing another analogy. Source readings must contain complete Chinese sentences; untranslated or truncated older caches are regenerated. PNG compatibility images retain the SVG canvas dimensions, avoiding cropped captions and sources.

Itemized reviews allow concise source object names and explain support separately, avoiding invented padding. Invalid model content remains in the local job’s `model-format-errors.json`, outside web error messages. It does not record request headers, credentials, or reasoning fields.

Diagrams check explicit neighboring operations. When an initial operation is followed by a stated next operation, the diagram retains those source facts and their order, avoiding a skipped intermediate step. This uses source sequencing cues, without a subject-specific process template.

Guided-source and comparison explanations also bind the topic’s most specific sourced phrase to a required spoken fact. Other facts on the same page cannot replace the current topic. This local text check does not establish synonym coverage, chapter completeness, or teaching quality.

Cross-subject regression fixtures cover approaching secants, probability areas, projectile motion, atom rearrangement, and schematic enzyme catalysis, using the same executor for narrated PPTX and video. These developer-authored storyboards test expression, computation, and rendering; real PDF/model planning is evaluated separately. See the [general scene validation report](docs/general-scene-validation.md) for actual results and scientific simplifications.

A real MIT calculus PDF has produced a deck and animations through the web page, local model, and speech API. This run used explicit teaching guidance and human corrections to three secant colors that disagreed with the narration. It validates that production path, without establishing unguided quality from the small local model for arbitrary textbooks. The report separates original output, corrections, and acceptance scope.

Built-in checks cover expressions, geometry, interpolation, equality, non-negativity, and declared upper bounds. Trusted project code or Python entry points `book2course.visual_checks` / `book2course.visual_validators` can add domain rules. The latter receives the full scene and `domain_data` for units, atoms, or relationships. Models cannot execute code or register rules. Extend the executor for new primitives or complex mechanisms; see the [general scene architecture](docs/scene-graph.md). Open subject scope still requires source-specific teaching validation.

The model chooses parameters and questions and drafts a structured storyboard. The program executes a finite set of supported operations, never model-generated code. SymPy checks matrix products, vector endpoints, area, projection idempotence, eigen relations, and composition order, rejecting incorrect calculations. Fact-bearing narration uses parameterized explanations bound to computed states; model drafts remain available for review. This prevents spoken claims from contradicting correct claim arrays. Phrase-level speech durations control intermediate holds. Rotation interpolates angles while preserving length; projection moves along the normal. SVG summaries use the same verified data.

`GET /api/config` returns `math_animation` and `visual_animation` environment status. The upload field `animation_mode=auto|visual|math|basic` selects the mode. Completed jobs display scene/check scope and offer `GET /api/jobs/{id}/scenes` with parameters, storyboards, speech cues, calculations, and rendered geometry checks. Specialized jobs retain `/math-scenes`. Optional `math_scene` and `visual_scene` fields preserve older lesson data.

Validation uses MIT's five-page [Linear transformations and their matrices](https://ocw.mit.edu/courses/18-06sc-linear-algebra-fall-2011/resources/mit18_06scf11_ses3-6sum/). Principle excerpts retain source pages; numeric examples, area explanations, and Chinese animation scripts are supplemental. See the [math animation validation report](docs/math-animation-validation.md) for methods and actual results. MIT material is credited under its [CC BY-NC-SA 4.0 license](https://ocw.mit.edu/pages/privacy-and-terms-of-use/). Local test files stay in Git-ignored `data/`.

## Quick start (Windows)

Run these commands in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/), upload a PDF that you have the right to use, confirm your rights, and start generating. You can try the [sample handout](examples/binary_search_original.pdf). When generation finishes, you can inspect sources, play or download the video, download the PPTX, and delete local jobs and files. Re-upload the source PDF for an older job that has no PPTX. A failed job can be regenerated from its original PDF. Press `Ctrl+C` to stop the web server.

The runtime requires Python 3.11+; a Chinese Windows system voice is needed when you select system narration. It has been verified with Python 3.13. `rapidocr` and `onnxruntime` run OCR locally, while `pypdfium2` renders scanned pages. `python-pptx` creates the deck. `imageio-ffmpeg` supplies the FFmpeg binary used to assemble videos and embedded clips, so a separate system FFmpeg installation is unnecessary.

## Use local Ollama

Install and start [Ollama](https://ollama.com/), then check your models with `ollama list`. The default template uses non-thinking [`qwen3:4b-instruct`](https://ollama.com/library/qwen3%3A4b-instruct). If it is not available locally, run `ollama pull qwen3:4b-instruct`. Enter the actual model name in the web page when using another model. Copy the configuration template and restart the web server:

```powershell
Copy-Item .env.local.example .env.local
```

`.env.local` is ignored by Git. You can change the Ollama URL and model there. Real AI mode uses the local `/api/chat` endpoint to generate key points, a course plan, and narration. Extracted PDF text is not sent to an external text model in this configuration. The model first selects numbered source excerpts with page references; the program then inserts and verifies the quotations to reduce errors from rewritten source text. Structured calls use an 8192-token context; general storyboards split object layout from operations/calculations, with separate repair stages. CPU inference and complex storyboards can take longer; small models may require revisions or fail checks. Choose a stronger model API in the page when needed.

Local validation uses Ollama 0.35.1. On low-memory computers, set the llama.cpp backend’s [prompt-cache limit](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) before starting Ollama. This computer uses 512 MiB. Exit the existing Ollama service, then run:

```powershell
$env:LLAMA_ARG_CACHE_RAM = "512"
ollama serve
```

Support depends on the backend version and takes effect after restarting the service. Model-interface 5xx errors get at most one format retry. A chat-parser HTTP 500 uses Ollama’s native [generation endpoint](https://docs.ollama.com/api/generate) with the same schema. Only duplicated closing tokens after a complete valid object can be removed; source and semantic checks still apply. Persistent failures preserve progress and report an error.

For a failed job, change the generation mode, text/speech APIs, voice, prompt, or animation mode, then select “使用原 PDF 重新生成” (regenerate from the original PDF). Retry uses the current settings without another upload. Changing an external service requires explicit transmission consent and its credential; the old destination's job credential is not forwarded to the new one.

Open `/?job=JOB_ID` locally to restore a job's progress and outputs; use the 32-character identifier returned by the API.

Failed retries retain completed PDF parsing, knowledge extraction, and storyboards that passed itemized review. Source-matched structure drafts are stored in `source-structure-XX.json` so failed speech planning can resume; these drafts remain unapproved and still require semantic review. Independent comprehension drafts are stored in `source-reading-XX.json`; reused drafts still undergo itemized review and are not treated as approved. Reused scenes are rechecked against sources and execution rules before fresh speech and rendering; rejected candidates are not cached. Changed PDFs, model endpoints, models, or prompts invalidate the corresponding analysis cache; credentials are excluded. Knowledge IDs are constrained to the current source batch. Extraction retains local definitions and conditions and excludes multi-column count headers. Candidate designs and rejection reasons remain in `knowledge-planning.json` and `teaching-design-XX.json`; `model-calls.json` records local call durations, token counts, and termination reasons for diagnosis.

In basic mode, concrete numbers must appear in the source excerpt; unsupported values trigger a rewrite, then removal and a review notice if needed. Specialized and general scenes accept labeled teaching parameters and calculated results without this source-number filter. Principles and supplemental examples are separate. Numeric checks do not prove free-form narration, domain facts, or teaching explanations.

New general storyboards use qualitative prose for objects, operations, and reasons; verified parameters and calculations generate numeric narration. Unbound literal numbers and common Chinese numeric assertions are rejected, so an approving review model cannot preserve that class of wrong spoken calculation. Each new segment plans 3–5 short steps with 12–100 characters of qualitative speech per step; older course data remains readable. Original drafts remain available. Qualitative explanations and domain facts still require source and human review.

You can skip `.env.local` and configure a job in the web page. API keys remain in server memory while the job runs and are never written to SQLite, lesson JSON, or responses. Refreshing or restarting before an external-model retry requires entering the key again. Prompts control planning, teaching parameters, and basic narration style. Math narration currently uses verified templates; prompts cannot bypass source or computation checks.

You can view a [sample video](demo/zhijiang_ollama_demo.mp4) and its [lesson script and sources](demo/zhijiang_ollama_lesson.json). The script was generated by a local model, and the voice comes from Windows system speech.

## Progress and resume for scanned textbooks

Parsing/OCR reports individual page progress and saves `parsed-pages/page-XXXXX.json`, including processed blank pages. Knowledge extraction reports source batches and saves validated results immediately in `knowledge-batches/batch-XXXX.json`. Retrying the original PDF reuses completed pages and batches; changed source files or corresponding analysis settings invalidate related caches. Previously completed whole-document parsing caches also remain reusable without repeating OCR.

Local Ollama streams progress with elapsed call time and received character counts. Elapsed time also updates during prompt processing before content arrives. Results are validated and saved only after the complete response and completion marker; partial JSON is never accepted as success. Whole textbooks can still take considerable time on a CPU. Percentages describe stage progress, not an estimated time remaining. Close or refresh the page and return through the job link, while keeping the local services running.

Chinese scanned excerpts retain short definitions, wrapped text, and adjacent context. Explicit publishing metadata, prefaces, and contents pages are excluded; judgement exercises retain their instructions. Knowledge summaries reject numbers absent from the current excerpt and cannot guess OCR-damaged fractions or ratios. Supplemental teaching examples are labeled and checked separately in later scenes. Text matching and number checks do not establish OCR accuracy, correct exercise answers, or full chapter coverage.

See [long textbook progress validation](docs/long-textbook-progress.md) for the actual grade-six scanned source, diagnosis, tests, and resumed-run status.

When one knowledge point fails number checks, only its explanation is repaired. Valid points keep their titles, types, explanations, and sources; the failed topic is retained. Unapproved batch drafts are saved as `batch-XXXX.draft.json`, so retries continue their repairs before validation. These drafts are not completed knowledge checkpoints. Persistent failure identifies the affected topic and retains the draft and repair records for source review.

If free rewriting repeatedly fails, the model may only select a readable clause ID from the current excerpt, and the program inserts that clause verbatim. Candidates exclude specific quantities and fractions and must belong to the point's source. When a short excerpt lacks a usable explanation, a further selection chooses a literal span from the same original page, updates only the failed point's quotation, and produces a qualitative summary. Same-page quotations must match contiguous source text, including when old caches are reused. Missing candidates or mismatched selections produce an explicit error. This constrained repair retains the topic without guessing damaged OCR; it does not recover missing formulas.

Matching digits do not establish a correct fraction, ratio, or formula. Quantitative clauses in knowledge summaries must preserve the current excerpt verbatim. Other quantitative wording receives a targeted repair to explain readable concepts and request source-image review. Checks include worded Chinese fractions and common numeric claims, distinguish generic Chinese references to a number or two numbers, and preserve sourced identifiers such as `CO2`, `H2O`, and `B12`. Older batches are checked against current rules without rewriting valid points. These text rules do not prove arbitrary domain facts or complete teaching meaning.

If local Ollama's native schema decoder interrupts, the job tries plain JSON decoding while retaining full contract validation. This format recovery allows at most three calls; valid formatting does not establish correct content. A successful compatibility mode is reused for the same stage in the current job and recorded in `model-calls.json`. Source-fact decoder patterns have a length bound. The program may append missing final sentence punctuation without changing words; short fragments, clipped operators, invalid IDs, and non-Chinese explanations remain rejected.

Before scanned pages enter scene design, independently extracted source facts also receive numeric-reference checks. Quantitative inferences that cannot match the excerpt verbatim are excluded from the fact array and recorded in `rejected_facts` within `source-reading-XX.json`. Course topics are retained, and readable definitions and conditions remain available for teaching. If no verifiable fact remains, the job fails explicitly. This check does not recover OCR-missing values or replace itemized semantic review and source-image inspection.

Qualitative diagrams explain source facts by default. Additional everyday analogies are enabled only when explicitly requested in the prompt; existing source examples take priority. Numerical examples require a computationally checked scene and cannot introduce unverified fractions or measurements through an analogy.

Unanswered quantity questions on scanned pages remain on the original page for inspection and are not narrated as established facts. Digits present in OCR do not establish intact fraction layout. Retrying rechecks fact drafts, records rejected optional assertions, and reuses the remaining readable facts.

If number checks reject every OCR fact draft, a constrained selection can choose readable source-clause IDs from the current excerpts. The program inserts those clauses verbatim and records repairs in `source-reading-XX.json/repairs`. No usable clause still produces an error, and semantic review remains required. Object candidates allow quantity and action phrases rather than requiring noun POS tags. Relations retain full source predicates, including single-character Chinese predicates; conjunctions alone do not form a relation. When a displayed name occurs explicitly in the same quotation, `source_term` binds to that literal name and records `literal_node_name`, preventing an unrelated nearby digit from being selected. Translation and meaning still require review.

Source reading validates the complete JSON container, count, and source IDs before checking each record's complete Chinese statement, length, and numeric references. Invalid records are rejected and logged individually while usable facts remain. If bounded container-format repair still fails, scanned pages may also try literal clause selection. Partial content from malformed JSON is not accepted, and connection or timeout failures are not treated as content repairs.

Meaning review checks nodes according to the chosen representation. Source-page annotations and comparisons may label phrases, actions, conditions, or outcomes without treating each label as an independent entity. Unlinked annotations do not imply a relationship. Links in relationship and process diagrams still require separate source checks; wrong references and omitted spoken conditions are rejected.

Review output records each item's source meaning and reason before its support verdict. The program checks item coverage and aggregates approval. Source annotations use separate `annotation_checks` rather than graph-entity checks. Raw OCR and layout concerns go into `source_warnings`; any concern preventing confirmation of the current explanation must still reject that item. Persisted rejections are not automatically approved. The current question comes from the storyboard, not a neighboring exercise on the same page.

Complete course ordering is saved to `course-order.json` and can be reused after a scene failure. Changes to the source, knowledge points, prompt, model, or API address invalidate this cache; missing or repeated IDs cannot be reused. Source-page images are reused after matching PDF and image-file hashes. The web page shows the page being exported or reused, and missing or damaged images are exported again individually.

## Use local AI narration

On a computer without an NVIDIA GPU, you can run the Chinese [Kokoro-82M v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) model on the CPU. In the project directory, install the optional dependencies and download the [ONNX Community quantized model](https://modelscope.cn/models/onnx-community/Kokoro-82M-v1.1-zh-ONNX) and four Mandarin voices (about 130 MB, stored in the Git-ignored `data/models/kokoro/` directory; the download script verifies SHA-256 checksums):

```powershell
.\.venv\Scripts\python -m pip install -e ".[local-tts]"
.\.venv\Scripts\python scripts\download_local_tts.py
```

Start the local speech API in one terminal and keep it running:

```powershell
.\.venv\Scripts\python -m uvicorn zhijiang.local_tts:app --host 127.0.0.1 --port 8766
```

Start the main web server in another terminal. After copying `.env.local.example` to `.env.local`, the web page defaults to `http://127.0.0.1:8766/v1`, model `kokoro-82m-v1.1-zh`, and Mandarin voice `zf_001`. You can also choose `zf_002`, `zm_009`, or `zm_010`. Alternatively, skip the file, select “AI 语音配音” (AI narration) in the web page, and enter those values there. The local API needs no key and synthesizes audio on this computer. The first request loads the model; long scripts take more CPU time. Open the [speech service health check](http://127.0.0.1:8766/health) to confirm the model files are installed.

## External models and speech services

To use an external text model, set the URL of a service compatible with `POST /chat/completions`, its model name, and its API key before starting the server:

```powershell
$env:ZHIJIANG_LLM_PROVIDER = "openai"
$env:ZHIJIANG_LLM_BASE_URL = "https://your-service.example/v1"
$env:ZHIJIANG_LLM_API_KEY = "your-api-key"
$env:ZHIJIANG_LLM_MODEL = "your-model"
```

External AI narration requires a service compatible with `POST /audio/speech` that returns WAV. These variables can replace the local speech settings in `.env.local`; you can also enter them for an individual job in the web page:

```powershell
$env:ZHIJIANG_TTS_BASE_URL = "https://your-speech-service.example/v1"
$env:ZHIJIANG_TTS_API_KEY = "your-speech-api-key"
$env:ZHIJIANG_TTS_MODEL = "your-speech-model"
$env:ZHIJIANG_TTS_VOICE = "alloy"
```

The web page asks for additional consent before sending extracted text or narration to an external service. Speech and text API keys stay in server process memory only while the job runs; retrying a failed external speech job requires entering the speech key again. Do not commit API keys to the repository.

## Tests and examples

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\generate_sample_pdf.py
.\.venv\Scripts\python scripts\build_demo.py
.\.venv\Scripts\python scripts\build_ollama_demo.py
.\.venv\Scripts\python scripts\build_general_examples.py
.\.venv\Scripts\python scripts\verify_teaching_artifacts.py --job-dir data\jobs\JOB_ID
```

`build_ollama_demo.py` requires local Ollama to be configured first. A [sample video that needs no model](demo/zhijiang_demo.mp4) is also available.

`build_general_examples.py` renders five original calculus, probability, physics, chemistry, and biology fixtures with the same general executor and the configured speech API. These test authored storyboards and rendering; real model planning is tested separately through PDF uploads. See the [cross-subject validation record](docs/general-scene-validation.md).

### Textbook validation without authored storyboards

Selected original pages from open linguistics, sociology, economics, and database design textbooks are passed to local models with an empty prompt. The model extracts topics and plans diagrams, narration, and animation. Bibliography, pages, and file hashes are recorded in [holdout-sources.json](examples/holdout-sources.json). Original PDFs, model outputs, failures, MP4s, and PPTX files stay in Git-ignored `data/`. Initial runs contained relation, example, and truncation errors. The [new-domain textbook validation](docs/generalization-validation-2026-10.md) separates models, iterations, actual media checks, and human content review; authored rendering fixtures are not generalization evidence.

```powershell
.\.venv\Scripts\python -m scripts.verify_textbook_generalization --pdf data\holdout\linguistics.pdf --pages 172,173,175 --output data\holdout\linguistics-verify --model qwen3.5:9b --no-thinking --render
```

The harness supplies no topic, SVG, object coordinates, storyboard, or tailored teaching prompt. The first three books informed defect fixes; the fourth was added afterward. It evaluates selected original pages, not whole-book coverage or guaranteed quality on arbitrary textbooks.

## Current scope

- Jobs run sequentially on one machine; one PDF produces one lesson.
- Text-based and scanned PDFs are supported. Uploads are limited to 200 MB, with no fixed page count limit. Scanned pages are OCRed one at a time in the background, so processing time grows with the page count.
- AI mode selects evidence from all pages containing text in batches and generates a course without a fixed target video duration. Actual duration depends on the source material, model output, and speech rate. Long documents require more model calls.
- Demo mode has no page or segment count limit either. For documents of up to two pages, it still selects the first six candidate segments; for longer documents, it selects at most three per page.
- Each segment has an SVG diagram slide and an embedded MP4 slide. General and specialized clips include synchronized narration; basic clips are silent. Click to play during a slideshow. Size and render time grow with content. Titles and source labels are editable; paths inside an SVG are not separate PowerPoint shapes.
- General scenes support parameterized 2-D processes across subjects; specialized reasoning covers the five linear transformation scenes above. Complex 3-D and molecular dynamics require additional executors. Automatic reasoning across chapters and proof of factual claims are not implemented.
