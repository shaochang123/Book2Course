"""本地网站与受限 API。使用 `python -m uvicorn zhijiang.main:app` 启动。"""

from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from zhijiang.config import Settings
from zhijiang.models import GenerationOptions, JobStatus, Mode, SpeechOptions, VoiceMode
from zhijiang.models import AnimationMode
from zhijiang.math_planning import math_capabilities
from zhijiang.visual_planning import PRIMITIVES, CHECKERS, DOMAIN_VALIDATORS, visual_capabilities
from zhijiang.pdf import PDFError, validate_pdf
from zhijiang.pipeline import JobProcessor, JobRunner
from zhijiang.storage import JobStore


STATIC_DIR = Path(__file__).parent / "static"


def model_options(settings: Settings, provider: str, base_url: str, model: str,
                  api_key: str, prompt: str) -> GenerationOptions:
    if len(prompt) > 4000:
        raise HTTPException(400, "自定义提示词不能超过 4000 字。")
    customized = bool(api_key or (provider and provider != settings.llm_provider)
                      or (base_url and base_url.rstrip("/") != settings.llm_base_url.rstrip("/"))
                      or (model and model != settings.llm_model))
    try:
        options = GenerationOptions(
            provider=provider or settings.llm_provider,
            base_url=(base_url or settings.llm_base_url).strip().rstrip("/"),
            model=(model or settings.llm_model).strip(),
            api_key=api_key.strip() if customized else settings.llm_api_key,
            prompt=prompt.strip(),
            semantic_thinking=settings.ollama_semantic_thinking,
        )
    except ValueError as exc:
        raise HTTPException(400, "模型提供方只支持 Ollama 或兼容接口。") from exc
    parsed = urlparse(options.base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise HTTPException(400, "请填写有效的 HTTP(S) 模型 API 地址。")
    if not options.model or (options.provider == "openai" and not options.api_key):
        raise HTTPException(400, "请填写模型名称和所需的 API 密钥。")
    return options


def speech_options(settings: Settings, base_url: str, model: str, voice: str,
                   api_key: str) -> SpeechOptions:
    customized = bool(api_key or (base_url and base_url.rstrip("/") != settings.tts_base_url.rstrip("/"))
                      or (model and model != settings.tts_model)
                      or (voice and voice != settings.tts_voice))
    options = SpeechOptions(
        base_url=(base_url or settings.tts_base_url).strip().rstrip("/"),
        model=(model or settings.tts_model).strip(),
        voice=(voice or settings.tts_voice).strip(),
        api_key=api_key.strip() if customized else settings.tts_api_key,
    )
    parsed = urlparse(options.base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise HTTPException(400, "请填写有效的 HTTP(S) 语音 API 地址。")
    if not options.model or not options.voice:
        raise HTTPException(400, "请填写语音模型名称和音色。")
    if not Settings._is_loopback(options.base_url) and not options.api_key:
        raise HTTPException(400, "外部语音 API 需要密钥。")
    return options


def create_app(settings: Settings | None = None, runner: JobRunner | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = JobStore(settings.data_dir)
    processor = JobProcessor(settings, store)
    runner = runner or JobRunner(processor)
    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        yield
        runner.shutdown()

    application = FastAPI(title="智讲 Agent", version="0.1.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.store = store
    application.state.runner = runner
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/api/config")
    def config() -> dict:
        return {
            "llm_ready": settings.llm_ready,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "llm_is_local": settings.llm_is_local,
            "ai_tts_ready": settings.ai_tts_ready,
            "tts_is_local": settings.tts_is_local,
            "max_pdf_bytes": settings.max_pdf_bytes,
            "llm_base_url": settings.llm_base_url,
            "tts_base_url": settings.tts_base_url,
            "tts_model": settings.tts_model,
            "tts_voice": settings.tts_voice,
            "demo_notice": "演示模式的知识选择和讲稿由确定性规则生成，并非 AI 生成。",
            "ollama_semantic_thinking": settings.ollama_semantic_thinking,
            "math_animation": math_capabilities(),
            "visual_animation": {**visual_capabilities(), "subject_restriction": None,
                "topics": None, "primitives": list(PRIMITIVES),
                "representations": ['geometry','process','relationship','comparison','source_figure'],
                "numeric_checks": sorted(CHECKERS), "domain_validators": sorted(DOMAIN_VALIDATORS),
                "verification_scope": "按表达类型核对来源摘录、关系引用或几何与数值关系；教学含义和领域事实需复核"},
        }

    @application.post("/api/jobs", status_code=202)
    async def create_job(
        file: Annotated[UploadFile, File()],
        rights_confirmed: Annotated[bool, Form()],
        mode: Annotated[Mode, Form()] = Mode.DEMO,
        voice_mode: Annotated[VoiceMode, Form()] = VoiceMode.SYSTEM,
        remote_consent: Annotated[bool, Form()] = False,
        llm_provider: Annotated[str, Form()] = "",
        llm_base_url: Annotated[str, Form()] = "",
        llm_model: Annotated[str, Form()] = "",
        llm_api_key: Annotated[str, Form()] = "",
        custom_prompt: Annotated[str, Form()] = "",
        animation_mode: Annotated[AnimationMode, Form()] = "auto",
        tts_base_url: Annotated[str, Form()] = "",
        tts_model: Annotated[str, Form()] = "",
        tts_voice: Annotated[str, Form()] = "",
        tts_api_key: Annotated[str, Form()] = "",
    ) -> dict:
        if not rights_confirmed:
            raise HTTPException(400, "请先确认拥有资料使用权。")
        options = model_options(settings, llm_provider, llm_base_url, llm_model,
                                llm_api_key, custom_prompt) if mode == Mode.AI else GenerationOptions()
        if mode == Mode.DEMO and animation_mode in {"math","visual"}:
            raise HTTPException(400, "数学推演需要选择真实 AI 模式。")
        options.animation_mode = animation_mode if mode == Mode.AI else "basic"
        if options.animation_mode in {"math","visual"} and not (
                math_capabilities() if options.animation_mode=='math' else visual_capabilities())["ready"]:
            capability=math_capabilities() if options.animation_mode=='math' else visual_capabilities()
            raise HTTPException(400, "教学动画环境未就绪：" + capability["reason"])
        voice_options = speech_options(settings, tts_base_url, tts_model, tts_voice,
                                       tts_api_key) if voice_mode == VoiceMode.AI else SpeechOptions()
        external_text = mode == Mode.AI and not Settings._is_loopback(options.base_url)
        external_voice = voice_mode == VoiceMode.AI and not Settings._is_loopback(voice_options.base_url)
        if (external_text or external_voice) and not remote_consent:
            raise HTTPException(400, "调用外部服务前须同意发送提取文本或讲稿。")
        filename = (file.filename or "source.pdf").replace("\\", "/").split("/")[-1]
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(400, "仅支持 PDF 文件。")
        chunks = []
        total = 0
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > settings.max_pdf_bytes:
                raise HTTPException(413, "PDF 文件超过上传上限。")
            chunks.append(chunk)
        content = b"".join(chunks)
        try:
            validate_pdf(content)
        except PDFError as exc:
            raise HTTPException(400, str(exc)) from exc
        job = store.create(filename, mode, voice_mode, rights_confirmed, remote_consent,
                           content, options, voice_options)
        runner.submit(job["id"])
        return job

    @application.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        return job

    @application.get("/api/jobs/{job_id}/lesson")
    def get_lesson(job_id: str) -> dict:
        if store.get(job_id) is None:
            raise HTTPException(404, "任务不存在。")
        lesson = store.lesson(job_id)
        if lesson is None:
            raise HTTPException(409, "课程尚未生成。")
        return lesson.model_dump(mode="json")

    @application.get("/api/jobs/{job_id}/video")
    def get_video(job_id: str) -> FileResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        path = store.jobs_dir / job_id / "lesson.mp4"
        if job["status"] != JobStatus.COMPLETED or not path.is_file():
            raise HTTPException(409, "视频尚未生成。")
        return FileResponse(path, media_type="video/mp4", filename="zhijiang-lesson.mp4",
                            content_disposition_type="inline")

    @application.get("/api/jobs/{job_id}/presentation")
    def get_presentation(job_id: str) -> FileResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        path = store.jobs_dir / job_id / "lesson.pptx"
        if job["status"] != JobStatus.COMPLETED or not path.is_file():
            raise HTTPException(409, "PPT 课件尚未生成。")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            filename="zhijiang-lesson.pptx",
        )

    @application.get("/api/jobs/{job_id}/math-scenes")
    def get_math_scenes(job_id: str) -> FileResponse:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        path = store.jobs_dir / job_id / "math-scenes.json"
        if job["status"] != JobStatus.COMPLETED or not path.is_file():
            raise HTTPException(409, "数学场景数据尚未生成。")
        return FileResponse(path, media_type="application/json", filename="math-scenes.json")

    @application.get("/api/jobs/{job_id}/scenes")
    def get_scenes(job_id: str) -> FileResponse:
        job=store.get(job_id)
        if job is None:
            raise HTTPException(404,"任务不存在。")
        folder=store.jobs_dir/job_id
        path=folder/"scene-data.json"
        if not path.is_file():
            path=folder/"math-scenes.json"
        if job["status"]!=JobStatus.COMPLETED or not path.is_file():
            raise HTTPException(409,"教学场景数据尚未生成。")
        return FileResponse(path,media_type="application/json",filename="teaching-scenes.json")

    @application.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str, llm_api_key: Annotated[str, Form()] = "",
                  tts_api_key: Annotated[str, Form()] = "",
                  mode: Annotated[Mode | None, Form()] = None,
                  voice_mode: Annotated[VoiceMode | None, Form()] = None,
                  llm_provider: Annotated[str | None, Form()] = None,
                  llm_base_url: Annotated[str | None, Form()] = None,
                  llm_model: Annotated[str | None, Form()] = None,
                  custom_prompt: Annotated[str | None, Form()] = None,
                  animation_mode: Annotated[AnimationMode | None, Form()] = None,
                  tts_base_url: Annotated[str | None, Form()] = None,
                  tts_model: Annotated[str | None, Form()] = None,
                  tts_voice: Annotated[str | None, Form()] = None,
                  replace_settings: Annotated[bool, Form()] = False,
                  remote_consent: Annotated[bool | None, Form()] = None) -> dict:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        if job["status"] != JobStatus.FAILED:
            raise HTTPException(409, "只有失败任务可以重新生成。")
        mode = mode or Mode(job["mode"])
        voice_mode = voice_mode or VoiceMode(job["voice_mode"])
        if mode == Mode.DEMO and animation_mode in {"math", "visual"}:
            raise HTTPException(400, "教学过程与数学推演需要选择真实 AI 模式。")
        options = store.get_options(job_id)
        if mode == Mode.AI:
            provider = options.provider if llm_provider is None else llm_provider
            base_url = options.base_url if llm_base_url is None else llm_base_url
            same_destination = (base_url.strip().rstrip("/") == options.base_url.rstrip("/")
                                and provider == options.provider)
            options = model_options(settings, provider if options.base_url else llm_provider or "",
                base_url, options.model if llm_model is None else llm_model,
                llm_api_key or (options.api_key if same_destination else ""),
                ("" if replace_settings else options.prompt) if custom_prompt is None else custom_prompt)
            options.animation_mode = animation_mode or store.get_options(job_id).animation_mode
            if options.animation_mode in {"math", "visual"} and not (
                    math_capabilities() if options.animation_mode=='math' else visual_capabilities())["ready"]:
                capability=math_capabilities() if options.animation_mode=='math' else visual_capabilities()
                raise HTTPException(400, "教学动画环境未就绪：" + capability["reason"])
        else:
            options = GenerationOptions(animation_mode="basic")
        voice_options = store.get_speech_options(job_id)
        if voice_mode == VoiceMode.AI:
            base_url = voice_options.base_url if tts_base_url is None else tts_base_url
            same_destination = base_url.strip().rstrip("/") == voice_options.base_url.rstrip("/")
            voice_options = speech_options(settings, base_url,
                voice_options.model if tts_model is None else tts_model,
                voice_options.voice if tts_voice is None else tts_voice,
                tts_api_key or (voice_options.api_key if same_destination else ""))
        else:
            voice_options = SpeechOptions()
        external_text = mode == Mode.AI and not Settings._is_loopback(options.base_url)
        external_voice = (voice_mode == VoiceMode.AI
                          and not Settings._is_loopback(voice_options.base_url))
        consent = job["remote_consent"] if remote_consent is None else remote_consent
        changed_external_destination = ((external_text and options.base_url != job["model_settings"].get("base_url"))
                                        or (external_voice and voice_options.base_url != job["voice_settings"].get("base_url")))
        if (external_text or external_voice) and (not consent or (changed_external_destination and remote_consent is not True)):
            raise HTTPException(400, "调用外部服务前须重新提交并同意发送文本。")
        if not (store.jobs_dir / job_id / "source.pdf").is_file():
            raise HTTPException(409, "原始 PDF 已丢失，请重新上传。")
        if not store.retry(job_id, mode=mode, voice_mode=voice_mode, options=options,
                           speech_options=voice_options, remote_consent=consent):
            raise HTTPException(409, "任务状态已改变，请刷新页面。")
        store.clear_api_key(job_id)
        store.set_api_key(job_id, options.api_key)
        store.set_tts_api_key(job_id, voice_options.api_key)
        runner.submit(job_id)
        return store.get(job_id)

    @application.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str) -> None:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        if job["status"] in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise HTTPException(409, "任务仍在处理中，请完成后再删除。")
        folder = (store.jobs_dir / job_id).resolve()
        root = store.jobs_dir.resolve()
        if folder == root or not folder.is_relative_to(root):
            raise HTTPException(400, "无效任务路径。")
        shutil.rmtree(folder, ignore_errors=False)
        store.delete(job_id)

    return application


class LazyApplication:
    """Do not open the persistent job store merely by importing this module."""

    def __init__(self) -> None:
        self._app: FastAPI | None = None

    async def __call__(self, scope: dict, receive, send) -> None:
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = LazyApplication()
