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


@pytest.mark.parametrize('heading',['omitted','course_title'])
def test_complete_revision_keeps_topic_headings_without_extra_calls(tmp_path,heading):
    class MetadataClient(DraftClient):
        def __init__(self):super().__init__();self.revisions=0
        def generate(self,schema,instruction,material,**kwargs):
            if schema.__name__!='TeachingDraftRevision':return super().generate(schema,instruction,material)
            self.revisions+=1;payload=json.loads(material);pages=[]
            for original in payload['draft']['pages']:
                page={**original,'render_kind':'story','graphic_group':'',
                    'context_is_condition':False,'figure_page':0,'figure_box':[]}
                if heading=='course_title':page['title']=payload['draft']['title']
                pages.append(page)
            return schema.model_validate({**payload['draft'],'pages':pages})
    document,bundle=inputs(4);client=MetadataClient()
    lesson=build_draft_lesson(client,bundle,document,'',VoiceMode.SYSTEM,
        template_id='paper',use_illustrations=False,folder=tmp_path,progress=lambda *a:None,repair_sources=True)
    assert client.revisions==1
    assert [s.title for s in lesson.segments]==[p.title for p in bundle.points]
    assert not lesson.animation_report['warnings']
    assert all('性能随经验提高' in s.narration for s in lesson.segments)


def test_missing_heading_cannot_hide_invalid_source_or_sentence_binding():
    from pydantic import ValidationError,create_model
    from typing import Literal
    from zhijiang.draft_source_repair import RevisedPage
    page={'source_id':1,'narration':'我们保留来源中的对象和必要条件，以便理解这一关系。',
        'bullets':['保留对象与条件'],'visual':{'representation':'key_idea','items':[
            {'label':'条件','caption':'当前关系的适用前提','sentence_id':1}]},
        'render_kind':'story','graphic_group':'','context_is_condition':False,'figure_page':0,'figure_box':[]}
    schema=create_model('ScopedPage',__base__=RevisedPage,source_id=(Literal[1],...))
    assert schema.model_validate(page).title is None
    with pytest.raises(ValidationError):schema.model_validate({**page,'source_id':2})
    page['visual']['items'][0]['sentence_id']=8
    with pytest.raises(ValidationError):schema.model_validate(page)


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


@pytest.mark.parametrize('root_flag',[False,None])
def test_redundant_or_misplaced_context_flag_does_not_discard_valid_content(root_flag):
    from zhijiang.draft_source_repair import RevisedPage
    page={'source_id':1,'title':'完整对象与适用条件','narration':'我们保留实际对象和适用条件，以便准确理解这段资料。',
        'bullets':['保留适用条件'],'visual':{'representation':'key_idea','context_is_condition':False,
        'items':[{'label':'适用条件','caption':'实际条件完整保留','sentence_id':1}]},
        'render_kind':'story','graphic_group':'','figure_page':0,'figure_box':[]}
    if root_flag is not None:page['context_is_condition']=root_flag
    repaired=RevisedPage.model_validate(page)
    assert not repaired.context_is_condition and repaired.visual.items[0].caption=='实际条件完整保留'
    assert 'context_is_condition' not in repaired.visual.model_dump()
    page['context_is_condition']=True
    with pytest.raises(ValueError,match='冲突'):RevisedPage.model_validate(page)


def test_category_association_is_not_a_causal_arrow_across_domains():
    from zhijiang.draft_generation import normalise_visual
    from zhijiang.slide_story import SlideVisualDraft
    for first,second,parent in [('狮子','老虎','哺乳动物'),('存款','贷款','银行业务')]:
        visual=SlideVisualDraft(representation='relationship',items=[
            {'label':first,'caption':'第一个对象','sentence_id':1},
            {'label':second,'caption':'第二个对象','sentence_id':1}],
            links=[{'source':1,'target':2,'label':'都属于'+parent,'sentence_id':1}])
        warnings=[];result=normalise_visual(visual,warnings.append)
        assert result.links[0].kind=='undirected' and warnings
    visual.links[0].label='产生'
    assert normalise_visual(visual,lambda _:None).links[0].kind=='directed'


def test_bindings_repair_uses_numbered_existing_speech_and_preserves_content():
    from zhijiang.draft_source_repair import RevisedPage,_revision_schema,_repair_sentence_bindings
    narration='物质顺浓度梯度移动，不消耗细胞提供的能量。这里用一个具体对象解释这个条件。'
    page={'source_id':1,'title':'对象与适用条件','narration':narration,'bullets':['保留适用条件'],
        'visual':{'representation':'comparison','items':[
            {'label':'实际对象','caption':'沿浓度梯度移动','sentence_id':5},
            {'label':'能量条件','caption':'不消耗细胞能量','sentence_id':6}], 'links':[]},
        'render_kind':'story','graphic_group':'','context_is_condition':False,'figure_page':0,'figure_box':[]}
    response={'title':'对象与适用条件','objective':'保留来源中的实际对象和完整条件。','pages':[page]}
    class Binding:
        def generate(self,schema,instruction,material):
            data=json.loads(material)
            assert [s['id'] for s in data['sentences']]==[1,2]
            assert data['sentences'][0]['text']=='物质顺浓度梯度移动，不消耗细胞提供的能量'
            return schema(item_1=1,item_2=1,context_sentence_id=None)
    result=_repair_sentence_bindings(Binding(),json.dumps(response),_revision_schema(RevisedPage,(1,)))
    assert result.pages[0].narration==narration
    assert [i.sentence_id for i in result.pages[0].visual.items]==[1,1]
    assert [i.caption for i in result.pages[0].visual.items]==[i['caption'] for i in page['visual']['items']]


def test_binding_repair_cannot_hide_an_invalid_source_identity():
    from zhijiang.draft_source_repair import RevisedPage,_revision_schema,_repair_sentence_bindings
    class Never:
        def generate(self,*args,**kwargs):raise AssertionError('Invalid source must not reach model')
    response={'title':'对象与适用条件','objective':'保留来源中的实际对象和完整条件。','pages':[{
        'source_id':4,'title':'不属于本次请求的编号','narration':'实际来源对象的讲解必须属于本次请求的知识点。',
        'bullets':['来源编号不改写'],'visual':{'representation':'key_idea',
        'items':[{'label':'实际对象','caption':'完整适用条件','sentence_id':5}]},
        'render_kind':'story','graphic_group':'','context_is_condition':False,'figure_page':0,'figure_box':[]}]}
    from pydantic import create_model,Field
    from typing import Literal
    bound=create_model('Bound',__base__=RevisedPage,source_id=(Literal[1],Field()))
    with pytest.raises(ValueError):_repair_sentence_bindings(Never(),json.dumps(response),_revision_schema(bound,(1,)))
