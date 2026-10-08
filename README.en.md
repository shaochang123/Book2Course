# Zhijiang Agent (Book2Course)

**Language / 语言:** [简体中文](README.md) | [English](README.en.md)

Convert textbooks, notes and knowledge PDFs you have permission to use into Chinese teaching videos and PPTX courseware with source references. The pipeline supports text extraction, local OCR, course planning, scripts, SVG diagrams, speech and video assembly. The website shows scripts, PDF pages, quotations and knowledge relations, with MP4, PPTX and scene data downloads.

**Real AI mode** uses local Ollama or a compatible service. **Deterministic demo mode** needs no model or key and is explicitly labelled as rule-generated. Source matching, model review and computation checks have limited scopes; teaching content still needs human review.

## Quick start (Windows)

Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m uvicorn zhijiang.main:app --host 127.0.0.1 --port 8765
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/), select the [original sample PDF](examples/binary_search_original.pdf), confirm rights, and try demo mode with Windows system speech. Review the script, sources, video and slides. **Press `Ctrl+C` in the server terminal to stop it**; closing the browser does not stop the service.

Python 3.11+ is required; Python 3.13 has been verified. System narration requires Windows Chinese speech; other environments can use a compatible speech API. `imageio-ffmpeg` supplies FFmpeg, so a system installation is unnecessary.

## Model and animation configuration

Copy the template for initial setup. If `.env.local` exists, edit it to preserve your settings:

```powershell
Copy-Item .env.local.example .env.local
ollama list
```

Set `ZHIJIANG_LLM_MODEL` to an installed model, start Ollama, and restart the web service. `.env.local`, model weights, uploads and generated artifacts are ignored by Git. The website also accepts per-job settings. External services require consent to send text or narration; job keys remain only in process memory.

```powershell
.\.venv\Scripts\python -m pip install -e ".[math-animation]"
```

| Animation mode | Current behavior |
| --- | --- |
| `auto` | AI default; selects source-based relations, processes, comparisons, annotations or geometry. Falls back to basic diagrams with a reason if the environment is unavailable. |
| `visual` | General scenes; fails explicitly when source or execution checks cannot pass. |
| `math` | Specialized 2-D linear transformations; requires suitable sources and TeX. |
| `basic` | Basic bullet diagrams; used by deterministic demo mode. |

Native relations and page annotations do not need TeX; computational geometry and specialized math need `latex` and `dvisvgm`. See [configuration and recovery](docs/configuration.en.md) for speech, Kokoro, external APIs and resume; see [teaching diagrams and animations](docs/animations.en.md) for diagrams and skills.

## Documentation and directories

| Entry | Contents |
| --- | --- |
| [Documentation index](docs/README.md) | Reading order and directory responsibilities. |
| [Product manual](docs/产品说明书.md) | Goals, design, value and limitations. |
| [User guide](docs/使用指南.md) | Start/stop, upload, inspect, download, retry and delete. |
| [Architecture and API](docs/架构与接口.md) | Actual modules, contracts, endpoints, states and caches. |
| [Implementation status and roadmap](docs/实现状态与路线图.md) | Reference design, implemented, partial and planned capabilities. |
| [Validation and acceptance](docs/验证与验收.md) | Automated, media and teaching-quality evidence. |
| [AI Coding record](docs/AI_Coding_全过程.md) | Actual Codex use, feedback, fixes and commits. |
| [Sources and licenses](docs/第三方来源与许可.md) | Dependencies, models and source documents. |

The index and main product documents are in Chinese; configuration and animation references have English equivalents. `zhijiang/` holds application and generation modules, `tests/` automated checks, `scripts/` sample/validation/document tools, `examples/` original PDF and source manifest, `demo/` historical media, and `data/` local jobs and models. See the [archive](docs/archive/2026-09/README.md) for historical documents and packages.

## Workflow

[![From PDF to videos and slides](docs/workflow.en.svg)](docs/workflow.en.svg)

Qualitative diagrams start with independent source reading and propositions. Subjects, predicates, objects and conditions form knowledge relations. Models select source IDs; the program binds quotations and shares SVG/animation layouts. Parametric geometry uses restricted expressions and numeric checks; model code is never executed. See [architecture and API](docs/架构与接口.md).

Qualitative scenes first retrieve required evidence from the current and adjacent input pages and review the title's scope, then bind facts to narration. Reading is no longer limited to three sentences around a citation. The program preserves complete inline italic foreign-language examples; source annotations zoom into the current evidence at each step. See the [Agent and model capability audit](docs/agent-model-capability-2026-10.md) for evidence and remaining issues.

## Tests and reproduction

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\build_demo.py
.\.venv\Scripts\python scripts\build_ollama_demo.py
.\.venv\Scripts\python scripts\verify_teaching_artifacts.py --job-dir data\jobs\YOUR_JOB_ID
.\.venv\Scripts\python scripts\build_documents.py
```

AI samples require a running local model; deterministic samples do not. Documents export to `output/pdf/` without creating jobs or calling models. See the [demo guide](docs/Demo_操作说明.md) for full operations and historical versions.

Selected textbook pages from linguistics, economics, sociology and database design produced 22 SVG/narrated clips, 4 MP4s and 4 PPTX files. Media checks passed; teaching quality was partial. These inputs informed debugging, so this is not an independent blind test or proof of full-book coverage. See [textbook validation](docs/generalization-validation-2026-10.md).

## Current limitations

- One sequential local queue; one PDF produces one lesson. Upload limit: 200 MB, with no fixed page or target-duration limit. Long books increase processing time and size.
- OCR does not guarantee recovery of complex formulas, tables or layout. No manual formula-confirmation interface exists.
- Each qualitative scene uses one source page and may reselect an adjacent input page. Missing title requirements or explanations requiring joint evidence across pages fail explicitly. Scope and semantic reviews can still be wrong and do not guarantee factual correctness.
- The website displays courses and sources but has no project list, knowledge selection/editor, script editor or human approval/publishing workflow.
- PPTX titles, source labels and notes are editable; SVG paths are not separate PowerPoint shapes. General/specialized clips include speech; basic embedded clips are silent, while the full video includes speech.
- Restricted 2-D scenes and source-relation tracing are supported. Complex 3-D mechanisms, cross-chapter reasoning, fact proofs, separate SRT/VTT subtitles and course ZIP export are not implemented.

Source code uses the [MIT License](LICENSE). Dependencies and textbooks have their own licenses; see [sources and licenses](docs/第三方来源与许可.md).
