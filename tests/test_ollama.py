"""本机模型配置和原生结构化输出契约。"""

import json

import httpx
from fastapi.testclient import TestClient

from zhijiang.agents import DemoAgents, GenerationError, OllamaClient
import pytest
from zhijiang.config import Settings
from zhijiang.main import create_app
from zhijiang.models import KnowledgeBundle, PageText, SourceDocument
from zhijiang.agents import source_candidates
from zhijiang.pdf import read_pdf


@pytest.mark.parametrize('provider',['ollama','compatible'])
def test_format_retry_supplies_enum_and_numeric_contract_without_echoing_input(provider):
    from typing import Literal
    from pydantic import BaseModel
    from zhijiang.agents import OpenAICompatibleClient
    class Draft(BaseModel):
        kind: Literal['concept','formula','process']
        value: float
        note: str
    requests=[]
    def handler(request):
        if request.url.path=='/api/show':
            return httpx.Response(200,json={})
        body=json.loads(request.content);requests.append(body)
        if len(requests)==1:
            result={'kind':'definition','value':'pi/4','note':'PRIVATE_RESPONSE_TOKEN'}
        else:
            feedback=body['messages'][-1]['content']
            assert all(v in feedback for v in ['concept','formula','process','number'])
            assert 'PRIVATE_RESPONSE_TOKEN' not in feedback
            assert 'PRIVATE_SOURCE_TOKEN' not in feedback
            result={'kind':'concept','value':.785,'note':'已修正数据类型'}
        content=json.dumps(result)
        return httpx.Response(200,json=({'message':{'content':content}} if provider=='ollama'
            else {'choices':[{'message':{'content':content}}]}))
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=(OllamaClient('http://localhost:11434','local',http_client,prefer_json=True)
                if provider=='ollama' else OpenAICompatibleClient('https://model.invalid/v1','api-secret','remote',http_client))
        result=client.generate(Draft,'遵循现有数据契约','PRIVATE_SOURCE_TOKEN')
        assert result.kind=='concept' and result.value==.785 and len(requests)==2


