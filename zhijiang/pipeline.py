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
from zhijiang.models import JobStatus, Mode, VoiceMode
from zhijiang.pdf import PDFError, read_pdf
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
    ):
        self.settings = settings
        self.store = store
        self.agent_factory = agent_factory
        self.speech_factory = speech_factory
        self.video_renderer = video_renderer

    def _agents(self, mode: Mode):
        if self.agent_factory:
            return self.agent_factory(mode)
        if mode == Mode.DEMO:
            return DemoAgents()
        if self.settings.llm_provider == "ollama":
            return AIAgents(OllamaClient(self.settings.llm_base_url, self.settings.llm_model))
        return AIAgents(
            OpenAICompatibleClient(
                self.settings.llm_base_url,
                self.settings.llm_api_key,
                self.settings.llm_model,
            )
        )

    def _speech(self, mode: VoiceMode):
        if self.speech_factory:
            return self.speech_factory(mode)
        if mode == VoiceMode.AI:
            return AISpeech(
                self.settings.tts_base_url,
                self.settings.tts_api_key,
                self.settings.tts_model,
                self.settings.tts_voice,
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
                job["filename"], self.settings.max_pdf_pages,
            )
            mode = Mode(job["mode"])
            voice_mode = VoiceMode(job["voice_mode"])
            agents = self._agents(mode)
            self.store.set_progress(job_id, "提取知识点", 22)
            bundle = agents.extract_knowledge(document)
            self.store.set_progress(job_id, "设计课程结构", 38)
            outline = agents.plan(bundle)
            self.store.set_progress(job_id, "编写讲稿与分镜", 53)
            lesson = agents.script(bundle, outline, voice_mode)
            if mode == Mode.AI and self.settings.llm_provider == "ollama":
                lesson.notice = "本机 Ollama 生成：页码引文已自动核对，知识正确性仍需人工复核。"
            self.store.set_progress(job_id, "核验引用与讲解结构", 64)
            validate_lesson(document, lesson)
            agents.review(lesson)
            self.store.save_lesson(job_id, lesson)
            self.store.set_progress(job_id, "合成配音", 73)
            speech = self._speech(voice_mode)
            audio_files: list[Path] = []
            for index, segment in enumerate(lesson.segments):
                audio = folder / f"audio-{index}.wav"
                speech.synthesize(segment.narration, audio)
                audio_files.append(audio)
            self.store.set_progress(job_id, "合成教学视频", 88)
            self.video_renderer(lesson, audio_files, folder / "lesson.mp4")
            self.store.complete(job_id)
        except (PDFError, GenerationError, SpeechError, VideoError) as exc:
            self.store.fail(job_id, str(exc))
        except Exception:
            logger.exception("任务 %s 发生未预期的错误", job_id)
            self.store.fail(job_id, "处理失败，请检查服务日志后重试。")
        finally:
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
