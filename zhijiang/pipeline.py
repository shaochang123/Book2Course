"""单机任务编排。各阶段状态持久化，失败时不留下伪完成结果。"""

from __future__ import annotations

import logging
import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from zhijiang.agents import (
    AIAgents, DemoAgents, GenerationError, OllamaClient, OpenAICompatibleClient,
    validate_lesson,
    validate_evidence,
)
from zhijiang.config import Settings
from zhijiang.models import GenerationOptions, JobStatus, Mode, SpeechOptions, VoiceMode, SourceDocument, KnowledgeBundle
from zhijiang.math_planning import MathAnimationError, math_capabilities, plan_math_lesson, supports_math
from zhijiang.math_media import render_math_assets
from zhijiang.visual_planning import plan_general_lesson, visual_capabilities
from zhijiang.visual_media import render_visual_assets
from zhijiang.teaching_design import prepare_source_assets, TeachingDesignError
from zhijiang.pdf import PDFError, read_pdf
from zhijiang.presentation import PresentationError, render_presentation
from zhijiang.speech import AISpeech, SpeechError, SystemSpeech
from zhijiang.storage import JobStore
from zhijiang.video import VideoError, render_video
from zhijiang.presentation_templates import template_instruction
from zhijiang.deck_planning import plan_deck
from zhijiang.visual_assets import AssetError


logger = logging.getLogger(__name__)


def checkpoint(path, fingerprint, schema, build):
    """Reuse only completed input-dependent stages; never cache credentials."""
    try:
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved.get('fingerprint')==fingerprint:
            return schema.model_validate(saved['data'])
    except (OSError,ValueError,KeyError):
        pass
    result=build()
    path.write_text(json.dumps({'fingerprint':fingerprint,'data':result.model_dump()},ensure_ascii=False),encoding='utf-8')
    return result