@pytest.mark.parametrize('stage',['TopicSourceScope','TopicScopeReview'])
@pytest.mark.parametrize('enabled',[True,False])
def test_topic_scope_stages_follow_semantic_thinking_configuration(stage,enabled):
    from pydantic import create_model
    schema=create_model(stage,reason=(str,...))
    def handler(request):
        if request.url.path=='/api/show':
            return httpx.Response(200,json={'thinking':{'values':[True,False],'default':False}})
        payload=json.loads(request.content)
        assert payload['think'] is enabled
        assert payload['options']['num_predict']==4096
        return httpx.Response(200,json={'message':{'content':'{"reason":"原文覆盖当前范围"}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','installed-model',http_client,semantic_thinking=enabled)
        assert client.generate(schema,'核对教学范围','source').reason=='原文覆盖当前范围'


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
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": ["completion"]})
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


def test_qwen3_uses_non_thinking_mode(sample_pdf):
    bundle = DemoAgents().extract_knowledge(read_pdf(sample_pdf, "original.pdf"))
    scene_stage=False
    response_content=bundle.model_dump_json()

    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"thinking": {"values": [True, False], "default": True}})
        body = json.loads(request.content)
        assert body["think"] is False
        if scene_stage:
            assert body['options']['num_ctx']==8192 and body['options']['num_predict']==3072
        return httpx.Response(200, json={"message": {"content": response_content}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient("http://127.0.0.1:11434", "qwen3:4b", http_client)
        assert client.generate(KnowledgeBundle, "提取", "资料") == bundle
        from scripts.build_general_examples import fixtures
        from zhijiang.visual_planning import VisualLayoutDraft
        scene_stage=True
        from zhijiang.visual_planning import LAYOUT_FIELDS
        response_content=fixtures()[0].model_dump_json(include=LAYOUT_FIELDS)
        assert client.generate(VisualLayoutDraft,'生成分镜','资料').domain=='微积分'


def test_teaching_semantic_review_uses_qwen3_deliberation():
    from zhijiang.teaching_design import TeachingSourceReview
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"thinking": {"values": [True], "default": True}})
        body=json.loads(request.content)
        assert body['think'] is True and body['options']['num_predict']==4096
        return httpx.Response(200,json={'message':{'content':'{"approved":false,"issues":["definition mismatch"]}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        review=OllamaClient('http://127.0.0.1:11434','qwen3:4b',http_client).generate(TeachingSourceReview,'核对定义','原文材料')
        assert not review.approved


def test_schema_repair_identifies_field_without_echoing_sensitive_input(sample_pdf):
    bundle=DemoAgents().extract_knowledge(read_pdf(sample_pdf,'original.pdf'))
    calls=[]
    def handler(request):
        if request.url.path == "/api/show":
            return httpx.Response(200, json={})
        body=json.loads(request.content);calls.append(body)
        if len(calls)==1:
            return httpx.Response(200,json={'message':{'content':json.dumps({'points':'private-input-do-not-echo'})}})
        repair=body['messages'][-1]['content']
        assert 'points:list_type' in repair and 'private-input-do-not-echo' not in repair
        return httpx.Response(200,json={'message':{'content':bundle.model_dump_json()}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://127.0.0.1:11434','qwen3:4b',http_client)
        assert client.generate(KnowledgeBundle,'提取','资料')==bundle
        assert client.call_metrics[0]['validation_error']=='points:list_type'
        assert len(client.invalid_outputs)==1
        assert client.invalid_outputs[0]['content']==json.dumps({'points':'private-input-do-not-echo'})
        assert set(client.invalid_outputs[0])=={'stage','attempt','endpoint','error','content','truncated'}
    assert len(calls)==2


@pytest.mark.parametrize("metadata,expected", [
    ({"thinking": {"values": [True], "default": True}}, True),
    ({"thinking": {"values": ["low", "high"], "default": "low"}}, "low"),
    ({"capabilities": ["completion"]}, None),
    ({}, None),
])
def test_thinking_controls_follow_metadata_not_model_name(sample_pdf, metadata, expected):
    bundle=DemoAgents().extract_knowledge(read_pdf(sample_pdf,'original.pdf'))
    shows=[]
    def handler(request):
        if request.url.path == '/api/show':
            shows.append(request)
            return httpx.Response(200,json=metadata)
        body=json.loads(request.content)
        if expected is None:
            assert 'think' not in body
        else:
            assert body['think'] == expected
        return httpx.Response(200,json={'message':{'content':bundle.model_dump_json()},'eval_count':21})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://127.0.0.1:11434','arbitrary-model',http_client)
        for _ in range(2):
            assert client.generate(KnowledgeBundle,'提取','资料')==bundle
        assert len(shows)==1 and len(client.call_metrics)==2
        assert client.call_metrics[0]['eval_count']==21


def test_ollama_output_budget_exhaustion_is_not_retried():
    from zhijiang.teaching_design import TeachingSourceReview
    chats=[]
    def handler(request):
        if request.url.path == '/api/show':
            return httpx.Response(200,json={})
        chats.append(request)
        return httpx.Response(200,json={'done_reason':'length','message':{'content':''}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(GenerationError,match='输出预算'):
            OllamaClient('http://localhost:11434','model',http_client).generate(TeachingSourceReview,'核对','资料')
    assert len(chats)==1


def test_ollama_repairs_one_runner_500_without_echoing_its_body(sample_pdf):
    bundle=DemoAgents().extract_knowledge(read_pdf(sample_pdf,'original.pdf'))
    calls=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        body=json.loads(request.content);calls.append(body)
        if len(calls)==1:return httpx.Response(500,json={'error':'private-invalid-model-output'})
        assert request.url.path=='/api/generate'
        assert 'private-invalid-model-output' not in body['prompt']
        assert '标准JSON' in body['prompt'] and '提取' in body['system']
        assert body['format']=='json'
        assert 'JSON Schema' in body['system']
        return httpx.Response(200,json={'response':bundle.model_dump_json()+']}]]}'} )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        c=OllamaClient('http://localhost:11434','model',http_client)
        assert c.generate(KnowledgeBundle,'提取','资料')==bundle
        assert c.call_metrics[0]['http_status']==500 and len(calls)==2
        assert c.call_metrics[-1]['format_repair']=='duplicate_terminators'


@pytest.mark.parametrize('suffix',[' invented extra prose',' {"second":"object"}'])
def test_native_json_normalization_does_not_ignore_prose_or_another_object(sample_pdf,suffix):
    bundle=DemoAgents().extract_knowledge(read_pdf(sample_pdf,'original.pdf'));calls=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        calls.append(request)
        return httpx.Response(200,json={'message':{'content':bundle.model_dump_json()+suffix}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(GenerationError,match='不符合'):
            OllamaClient('http://localhost:11434','model',http_client).generate(KnowledgeBundle,'提取','资料')
    assert len(calls)==2


@pytest.mark.parametrize('status,count',[(401,1),(503,2)])
def test_ollama_http_repair_is_bounded_and_does_not_retry_auth(status,count):
    calls=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        calls.append(request);return httpx.Response(status,json={'error':'unavailable'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(GenerationError,match='HTTP '+str(status)):
            OllamaClient('http://localhost:11434','model',http_client).generate(KnowledgeBundle,'提取','资料')
    assert len(calls)==count


def test_long_english_pdf_candidates_fit_small_batches():
    document = SourceDocument(filename="paper.pdf", pages=[
        PageText(page=number, text="\n".join(
            f"Page {number} paragraph {index} explains a substantial part of the method and results."
            for index in range(20)))
        for number in range(1, 18)
    ])
    candidates = source_candidates(document)
    assert len(candidates) == 34
    assert candidates[-1]["page"] == 17
    from zhijiang.models import Evidence
    assert all(Evidence(page=item['page'],quote=item['quote'],ocr=item['ocr']) for item in candidates)


def test_long_document_keeps_definition_context_and_skips_table_headers():
    definition='A synthetic dataset contains generated examples for the robotic device. It does not capture human behavior directly.'
    document=SourceDocument(filename='input.pdf',pages=[
        PageText(page=number,text=definition+'\nDataset Human Sim/Real Type Visual Data #Object #Pose #Motion Seq.')
        for number in range(1,8)])
    quotes=[item['quote'] for item in source_candidates(document)]
    assert any('does not capture human behavior' in quote for quote in quotes)
    assert not any('#Object' in quote for quote in quotes)


def test_knowledge_schema_restricts_ids_to_current_batch():
    from pydantic import ValidationError
    from zhijiang.agents import knowledge_selection_schema
    schema=knowledge_selection_schema([21,24,27])
    point={'title':'主题概念','kind':'concept','explanation':'根据真实来源讲解其定义和适用条件。'}
    data={'points':[{**point,'source_id':key} for key in (21,24,27)]}
    assert len(schema.model_validate(data).points)==3
    data['points'][0]['source_id']=1
    with pytest.raises(ValidationError):schema.model_validate(data)


def test_distinct_concepts_can_share_a_source_excerpt():
    from zhijiang.agents import AIAgents
    text='Observation identifies changes, classification groups the observations, and recording preserves their context.'
    document=SourceDocument(filename='method.pdf',pages=[PageText(page=1,text=text+'\n'
        'The method records context so observations can be compared.\n'
        'Classification preserves the distinction between observed categories.')])
    class Client:
        def generate(self,schema,instruction,material):
            sources=json.loads(material)['sources'];key=sources[0]['id']
            return schema.model_validate({'points':[{'title':title,'kind':'concept',
                'explanation':'解释原文中该步骤的含义及与其他步骤的关系。','source_id':key}
                for title in ('观测','分类','记录')]})
    bundle=AIAgents(Client()).extract_knowledge(document)
    assert len(bundle.points)==3 and all(p.evidence==bundle.points[0].evidence for p in bundle.points)


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
