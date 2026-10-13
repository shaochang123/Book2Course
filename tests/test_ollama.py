"""本机模型配置和原生结构化输出契约。"""

import json
from typing import Literal

import httpx
from fastapi.testclient import TestClient

from zhijiang.agents import DemoAgents, GenerationError, OllamaClient
import pytest
from zhijiang.config import Settings
from zhijiang.main import create_app
from zhijiang.models import KnowledgeBundle, PageText, SourceDocument
from zhijiang.agents import source_candidates
from zhijiang.pdf import read_pdf


def test_semantic_repair_hints_use_schema_rules_without_echoing_error_values():
    from pydantic import BaseModel,ValidationError,model_validator
    from zhijiang.agents import _validation_repair_hints
    class Contract(BaseModel):
        """Actual position requires a declared control, never a free variable."""
        coordinate: str
        @model_validator(mode='after')
        def rule(self):raise ValueError('secret-response-value-'+self.coordinate)
    try:Contract(coordinate='private-source-fragment')
    except ValidationError as exc:hints=_validation_repair_hints(Contract,exc)
    assert 'declared control' in hints and 'free variable' in hints
    assert 'private-source-fragment' not in hints and 'secret-response-value' not in hints


def test_object_patch_repair_sees_its_complete_rejected_candidate():
    from zhijiang.automatic_construction import graph_patch_schema
    from zhijiang.math_construction import MathConstructionDraft
    graph=MathConstructionDraft(title='真实函数与动点',objective='保留函数来源并修复实际点的参数绑定。',
        source_id=1,parameters={'u':0},constructions=[
            {'id':'f','op':'function','expr':['sin(x)']},
            {'id':'p','op':'point_on_function','refs':['f'],'expr':['0']}])
    schema=graph_patch_schema(graph,'p');requests=[]
    bad={'upserts':[{'id':'p','op':'point_on_function','refs':['f'],'expr':['x']}]}
    good={'upserts':[{'id':'p','op':'point_on_function','refs':['f'],'expr':['u']}]}
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'content':json.dumps(bad if len(requests)==1 else good)}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','local',http_client,semantic_thinking=False)
        result=client.generate(schema,'repair actual point','complete source and graph')
    assert result.upserts[0].expr==['u'] and len(requests)==2
    assert any(m['role']=='assistant' and json.loads(m['content'])==bad for m in requests[1]['messages'])
    assert '函数自由变量' in requests[1]['messages'][-1]['content']