class JobProcessor:
    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        agent_factory: Callable[[Mode], object] | None = None,
        speech_factory: Callable[[VoiceMode], object] | None = None,
        video_renderer: Callable = render_video,
        presentation_renderer: Callable = render_presentation,
    ):
        self.settings = settings
        self.store = store
        self.agent_factory = agent_factory
        self.speech_factory = speech_factory
        self.video_renderer = video_renderer
        self.presentation_renderer = presentation_renderer

    def _agents(self, mode: Mode, options: GenerationOptions):
        if self.agent_factory:
            return self.agent_factory(mode)
        if mode == Mode.DEMO:
            return DemoAgents()
        teaching_prompt = options.prompt + (template_instruction(options.ppt_template)
            if options.ppt_template != 'classic' else '')
        if options.provider == "ollama":
            return AIAgents(OllamaClient(options.base_url, options.model,
                semantic_thinking=options.semantic_thinking,
                num_gpu=self.settings.ollama_num_gpu,thinking_level=self.settings.ollama_thinking_level), teaching_prompt)
        return AIAgents(
            OpenAICompatibleClient(
                options.base_url,
                options.api_key,
                options.model,
            ), teaching_prompt
        )

    def _speech(self, mode: VoiceMode, options: SpeechOptions):
        if self.speech_factory:
            return self.speech_factory(mode)
        if mode == VoiceMode.AI:
            return AISpeech(
                options.base_url,
                options.api_key,
                options.model,
                options.voice,
                timeout_seconds=self.settings.tts_timeout_seconds,
            )
        return SystemSpeech(self.settings.system_voice)

    def process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None or job["status"] != JobStatus.QUEUED:
            return
        folder = self.store.jobs_dir / job_id
        agents = None
        math_reviewer = None
        math_planner = None
        speech = None
        active_stage = ['解析 PDF', 8]

        def progress(stage, value):
            active_stage[:] = [stage, value]
            self.store.set_progress(job_id, stage, value)

        def model_progress(stage, elapsed, characters):
            self.store.set_progress(job_id,
                f'{active_stage[0]} · 模型生成中（{elapsed}秒，{characters}字）', active_stage[1])

        try:
            progress("解析 PDF", 8)
            source_bytes=(folder/'source.pdf').read_bytes()
            source_hash=hashlib.sha256(source_bytes).hexdigest()
            mode = Mode(job["mode"])
            voice_mode = VoiceMode(job["voice_mode"])
            options = self.store.get_options(job_id)
            teaching_prompt = options.prompt + (template_instruction(options.ppt_template)
                if options.ppt_template != 'classic' else '')
            agents = self._agents(mode, options)
            if isinstance(agents, AIAgents) and isinstance(agents.client, OllamaClient):
                agents.client.progress = model_progress
                agents.client.prefer_json=options.animation_mode=='geometry'
            if mode==Mode.AI and options.animation_mode=='geometry':
                from zhijiang.math_sources import read_math_pdf
                from zhijiang.mathematical_planning import plan_constructed_lesson
                document=checkpoint(folder/'parsed-source.json',
                    'visual-math-source-v2:'+source_hash+options.model+options.base_url,SourceDocument,
                    lambda:read_math_pdf(agents.client,source_bytes,job['filename'],
                        cache_dir=folder/'math-source-pages',progress=lambda done,total,label:
                            progress(f'{label}（{done}/{total} 页）',8+done*13//total)))
            else:
                document=checkpoint(folder/'parsed-source.json','pdf-v2:'+source_hash,SourceDocument,
                    lambda:read_pdf(source_bytes,job['filename'], cache_dir=folder/'parsed-pages',
                        progress=lambda done,total,label:progress(
                            f'解析 PDF（{done}/{total} 页）：{label}', 8 + done * 13 // total)))
            # Special-purpose templates are opt-in. A mixed textbook must keep
            # all extracted topics and choose an expression for each of them.
            use_math = mode == Mode.AI and options.animation_mode == "math" and supports_math(document)
            use_visual = mode == Mode.AI and options.animation_mode in {"auto","visual","geometry"} and not use_math
            fallback_reason = "当前任务选择基础图示。"
            if options.animation_mode == "math" and not use_math:
                raise MathAnimationError("数学模式首轮仅支持有足够原文依据的二维线性变换，请使用相关讲义。")
            if use_math or use_visual:
                capability = math_capabilities() if use_math else visual_capabilities()
                if options.animation_mode=='geometry' and not capability.get('geometry_ready'):
                    raise MathAnimationError('数学对象推演需要 TeX：'+capability.get('geometry_reason','缺少 TeX'))
                if not capability["ready"]:
                    if options.animation_mode in {"math","visual","geometry"}:
                        raise MathAnimationError("请安装 math-animation 动画依赖" + ("和 LaTeX" if use_math else "") + "：" + capability["reason"])
                    use_math = False
                    use_visual = False
                    fallback_reason = "动画环境未就绪，自动模式使用基础图示：" + capability["reason"]
            if use_visual and options.animation_mode=='geometry':
                if options.math_model and options.math_model!=options.model:
                    math_planner=(OllamaClient(options.base_url,options.math_model,
                        semantic_thinking=options.semantic_thinking,prefer_json=True,progress=model_progress,
                        num_gpu=self.settings.ollama_num_gpu,thinking_level=self.settings.ollama_thinking_level)
                        if options.provider=='ollama' else OpenAICompatibleClient(
                            options.base_url,options.api_key,options.math_model))
                if options.review_model and options.review_model!=options.model:
                    math_reviewer=(OllamaClient(options.base_url,options.review_model,
                        semantic_thinking=options.semantic_thinking,prefer_json=True,progress=model_progress,
                        num_gpu=self.settings.ollama_num_gpu,thinking_level=self.settings.ollama_thinking_level)
                        if options.provider=='ollama' else OpenAICompatibleClient(
                            options.base_url,options.api_key,options.review_model))
                lesson=plan_constructed_lesson(agents.client,document,teaching_prompt,voice_mode,
                    progress,draft_output=folder/'visual-planning.json',review_client=math_reviewer,
                    planning_client=math_planner,
                    source_image_loader=lambda page:__import__('zhijiang.math_sources',fromlist=['page_png']).page_png(source_bytes,page))
            elif use_math:
                progress("规划数学对象与推理分镜", 25)
                lesson = plan_math_lesson(agents.client, document, teaching_prompt, voice_mode,
                    progress)
            else:
                progress("提取知识点", 22)
                # A failed diagram should not repeat a successful OCR/extraction.
                # Input or model/prompt changes invalidate the analysis cache.
                batch_fingerprint=hashlib.sha256(json.dumps({'version':'content-selection-v7',
                    'source':source_hash,'mode':mode,'options':options.model_dump()},sort_keys=True).encode()).hexdigest()
                fingerprint=hashlib.sha256(('quantity-binding-v1:'+batch_fingerprint).encode()).hexdigest()
                bundle=checkpoint(folder/'knowledge.json',fingerprint,KnowledgeBundle,
                    lambda:agents.extract_knowledge(document, cache_dir=folder/'knowledge-batches',
                        cache_fingerprint=batch_fingerprint,
                        complete_sources=options.animation_mode=='geometry',
                        teaching_preference=(options.prompt+' 只选择需要数学对象推演的核心数学知识与必要条件，不选人物历史背景或泛泛回顾。'
                            if options.animation_mode=='geometry' else options.prompt),
                        progress=lambda done,total,label:progress(
                            f'提取知识点（{done}/{total} 批）：{label}',22 + done * 15 // total))
                        if isinstance(agents,AIAgents) else agents.extract_knowledge(document))
                for point in bundle.points: validate_evidence(document,point.evidence)
                progress("设计课程结构", 38)
                if use_visual:
                    source_assets=prepare_source_assets(folder/'source.pdf',folder/'source-pages',document,
                        progress=lambda done,total,label:progress(f'{label}（{done}/{total} 页）',38+done*4//total))
                    lesson=plan_general_lesson(agents.client,bundle,document,teaching_prompt,voice_mode,
                        progress,draft_output=folder/'visual-planning.json',
                        source_assets=source_assets,pdf_path=folder/'source.pdf',
                        geometry_only=options.animation_mode=='geometry')
                else:
                    outline = agents.plan(bundle)
                    progress("编写讲稿与分镜", 53)
                    lesson = agents.script(bundle, outline, voice_mode)
                    lesson.animation_report = {"renderer": "Pillow basic", "scene_count": 0,
                        "reason": fallback_reason}
            if mode == Mode.AI and options.provider == "ollama":
                remote=any(Settings.model_is_remote(options.provider,options.base_url,name)
                    for name in [options.model,options.review_model,options.math_model] if name)
                lesson.notice = lesson.notice.replace("AI 生成：", "Ollama 云模型参与生成：" if remote else "本机 Ollama 生成：", 1)
            if any(page.ocr for page in document.pages):
                lesson.notice += " 页中文字与公式经图像识别，请核对识别结果和引用。"
            progress("核验引用与讲解结构", 64)
            validate_lesson(document, lesson)
            if isinstance(agents, AIAgents):
                from zhijiang.caption_grounding import ground_lesson_captions
                progress('绑定画面要点与完整讲稿', 65)
                ground_lesson_captions(lesson, agents.client, output=folder/'caption-grounding.json')
            if not use_math and not use_visual:
                agents.review(lesson)
            lesson.ppt_template = options.ppt_template
            progress('检索教学素材并规划页面版式', 68)
            lesson.deck_plan = plan_deck(lesson, options.ppt_template,
                agents.client if isinstance(agents, AIAgents) else None,
                output=folder/'presentation-plan.json', use_illustrations=options.use_illustrations)
            self.store.save_lesson(job_id, lesson)
            self.store.set_progress(job_id, "合成配音", 73)
            speech = self._speech(voice_mode, self.store.get_speech_options(job_id))
            audio_files: list[Path] = []
            if use_math:
                render_math_assets(lesson, speech, folder,
                    lambda stage, value: self.store.set_progress(job_id, stage, value))
                self.store.save_lesson(job_id, lesson)
            if use_visual:
                render_visual_assets(lesson,speech,folder,
                    lambda stage,value: self.store.set_progress(job_id,stage,value))
                self.store.save_lesson(job_id,lesson)
            for index, segment in enumerate(lesson.segments):
                if segment.math_scene:
                    audio_files.append(folder / "math" / f"scene-{index+1:02d}" / "narration.wav")
                    continue
                if segment.visual_scene:
                    audio_files.append(folder / "visual" / f"scene-{index+1:02d}" / "narration.wav")
                    continue
                audio = folder / f"audio-{index}.wav"
                speech.synthesize(segment.narration, audio)
                audio_files.append(audio)
                self.store.set_progress(
                    job_id, f"合成配音（{index + 1}/{len(lesson.segments)}）",
                    73 + (index + 1) * 14 // len(lesson.segments),
                )
            self.store.set_progress(job_id, "制作共享教学画面与 PPT", 88)
            self.presentation_renderer(lesson, folder / "lesson.pptx")
            self.store.set_progress(job_id, "合成同模板完整视频", 94)
            self.video_renderer(lesson, audio_files, folder / "lesson.mp4")
            self.store.complete(job_id)
        except (PDFError, GenerationError, SpeechError, VideoError, PresentationError, MathAnimationError, TeachingDesignError, AssetError) as exc:
            self.store.fail(job_id, str(exc))
        except Exception:
            logger.exception("任务 %s 发生未预期的错误", job_id)
            self.store.fail(job_id, "处理失败，请检查服务日志后重试。")
        finally:
            if math_planner is not None:
                if isinstance(math_planner,OllamaClient):
                    (folder/'mathematical-planning-calls.json').write_text(json.dumps(math_planner.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
                    if math_planner.invalid_outputs:
                        (folder/'mathematical-planning-format-errors.json').write_text(json.dumps(math_planner.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
                math_planner.close()
            self.store.clear_api_key(job_id)
            if math_reviewer is not None:
                if isinstance(math_reviewer,OllamaClient):
                    (folder/'independent-review-calls.json').write_text(json.dumps(math_reviewer.call_metrics,
                        ensure_ascii=False,indent=2),encoding='utf-8')
                    if math_reviewer.invalid_outputs:
                        path=folder/'independent-review-format-errors.json'
                        try:
                            previous=json.loads(path.read_text(encoding='utf-8'))
                            if not isinstance(previous,list):previous=[]
                        except (OSError,ValueError):previous=[]
                        path.write_text(json.dumps(previous+math_reviewer.invalid_outputs,
                            ensure_ascii=False,indent=2),encoding='utf-8')
                math_reviewer.close()
            if agents is not None and isinstance(agents, AIAgents):
                knowledge_log=folder / 'knowledge-planning.json'
                if agents.knowledge_drafts or not knowledge_log.exists():
                    knowledge_log.write_text(json.dumps(
                        agents.knowledge_drafts, ensure_ascii=False, indent=2), encoding='utf-8')
                if isinstance(agents.client, OllamaClient):
                    (folder / 'model-calls.json').write_text(json.dumps(
                        agents.client.call_metrics, ensure_ascii=False, indent=2), encoding='utf-8')
                    if agents.client.invalid_outputs:
                        invalid_path=folder/'model-format-errors.json'
                        try:
                            previous=json.loads(invalid_path.read_text(encoding='utf-8'))
                            if not isinstance(previous,list):previous=[]
                        except (OSError,ValueError):previous=[]
                        invalid_path.write_text(json.dumps(previous+agents.client.invalid_outputs,
                            ensure_ascii=False,indent=2),encoding='utf-8')
                agents.client.close()
            if speech is not None and isinstance(speech, AISpeech):
                speech.close()
            for pattern in ("audio-*.wav", "audio-normal-*.wav", "slide-*.png"):
                for path in folder.glob(pattern):
                    path.unlink(missing_ok=True)
            for name in ("narration.wav", "slides.txt"):
                (folder / name).unlink(missing_ok=True)


class JobRunner:
    def __init__(self, processor: JobProcessor):
        self.processor = processor
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zhijiang")
        self.futures: dict[str, Future] = {}

    def submit(self, job_id: str) -> None:
        self.futures[job_id] = self.executor.submit(self.processor.process, job_id)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True)
