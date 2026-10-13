import pytest
from types import SimpleNamespace
from zhijiang.models import SourceDocument,PageText
from zhijiang.construction_intent import read_construction_intent


def document(text='This source describes a sequence of attention, rather than moving physical objects.'):
    return SourceDocument(filename='filename-must-not-decide-routing.pdf',pages=[PageText(page=1,text=text)])


def test_routing_uses_complete_source_and_reuses_only_matching_source_cache(tmp_path):
    calls=[]
    class Client:
        model='local';base_url='http://localhost';semantic_thinking=False
        def generate(self,schema,instruction,material):
            calls.append(material)
            assert 'filename-must-not-decide-routing.pdf' not in material
            return schema(relation_kind='symbolic_sequence',source_ids=[1],
                          observation='原文说明注意力的顺序，不是物理位置的变化。')
    requests=[{'title':'原文主题','narration':'解释来源中的先后顺序。'}]
    source=document();first=read_construction_intent(Client(),source,requests,tmp_path)
    assert read_construction_intent(Client(),source,requests,tmp_path).model_dump()==first.model_dump() and len(calls)==1
    read_construction_intent(Client(),document(source.pages[0].text+' Another source condition.'),requests,tmp_path)
    assert len(calls)==2


@pytest.mark.parametrize('kind',['symbolic_sequence','concept_comparison','quantitative','physical_process','uncertain'])
def test_only_clear_symbolic_content_routes_to_diagrams_without_losing_narration(tmp_path,monkeypatch,kind):
    import zhijiang.automatic_construction as automatic
    import zhijiang.construction_intent as routing
    import zhijiang.visual_planning as planning
    from zhijiang.agents import GenerationError
    from test_deck_planning import example_lesson
    monkeypatch.setattr(planning,'visual_capabilities',lambda:{'geometry_ready':True})
    monkeypatch.setattr(routing,'read_construction_intent',lambda *a,**k:SimpleNamespace(
        relation_kind=kind,observation='根据原文对象、关系与变化判断表达类型。'))
    calls=[]
    def construct(*a,**k):calls.append(kind);raise GenerationError('保留原课程的可选演示失败')
    monkeypatch.setattr(automatic,'build_scene',construct)
    lesson=example_lesson(2);original=[s.model_dump() for s in lesson.segments]
    pdf=tmp_path/'source.pdf';pdf.write_bytes(b'local source placeholder')
    automatic.enrich_constructions(lesson,document(),object(),[{'segment_id':1,'page':1,'graphic_group':'source group'}],
        folder=tmp_path,pdf_path=pdf,progress=lambda *a:None)
    assert [s.model_dump() for s in lesson.segments]==original
    assert bool(calls)==(kind in {'quantitative','physical_process','uncertain'})
    if not calls:assert lesson.animation_report['construction_routing'][0]['renderer']=='teaching_diagram'


def test_routing_cannot_accept_foreign_source_identity(tmp_path):
    class Client:
        def generate(self,schema,*a):
            return schema(relation_kind='quantitative',source_ids=[99],observation='此编号不属于任何给定原文，必须拒绝。')
    with pytest.raises(ValueError):read_construction_intent(Client(),document(),[],tmp_path)
    assert not (tmp_path/'intent.json').exists()
