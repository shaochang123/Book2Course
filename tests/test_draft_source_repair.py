import json

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
