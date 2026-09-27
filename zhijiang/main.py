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
from zhijiang.models import GenerationOptions, JobStatus, Mode, VoiceMode
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
            "demo_notice": "演示模式的知识选择和讲稿由确定性规则生成，并非 AI 生成。",
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
    ) -> dict:
        if not rights_confirmed:
            raise HTTPException(400, "请先确认拥有资料使用权。")
        options = model_options(settings, llm_provider, llm_base_url, llm_model,
                                llm_api_key, custom_prompt) if mode == Mode.AI else GenerationOptions()
        if voice_mode == VoiceMode.AI and not settings.ai_tts_ready:
            raise HTTPException(400, "AI 配音尚未配置语音服务。")
        external_text = mode == Mode.AI and not Settings._is_loopback(options.base_url)
        external_voice = voice_mode == VoiceMode.AI and not settings.tts_is_local
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
                           content, options)
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

    @application.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str, llm_api_key: Annotated[str, Form()] = "") -> dict:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        if job["status"] != JobStatus.FAILED:
            raise HTTPException(409, "只有失败任务可以重新生成。")
        options = store.get_options(job_id)
        if llm_api_key:
            options.api_key = llm_api_key
        if Mode(job["mode"]) == Mode.AI and not options.base_url:
            options = model_options(settings, "", "", "", llm_api_key, options.prompt)
            store.update_options(job_id, options)
        if Mode(job["mode"]) == Mode.AI and options.provider == "openai" and not options.api_key:
            raise HTTPException(400, "请重新输入此任务的 API 密钥后重试。")
        if VoiceMode(job["voice_mode"]) == VoiceMode.AI and not settings.ai_tts_ready:
            raise HTTPException(400, "AI 配音尚未配置语音服务。")
        external_text = Mode(job["mode"]) == Mode.AI and not Settings._is_loopback(options.base_url)
        external_voice = VoiceMode(job["voice_mode"]) == VoiceMode.AI and not settings.tts_is_local
        if (external_text or external_voice) and not job["remote_consent"]:
            raise HTTPException(400, "调用外部服务前须重新提交并同意发送文本。")
        if not (store.jobs_dir / job_id / "source.pdf").is_file():
            raise HTTPException(409, "原始 PDF 已丢失，请重新上传。")
        if not store.retry(job_id):
            raise HTTPException(409, "任务状态已改变，请刷新页面。")
        store.set_api_key(job_id, options.api_key)
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


app = create_app()
