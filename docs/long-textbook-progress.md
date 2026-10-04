# Long scanned textbook progress and resume

## 实际问题 / Observed problem

2026-10-04：用户上传人教版六年级上册数学教材后，页面长期停留在“解析 PDF”。检查服务日志与任务状态发现，后台仍在执行本机 OCR；固定阶段百分比没有反映页级进度。后续知识点提取也只有整阶段完成后才保存。

The supplied grade-six mathematics textbook has 124 PDF pages. OCR retained text on 123 pages, with original page numbers. The job started at 14:10:16 and completed parsing at 14:57:18 (Asia/Shanghai), about 47 minutes. During this work the page continued to show “解析 PDF” at 8%, making active processing appear stalled. Extraction then used several local model calls without per-batch checkpoints.

Runtime: local CPU OCR, Ollama `qwen3:4b-instruct`, local Kokoro speech API, and general `visual` animation mode. The original source and user settings were retained; no source text was sent to an external model. The PDF and job artifacts remain in Git-ignored `data/`.

## Repairs

- **Page progress and checkpoints:** report the current page and OCR operation; atomically save each completed page, including blank pages. Match the PDF hash before reuse. Existing whole-document parsing caches remain valid, so this job did not repeat its 47-minute OCR run.
- **Batch progress and checkpoints:** report completed/total knowledge batches and their page ranges. Save only selections that pass ID, title, source, and number checks. Retry reuses successful batches and rechecks them; source or analysis changes invalidate their fingerprints.
- **Visible local inference:** stream native Ollama responses; update elapsed time during prompt processing and received character counts during generation. Accept only complete responses with the server completion marker and a valid schema. Retain bounded timeouts and format retries.
- **Chinese excerpt context:** retain short wrapped definitions and contiguous neighboring text. Exclude explicit publishing metadata, prefaces, and contents pages. Keep judgement instructions with their propositions. Every selected excerpt still has to match the actual OCR text.
- **Missing OCR values:** an actual initial selection invented a fraction for an exercise whose ratio was missing from OCR. Knowledge summaries now reject numbers absent from their selected excerpt and request a correction. They do not invent numerical examples; later scenes may contain separately labeled, verified teaching examples. This is a number check, not a proof that all OCR or mathematical meaning is correct.
- **Course ordering:** pass topic IDs, titles, and kinds to the course-ordering call rather than repeating all scanned excerpts. Scene planning still receives its actual source evidence. This reduces unnecessary context use without dropping selected topics.
- **User guidance:** the page explains that local services must stay running, the browser may be refreshed or closed, and percentage progress is not an estimate of remaining time. Both README languages, workflow diagrams, and related project skills describe the new behavior.

## Tests and actual run

All **131 tests passed** on 2026-10-04. Seven new regression tests cover interrupted OCR recovery with blank pages, source-hash invalidation, Chinese definition and exercise context, knowledge-batch resume with invalid-cache rejection, rejection of an invented OCR-missing ratio, streamed completion, rejection of a truncated stream even when its JSON looks valid, and one bounded native-generation retry when a stream reports a parser error. Existing source, math, geometry, speech, PPTX, and API tests also passed.

The actual original textbook job was resumed through `POST /api/jobs/{id}/retry`, reusing `parsed-source.json`. The web page showed the current batch, source-page range, elapsed inference time, and increasing character count. Earlier progress repairs saved successful batches immediately. After the missing-value rule was added, changed extraction instructions correctly invalidated those older selections and started fresh knowledge extraction while preserving all completed OCR.

After the additional check was deployed, the first batch produced five source-backed topics on fraction multiplication and mixed operations, without the previously invented ratios and numeric examples. The next batches continued with live inference updates. There are 237 selected source excerpts in 15 extraction batches; selecting excerpts does not guarantee coverage of every concept.

The current job link is available locally:

`http://127.0.0.1:8765/?job=68e41c2a1ad3488485d0599def3c1645`

The whole textbook remains a long CPU task. **This validation establishes diagnosis, visible progress, checkpoint behavior, and resumed extraction. It does not mark the textbook's complete PPTX/video or teaching quality as accepted.** Source checking, final animation rendering, full playback/listening, and PowerPoint slideshow checks require the actual completed outputs. Damaged fractions, mixed OCR reading order, chapter coverage, and correct exercise interpretation still need review.
