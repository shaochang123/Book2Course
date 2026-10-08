# Generation configuration and recovery

[简体中文](生成配置与恢复.md) | [English](configuration.en.md)

Detailed reference moved from the project README. See the [implementation status](实现状态与路线图.md) (Chinese) for current scope. Machine versions and validation results are specific to their linked reports.

## Use local Ollama

Install and start [Ollama](https://ollama.com/), then check your models with `ollama list`. The default template uses non-thinking [`qwen3:4b-instruct`](https://ollama.com/library/qwen3%3A4b-instruct). If it is not available locally, run `ollama pull qwen3:4b-instruct`. Enter the actual model name in the web page when using another model. Copy the configuration template and restart the web server:

```powershell
Copy-Item .env.local.example .env.local
```

`.env.local` is ignored by Git. You can change the Ollama URL and model there. Real AI mode uses the local `/api/chat` endpoint to generate key points, a course plan, and narration. Extracted PDF text is not sent to an external text model in this configuration. The model first selects numbered source excerpts with page references; the program then inserts and verifies the quotations to reduce errors from rewritten source text. Structured calls use an 8192-token context; general storyboards split object layout from operations/calculations, with separate repair stages. CPU inference and complex storyboards can take longer; small models may require revisions or fail checks. Choose a stronger model API in the page when needed.

The previous guide recorded Ollama 0.35.1 and a 512 MiB prompt cache as a historical machine configuration, not an installation requirement. Check actual models and versions with `ollama list`, `ollama --version` and each validation report. On low-memory computers, set the llama.cpp backend's [prompt-cache limit](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) before starting Ollama. Exit the existing service, then run:

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

## General mathematical object mode

`geometry` is available in real AI mode and requires TeX and general animation dependencies. It plans 2-D objects, function curves and parametric curves from the complete cited page, without flowchart, highlight or fading-card fallback. Expressions bind to declared parameters; SVG and video share equal coordinate units. Model planning can fail, and successful execution still needs source and visual review. Graphical formulas on mixed prose/formula pages are not fully recovered by automatic OCR. See [mathematics validation](math-level-validation-2026-10.md).

Local Ollama calls in this mode use simple JSON decoding with full program-side structure, variable and source validation. Source relations bind to actual geometry and are measured during planning samples and rendered frames. Visible point and label anchors outside the coordinate window are rejected. Numeric scene caches require matching digests and renewed checks, rather than trusting old model approval. Omitted or misbound relations remain a limitation.

Mathematical tests record the actual digests, quantization and settings for `qwen3.5:9b` and `qwen2.5:7b`. The local 8 GB GPU experienced long output stalls under heavy load. Serial execution and recorded model changes support diagnosis but do not establish a capability ranking. The application does not automatically rewrite `.env.local` or download models; select an installed text-generation model rather than an embedding model.
