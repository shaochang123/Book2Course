import json
import pytest

from zhijiang.draft_generation import build_draft_lesson
from zhijiang.models import VoiceMode
from zhijiang.agents import GenerationError
from test_draft_generation import DraftClient,inputs


def test_revision_contract_cannot_silently_omit_teaching_content_or_visual_decisions():
    from zhijiang.draft_source_repair import RevisedPage
    schema=RevisedPage.model_json_schema()
    assert {'render_kind','graphic_group','figure_page','figure_box'}<=set(schema['required'])
    item=schema['$defs']['SourceRevisedVisualItem']
    assert 'caption' in item['required'] and item['properties']['caption']['minLength']>=1


class RevisingClient(DraftClient):
    def generate(self,schema,instruction,material,**kwargs):
        if schema.__name__!='TeachingDraftRevision':return super().generate(schema,instruction,material)
        payload=json.loads(material);self.calls.append({'revision':payload})
        assert '完整教材页' in instruction and '不能执行' in instruction
        pages=[]
        for page in payload['draft']['pages']:
            pages.append({**page,'title':'学习定义与适用条件','render_kind':'story','graphic_group':'',
                'context_is_condition':False,'issues':['标题须包含定义的条件'], 'figure_page':0,'figure_box':[]})
        return schema.model_validate({**payload['draft'],'pages':pages})


def test_revision_retains_every_source_identity_and_raw_draft(tmp_path):
    document,bundle=inputs(2);client=RevisingClient()
    options=dict(template_id='paper',use_illustrations=False,folder=tmp_path,progress=lambda *a:None,repair_sources=True)
    result=build_draft_lesson(client,bundle,document,'',VoiceMode.SYSTEM,**options)
    assert len(result.segments)==2
    assert result.segments[0].title=='学习定义与适用条件'
    assert [s.evidence for s in result.segments]==[p.evidence for p in bundle.points]
    raw=json.loads((tmp_path/'batch-001.json').read_text(encoding='utf-8'))
    assert 'title' not in raw['data']['pages'][0]
    assert result.animation_report['content_review']=='same_model_revision'
    calls=len(client.calls)
    again=build_draft_lesson(client,bundle,document,'',VoiceMode.SYSTEM,**options)
    assert len(client.calls)==calls and again.model_dump()==result.model_dump()


def test_optional_revision_service_failure_keeps_the_full_course(tmp_path):
    class Offline(DraftClient):
        def generate(self,schema,instruction,material):
            if schema.__name__=='TeachingDraftRevision':raise GenerationError('修订服务断开')
            return super().generate(schema,instruction,material)
    document,bundle=inputs(2)
    result=build_draft_lesson(Offline(),bundle,document,'',VoiceMode.SYSTEM,template_id='paper',
        use_illustrations=False,folder=tmp_path,progress=lambda *a:None,repair_sources=True)
    assert len(result.segments)==2
    assert any(w['stage']=='source_revision' for w in result.animation_report['warnings'])


def test_blank_table_is_not_rendered_as_empty_value_cells():
    from zhijiang.draft_generation import normalise_visual
    from zhijiang.slide_story import SlideVisualDraft
    visual=SlideVisualDraft(representation='table',items=[
        {'label':'完整概念名称','caption':'','sentence_id':1},
        {'label':'另一个实际概念','caption':'','sentence_id':2}])
    warnings=[];result=normalise_visual(visual,warnings.append)
    assert result.representation=='comparison' and len(result.items)==2 and warnings


def test_complete_english_example_can_survive_the_diagram_contract():
    from zhijiang.slide_story import SlideVisualDraft
    sentence='The children working in the garden are watering the flowers.'
    visual=SlideVisualDraft(representation='comparison',items=[
        {'label':sentence,'caption':'完整主语与谓语，不截断例句','sentence_id':1}])
    assert visual.items[0].label==sentence


def test_partial_revision_repairs_only_missing_pages_without_copying_blank_visuals(tmp_path):
    from zhijiang.agents import ModelContractError
    from pydantic import ValidationError
    class Partial(RevisingClient):
        def __init__(self):super().__init__();self.repairs=[]
        def generate(self,schema,instruction,material,**kwargs):
            if schema.__name__!='TeachingDraftRevision':return super().generate(schema,instruction,material)
            data=json.loads(material);ids=[p['source_id'] for p in data['source']['points']]
            if len(ids)>1:
                page={**data['draft']['pages'][0],'title':'完整定义与条件','render_kind':'story','graphic_group':'',
                    'context_is_condition':False,'figure_page':0,'figure_box':[]}
                response={**data['draft'],'pages':[page]}
                with pytest.raises(ValidationError):schema.model_validate(response)
                raise ModelContractError('批量编号不完整',content=json.dumps(response),schema=schema)
            self.repairs.extend(ids)
            assert 'visual' not in data['draft']['pages'][0]
            page={**data['draft']['pages'][0],'title':'单独补齐的定义与条件','render_kind':'story','graphic_group':'',
                'context_is_condition':False,'figure_page':0,'figure_box':[],
                'visual':{'representation':'key_idea','items':[{'label':'定义条件',
                    'caption':'性能随经验提高','sentence_id':1}]}}
            return schema.model_validate({**data['draft'],'pages':[page]})
    document,bundle=inputs(3);client=Partial()
    lesson=build_draft_lesson(client,bundle,document,'',VoiceMode.SYSTEM,template_id='paper',
        use_illustrations=False,folder=tmp_path,progress=lambda *args:None,repair_sources=True)
    assert client.repairs==[2,3]
    assert [s.evidence for s in lesson.segments]==[p.evidence for p in bundle.points]
    assert all('caption' in v['visual']['items'][0] and v['visual']['items'][0]['caption']
        for v in lesson.deck_plan['visual_story']['visuals'].values())
    assert lesson.segments[1].title=='单独补齐的定义与条件'