def test_source_revision_returns_invalid_complete_response_to_page_repair_once():
    from zhijiang.draft_source_repair import _revision_schema,RevisedPage
    from zhijiang.agents import ModelContractError
    schema=_revision_schema(RevisedPage,(1,2))
    page={'source_id':1,'title':'完整来源条件','narration':'我们解释实际来源对象和成立条件，不能忽略这些条件。',
        'bullets':['保留成立条件'],'visual':{'representation':'key_idea',
        'items':[{'label':'来源条件','caption':'明确适用范围','sentence_id':1}]},
        'render_kind':'story','graphic_group':'','context_is_condition':False,'figure_page':0,'figure_box':[]}
    content=json.dumps({'title':'理解来源关系','objective':'保留来源对象与实际成立条件。','pages':[page]})
    requests=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        requests.append(request)
        return httpx.Response(200,json={'message':{'content':content}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','local',http_client,semantic_thinking=False)
        with pytest.raises(ModelContractError) as error:client.generate(schema,'revise every point','source')
        assert error.value.content==content and len(requests)==1


def test_knowledge_json_decoder_still_rejects_foreign_source_ids():
    from pydantic import create_model
    from zhijiang.agents import ModelContractError
    schema=create_model('KnowledgeSelection',source_id=(Literal[2],...))
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        assert json.loads(request.content)['format']=='json'
        return httpx.Response(200,json={'message':{'content':'{"source_id":99}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','local',http_client)
        with pytest.raises(ModelContractError):client.generate(schema,'select supplied source','source 2')


@pytest.mark.parametrize('stage',['DeckDirectorRepair','DeckIllustrationPlacement','CourseOutlineRepair','ScriptCaptionSelection'])
def test_small_deck_repairs_use_native_schema_even_with_json_preference(stage):
    from pydantic import create_model
    schema=create_model(stage,selection=(str,...))
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        payload=json.loads(request.content)
        assert payload['format']==schema.model_json_schema()
        return httpx.Response(200,json={'message':{'content':'{"selection":"valid"}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','local',http_client,prefer_json=True)
        assert client.generate(schema,'choose verified fields','source').selection=='valid'
        assert client.call_metrics[-1]['decoding']=='schema'


@pytest.mark.parametrize('prefer_json',[True,False])
def test_math_task_boundary_configured_context_and_unlimited_generation(prefer_json):
    from pydantic import create_model
    schema=create_model('MathProgramDraft',reason=(str,...))
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={'thinking':{'values':[True,False],'default':True}})
        payload=json.loads(request.content)
        assert payload['options']['num_ctx']==16384
        assert payload['options']['num_predict']==-1
        assert payload['options']['num_gpu']==24
        assert payload['options']['presence_penalty']==0
        assert payload['think'] is True
        assert (payload['format']=='json') if prefer_json else isinstance(payload['format'],dict)
        user=payload['messages'][1]['content']
        assert user.index('</source_data>')<user.index('应用提供的阶段任务')<user.index('EXECUTE_THIS_TASK')
        return httpx.Response(200,json={'message':{'content':'{"reason":"valid"}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','local',http_client,prefer_json=prefer_json,num_gpu=24,context_tokens=16384)
        assert client.generate(schema,'EXECUTE_THIS_TASK','untrusted textbook question').reason=='valid'


def test_image_request_rejects_advertised_text_only_model():
    from pydantic import create_model
    schema=create_model('MathSourceReading',reason=(str,...))
    def handler(request):
        assert request.url.path=='/api/show'
        return httpx.Response(200,json={'capabilities':['completion']})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','text-only',http_client)
        with pytest.raises(GenerationError,match='vision'):client.generate(schema,'read page','text',images=[b'page'])


def test_upstream_truncation_retries_without_accepting_truncated_content():
    from pydantic import create_model
    schema=create_model('MathSourceReview',approved=(bool,...))
    budgets=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        payload=json.loads(request.content);budgets.append(payload['options']['num_predict'])
        if len(budgets)==1:return httpx.Response(200,json={'done_reason':'length','message':{'content':'{"approved":true}'}})
        return httpx.Response(200,json={'done_reason':'stop','message':{'content':'{"approved":false}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','local',http_client)
        assert client.generate(schema,'review','source').approved is False
        assert budgets==[-1,-1]


def test_upstream_truncation_recovery_remains_available_after_schema_repair():
    from pydantic import create_model
    schema=create_model('MathSourceReview',approved=(bool,...))
    budgets=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={'capabilities':[]})
        payload=json.loads(request.content);budgets.append(payload['options']['num_predict'])
        values=[{'done_reason':'stop','message':{'content':'{}'}},
                {'done_reason':'length','message':{'content':'{"approved":true}'}},
                {'done_reason':'stop','message':{'content':'{"approved":false}'}}]
        return httpx.Response(200,json=values[len(budgets)-1])
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client=OllamaClient('http://localhost:11434','mock',http,prefer_json=True)
        assert client.generate(schema,'Complete valid result.','Source.').approved is False
        assert budgets==[-1,-1,-1]


@pytest.mark.parametrize('recovers',[True,False])
def test_upstream_truncation_retry_remains_after_two_format_failures(recovers):
    from pydantic import create_model
    schema=create_model('MathSourceReview',approved=(bool,...));budgets=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        budgets.append(json.loads(request.content)['options']['num_predict'])
        count=len(budgets)
        content='{}' if count<3 or not recovers else '{"approved":false}'
        return httpx.Response(200,json={'done_reason':'length' if count==3 else 'stop',
            'message':{'content':content}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client=OllamaClient('http://localhost:11434','mock',http,prefer_json=True)
        if recovers:assert client.generate(schema,'review','source').approved is False
        else:
            with pytest.raises(GenerationError,match='不符合数据契约'):client.generate(schema,'review','source')
    assert budgets==[-1,-1,-1,-1]


@pytest.mark.parametrize('values,expected',[(['low','medium','high'],'low'),([True,False],True)])
def test_named_thinking_level_uses_advertised_controls(values,expected):
    from pydantic import create_model
    schema=create_model('MathSourceReview',approved=(bool,...))
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={'thinking':{'values':values,'default':values[1]}})
        assert json.loads(request.content)['think']==expected
        return httpx.Response(200,json={'message':{'content':'{"approved":false}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert OllamaClient('http://localhost:11434','mock',http,thinking_level='low').generate(schema,'review','source').approved is False


def test_cloud_fenced_json_is_strictly_validated_without_accepting_extra_prose():
    from pydantic import create_model
    schema=create_model('MathSourceReading',reason=(str,...))
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        return httpx.Response(200,json={'message':{'content':'```json\n{"reason":"page-read"}\n```'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','model:cloud',http_client)
        assert client.generate(schema,'read','page').reason=='page-read'
        assert client.call_metrics[-1]['format_repair']=='fenced_json'


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


@pytest.mark.parametrize('stage',['TopicSourceScope','TopicScopeReview','TeachingDraftBatch',
    'TeachingDraftRevision','SourcePictureReading','SourceFigureAlignment'])
@pytest.mark.parametrize('enabled',[True,False])
def test_topic_scope_stages_follow_semantic_thinking_configuration(stage,enabled):
    from pydantic import create_model
    schema=create_model(stage,reason=(str,...))
    def handler(request):
        if request.url.path=='/api/show':
            return httpx.Response(200,json={'thinking':{'values':[True,False],'default':False}})
        payload=json.loads(request.content)
        assert payload['think'] is enabled
        assert payload['options']['num_predict']==-1
        assert ('temperature' not in payload['options']) if enabled else payload['options']['temperature']==0
        return httpx.Response(200,json={'message':{'content':'{"reason":"原文覆盖当前范围"}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','installed-model',http_client,semantic_thinking=enabled)
        assert client.generate(schema,'核对教学范围','source').reason=='原文覆盖当前范围'


def test_ollama_cloud_omits_negative_limit_and_local_gpu_knobs():
    from pydantic import create_model
    schema=create_model('SourceFigureAlignment',reason=(str,...))
    def handler(request):
        if request.url.path=='/api/show':
            return httpx.Response(200,json={'thinking':{'values':[False,True],'default':False}})
        payload=json.loads(request.content)
        assert not {'num_predict','num_gpu','num_ctx'}&set(payload['options'])
        assert payload['think'] is True
        return httpx.Response(200,json={'message':{'content':'{"reason":"完整生成"}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://127.0.0.1:11434','example:cloud',http_client,
            semantic_thinking=True,context_tokens=16384,num_gpu=24)
        assert client.generate(schema,'读取公开来源','source').reason=='完整生成'
        assert client.call_metrics[-1]['output_token_limit'] is None


def test_rate_limit_obeys_retry_after_and_retains_full_request(monkeypatch):
    from pydantic import create_model
    waited=[];requests=[]
    monkeypatch.setattr('zhijiang.agents.time.sleep',waited.append)
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        requests.append(json.loads(request.content))
        if len(requests)==1:return httpx.Response(429,json={'error':'limited'},headers={'Retry-After':'17'})
        return httpx.Response(200,json={'message':{'content':'{"ready":true}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','example:cloud',http_client)
        assert client.generate(create_model('Ready',ready=(bool,...)),'Return the complete object','public source').ready
    assert waited==[17] and requests[0]==requests[1]
    assert client.call_metrics[0]['retry_after_seconds']==17


def test_monthly_provider_limit_is_not_retried_as_transient(monkeypatch):
    from pydantic import create_model
    from zhijiang.agents import GenerationError
    waited=[];calls=[]
    monkeypatch.setattr('zhijiang.agents.time.sleep',waited.append)
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        calls.append(request)
        return httpx.Response(429,json={'error':'you have reached your monthly usage limit'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost:11434','example:cloud',http_client)
        with pytest.raises(GenerationError,match='月度额度已用尽'):
            client.generate(create_model('Ready',ready=(bool,...)),'Return the object','public source')
    assert len(calls)==1 and not waited and client.call_metrics[-1]['error']=='upstream_monthly_usage_limit'


def test_semantic_sampler_recovers_when_runtime_thinks_despite_disabled_control():
    from pydantic import create_model
    bodies=[]
    def handler(request):
        if request.url.path=='/api/show':
            return httpx.Response(200,json={'thinking':{'values':[False,True],'default':False}})
        bodies.append(json.loads(request.content))
        return httpx.Response(200,json={'message':{'thinking':'Unexpected reasoning from this runtime.',
            'content':'{"ready":true}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://localhost','local',http_client,semantic_thinking=False)
        for stage in ['SourcePictureReading','SourceFigureAlignment']:
            assert client.generate(create_model(stage,ready=(bool,...)),'Read the source','source').ready
    assert bodies[0]['think'] is False and bodies[0]['options']['temperature']==0
    assert bodies[1]['think'] is False and 'temperature' not in bodies[1]['options']
    assert client.call_metrics[-1]['reasoning_observed']


@pytest.mark.parametrize('stage',['SourcePictureReading','SourceFigureAlignment','TeachingDraftRevision'])
def test_vision_revision_uses_simple_json_decoding_and_full_contract(stage):
    from pydantic import create_model
    schema=create_model(stage,selected=(Literal[1,2],...))
    calls=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        payload=json.loads(request.content);calls.append(payload)
        assert payload['format']=='json'
        return httpx.Response(200,json={'message':{'content':'{"selected":2}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        assert OllamaClient('http://localhost','local',http_client).generate(schema,'Use a valid ID','source').selected==2
    assert calls and 'selected' in calls[0]['messages'][0]['content']+calls[0]['messages'][1]['content']


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


@pytest.mark.parametrize('stage', ['KnowledgeSelection','TopicSourceScope','TopicScopeReview',
    'TeachingDesignDraft','TeachingScriptDraft','SourceFactsDraft','SourcePropositionsDraft',
    'SourceFactClauseSelection','VisualCoursePlan','VisualLayoutDraft','VisualSceneDraft','ReviewResult',
    'DeckDirectorDraft','DeckIllustrationPlacement','ScriptCaptionSelection','TeachingExhibitDraft',
    'MathProgramDraft','MathConstructionPatch','MathBehaviorDraft','MathRolesRepair','MathMetadataRepair',
    'CustomFutureStage'])
@pytest.mark.parametrize('context', [None, 32768])
def test_all_stages_request_unlimited_output_and_context_is_operator_controlled(stage, context):
    from pydantic import create_model
    schema=create_model(stage,complete=(str,...))
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        payload=json.loads(request.content)
        assert payload['options']['num_predict']==-1
        assert payload['options'].get('num_ctx')==context
        assert ('num_ctx' in payload['options']) is (context is not None)
        return httpx.Response(200,json={'done_reason':'stop','message':{'content':schema(complete='x'*20000).model_dump_json()},'eval_count':20000})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client=OllamaClient('http://localhost:11434','mock',http,context_tokens=context)
        assert len(client.generate(schema,'return complete result','source').complete)==20000
        assert client.call_metrics[-1]['output_token_limit']==-1


def test_context_configuration_has_no_project_upper_clamp_and_env_precedence(tmp_path,monkeypatch):
    p=tmp_path/'.env.local';p.write_text('ZHIJIANG_OLLAMA_CONTEXT_TOKENS=32768\n',encoding='utf-8')
    monkeypatch.setenv('ZHIJIANG_ENV_FILE',str(p))
    monkeypatch.delenv('ZHIJIANG_OLLAMA_CONTEXT_TOKENS',raising=False)
    assert Settings.from_env().ollama_context_tokens==32768
    monkeypatch.setenv('ZHIJIANG_OLLAMA_CONTEXT_TOKENS','131072')
    assert Settings.from_env().ollama_context_tokens==131072
    monkeypatch.setenv('ZHIJIANG_OLLAMA_CONTEXT_TOKENS','')
    assert Settings.from_env().ollama_context_tokens is None


@pytest.mark.parametrize('invalid', [0,-1,True,1.5])
def test_invalid_memory_context_is_rejected(invalid):
    with pytest.raises(ValueError,match='上下文大小必须为正整数'):
        OllamaClient('http://localhost:11434','mock',context_tokens=invalid)


@pytest.mark.parametrize('recovers',[True,False])
def test_compatible_service_truncation_does_not_approve_even_closed_json(recovers):
    from pydantic import create_model
    from zhijiang.agents import OpenAICompatibleClient
    schema=create_model('Review',approved=(bool,...));requests=[]
    def handler(request):
        payload=json.loads(request.content);requests.append(payload)
        assert not any(key in payload for key in ['max_tokens','max_completion_tokens','max_output_tokens'])
        assert request.extensions['timeout']['read'] is None
        complete=recovers and len(requests)==2
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop' if complete else 'length',
            'message':{'content':'{"approved":false}' if complete else '{"approved":true}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client=OpenAICompatibleClient('https://model.invalid/v1','secret','model',http)
        if recovers:assert client.generate(schema,'review','source').approved is False
        else:
            with pytest.raises(GenerationError,match='服务返回截断结果'):client.generate(schema,'review','source')
    assert len(requests)==2


@pytest.mark.parametrize('streaming', [False, True])
def test_inference_has_no_read_or_fifteen_minute_deadline(monkeypatch, streaming):
    from pydantic import create_model
    import zhijiang.agents as agents
    schema=create_model('TopicSourceScope',complete=(bool,...))
    elapsed=iter([0,1801,1802,1803])
    monkeypatch.setattr(agents.time,'monotonic',lambda:next(elapsed,1803))
    updates=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        assert request.extensions['timeout']['read'] is None
        body=json.loads(request.content)
        assert body['stream'] is streaming and body['options']['num_predict']==-1
        result={'done':True,'done_reason':'stop','message':{'content':'{"complete":true}'}}
        if streaming:
            return httpx.Response(200,content=json.dumps(result)+'\n')
        return httpx.Response(200,json=result)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client=OllamaClient('http://localhost:11434','mock',http,
            progress=(lambda *args:updates.append(args)) if streaming else None)
        assert client.generate(schema,'Return a complete object.','Source.').complete is True
    if streaming:assert updates[-1][1]>=1801


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
            assert 'num_ctx' not in body['options'] and body['options']['num_predict']==-1
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
        assert body['think'] is True and body['options']['num_predict']==-1
        return httpx.Response(200,json={'message':{'content':'{"approved":false,"issues":["definition mismatch"]}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        review=OllamaClient('http://127.0.0.1:11434','qwen3:4b',http_client).generate(TeachingSourceReview,'核对定义','原文材料')
        assert not review.approved


@pytest.mark.parametrize('stage',['DeckClosingReview','DeckRouteReview','SlideSourcePropositionsDraft',
    'TeachingExhibitIntent','TeachingExhibitDraft','TeachingExhibitReview','TeachingRelationSelection',
    'TeachingArithmeticRepair','TeachingArithmeticTarget'])
def test_compact_story_stages_use_bounded_native_schema(stage):
    from pydantic import create_model
    schema=create_model(stage,point_1=(bool,...),issues=(str,''))
    def handler(request):
        if request.url.path=='/api/show':
            return httpx.Response(200,json={'thinking':{'values':[True,False],'default':False}})
        body=json.loads(request.content)
        assert body['think'] is False and isinstance(body['format'],dict)
        assert body['options']['num_predict']==-1
        return httpx.Response(200,json={'message':{'content':'{"point_1":true,"issues":""}'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=OllamaClient('http://127.0.0.1:11434','local',http_client,semantic_thinking=True,prefer_json=True)
        assert client.generate(schema,'审核结尾','完整来源').point_1


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


def test_persistent_upstream_truncation_identifies_service_and_keeps_incomplete_result_unapproved():
    from zhijiang.teaching_design import TeachingSourceReview
    chats=[]
    def handler(request):
        if request.url.path == '/api/show':
            return httpx.Response(200,json={})
        assert json.loads(request.content)['options']['num_predict']==-1
        chats.append(request)
        return httpx.Response(200,json={'done_reason':'length','message':{'content':''}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(GenerationError,match='Ollama 服务仍返回截断结果'):
            OllamaClient('http://localhost:11434','model',http_client).generate(TeachingSourceReview,'核对','资料')
    assert len(chats)==2


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


@pytest.mark.parametrize('status,count',[(401,1),(429,3),(502,3),(503,3),(504,3)])
def test_ollama_http_repair_is_bounded_and_does_not_retry_auth(status,count,monkeypatch):
    pauses=[];monkeypatch.setattr('zhijiang.agents.time.sleep',pauses.append)
    calls=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        calls.append(request);return httpx.Response(status,json={'error':'unavailable'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(GenerationError,match='HTTP '+str(status)):
            OllamaClient('http://localhost:11434','model',http_client).generate(KnowledgeBundle,'提取','资料')
    assert len(calls)==count
    assert pauses==([2,5] if count==3 else [])


def test_transient_cloud_502_preserves_request_and_recovers(sample_pdf,monkeypatch):
    monkeypatch.setattr('zhijiang.agents.time.sleep',lambda seconds:None)
    bundle=DemoAgents().extract_knowledge(read_pdf(sample_pdf,'sample.pdf'));bodies=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        bodies.append(request.content)
        if len(bodies)==1:return httpx.Response(502,json={'error':'temporary'})
        return httpx.Response(200,json={'message':{'content':bundle.model_dump_json()}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result=OllamaClient('http://localhost:11434','cloud',http_client).generate(KnowledgeBundle,'提取','资料')
    assert result==bundle and len(bodies)==2 and bodies[0]==bodies[1]


@pytest.mark.parametrize('recovers',[True,False])
def test_eof_without_done_retries_same_payload_bounded_never_accepts_partial(recovers,monkeypatch):
    from pydantic import create_model
    monkeypatch.setattr('zhijiang.agents.time.sleep',lambda seconds:None)
    schema=create_model('MathSourceReview',approved=(bool,...));bodies=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        bodies.append(request.content)
        chunk={'message':{'content':'{"approved":true}'},'done':False}
        if recovers and len(bodies)==2:chunk={'message':{'content':'{"approved":false}'},'done':True}
        return httpx.Response(200,content=json.dumps(chunk)+'\n')
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client=OllamaClient('http://localhost:11434','cloud',http,progress=lambda *args:None)
        if recovers:assert client.generate(schema,'review','source').approved is False
        else:
            with pytest.raises(GenerationError,match='输出中断'):client.generate(schema,'review','source')
    assert len(bodies)==(2 if recovers else 3) and len(set(bodies))==1


def test_math_schema_repair_uses_third_attempt_and_one_based_step_feedback():
    from pydantic import create_model,Field
    from typing import Annotated
    schema=create_model('MathBehaviorDraft',steps=(list[Annotated[int,Field(ge=1,le=10)]],...))
    calls=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        body=json.loads(request.content);calls.append(body)
        if len(calls)>1:assert '"minimum": 1' in body['messages'][-1]['content']
        return httpx.Response(200,json={'message':{'content':json.dumps({'steps':[1 if len(calls)==3 else 0]})}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert OllamaClient('http://localhost:11434','cloud',http).generate(schema,'steps','source').steps==[1]
    assert len(calls)==3


def test_math_typed_measurement_repair_provides_actual_valid_point_ids():
    from zhijiang.math_behavior import behavior_schema
    from tests.test_math_construction import program
    p=program([{'id':'f','op':'function','expr':['exp(x)']},
        {'id':'origin','op':'point','expr':['0','0'],'visible':False},
        {'id':'moving','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(moving)','rhs':'value(f,u)'}])
    schema=behavior_schema(p,{1});calls=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={})
        body=json.loads(request.content);calls.append(body)
        if len(calls)>1:
            hint=body['messages'][-1]['content']
            assert 'moving' in hint and 'origin' in hint and 'enum' in hint
        point='invented' if len(calls)==1 else 'moving'
        data={'operations':[{'narration':'观察函数上的运动点与实际输出的对应关系。','changes':{'u':v}}
            for v in [.3,.6,.8]],'claims':[{'source_id':1,
                'left':{'terms':[{'kind':'ycoord','point':point}]},
                'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]}
        return httpx.Response(200,json={'message':{'content':json.dumps(data)}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        result=OllamaClient('http://localhost:11434','cloud',http).generate(schema,'类型测量','实际对象')
    assert result.claims[0].left.terms[0].point=='moving' and len(calls)==2


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
