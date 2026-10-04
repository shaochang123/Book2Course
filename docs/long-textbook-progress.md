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

## Follow-up: rejected knowledge batch 6 / 第 6 批失败修复

The subsequent screenshot showed an actual failure at batch 6 of 15, rather than idle OCR. The local model guessed music-note fractions whose fraction bars were missing in the OCR. A whole-batch retry also replaced otherwise valid points and introduced a road-length value absent from the selected excerpt. Further inspection found that rewriting fractions into Chinese bypassed the old digit-only check, while a bridge explanation reused a source digit as a false ratio.

The repair now preserves all selected topics and valid fields, changes only explanations rejected by source checks, and saves unapproved drafts separately. Numeric clauses must retain source wording; Chinese fractions and common quantity statements are checked as well. Generic Chinese articles and sourced scientific identifiers are distinguished from numerical claims. The whole knowledge cache has a new validation fingerprint; individual older batches are reused only after rechecking them.

Two bounded qualitative rewrites are attempted. If they continue to invent quantities, a constrained selection call chooses a readable clause from that point's current excerpt. The program inserts the literal source text, with no model-authored rewrite. Candidates exclude specific quantities and fractions; selections from another point's source are rejected. A source with no readable candidate still fails explicitly. This repairs a readable concept, not a lost formula or all its original numerical teaching content.

With the original local `qwen3:4b-instruct`, the actual batch-6 preflight passed using the source clause “不同的音符表示不同的时值（即 音的长短）”. The rejected Chinese fraction claims remained in local diagnostic records. No topics were removed. The original job was resumed with unchanged local model, speech, prompt, and animation settings and the existing OCR cache.

The repair adds regression cases for per-point repair with shared source excerpts, preservation of valid fields, unapproved-draft recovery, Chinese fraction/ratio rejection, generic article and chemical-name handling, literal source-clause selection, and rejection of cross-point clause selection. The actual full-job progress and final test count are recorded below when verified; preflight and automated checks alone do not establish completed PPTX/video quality.

Source-quality spot checks also found OCR omissions in the circle definitions on PDF page 62 and damaged formula layout on page 67. A literal clause can be incomplete as a teaching explanation even though its source binding is exact. These pages and any resulting explanations still require comparison with the original PDF image. Passing extraction checks must not be presented as recovery of all mathematical notation or acceptance of the final teaching content.

## Follow-up: sampled excerpt missing context / 短摘录缺少同页结论

The actual resumed job reached batch 14, where the sampled excerpt on PDF page 111 ended in an observation question. The same page retained the subsequent observation about the accumulated fractions approaching a value, with numeric rows interleaved in OCR reading order. The model alternated between an unsupported doubling claim and an unsupported worded fraction when asked to repair only the short excerpt.

A further constrained selection now uses bounded literal spans from the same original page. The model chooses a span ID; it cannot rewrite the quotation. The failed point retains its topic, type, source ID, and page, while its quotation may be repaired to the selected span. The program checks the literal match and generates a qualitative explanation from this corrected quotation. Other points are preserved. Cache validation rejects a repaired quotation absent from that point's original page. This addresses clipped context without claiming recovery of damaged notation or allowing cross-page numerical guesses.

Actual preflight also exposed a same-page selection that quoted adjacent odd-number addition for the fraction-accumulation topic. That choice was rejected in the implementation: candidate spans retain the most specific literal title term found on the page, using length and source frequency rather than a subject vocabulary list. Cached repaired quotes receive this check as well. This lexical check reduces adjacent-topic substitution; it does not prove all semantic equivalence or coverage.

With the unchanged local model, the subsequent batch-14 preflight selected the OCR span containing the fractions' gradual approach to a value and produced a qualitative summary of that observation. Interleaved numeric rows remained in the stored source quotation and were not taught as a recovered formula. The raw source and rejected attempts are retained locally in `page-repair-preflight.json` and `page-repair-preflight-result.json`.

## Verified resumed extraction / 实际续跑验收

At **16:52–16:53 on 2026-10-04 (Asia/Shanghai)**, the original web job completed all **15 extraction batches**, saved **83 selected points** to `knowledge.json`, and entered course-structure design. An independent read of the actual checkpoints rechecked source IDs, title uniqueness within each batch, same-page repaired quotations, quantitative summary guards, and every final quotation against the original parsed page. All 15 batches passed these checks. The machine-readable result is saved locally as `knowledge-extraction-validation.json` in the original job folder.

All **140 tests passed** after the final repair, with one existing dependency deprecation warning. The additional same-page tests cover recovery outside a sampled excerpt, rejection of a quotation from another page, and preservation of the specific topic instead of adjacent page background. Both README languages and workflow SVGs were updated; the Chinese and English diagrams were rendered and visually checked for clipping and overlap.

This verifies that the reported extraction failure and the later batch-14 context failure are resolved on the actual supplied textbook. **Full scene planning, narration, rendering, downloadable PPTX/video, and teaching-quality acceptance remain pending in this long-running job.** The source-quality review flags above remain applicable.
