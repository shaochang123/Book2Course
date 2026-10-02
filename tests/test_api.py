import wave
import sqlite3

import httpx
from fastapi.testclient import TestClient

from zhijiang.agents import (
    AIAgents, DemoAgents, KnowledgeSelection, KnowledgeSelectionPoint,
    OpenAICompatibleClient, ScriptDraft, ScriptDraftSegment, source_candidates,
)
from zhijiang.config import Settings
from zhijiang.main import create_app
from zhijiang.models import GenerationOptions, JobStatus, Mode, ReviewResult, VoiceMode
from zhijiang.pdf import read_pdf
from zhijiang.pipeline import JobProcessor
from zhijiang.speech import SpeechError
from zhijiang.storage import JobStore


class FakeSpeech:
    def synthesize(self, text, output):
        with wave.open(str(output), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24000)
            audio.writeframes(b"\x00\x00" * 2400)


class InlineRunner:
    processor = None

    def submit(self, job_id):
        self.processor.process(job_id)

    def shutdown(self):
        pass


def make_client(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    runner = InlineRunner()
    app = create_app(settings, runner)
    runner.processor = JobProcessor(
        settings, app.state.store,
        speech_factory=lambda _: FakeSpeech(),
        video_renderer=lambda lesson, audio, path: path.write_bytes(b"fake mp4"),
        presentation_renderer=lambda lesson, path: path.write_bytes(b"fake pptx"),
    )
    return TestClient(app), app.state.store


def test_api_upload_result_video_and_delete(tmp_path, sample_pdf):
    client, store = make_client(tmp_path)
    with client:
        response = client.post(
            "/api/jobs",
            files={"file": ("original.pdf", sample_pdf, "application/pdf")},
            data={"mode": "demo", "voice_mode": "system", "rights_confirmed": "true"},
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        status = client.get(f"/api/jobs/{job_id}").json()
        assert status["status"] == "completed"
        assert status["progress"] == 100
        lesson = client.get(f"/api/jobs/{job_id}/lesson").json()
        assert len(lesson["segments"]) == 6
        assert lesson["segments"][0]["evidence"]["page"] == 1
        assert client.get(f"/api/jobs/{job_id}/video").status_code == 200
        assert status["has_presentation"]
        presentation = client.get(f"/api/jobs/{job_id}/presentation")
        assert presentation.status_code == 200
        assert presentation.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert not (store.jobs_dir / job_id).exists()


def test_failed_job_can_retry_with_saved_pdf(tmp_path, sample_pdf):
    client, store = make_client(tmp_path)
    with client:
        response = client.post(
            "/api/jobs", files={"file": ("original.pdf", sample_pdf)},
            data={"mode": "demo", "voice_mode": "system", "rights_confirmed": "true"},
        )
        job_id = response.json()["id"]
        assert client.post(f"/api/jobs/{job_id}/retry").status_code == 409
        store.fail(job_id, "模拟先前失败")
        assert (store.jobs_dir / job_id / "source.pdf").is_file()
        for name in ("math", "visual"):
            scene_folder=store.jobs_dir / job_id / name / "scene-01"
            scene_folder.mkdir(parents=True)
            (scene_folder / "clip.mp4").write_bytes(b"obsolete scene media")
        retry = client.post(f"/api/jobs/{job_id}/retry")
        assert retry.status_code == 202, retry.text
        assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
        assert client.get(f"/api/jobs/{job_id}/lesson").status_code == 200
        assert all(not (store.jobs_dir / job_id / name).exists() for name in ("math", "visual"))


def test_upload_guards_and_error_messages(tmp_path, sample_pdf):
    client, _ = make_client(tmp_path)
    with client:
        def upload(pdf, **data):
            return client.post("/api/jobs", files={"file": ("sample.pdf", pdf, "application/pdf")}, data=data)

        assert upload(sample_pdf, rights_confirmed="false").status_code == 400
        assert upload(b"broken", rights_confirmed="true").status_code == 400
        assert upload(sample_pdf, rights_confirmed="true", mode="ai").status_code == 400
        assert upload(sample_pdf, rights_confirmed="true", voice_mode="ai").status_code == 400
        assert client.get("/api/jobs/notfound").status_code == 404
        assert client.get("/").status_code == 200
        assert "确定性演示模式" in client.get("/").text


def test_remote_consent_and_running_delete_guard(tmp_path, sample_pdf):
    settings = Settings(data_dir=tmp_path / "data", llm_base_url="https://example.invalid/v1",
                        llm_api_key="fake", llm_model="fake")

    class QueuedRunner:
        def submit(self, job_id):
            pass
        def shutdown(self):
            pass

    app = create_app(settings, QueuedRunner())
    with TestClient(app) as client:
        response = client.post("/api/jobs", files={"file": ("source.pdf", sample_pdf)},
                               data={"rights_confirmed": "true", "mode": "ai"})
        assert response.status_code == 400
        assert "同意" in response.json()["detail"]
        response = client.post("/api/jobs", files={"file": ("source.pdf", sample_pdf)},
                               data={"rights_confirmed": "true", "mode": "ai", "remote_consent": "true"})
        assert response.status_code == 202
        assert client.delete(f"/api/jobs/{response.json()['id']}").status_code == 409


def test_web_model_overrides_and_prompt_do_not_store_api_key(tmp_path, sample_pdf):
    class QueuedRunner:
        def submit(self, job_id):
            pass
        def shutdown(self):
            pass

    app = create_app(Settings(data_dir=tmp_path / "data"), QueuedRunner())
    with TestClient(app) as client:
        assert 'id="custom-prompt"' in client.get("/").text
        payload = {
            "rights_confirmed": "true", "mode": "ai", "remote_consent": "true",
            "llm_provider": "openai", "llm_base_url": "https://example.invalid/v1",
            "llm_model": "my-model", "llm_api_key": "secret-for-this-job",
            "custom_prompt": "给初学者讲得详细一些，增加例子。",
        }
        response = client.post("/api/jobs", files={"file": ("source.pdf", sample_pdf)}, data=payload)
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        options = app.state.store.get_options(job_id)
        assert options.model == "my-model"
        assert "初学者" in options.prompt
        assert options.api_key == "secret-for-this-job"
        assert "secret-for-this-job" not in str(response.json())
        assert b"secret-for-this-job" not in app.state.store.db_path.read_bytes()
        app.state.store.fail(job_id, "模拟分镜失败")
        changed = {"llm_base_url": "https://another.invalid/v1", "llm_model": "stronger-model",
                   "custom_prompt": "改用连续教学过程", "animation_mode": "basic"}
        # A destination change must not inherit the old credential or consent.
        assert client.post(f"/api/jobs/{job_id}/retry", data=changed).status_code == 400
        changed["llm_api_key"] = "new-destination-secret"
        assert client.post(f"/api/jobs/{job_id}/retry", data=changed).status_code == 400
        assert app.state.store.get(job_id)["status"] == JobStatus.FAILED
        assert app.state.store.get_options(job_id).base_url == "https://example.invalid/v1"
        changed["remote_consent"] = "true"
        retry = client.post(f"/api/jobs/{job_id}/retry", data=changed)
        assert retry.status_code == 202, retry.text
        updated = app.state.store.get_options(job_id)
        assert updated.model == "stronger-model" and updated.prompt == "改用连续教学过程"
        assert updated.animation_mode == "basic" and updated.api_key == "new-destination-secret"
        assert b"new-destination-secret" not in app.state.store.db_path.read_bytes()
        assert "new-destination-secret" not in str(retry.json())
        app.state.store.fail(job_id, "再次模拟失败")
        cleared = client.post(f"/api/jobs/{job_id}/retry", data={"replace_settings": "true", "custom_prompt": ""})
        assert cleared.status_code == 202, cleared.text
        assert app.state.store.get_options(job_id).prompt == ""


def test_web_voice_overrides_use_local_service_without_key(tmp_path, sample_pdf):
    class QueuedRunner:
        def submit(self, job_id):
            pass
        def shutdown(self):
            pass

    app = create_app(Settings(data_dir=tmp_path / "data"), QueuedRunner())
    with TestClient(app) as client:
        page = client.get("/").text
        assert 'id="tts-base-url"' in page
        assert 'id="tts-voice"' in page
        response = client.post(
            "/api/jobs", files={"file": ("source.pdf", sample_pdf)},
            data={
                "rights_confirmed": "true", "voice_mode": "ai",
                "tts_base_url": "http://127.0.0.1:8766/v1",
                "tts_model": "kokoro-82m-v1.1-zh", "tts_voice": "zf_xiaoxiao",
            },
        )
        assert response.status_code == 202, response.text
        assert response.json()["voice_settings"]["voice"] == "zf_xiaoxiao"
        assert app.state.store.get_speech_options(response.json()["id"]).model == "kokoro-82m-v1.1-zh"
        job_id = response.json()["id"]
        app.state.store.fail(job_id, "模拟失败")
        retry = client.post(f"/api/jobs/{job_id}/retry", data={"mode":"ai", "voice_mode":"ai",
            "llm_provider":"ollama", "llm_base_url":"http://127.0.0.1:11434", "llm_model":"qwen3:4b",
            "custom_prompt":"重新规划分镜", "animation_mode":"basic", "tts_voice":"zf_002"})
        assert retry.status_code == 202, retry.text
        assert retry.json()["mode"] == "ai"
        assert retry.json()["voice_settings"]["voice"] == "zf_002"
        assert app.state.store.get_options(job_id).prompt == "重新规划分镜"


def test_external_voice_requires_consent_and_retry_key(tmp_path, sample_pdf):
    class QueuedRunner:
        def submit(self, job_id):
            pass
        def shutdown(self):
            pass

    app = create_app(Settings(data_dir=tmp_path / "data"), QueuedRunner())
    payload = {
        "rights_confirmed": "true", "voice_mode": "ai",
        "tts_base_url": "https://example.invalid/v1",
        "tts_model": "speech-model", "tts_voice": "voice-a",
        "tts_api_key": "voice-secret",
    }
    with TestClient(app) as client:
        denied = client.post("/api/jobs", files={"file": ("source.pdf", sample_pdf)}, data=payload)
        assert denied.status_code == 400
        assert "同意" in denied.json()["detail"]
        payload["remote_consent"] = "true"
        response = client.post("/api/jobs", files={"file": ("source.pdf", sample_pdf)}, data=payload)
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        assert "voice-secret" not in str(response.json())
        assert b"voice-secret" not in app.state.store.db_path.read_bytes()
        app.state.store.fail(job_id, "模拟语音失败")
        app.state.store.clear_api_key(job_id)
        assert client.post(f"/api/jobs/{job_id}/retry").status_code == 400
        retry = client.post(f"/api/jobs/{job_id}/retry", data={"tts_api_key": "new-secret"})
        assert retry.status_code == 202, retry.text
        assert app.state.store.get_speech_options(job_id).api_key == "new-secret"
        assert b"new-secret" not in app.state.store.db_path.read_bytes()


def test_store_marks_interrupted_jobs_failed(tmp_path, sample_pdf):
    store = JobStore(tmp_path / "data")
    job = store.create("sample.pdf", Mode.DEMO, VoiceMode.SYSTEM, True, False, sample_pdf)
    restarted = JobStore(tmp_path / "data")
    assert restarted.get(job["id"])["status"] == JobStatus.FAILED


def test_existing_job_database_is_migrated(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with sqlite3.connect(data_dir / "jobs.sqlite3") as connection:
        connection.execute("""CREATE TABLE jobs (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, mode TEXT NOT NULL,
            voice_mode TEXT NOT NULL, rights_confirmed INTEGER NOT NULL,
            remote_consent INTEGER NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL,
            progress INTEGER NOT NULL, error TEXT, lesson_json TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    store = JobStore(data_dir)
    assert store.get_options("missing").provider == "openai"
    with sqlite3.connect(store.db_path) as connection:
        assert "options_json" in {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}


def test_full_ai_pipeline_with_mock_model(tmp_path, sample_pdf):
    document = read_pdf(sample_pdf, "sample.pdf")
    demo = DemoAgents()
    bundle = demo.extract_knowledge(document)
    candidates = source_candidates(document)
    selection = KnowledgeSelection(points=[
        KnowledgeSelectionPoint(
            title=point.title, kind=point.kind, explanation=point.explanation,
            source_id=next(
                item["id"] for item in candidates
                if item["page"] == point.evidence.page and item["quote"] == point.evidence.quote
            ),
        ) for point in bundle.points
    ])
    outline = demo.plan(bundle)
    lesson = demo.script(bundle, outline, VoiceMode.SYSTEM)
    lesson.mode = Mode.AI
    lesson.segments = lesson.segments[:3]
    for segment in lesson.segments:
        while len(segment.narration) < 180:
            segment.narration += "结合原文中的条件，逐步检查当前范围与比较结果。"
    script_draft = ScriptDraft(segments=[
        ScriptDraftSegment(
            source_id=index, title=segment.title, kind=segment.kind,
            narration=segment.narration, bullets=segment.bullets,
        ) for index, segment in enumerate(lesson.segments, start=1)
    ])
    replies = [selection, outline, script_draft, ReviewResult(approved=True)]
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, json={"choices": [{"message": {"content": replies.pop(0).model_dump_json()}}]}
        )
    )
    settings = Settings(data_dir=tmp_path / "data", llm_base_url="https://example.invalid/v1",
                        llm_api_key="fake", llm_model="fake")
    store = JobStore(settings.data_dir)
    job = store.create("sample.pdf", Mode.AI, VoiceMode.SYSTEM, True, True, sample_pdf,
                       GenerationOptions(animation_mode="basic"))
    with httpx.Client(transport=transport) as http_client:
        ai_agents = AIAgents(OpenAICompatibleClient(settings.llm_base_url, "fake", "fake", http_client))
        processor = JobProcessor(
            settings, store,
            agent_factory=lambda _: ai_agents,
            speech_factory=lambda _: FakeSpeech(),
            video_renderer=lambda lesson, audio, path: path.write_bytes(b"fake mp4"),
            presentation_renderer=lambda lesson, path: path.write_bytes(b"fake pptx"),
        )
        processor.process(job["id"])
    assert store.get(job["id"])["status"] == JobStatus.COMPLETED
    assert store.lesson(job["id"]).mode == Mode.AI
    assert not replies


def test_speech_failure_marks_job_failed(tmp_path, sample_pdf):
    class BrokenSpeech:
        def synthesize(self, text, output):
            raise SpeechError("语音服务模拟失败")

    settings = Settings(data_dir=tmp_path / "data")
    store = JobStore(settings.data_dir)
    job = store.create("sample.pdf", Mode.DEMO, VoiceMode.SYSTEM, True, False, sample_pdf)
    JobProcessor(settings, store, speech_factory=lambda _: BrokenSpeech()).process(job["id"])
    result = store.get(job["id"])
    assert result["status"] == JobStatus.FAILED
    assert "语音服务模拟失败" in result["error"]
    assert not result["has_video"]
