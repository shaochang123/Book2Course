# Generation configuration and recovery

[简体中文](生成配置与恢复.md) | [English](configuration.en.md)

Detailed reference moved from the project README. See the [implementation status](实现状态与路线图.md) (Chinese) for current scope. Machine versions and validation results are specific to their linked reports.

## Use local Ollama

Install and start [Ollama](https://ollama.com/), then check your models with `ollama list`. The default template uses non-thinking [`qwen3:4b-instruct`](https://ollama.com/library/qwen3%3A4b-instruct). If it is not available locally, run `ollama pull qwen3:4b-instruct`. Enter the actual model name in the web page when using another model. Copy the configuration template and restart the web server:

```powershell
Copy-Item .env.local.example .env.local
```

`.env.local` is ignored by Git. You can change the Ollama URL and model there. Real AI mode uses `/api/chat` to generate key points, a course plan, and narration. With a local endpoint and a locally executed model, extracted text remains local; Ollama cloud tags still forward it to an external service. The model first selects numbered source excerpts with page references; the program then inserts and verifies the quotations to reduce errors from rewritten source text. Ordinary structured calls use an 8192-token context; mathematical construction calls request 16384. General storyboards split object layout from operations/calculations, with separate repair stages. CPU inference and complex storyboards can take longer; small models may require revisions or fail checks. Choose a stronger model API in the page when needed.

The previous guide recorded Ollama 0.35.1 and a 512 MiB prompt cache as a historical machine configuration, not an installation requirement. Check actual models and versions with `ollama list`, `ollama --version` and each validation report. On low-memory computers, set the llama.cpp backend's [prompt-cache limit](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) before starting Ollama. Exit the existing service, then run:

```powershell
$env:LLAMA_ARG_CACHE_RAM = "512"
ollama serve
```

Support depends on the backend version and takes effect after restarting the service. Transient HTTP 429, 502, 503 and 504 errors receive at most two retries with backoff; authentication errors are not retried. A chat-parser HTTP 500 uses Ollama’s native [generation endpoint](https://docs.ollama.com/api/generate) with the same schema. Format recovery and service retries are counted separately. Only duplicated closing tokens after a complete valid object can be removed; source and semantic checks still apply. Persistent failures preserve progress and report an error.

For a failed job, change the generation mode, text/speech APIs, voice, prompt, or animation mode, then select “使用原 PDF 重新生成” (regenerate from the original PDF). Retry uses the current settings without another upload. Changing an external service requires explicit transmission consent and its credential; the old destination's job credential is not forwarded to the new one.

Open `/?job=JOB_ID` locally to restore a job's progress and outputs; use the 32-character identifier returned by the API.

Failed retries retain completed PDF parsing, knowledge extraction, and storyboards that passed itemized review. Source-matched structure drafts are stored in `source-structure-XX.json` so failed speech planning can resume; these drafts remain unapproved and still require semantic review. Independent comprehension drafts are stored in `source-reading-XX.json`; reused drafts still undergo itemized review and are not treated as approved. Reused scenes are rechecked against sources and execution rules before fresh speech and rendering; rejected candidates are not cached. Changed PDFs, model endpoints, models, or prompts invalidate the corresponding analysis cache; credentials are excluded. Knowledge IDs are constrained to the current source batch. Extraction retains local definitions and conditions and excludes multi-column count headers. Candidate designs and rejection reasons remain in `knowledge-planning.json` and `teaching-design-XX.json`; `model-calls.json` records local call durations, token counts, and termination reasons for diagnosis.

In basic mode, concrete numbers must appear in the source excerpt; unsupported values trigger a rewrite, then removal and a review notice if needed. Specialized and general scenes accept labeled teaching parameters and calculated results without this source-number filter. Principles and supplemental examples are separate. Numeric checks do not prove free-form narration, domain facts, or teaching explanations.

New general storyboards use qualitative prose for objects, operations, and reasons; verified parameters and calculations generate numeric narration. Unbound literal numbers and common Chinese numeric assertions are rejected, so an approving review model cannot preserve that class of wrong spoken calculation. Each new segment plans 3–5 short steps with 12–100 characters of qualitative speech per step; older course data remains readable. Original drafts remain available. Qualitative explanations and domain facts still require source and human review.

You can skip `.env.local` and configure a job in the web page. API keys remain in server memory while the job runs and are never written to SQLite, lesson JSON, or responses. Refreshing or restarting before an external-model retry requires entering the key again. Prompts control planning, teaching parameters, and basic narration style. Math narration currently uses verified templates; prompts cannot bypass source or computation checks.

You can view a [sample video](../demo/zhijiang_ollama_demo.mp4) and its [lesson script and sources](../demo/zhijiang_ollama_lesson.json). The script was generated by a local model, and the voice comes from Windows system speech.

## Progress and resume for scanned textbooks

Parsing/OCR reports individual page progress and saves `parsed-pages/page-XXXXX.json`, including processed blank pages. Knowledge extraction reports source batches and saves validated results immediately in `knowledge-batches/batch-XXXX.json`. Retrying the original PDF reuses completed pages and batches; changed source files or corresponding analysis settings invalidate related caches. Previously completed whole-document parsing caches also remain reusable without repeating OCR.

Local Ollama streams progress with elapsed call time and received character counts. Elapsed time also updates during prompt processing before content arrives. Results are validated and saved only after the complete response and completion marker; partial JSON is never accepted as success. Whole textbooks can still take considerable time on a CPU. Percentages describe stage progress, not an estimated time remaining. Close or refresh the page and return through the job link, while keeping the local services running.

Chinese scanned excerpts retain short definitions, wrapped text, and adjacent context. Explicit publishing metadata, prefaces, and contents pages are excluded; judgement exercises retain their instructions. Knowledge summaries reject numbers absent from the current excerpt and cannot guess OCR-damaged fractions or ratios. Supplemental teaching examples are labeled and checked separately in later scenes. Text matching and number checks do not establish OCR accuracy, correct exercise answers, or full chapter coverage.

See [long textbook progress validation](long-textbook-progress.md) for the actual grade-six scanned source, diagnosis, tests, and resumed-run status.

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

## Local reference-conditioned speech

Qwen3-TTS 0.6B Base conditions new narration on a local reference clip. It runs in a separate environment; the main web environment does not need Torch, Qwen, or Gradio. The model/SDK license is Apache-2.0. References, transcripts, auditions, weights, and `.env.local` are Git-ignored. Reference audio and scripts stay local. Base uses a voice prompt; it does not expose CustomVoice/VoiceDesign's free-form style instructions.

```powershell
.\.venv\Scripts\python -m venv .venv-tts
.\.venv-tts\Scripts\python -m pip install torch==2.10.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv-tts\Scripts\python -m pip install -r requirements-tts.txt
.\.venv-tts\Scripts\python scripts/download_qwen_tts.py
.\.venv\Scripts\python scripts/prepare_voice_reference.py --input "reference.mp4" --start 4 --duration 14
```

For CPU inference, replace the Torch index with `https://download.pytorch.org/whl/cpu`. Model weights need about 1.83 GB, the speech decoder 0.68 GB, and CUDA needs additional space. Use a clear 3–25 second local clip; supply `--transcript` only with a matching transcription. With no transcript the service uses speaker-embedding mode; with a transcript it uses full reference context. Changing either invalidates the cached prompt.

Preserve existing `.env.local` settings and set:

```dotenv
ZHIJIANG_TTS_BASE_URL=http://127.0.0.1:8766/v1
ZHIJIANG_TTS_MODEL=qwen3-tts-0.6b-base
ZHIJIANG_TTS_TIMEOUT_SECONDS=900
ZHIJIANG_TTS_VOICE=notebook-reference
ZHIJIANG_DEFAULT_VOICE_MODE=ai
ZHIJIANG_QWEN_TTS_MODEL_DIR=data/models/qwen3-tts-0.6b-base
ZHIJIANG_QWEN_TTS_REFERENCE=data/voice-reference/voice.json
ZHIJIANG_QWEN_TTS_DEVICE=auto
ZHIJIANG_QWEN_TTS_CODEC_DEVICE=cpu
ZHIJIANG_QWEN_TTS_QUANTIZATION=none
ZHIJIANG_QWEN_TTS_IDLE_SECONDS=60
```

Run `.\scripts\start_voice_service.ps1` and the main web server in separate terminals; `Ctrl+C` stops the corresponding service. `auto` uses CUDA when available, otherwise CPU; the audio codec stays on CPU by default to reduce GPU memory use. Set `cpu` and restart speech if GPU memory is insufficient. CPU is usually slower. The speech process releases its model after 60 idle seconds and reloads it on the next request. Narration is split into punctuation-preserving chunks of at most 50 characters and uses the model's default incremental-text mode; HTTP returns a complete WAV. Hitting the generation limit fails rather than returning truncated audio.

This machine uses the unquantized 0.6B model; synthesis is not real-time. `ZHIJIANG_TTS_TIMEOUT_SECONDS=900` allows 15 minutes per HTTP speech request. Its unchanged default is 300 seconds, bounded to 30–3600. Both the pipeline and audition tool use it. Optional 1.7B downloads use `--size 1.7b`; change both the model name and directory. Optional CUDA language-layer int8 uses `requirements-tts-int8.txt` and `ZHIJIANG_QWEN_TTS_QUANTIZATION=int8`; the audio codec stays floating point. CPU dynamic int8 failed the actual generation check and is not offered; use `none` on CPU. Model aliases must match actual Base configuration.

With speech running, execute `.\.venv\Scripts\python -m scripts.preview_voice`. The website serves this pre-generated original audition only when its model, voice, address, and checksum match configuration; playing it does not call a remote model. New website sessions prefer AI narration with `ZHIJIANG_DEFAULT_VOICE_MODE=ai`; old jobs restore their own selection, and API calls without `voice_mode` still default to system speech. Video and PPT use the actual synthesized WAV duration. Failed chunks fail the request rather than returning partial narration.

Checks cover text preservation, reference integrity, invalid/silent audio, explicit errors, and audition matching. Local transcription and pitch statistics support comparison; listening is needed to judge voice similarity, emphasis, pauses, and naturalness. See [the Chinese speech guide](自然讲解配音.md) and [validation records](验证与验收.md).

## Use local AI narration

The configuration template now selects Qwen. The following Kokoro service is a lighter alternative; explicitly change its model and voice values. Start either speech service on port 8766.

On a computer without an NVIDIA GPU, you can run the Chinese [Kokoro-82M v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) model on the CPU. In the project directory, install the optional dependencies and download the [ONNX Community quantized model](https://modelscope.cn/models/onnx-community/Kokoro-82M-v1.1-zh-ONNX) and four Mandarin voices (about 130 MB, stored in the Git-ignored `data/models/kokoro/` directory; the download script verifies SHA-256 checksums):

```powershell
.\.venv\Scripts\python -m pip install -e ".[local-tts]"
.\.venv\Scripts\python scripts\download_local_tts.py
```

Start the local speech API in one terminal and keep it running:

```powershell
.\.venv\Scripts\python -m uvicorn zhijiang.local_tts:app --host 127.0.0.1 --port 8766
```

Start the main web server in another terminal. For Kokoro, set `http://127.0.0.1:8766/v1`, model `kokoro-82m-v1.1-zh`, and voice `zf_001` in `.env.local` or the website. You can also choose `zf_002`, `zm_009`, or `zm_010`. The local API needs no key and synthesizes audio on this computer. The first request loads the model; long scripts take more CPU time. Open the [speech service health check](http://127.0.0.1:8766/health) to confirm the model files are installed.

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

## General mathematical object mode

`geometry` is available in real AI mode and requires TeX and general animation dependencies. It plans 2-D objects, function curves and parametric curves from the complete cited page, without flowchart, highlight or fading-card fallback. Expressions bind to declared parameters; SVG and video share equal coordinate units. Model planning can fail, and successful execution still needs source and visual review. Page-image recognition can still misread complex formulas or diagrams. See the historical [mathematics validation](math-level-validation-2026-10.md).

This mode requires a generation model with image input. It transcribes and reviews formulas against actual page images before planning constructions and teaching operations; ordinary text OCR is not the only evidence for complex formulas. The web mathematical object mode uses JSON decoding with the full schema in the task; returned content still undergoes complete structure, variable and source validation. Mathematical calls request a 16K context. Relations are measured from actual objects during planning samples and rendered frames. Discrete quantities such as polynomial degree and partition count cannot be continuous controls; finite-series terms can grow through individual weights.

Optional mathematics planning and independent review models use the same API endpoint. The image-capable generation model reads pages, creates source scope and reviews SVG images; the planning model produces designs, constructions and behavior; the reviewer independently checks text and coverage. A different planning model first checks source-scope meaning; when generation and planning share a model, the reviewer does this check. A single-model configuration remains self-review. Empty fields use the generation model. Per-job API fields are `llm_math_model` and `llm_review_model`; scene `model_roles` records actual models. Planner calls and format failures are saved in `mathematical-planning-calls.json` and `mathematical-planning-format-errors.json`. Choose a different model from the planner for independent review. Candidate self-review is not independent review, and neither is a proof of correctness.

Page transcription retains the original language, conditions and actual diagrams. English prose missing most original words triggers rereading; summaries and translations cannot become literal quotations. Blank pages fail before model calls, and review can remove descriptions of nonexistent diagrams. Source caches bind to the image, native text, model and endpoint. These rules do not establish transcription accuracy.

Object construction and teaching behavior are separate stages. Measurement tools are constrained to actual object types: signed coordinates, nonnegative distances, areas, unsigned included angles, directed angles, function values and derivatives. Ratios also measure their denominators. Claims can be invariants or designated step-end conditions; endpoint conclusions cannot masquerade as invariants. Labels anchor to moving points and colors follow their curves. Visible finite anchors determine the equal-unit camera; remote function tails can be clipped. Core points must remain readable.

A source coverage list is generated independently before candidate planning. It records required conditions, conclusions and core worked examples. The model selects constrained `source_ids`; the program inserts the corresponding original excerpts into `source_excerpts`, with `citation_method=selected_exact_source_excerpts`. Facts spanning excerpts retain separate citations rather than a rewritten quotation. Index binding does not prove meaning, which still requires review against the complete source. Concept photographs and decorative illustrations may use equivalent correct mathematical diagrams; core worked examples retain their values and conditions. Source subjects bind to object types, vertex counts, visible steps and measurement dependencies, rejecting unrelated placeholder figures. Mathematics lessons use 3–10 steps according to the source; concise complete Chinese narration needs no padding. A failed list is not a teaching-quality approval.

`align` computes rotation and translation from actual source and target anchor/direction pairs. Progress runs from zero to one without scaling; every frame checks progress and nondegenerate directions. Actual arc endpoints may serve as hidden landmarks instead of guessed rotation angles. Construction errors return to construction repair even when the criticism also mentions the objective. Only behavior or wording errors retain geometry for local repair. Persistent semantic construction errors trigger at most two design revisions, retaining earlier drafts, replacements and rejection evidence.

`point_on_curve` computes measurement points from actual parametric curves or arcs; auxiliary points may be hidden. These support endpoint checks for alignment and joins. Hide a transformed object's original, or set `reference=true` to dim and label it as a reference. EOF without a completion marker discards that response and retries the same request at most twice. Mathematics field formats allow at most three recovery attempts and still require full validation.

When generation reaches its output budget, that stage gets one budget increase capped at 16384. A complete completion marker and full schema validation are still required; parsable truncated JSON is never approved. Mathematical planning allows ten repair rounds. A valid construction proceeds to operations and verification within that same round, including the final round. Repair requests include the rejected candidate and specific offending phrases. Missing controls and repeatedly unsuccessful behavior return to construction planning. Objects, operations, rejections and reviews are retained; rejected candidates do not proceed to media generation. A teaching-design draft is not supplied to reviewers as a source fact.

Ollama `:cloud` and `-cloud` models send materials to the cloud even through `127.0.0.1`. The page and API require additional consent if either the generation or review model is remote. Mathematics mode sends page images and text. Check the actual destination of custom proxies or aliases without cloud tags yourself. Local defaults are not automatically changed to cloud models.

Optional `ZHIJIANG_OLLAMA_NUM_GPU` sets the number of GPU layers; leave it empty for automatic allocation. This round used `24` on the 8 GB GPU to reserve room for desktop applications and context, not as an optimum for every machine. Logs record requests, durations, token counts and termination reasons. Cloud enforcement of requested context and sampling settings depends on the provider. Old approvals or caches do not count as acceptance of a new implementation.

Mathematical tests record the actual digests, quantization and settings for `qwen3.5:9b` and `qwen2.5:7b`. The local 8 GB GPU experienced long output stalls under heavy load. Serial execution and recorded model changes support diagnosis but do not establish a capability ranking. The application does not automatically rewrite `.env.local` or download models; select an installed text-generation model rather than an embedding model.


Mathematical review compares the original page images with each generated SVG. Source, geometry and motion observations precede approval. Shared-endpoint segments support vertex angles; directed arcs can retain a full signed sweep, whose actual endpoints are checked. Complex computed renderer expressions use bounded intermediate nodes without relaxing AST limits. Numeric narration repairs preserve the validated objects and operations; motion frames are checked continuously and holds retain a verified final state.


### Source meaning, construction tools and targeted repair

Source scope is generated against original page images and checked for translation, conditions, values, reference wholes and worked-example classification before scene design, with at most three repairs. `math-source-scope-attempts.json` retains the attempts. This remains model review and requires human comparison with the source. Tools return actual initial coordinates, areas, lengths and angles before checking whether the graph and its controls can express the required content.

`intersection` supports two lines/rays/segments or two circles, computing intersections and checking actual bounds and membership on rendered frames. Mixed line-circle intersections are unsupported. Lines and rays extend to the actual viewport. Curve points, including hidden auxiliary points, must remain within their curve's plotted domain.

Invalid `operations`, `claims` or `roles` fields in a complete behavior response can receive targeted repair while valid fields remain intact; `behavior_format_repairs` records changes. Malformed JSON is never recovered from partial content. The full contract, actual relationships, source, SVG and motion checks still apply. Worded Chinese fractions must also bind to real calculations. A gap that closes to zero is checked across motion samples, not just endpoints; a line that remains degenerate is still rejected.

`ZHIJIANG_OLLAMA_THINKING_LEVEL` uses only string levels actually advertised by `/api/show`; leave it empty for the service default. Unsupported levels fail explicitly. Boolean-switch models continue to use `ZHIJIANG_OLLAMA_SEMANTIC_THINKING`. Mathematical formatting recovery allows three attempts; one extra budget retry is available only when the third attempt first hits the output limit, never approving truncation. Cloud services currently do not support native structured outputs; schemas remain in prompts with program validation, as documented by [Ollama](https://docs.ollama.com/capabilities/structured-outputs).


Draft construction graphs allow 32 definitions, expanded core objects 48, and the rendering contract with point labels 64. A valid source-reviewed graph can receive a bounded `MathConstructionPatch`, retaining correct objects and adding missing constructions and real continuous controls. Dependency ordering is followed by complete compilation and acceptance checks. Two consecutive behavior failures return to construction repair even when wording differs; two patch format/compilation failures trigger full graph generation. Patches and their bases remain recorded, and model edits are not authored human storyboards.

Source and readiness reviews use batches of two while retaining all obligations. Reviewed Chinese source statements bind verbatim to explanation cards and actual speech, with definitions and conditions before the first motion. Cards cannot replace core diagrams, examples or mathematical movement. `fact_panels` and `source_seconds` record real speech durations; the web script retains these statements. General algebraic definitions may use these explanations without demanding arbitrary-order dynamic objects, while concrete examples still require accurate drawings and validation.

Up to six source subjects use atomic geometry types and `count`; composite entities decompose into required objects rather than using the compiler's internal partition `group` type. Bindings check each object's count, type, visibility and measured dependencies. Missing measurements or step visibility first repair behavior; missing objects or wrong types return to construction repair, with escalation after two failed behavior attempts. Completed diagram examples are not omitted merely because no printed calculation accompanies them. Undefined initial data is rejected before model review, and rejected candidates cannot enter media generation.

## PPT templates and recovery

Select a template on the website or submit `ppt_template=classic|paper|academic|editorial` in job creation/retry forms. No additional dependencies are required. Old jobs and API calls default to `classic`; new website jobs default to `paper`. New-template layout planning uses the current job model and existing scripts, bullets, figures and clips under the same external-transmission consent. Changing a template does not authorize a new remote destination. Cache fingerprints bind lesson content, model address/name and the template contract; changed source text, bullets or templates invalidate the plan. Retrying clears old layout previews. See [course director and PPT templates](课程导演与PPT模板.md).
