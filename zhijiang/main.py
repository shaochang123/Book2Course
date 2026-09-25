"""本地网站与受限 API。使用 `python -m uvicorn zhijiang.main:app` 启动。"""

from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from zhijiang.config import Settings
from zhijiang.models import JobStatus, Mode, VoiceMode
from zhijiang.pdf import PDFError, read_pdf
from zhijiang.pipeline import JobProcessor, JobRunner
from zhijiang.storage import JobStore


STATIC_DIR = Path(__file__).parent / "static"


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
            "llm_model": settings.llm_model if settings.llm_ready else "",
            "llm_is_local": settings.llm_is_local,
            "ai_tts_ready": settings.ai_tts_ready,
            "tts_is_local": settings.tts_is_local,
            "max_pdf_bytes": settings.max_pdf_bytes,
            "max_pdf_pages": settings.max_pdf_pages,
            "demo_notice": "演示模式的知识选择和讲稿由确定性规则生成，并非 AI 生成。",
        }

    @application.post("/api/jobs", status_code=202)
    async def create_job(
        file: Annotated[UploadFile, File()],
        rights_confirmed: Annotated[bool, Form()],
        mode: Annotated[Mode, Form()] = Mode.DEMO,
        voice_mode: Annotated[VoiceMode, Form()] = VoiceMode.SYSTEM,
        remote_consent: Annotated[bool, Form()] = False,
    ) -> dict:
        if not rights_confirmed:
            raise HTTPException(400, "请先确认拥有资料使用权。")
        if mode == Mode.AI and not settings.llm_ready:
            raise HTTPException(400, "真实 AI 模式尚未配置文本模型服务。")
        if voice_mode == VoiceMode.AI and not settings.ai_tts_ready:
            raise HTTPException(400, "AI 配音尚未配置语音服务。")
        external_text = mode == Mode.AI and not settings.llm_is_local
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
            read_pdf(content, filename, settings.max_pdf_pages)
        except PDFError as exc:
            raise HTTPException(400, str(exc)) from exc
        job = store.create(filename, mode, voice_mode, rights_confirmed, remote_consent, content)
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
    def retry_job(job_id: str) -> dict:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "任务不存在。")
        if job["status"] != JobStatus.FAILED:
            raise HTTPException(409, "只有失败任务可以重新生成。")
        if Mode(job["mode"]) == Mode.AI and not settings.llm_ready:
            raise HTTPException(400, "真实 AI 模式尚未配置文本模型服务。")
        if VoiceMode(job["voice_mode"]) == VoiceMode.AI and not settings.ai_tts_ready:
            raise HTTPException(400, "AI 配音尚未配置语音服务。")
        external_text = Mode(job["mode"]) == Mode.AI and not settings.llm_is_local
        external_voice = VoiceMode(job["voice_mode"]) == VoiceMode.AI and not settings.tts_is_local
        if (external_text or external_voice) and not job["remote_consent"]:
            raise HTTPException(400, "调用外部服务前须重新提交并同意发送文本。")
        if not (store.jobs_dir / job_id / "source.pdf").is_file():
            raise HTTPException(409, "原始 PDF 已丢失，请重新上传。")
        if not store.retry(job_id):
            raise HTTPException(409, "任务状态已改变，请刷新页面。")
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
