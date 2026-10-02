"""单机任务编排。各阶段状态持久化，失败时不留下伪完成结果。"""

from __future__ import annotations

import logging
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from zhijiang.agents import (
    AIAgents, DemoAgents, GenerationError, OllamaClient, OpenAICompatibleClient,
    validate_lesson,
)
from zhijiang.config import Settings
from zhijiang.models import GenerationOptions, JobStatus, Mode, SpeechOptions, VoiceMode
from zhijiang.math_planning import MathAnimationError, math_capabilities, plan_math_lesson, supports_math
from zhijiang.math_media import render_math_assets
from zhijiang.visual_planning import plan_general_lesson
from zhijiang.visual_media import render_visual_assets
from zhijiang.pdf import PDFError, read_pdf
from zhijiang.presentation import PresentationError, render_presentation
from zhijiang.speech import AISpeech, SpeechError, SystemSpeech
from zhijiang.storage import JobStore
from zhijiang.video import VideoError, render_video


logger = logging.getLogger(__name__)


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
        if options.provider == "ollama":
            return AIAgents(OllamaClient(options.base_url, options.model), options.prompt)
        return AIAgents(
            OpenAICompatibleClient(
                options.base_url,
                options.api_key,
                options.model,
            ), options.prompt
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
            )
        return SystemSpeech(self.settings.system_voice)

    def process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None or job["status"] != JobStatus.QUEUED:
            return
        folder = self.store.jobs_dir / job_id
        agents = None
        speech = None
        try:
            self.store.set_progress(job_id, "解析 PDF", 8)
            document = read_pdf(
                (folder / "source.pdf").read_bytes(),
                job["filename"],
            )
            mode = Mode(job["mode"])
            voice_mode = VoiceMode(job["voice_mode"])
            options = self.store.get_options(job_id)
            agents = self._agents(mode, options)
            use_math = mode == Mode.AI and options.animation_mode in {"auto","math"} and supports_math(document)
            use_visual = mode == Mode.AI and options.animation_mode in {"auto","visual"} and not use_math
            fallback_reason = "当前任务选择基础图示。"
            if options.animation_mode == "math" and not use_math:
                raise MathAnimationError("数学模式首轮仅支持有足够原文依据的二维线性变换，请使用相关讲义。")
            if use_math or use_visual:
                capability = math_capabilities()
                if not capability["ready"]:
                    if options.animation_mode in {"math","visual"}:
                        raise MathAnimationError("请安装 math-animation 依赖和 LaTeX：" + capability["reason"])
                    use_math = False
                    use_visual = False
                    fallback_reason = "数学动画环境未就绪，自动模式使用基础图示：" + capability["reason"]
            if use_math:
                self.store.set_progress(job_id, "规划数学对象与推理分镜", 25)
                lesson = plan_math_lesson(agents.client, document, options.prompt, voice_mode,
                    lambda stage, value: self.store.set_progress(job_id, stage, value))
            else:
                self.store.set_progress(job_id, "提取知识点", 22)
                bundle = agents.extract_knowledge(document)
                self.store.set_progress(job_id, "设计课程结构", 38)
                if use_visual:
                    lesson=plan_general_lesson(agents.client,bundle,document,options.prompt,voice_mode,
                        lambda stage,value: self.store.set_progress(job_id,stage,value),draft_output=folder/'visual-planning.json')
                else:
                    outline = agents.plan(bundle)
                    self.store.set_progress(job_id, "编写讲稿与分镜", 53)
                    lesson = agents.script(bundle, outline, voice_mode)
                    lesson.animation_report = {"renderer": "Pillow basic", "scene_count": 0,
                        "reason": fallback_reason}
            if mode == Mode.AI and options.provider == "ollama":
                lesson.notice = lesson.notice.replace("AI 生成：", "本机 Ollama 生成：", 1)
            if any(page.ocr for page in document.pages):
                lesson.notice += " 扫描页文字经 OCR 识别，请核对识别结果和引用。"
            self.store.set_progress(job_id, "核验引用与讲解结构", 64)
            validate_lesson(document, lesson)
            if not use_math and not use_visual:
                agents.review(lesson)
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
            self.store.set_progress(job_id, "合成教学视频", 88)
            self.video_renderer(lesson, audio_files, folder / "lesson.mp4")
            self.store.set_progress(job_id, "制作 SVG 教学图与 PPT 动画", 94)
            self.presentation_renderer(lesson, folder / "lesson.pptx")
            self.store.complete(job_id)
        except (PDFError, GenerationError, SpeechError, VideoError, PresentationError, MathAnimationError) as exc:
            self.store.fail(job_id, str(exc))
        except Exception:
            logger.exception("任务 %s 发生未预期的错误", job_id)
            self.store.fail(job_id, "处理失败，请检查服务日志后重试。")
        finally:
            self.store.clear_api_key(job_id)
            if agents is not None and isinstance(agents, AIAgents):
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
