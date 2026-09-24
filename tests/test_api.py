import wave

import httpx
from fastapi.testclient import TestClient

from zhijiang.agents import AIAgents, DemoAgents, OpenAICompatibleClient
from zhijiang.config import Settings
from zhijiang.main import create_app
from zhijiang.models import JobStatus, Mode, ReviewResult, VoiceMode
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
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
        assert not (store.jobs_dir / job_id).exists()


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


def test_store_marks_interrupted_jobs_failed(tmp_path, sample_pdf):
    store = JobStore(tmp_path / "data")
    job = store.create("sample.pdf", Mode.DEMO, VoiceMode.SYSTEM, True, False, sample_pdf)
    restarted = JobStore(tmp_path / "data")
    assert restarted.get(job["id"])["status"] == JobStatus.FAILED


def test_full_ai_pipeline_with_mock_model(tmp_path, sample_pdf):
    document = read_pdf(sample_pdf, "sample.pdf")
    demo = DemoAgents()
    bundle = demo.extract_knowledge(document)
    outline = demo.plan(bundle)
    lesson = demo.script(bundle, outline, VoiceMode.SYSTEM)
    lesson.mode = Mode.AI
    lesson.segments = lesson.segments[:3]
    for segment in lesson.segments:
        while len(segment.narration) < 180:
            segment.narration += "结合原文中的条件，逐步检查当前范围与比较结果。"
    replies = [bundle, outline, lesson, ReviewResult(approved=True)]
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, json={"choices": [{"message": {"content": replies.pop(0).model_dump_json()}}]}
        )
    )
    settings = Settings(data_dir=tmp_path / "data", llm_base_url="https://example.invalid/v1",
                        llm_api_key="fake", llm_model="fake")
    store = JobStore(settings.data_dir)
    job = store.create("sample.pdf", Mode.AI, VoiceMode.SYSTEM, True, True, sample_pdf)
    with httpx.Client(transport=transport) as http_client:
        ai_agents = AIAgents(OpenAICompatibleClient(settings.llm_base_url, "fake", "fake", http_client))
        processor = JobProcessor(
            settings, store,
            agent_factory=lambda _: ai_agents,
            speech_factory=lambda _: FakeSpeech(),
            video_renderer=lambda lesson, audio, path: path.write_bytes(b"fake mp4"),
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
