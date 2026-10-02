# Zhijiang Agent (Book2Course)

**Language / 语言:** [简体中文](README.md) | [English](README.en.md)

Zhijiang Agent turns PDFs that you have the right to use into Chinese educational videos and presentation decks. It extracts text directly from text-based PDFs and runs OCR locally for scanned pages. After you upload a document, the web page shows the course outline, narration for each segment, PDF page numbers, and source excerpts. It also provides downloadable MP4 and PPTX files. The PPTX contains SVG teaching diagrams, playable explanatory clips, and speaker notes.

There are two generation modes: **real AI mode** uses local Ollama or an external compatible model; **deterministic demo mode** uses fixed rules and needs no model or API key. The demo is labeled in the page and video. For each job, the web page lets you set the text model provider, API URL, model name, API key, and an instruction prompt. You can configure the speech API URL, model, voice, and key separately. Narration can use a Chinese Windows system voice, a local Chinese Kokoro AI speech model, or an external compatible speech service. Source verification checks that excerpts match the corresponding extracted or OCR text; the accuracy of explanations and OCR still needs human review.

## From book to course

The sketch's “book → OCR/typesetting → pages” and “main slides → narration/animation → assembly” paths form one workflow with source references. There are three routes: basic diagrams, general scenes across subjects, and specialized 2-D linear transformations. Scenes receive their corresponding checks and use actual speech durations for Manim/LaTeX rendering. Citation checks locate excerpts; teaching quality still needs human review.

[![Workflow from PDF to lesson video](docs/workflow.en.svg)](docs/workflow.en.svg)

Basic videos use Pillow. General teaching scenes and specialized math videos use local Manim Cairo with LaTeX formulas. The PPTX has a cover and two slides per topic: an SVG summary and an animation. Native text is editable; each SVG has a PNG fallback. Click a segment's MP4 during a slideshow. Notes contain step-by-step narration, source pages, and excerpts. General and specialized clips include narration and reuse the full lesson video's assets, embedded at their original 16:9 aspect ratio.

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

TeX Live or another LaTeX distribution must provide `latex`, `dvisvgm`, and the `standalone` package on PATH. Restart the web server after installation. This computer uses its existing TeX Live installation and needs no GPU. Animation renders on the local CPU; text and speech use the APIs configured in the page.

Select real AI mode and choose an animation mode:

| Mode | Behavior |
| --- | --- |
| `auto` (default for new AI jobs) | Use specialized reasoning for 2-D linear transformations and general parameterized scenes for other subjects. Missing dependencies produce an explained basic fallback. |
| `visual` | Require general teaching scenes without a subject restriction; invalid storyboards or declared numeric relations fail explicitly. |
| `math` | Require source-backed 2-D linear transformation material and a complete math environment. Unsupported content, invalid parameters, and failed computation checks produce explicit errors. |
| `basic` | Use the existing concept, formula, and process templates; embedded basic clips remain silent. |

The specialized executor covers linearity and translation counterexamples, basis images and matrix columns, grids and unit squares, orthogonal projections and eigendirections, and rotation/stretch composition order. Set teaching parameters in the prompt, such as `A=[[2,1],[0,1]]` and `v=[1,2]`. Supplemental examples are labeled. Math jobs focus on this supported thread and do not imply that 3-D or function-space material in the source has been animated.

The general `visual_scene` contract has no subject-name whitelist. The model can use curves, points, circles, lines, arrows, polygons, and labels with stable identities, parameters, and successive changes for calculus, probability, physics, chemistry, biology, or other fields. The same data produces SVG summaries, narrated animations, and speaker notes. Restricted expressions generate LaTeX formulas; numeric results and geometry update together as parameters change.

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

Install and start [Ollama](https://ollama.com/), then check your models with `ollama list`. The default template uses `qwen3:4b`. If that model is not available locally, run `ollama pull qwen3:4b`. Copy the configuration template and restart the web server:

```powershell
Copy-Item .env.local.example .env.local
```

`.env.local` is ignored by Git. You can change the Ollama URL and model there. Real AI mode uses the local `/api/chat` endpoint to generate key points, a course plan, and narration. Extracted PDF text is not sent to an external text model in this configuration. The model first selects numbered source excerpts with page references; the program then inserts and verifies the quotations to reduce errors from rewritten source text. Structured calls use an 8192-token context; general storyboards split object layout from operations/calculations, with separate repair stages. CPU inference and complex storyboards can take longer; small models may require revisions or fail checks. Choose a stronger model API in the page when needed.

For a failed job, change the generation mode, text/speech APIs, voice, prompt, or animation mode, then select “使用原 PDF 重新生成” (regenerate from the original PDF). Retry uses the current settings without another upload. Changing an external service requires explicit transmission consent and its credential; the old destination's job credential is not forwarded to the new one.

In basic mode, concrete numbers must appear in the source excerpt; unsupported values trigger a rewrite, then removal and a review notice if needed. Specialized and general scenes accept labeled teaching parameters and calculated results without this source-number filter. Principles and supplemental examples are separate. Numeric checks do not prove free-form narration, domain facts, or teaching explanations.

New general storyboards use qualitative prose for objects, operations, and reasons; verified parameters and calculations generate numeric narration. Unbound literal numbers and common Chinese numeric assertions are rejected, so an approving review model cannot preserve that class of wrong spoken calculation. Each new segment plans 3–5 short steps with 12–100 characters of qualitative speech per step; older course data remains readable. Original drafts remain available. Qualitative explanations and domain facts still require source and human review.

You can skip `.env.local` and configure a job in the web page. API keys remain in server memory while the job runs and are never written to SQLite, lesson JSON, or responses. Refreshing or restarting before an external-model retry requires entering the key again. Prompts control planning, teaching parameters, and basic narration style. Math narration currently uses verified templates; prompts cannot bypass source or computation checks.

You can view a [sample video](demo/zhijiang_ollama_demo.mp4) and its [lesson script and sources](demo/zhijiang_ollama_lesson.json). The script was generated by a local model, and the voice comes from Windows system speech.

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

## Current scope

- Jobs run sequentially on one machine; one PDF produces one lesson.
- Text-based and scanned PDFs are supported. Uploads are limited to 200 MB, with no fixed page count limit. Scanned pages are OCRed one at a time in the background, so processing time grows with the page count.
- AI mode selects evidence from all pages containing text in batches and generates a course without a fixed target video duration. Actual duration depends on the source material, model output, and speech rate. Long documents require more model calls.
- Demo mode has no page or segment count limit either. For documents of up to two pages, it still selects the first six candidate segments; for longer documents, it selects at most three per page.
- Each segment has an SVG diagram slide and an embedded MP4 slide. General and specialized clips include synchronized narration; basic clips are silent. Click to play during a slideshow. Size and render time grow with content. Titles and source labels are editable; paths inside an SVG are not separate PowerPoint shapes.
- General scenes support parameterized 2-D processes across subjects; specialized reasoning covers the five linear transformation scenes above. Complex 3-D and molecular dynamics require additional executors. Automatic reasoning across chapters and proof of factual claims are not implemented.