def test_failed_single_page_repair_preserves_other_successful_revisions(tmp_path):
    from zhijiang.agents import ModelContractError
    class Mixed(RevisingClient):
        def generate(self,schema,instruction,material,**kwargs):
            if schema.__name__!='TeachingDraftRevision':return super().generate(schema,instruction,material)
            data=json.loads(material);ids=[p['source_id'] for p in data['source']['points']]
            if len(ids)>1:
                page={**data['draft']['pages'][0],'title':'保留成功修订','render_kind':'story','graphic_group':'',
                    'context_is_condition':False,'figure_page':0,'figure_box':[]}
                raise ModelContractError('missing',content=json.dumps({**data['draft'],'pages':[page]}))
            raise GenerationError('单页服务暂时不可用')
    document,bundle=inputs(2)
    lesson=build_draft_lesson(Mixed(),bundle,document,'',VoiceMode.SYSTEM,template_id='paper',
        use_illustrations=False,folder=tmp_path,progress=lambda *args:None,repair_sources=True)
    assert len(lesson.segments)==2 and lesson.segments[0].title=='保留成功修订'
    assert lesson.segments[1].evidence==bundle.points[1].evidence
    assert any(w['segment_id']==2 and '其他已修订页继续使用' in w['message'] for w in lesson.animation_report['warnings'])


def test_no_successful_page_cannot_be_reported_as_a_completed_revision(tmp_path):
    from zhijiang.agents import ModelContractError
    class Unavailable(DraftClient):
        def generate(self,schema,instruction,material,**kwargs):
            if schema.__name__=='TeachingDraftRevision':
                raise ModelContractError('not a complete response',content='{"pages":[')
            return super().generate(schema,instruction,material)
    document,bundle=inputs(2)
    lesson=build_draft_lesson(Unavailable(),bundle,document,'',VoiceMode.SYSTEM,template_id='paper',
        use_illustrations=False,folder=tmp_path,progress=lambda *args:None,repair_sources=True)
    assert len(lesson.segments)==2 and lesson.animation_report['content_review']=='revision_unavailable'
    assert not list(tmp_path.glob('revision-*.json'))


def test_revision_can_rebuild_a_point_already_missing_from_initial_draft(tmp_path):
    from zhijiang.agents import ModelContractError
    class Missing(DraftClient):
        def generate(self,schema,instruction,material,**kwargs):
            if schema.__name__!='TeachingDraftRevision':
                result=super().generate(schema,instruction,material)
                if hasattr(result,'pages'):result.pages=result.pages[:1]
                return result
            data=json.loads(material);ids=[p['source_id'] for p in data['source']['points']]
            if len(ids)>1:
                page={**data['draft']['pages'][0],'title':'来源完整条件','render_kind':'story','graphic_group':'',
                    'context_is_condition':False,'figure_page':0,'figure_box':[]}
                raise ModelContractError('missing page',content=json.dumps({**data['draft'],'pages':[page]}))
            assert ids==[2] and '性能' in data['source']['source_pages'][0]['text']
            page={**data['draft']['pages'][0],'title':'从来源重建遗漏页','render_kind':'story','graphic_group':'',
                'context_is_condition':False,'figure_page':0,'figure_box':[],
                'visual':{'representation':'key_idea','items':[{
                    'label':'定义的条件','caption':'性能随经验提高','sentence_id':1}]}}
            return schema.model_validate({**data['draft'],'pages':[page]})
    document,bundle=inputs(2)
    lesson=build_draft_lesson(Missing(),bundle,document,'',VoiceMode.SYSTEM,template_id='paper',
        use_illustrations=False,folder=tmp_path,progress=lambda *args:None,repair_sources=True)
    assert len(lesson.segments)==2 and lesson.segments[1].title=='从来源重建遗漏页'


def test_partial_page_salvage_rejects_truncated_json_and_duplicate_identity():
    from zhijiang.draft_source_repair import _valid_partial_pages,RevisedPage
    page={'source_id':1,'title':'完整对象与条件','narration':'我们保留来源里的实际对象和适用条件，以便正确理解。',
        'bullets':['来源条件'],'visual':{'representation':'key_idea',
        'items':[{'label':'来源对象','caption':'实际适用条件','sentence_id':1}]},
        'render_kind':'story','graphic_group':'','context_is_condition':False,'figure_page':0,'figure_box':[]}
    content=json.dumps({'pages':[page]})
    assert set(_valid_partial_pages(content,RevisedPage))=={1}
    assert not _valid_partial_pages(content[:-1],RevisedPage)
    assert not _valid_partial_pages(json.dumps({'pages':[page,page]}),RevisedPage)


@pytest.mark.parametrize('binding',['item','link','context'])
def test_source_revision_binding_cannot_reference_a_different_pages_sentence(binding):
    from zhijiang.draft_source_repair import RevisedPage
    from pydantic import ValidationError
    visual={'representation':'process','items':[
        {'label':'来源对象','caption':'实际适用条件','sentence_id':1},
        {'label':'变化结果','caption':'成立条件不省略','sentence_id':1}], 'links':[]}
    if binding=='item':visual['items'][0]['sentence_id']=4
    if binding=='link':visual['links']=[{'source':1,'target':2,'label':'实际关系','sentence_id':4}]
    if binding=='context':visual.update(context='来源条件必须成立',context_sentence_id=4)
    with pytest.raises(ValidationError,match='本页口播'):
        RevisedPage(source_id=1,title='来源对象与成立条件',narration='我们保留来源对象和成立条件，以便正确理解。',
            bullets=['来源条件'],visual=visual,render_kind='story',graphic_group='',
            context_is_condition=True,figure_page=0,figure_box=[])
