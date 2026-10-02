# Zhijiang Agent (Book2Course)

**Language / 语言:** [简体中文](README.md) | [English](README.en.md)

Zhijiang Agent turns PDFs that you have the right to use into Chinese educational videos and presentation decks. It extracts text directly from text-based PDFs and runs OCR locally for scanned pages. After you upload a document, the web page shows the course outline, narration for each segment, PDF page numbers, and source excerpts. It also provides downloadable MP4 and PPTX files. The PPTX contains SVG teaching diagrams, playable explanatory clips, and speaker notes.

There are two generation modes: **real AI mode** uses local Ollama or an external compatible model; **deterministic demo mode** uses fixed rules and needs no model or API key. The demo is labeled in the page and video. For each job, the web page lets you set the text model provider, API URL, model name, API key, and an instruction prompt. You can configure the speech API URL, model, voice, and key separately. Narration can use a Chinese Windows system voice, a local Chinese Kokoro AI speech model, or an external compatible speech service. Source verification checks that excerpts match the corresponding extracted or OCR text; the accuracy of explanations and OCR still needs human review.

## From book to course

The sketch's “book → OCR/typesetting → pages” and “main slides → narration/animation → assembly” paths are combined here into one source-linked workflow. **Green solid arrows show the implemented MP4 and PPTX paths; the diagram note marks specialized LaTeX and Manim work as planned.** Citation checks locate excerpts in the extracted text. They do not guarantee complete topic coverage or correct teaching explanations, so review the result before use.

[![Workflow from PDF to lesson video](docs/workflow.en.svg)](docs/workflow.en.svg)

The video uses temporary Pillow frames that are cleaned up after each job. The PPTX has a cover and two slides per knowledge point: a teaching diagram and an animation. Titles and other native PowerPoint text can be edited. Each SVG is embedded as a vector picture with a PNG compatibility fallback, and each segment's MP4 can be clicked during a slideshow. Speaker notes contain narration, the source page, and the exact excerpt. Automatic diagrams and clips use constrained templates; complex continuous math transformations, LaTeX formula layout, and Manim scenes still require custom production.

### PPT production skills

The following repository Codex skills help refine PPT content and assets. Web jobs generate a PPTX with built-in templates and do not invoke these skills automatically. Invoke them by name in a Codex task for this project:

| Skill | Purpose |
| --- | --- |
| [`$book2course-ppt-outline`](.agents/skills/book2course-ppt-outline/SKILL.md) | Plan slides from learning dependencies and source pages; check for missing key concepts. |
| [`$book2course-ppt-script`](.agents/skills/book2course-ppt-script/SKILL.md) | Write a page-aligned speaker script, notes, narration, and visual cues. |
| [`$book2course-svg-diagrams`](.agents/skills/book2course-svg-diagrams/SKILL.md) | Create editable SVG flowcharts, concept diagrams, and formula step diagrams. |
| [`$book2course-explainer-animation`](.agents/skills/book2course-explainer-animation/SKILL.md) | Design explanatory visual transformations and check visuals against narration and timing; use [Manim Community](https://docs.manim.community/en/stable/) when needed. |

For more complex teaching than the automatic deck provides, use Codex's Presentations skill to assemble the outline, script, SVGs, and animation assets, then inspect slide layout and speaker notes. Manim is an optional animation authoring tool and is not a base dependency of the web service.

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

`.env.local` is ignored by Git. You can change the Ollama URL and model there. Real AI mode uses the local `/api/chat` endpoint to generate key points, a course plan, and narration. Extracted PDF text is not sent to an external text model in this configuration. The model first selects numbered source excerpts with page references; the program then inserts and verifies the quotations to reduce errors from rewritten source text.

Concrete numbers in the script must appear in the corresponding source excerpt. If the model adds an unsupported value, the program requests one rewrite, then removes unsupported sentences or bullets and flags the result for review if needed. This check cannot prove that every explanation is correct; source material without worked examples may produce a more conceptual script. Review the result before teaching.

You can also skip `.env.local` and enter the API configuration for a job directly in the web page after selecting real AI mode. The API key stays only in the server process memory while the job runs. It is not written to SQLite, the lesson JSON, or the web response. If you refresh the page or restart the service before retrying a job that uses an external model, you must enter the key again. A custom prompt controls the course plan and narration style but cannot bypass source verification.

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
```

`build_ollama_demo.py` requires local Ollama to be configured first. A [sample video that needs no model](demo/zhijiang_demo.mp4) is also available.

## Current scope

- Jobs run sequentially on one machine; one PDF produces one lesson.
- Text-based and scanned PDFs are supported. Uploads are limited to 200 MB, with no fixed page count limit. Scanned pages are OCRed one at a time in the background, so processing time grows with the page count.
- AI mode selects evidence from all pages containing text in batches and generates a course without a fixed target video duration. Actual duration depends on the source material, model output, and speech rate. Long documents require more model calls.
- Demo mode has no page or segment count limit either. For documents of up to two pages, it still selects the first six candidate segments; for longer documents, it selects at most three per page.
- For each segment, the PPTX has one SVG diagram slide and one animation slide with an embedded silent MP4. Click to play during a slideshow; speaker notes guide the live explanation. Deck size and render time grow with the segment count. Native PowerPoint titles and labels are editable; individual paths and text inside an SVG picture are not directly editable as separate slide shapes.
- Concept cards, formula steps, and process visuals are supported. Automatic clips gradually reveal numbers, relationships, and steps. Complex Manim animation, continuity across chapters, and automatic proof of factual claims are not implemented yet.
