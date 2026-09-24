"""本机模型配置和原生结构化输出契约。"""

import json

import httpx
from fastapi.testclient import TestClient

from zhijiang.agents import DemoAgents, OllamaClient
from zhijiang.config import Settings
from zhijiang.main import create_app
from zhijiang.models import KnowledgeBundle
from zhijiang.pdf import read_pdf


def test_local_config_and_environment_precedence(tmp_path, monkeypatch):
    config = tmp_path / ".env.local"
    config.write_text(
        "ZHIJIANG_LLM_PROVIDER=ollama\n"
        "ZHIJIANG_LLM_BASE_URL=http://127.0.0.1:11434\n"
        "ZHIJIANG_LLM_MODEL=qwen2.5:7b\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZHIJIANG_ENV_FILE", str(config))
    settings = Settings.from_env()
    assert settings.llm_ready and settings.llm_is_local
    assert settings.llm_model == "qwen2.5:7b"
    monkeypatch.setenv("ZHIJIANG_LLM_MODEL", "qwen3:8b")
    assert Settings.from_env().llm_model == "qwen3:8b"


def test_ollama_native_json_schema_request(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    bundle = DemoAgents().extract_knowledge(document)
    requests = []

    def handler(request):
        requests.append(request)
        body = json.loads(request.content)
        assert request.url.path == "/api/chat"
        assert body["stream"] is False
        assert body["format"] == KnowledgeBundle.model_json_schema()
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"message": {"content": bundle.model_dump_json()}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient("http://127.0.0.1:11434", "qwen2.5:7b", http_client)
        assert client.generate(KnowledgeBundle, "提取", "测试资料") == bundle
    assert len(requests) == 1


def test_local_ollama_does_not_require_remote_consent(tmp_path, sample_pdf):
    class QueuedRunner:
        def submit(self, job_id):
            pass

        def shutdown(self):
            pass

    settings = Settings(
        data_dir=tmp_path / "data", llm_provider="ollama",
        llm_base_url="http://127.0.0.1:11434", llm_model="qwen2.5:7b",
    )
    with TestClient(create_app(settings, QueuedRunner())) as client:
        response = client.post(
            "/api/jobs", files={"file": ("original.pdf", sample_pdf)},
            data={"rights_confirmed": "true", "mode": "ai"},
        )
        assert response.status_code == 202, response.text
        assert response.json()["remote_consent"] is False
