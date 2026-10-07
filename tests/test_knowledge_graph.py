"""Regressions for source graphs rather than topic-specific drawing templates."""
import json

import pytest

from zhijiang.models import TeachingDiagram,TeachingSourceFact,Evidence,LessonSegment
from zhijiang.teaching_design import (structure_schema,resolve_design,validate_diagram,
    bind_script_focus,compose_script,complete_relation_focus,script_schema,TeachingDesignError)
from zhijiang.teaching_graph import knowledge_graph,graph_layers,design_digest
from zhijiang.teaching_layout import layout_diagram


@pytest.mark.parametrize('label',['our sense of self is not','some internal source of',
    'the happiness you will','number of weeks an','三种材料和','十五元的费用、二十元的','we','我们','那组对象','这些记录'])
def test_graph_rejects_dangling_phrases_and_unresolved_pronouns(label):
    from zhijiang.teaching_graph import _checked_propositions
    fact={'id':1,'source_id':1,'statement':f'对象包括{label}。','source_quote':f'对象包括{label}。'}
    kept,rejected=_checked_propositions([{'subject':'对象','predicate':'包括','object':label,'fact_ids':[1]}],[fact])
    assert not kept and rejected


def test_identity_relation_does_not_turn_an_object_into_its_property():
    from zhijiang.teaching_graph import _checked_propositions
    facts=[{'id':1,'statement':'这是设备运行所产生的维护费用。','source_quote':'This is the maintenance cost for operating the equipment.'},
           {'id':2,'statement':'维护费用是支出的一种。','source_quote':'The maintenance cost is a type of expenditure.'}]
    drafts=[{'subject':'设备运行','predicate':'是','object':'维护费用','fact_ids':[1],
             'subject_source_term':'operating the equipment','object_source_term':'maintenance cost'},
            {'subject':'维护费用','predicate':'是','object':'支出','fact_ids':[2],
             'subject_source_term':'maintenance cost','object_source_term':'expenditure'}]
    kept,rejected=_checked_propositions(drafts,facts)
    assert len(kept)==len(rejected)==1 and kept[0]['subject']=='维护费用'


@pytest.mark.parametrize('predicate',['是...费用','是…费用','是维护费用'])
def test_predicate_cannot_hide_false_identity_in_a_long_label(predicate):
    from zhijiang.teaching_graph import _checked_propositions
    fact={'id':1,'statement':'这是设备运行所产生的维护费用。','source_quote':'This is the maintenance cost for operating the equipment.'}
    kept,rejected=_checked_propositions([{'subject':'设备运行','predicate':predicate,'object':'维护费用','fact_ids':[1],
        'subject_source_term':'operating the equipment','object_source_term':'maintenance cost'}],[fact])
    assert not kept and rejected


def test_word_wrapping_preserves_complete_words_and_cjk_text():
    from zhijiang.teaching_layout import wrap_label
    for value in ['how we look to others','internal source of identity','完整的中文条件与结果']:
        lines=wrap_label(value,7).splitlines()
        assert ''.join(lines).replace(' ','')==value.replace(' ','')
        if value.isascii():
            assert all(word in value.split() for line in lines for word in line.split())


def test_wide_horizontal_branch_label_stays_near_its_own_arrow():
    from types import SimpleNamespace as Item
    d=Item(source_asset='',representation='relationship',
        nodes=[Item(id=i,label='当前对象') for i in range(1,6)],
        relations=[Item(id=i,source=a,target=b,directed=True,label=label,condition='')
            for i,a,b,label in [(1,1,2,'should be part of'),(2,3,4,'focuses on'),(3,3,5,'represents')]])
    _,edges=layout_diagram(d)
    horizontal=edges[3]
    assert abs(horizontal['start'][1]-horizontal['end'][1])<1e-6
    assert abs(horizontal['label'][1]-horizontal['start'][1])<.5
    diagonal=edges[2]
    assert abs(horizontal['label'][1]-(diagonal['start'][1]+diagonal['end'][1])/2)>.5


def test_topic_citation_cannot_be_replaced_by_an_adjacent_positive_rule():
    from tests.test_teaching_design import diagram
    from zhijiang.teaching_design import preserve_topic_focus,cached_topic_focus_covered
    from types import SimpleNamespace
    d=diagram();quote='如果记录缺少必要字段，本次检查不能通过，必须保留这个失败的来源事实。'
    facts=[{'id':1,'source_id':1,'source_quote':d.nodes[0].source_quote,'statement':'控制信号属于当前原文中的对象。'}]
    facts.append({'id':99,'source_id':99,'source_quote':quote,'statement':quote})
    with pytest.raises(TeachingDesignError,match='原始引文'):
        preserve_topic_focus(d,facts,'失败情境',quote)
    scene=SimpleNamespace(diagram=d,evidence=Evidence(page=1,quote=quote))
    assert not cached_topic_focus_covered(scene,facts,'失败情境')
    d.representation='source_figure';d.relations=[]
    assert preserve_topic_focus(d,facts,'失败情境',quote)==[99]
    assert any(node.source_quote==quote for node in d.nodes)


def test_translated_page_note_anchors_the_quote_instead_of_a_guessed_field():
    from tests.test_teaching_design import diagram
    from zhijiang.teaching_design import bind_annotation_anchors
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:2]
    quote='Course information includes several attributes, including the identifier CourseNo.'
    d.nodes[0].label='课程信息';d.nodes[0].source_quote=quote;d.nodes[0].source_term='CourseNo'
    d.nodes[1].label='CourseNo';d.nodes[1].source_quote=quote;d.nodes[1].source_term='information'
    repairs=[];bind_annotation_anchors(d,repairs)
    assert d.nodes[0].source_term=='' and d.nodes[0].source_quote==quote
    assert d.nodes[1].source_term=='CourseNo' and len(repairs)==2
    d.representation='relationship';d.nodes[0].source_term='original term'
    bind_annotation_anchors(d,repairs)
    assert d.nodes[0].source_term=='original term'


def test_scaled_decimal_svg_font_renders_a_real_png(tmp_path):
    from PIL import Image,ImageChops
    from zhijiang.math_media import render_summary_png
    source=tmp_path/'summary.svg';output=tmp_path/'summary.png'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">'
        '<rect width="1200" height="675" fill="#081623"/>'
        '<text x="600" y="300" text-anchor="middle" font-size="20.898550724637683" fill="#FFFFFF">Complete label</text></svg>')
    render_summary_png(source,output)
    with Image.open(output) as image:
        assert image.size==(1200,675)
        assert ImageChops.difference(image.convert('RGB'),Image.new('RGB',image.size,'#081623')).getbbox()


@pytest.mark.parametrize('left,right,action',[
    ('审核人员','申请材料','检查'),('装配设备','待加工零件','接收'),('采样人员','观测记录','读取')])
def test_multisentence_graph_generalizes_entities_and_keeps_provenance(left,right,action):
    first=f'首先由{left}{action}{right}，保留来源中的适用条件。'
    second=f'随后将{right}交给复核环节，复核仅检查所记录的信息。'
    spans={1:first,2:second}
    facts=[{'id':i,'source_id':i,'source_quote':text,'statement':text} for i,text in spans.items()]
    schema=structure_schema(spans,facts=facts)
    value={'representation':'process','rationale':'依据来源明确的初始与随后操作设计关系追踪。','question':'怎样追踪这段操作？',
        'nodes':[{'id':2,'label':right,'source_id':2,'source_term':right},
                 {'id':1,'label':left,'source_id':1,'source_term':left}],
        'relations':[{'id':1,'source':1,'target':2,'label':'按原文步骤传递','source_fact_id':1,'supporting_fact_ids':[2]}]}
    draft=resolve_design(schema.model_validate(value),spans,facts=facts)
    draft.source_facts=[TeachingSourceFact.model_validate(f) for f in facts]
    script=script_schema(draft,facts).model_validate({'steps':[{'fact_id':1},{'fact_id':2}]})
    script=bind_script_focus(script,draft,facts);complete_relation_focus(script,draft.relations)
    draft.steps=compose_script(script,facts)
    assert validate_diagram(draft,first+second)['passed']
    assert draft.relations[0].supporting_quotes==[second]
    assert draft.relations[0].source_statements==[first,second]
    graph=knowledge_graph(draft,7)
    assert graph['triples'][0]['fact_ids']==[1,2] and graph['page']==7
    # The source node precedes its destination despite reversed entity numbering.
    nodes,_=layout_diagram(TeachingDiagram.model_validate(draft.model_dump(exclude={'question'})))
    assert nodes[1]['position'][0]<nodes[2]['position'][0]
    draft.relations[0].source_statements=[first]
    with pytest.raises(TeachingDesignError,match='完整保留'):validate_diagram(draft,first+second)


def test_semantic_edge_accepts_passive_clause_but_not_unrelated_endpoints():
    source='申请材料由审核人员检查，并按原文条件记录检查结果。'
    unrelated='地表温度会在记录的环境条件下发生变化。'
    facts=[{'id':1,'source_id':1,'source_quote':source,'statement':source},
           {'id':2,'source_id':2,'source_quote':unrelated,'statement':unrelated}]
    schema=structure_schema({1:source,2:unrelated},facts=facts)
    value={'representation':'relationship','rationale':'依据被动句保留审核对象与审核动作的真实方向。','question':'谁检查这些材料？',
        'nodes':[{'id':1,'label':'审核人员','source_id':1,'source_term':'审核人员'},
                 {'id':2,'label':'申请材料','source_id':1,'source_term':'申请材料'}],
        'relations':[{'id':1,'source':1,'target':2,'label':'检查','source_fact_id':1}]}
    draft=resolve_design(schema.model_validate(value),{1:source,2:unrelated},facts=facts)
    draft.source_facts=[TeachingSourceFact.model_validate(facts[0])]
    assert draft.relations[0].binding=='semantic'
    assert validate_diagram(draft,source,require_steps=False)['passed']
    value['nodes'][1]={'id':2,'label':'地表温度','source_id':2,'source_term':'地表温度'}
    # A citation repair is not semantic approval; unrelated co-occurrence is
    # rejected by the itemized meaning gate rather than by a POS/subject rule.
    repaired=resolve_design(schema.model_validate(value),{1:source,2:unrelated},facts=facts)
    from zhijiang.teaching_design import TeachingSourceReview,validate_meaning_review
    with pytest.raises(TeachingDesignError,match='relation_checks'):
        validate_meaning_review(TeachingSourceReview(approved=False,
            node_checks=[{'id':i,'source_meaning':'原文确实出现这个对象。','reason':'节点绑定来源事实且含义明确，可独立核对。','supported':True} for i in (1,2)],
            relation_checks=[{'id':1,'source_meaning':'原文分别说明材料审核和地表温度。','reason':'这些事实没有说明审核人员检查地表温度，关系不能成立。','supported':False}]),repaired)


def test_direct_predicate_preserves_negation_and_reports_repair():
    source='有效的缓存结果不再访问源服务器，但缓存失效时仍需回源。'
    facts=[{'id':1,'source_id':1,'source_quote':source,'statement':source}]
    schema=structure_schema({1:source},facts=facts)
    value={'representation':'relationship','rationale':'保留原文的否定以及失效时的适用条件。','question':'有效缓存怎样影响访问？',
        'nodes':[{'id':1,'label':'缓存结果','source_id':1,'source_term':'缓存结果'},
                 {'id':2,'label':'源服务器','source_id':1,'source_term':'源服务器'}],
        'relations':[{'id':1,'source':1,'target':2,'label':'必须访问','source_fact_id':1}]}
    repairs=[];draft=resolve_design(schema.model_validate(value),{1:source},repairs,facts)
    assert draft.relations[0].label=='不再访问'
    assert draft.relations[0].source_statements==[source]
    assert repairs[-1]['repair']=='literal_fact_predicate'


def test_branch_and_cycle_layout_follow_graph_not_subject_or_node_order():
    from tests.test_teaching_design import diagram
    d=diagram();d.nodes=list(reversed(d.nodes));d.relations[1].source=1
    assert graph_layers(d)==[[1],[3,2]]
    nodes,_=layout_diagram(d)
    assert nodes[2]['position'][0]==nodes[3]['position'][0]>nodes[1]['position'][0]
    d.relations[1].source=2;d.relations.append(d.relations[0].model_copy(update={'id':3,'source':3,'target':1}))
    assert graph_layers(d)==[]
    nodes,_=layout_diagram(d)
    assert len({g['position'] for g in nodes.values()})==3


def test_review_digest_covers_predicate_direction_conditions_and_steps():
    from tests.test_teaching_design import diagram
    d=diagram();digest=design_digest(d)
    for field,value in [('label','新增关系'),('source',3),('source_statements',['删除了原始条件。'])]:
        changed=d.model_copy(deep=True);setattr(changed.relations[0],field,value)
        assert design_digest(changed)!=digest
    changed=d.model_copy(deep=True);changed.source_asset='machine-specific.png'
    assert design_digest(changed)==digest


def test_basic_svg_does_not_select_a_subject_template_from_keywords():
    from zhijiang.presentation import _diagram_svg,_animation_frame
    segment=LessonSegment(title='概率在算法复杂度分析中的作用',kind='formula',
        narration='这里的符号零和一是教材给定的编码，不代表概率的边界。',
        bullets=['概率和 0、1 编码只是本段使用的记号'],evidence=Evidence(page=1,quote='Original notation without a probability-bound assertion.'))
    text=_diagram_svg(segment).decode()
    assert '概率取值范围' not in text and '可能的概率值' not in text
    assert '编码只是本段使用的记号' in text
    assert _animation_frame(segment,1,1,.5).size==(960,540)


def test_visual_capability_does_not_require_tex_for_native_text_diagrams(monkeypatch):
    from zhijiang.visual_planning import visual_capabilities
    monkeypatch.setattr('zhijiang.visual_planning.importlib.util.find_spec',lambda _:object())
    monkeypatch.setattr('zhijiang.visual_planning.shutil.which',lambda _:None)
    capabilities=visual_capabilities()
    assert capabilities['ready'] and not capabilities['geometry_ready']


def test_independent_propositions_bind_roles_and_reject_copied_approval(tmp_path):
    from zhijiang.teaching_graph import source_propositions,validate_source_propositions
    from zhijiang.teaching_design import TeachingDesignDraft
    fact={'id':1,'source_id':1,'source_quote':'两位研究者共同创建了这一研究传统，没有互为创建者。',
          'statement':'甲研究者与乙研究者共同创建了研究传统。'}
    class Client:
        calls=0
        def generate(self,schema,instruction,material):
            self.calls+=1
            assert set(json.loads(material))=={'sources'}
            assert '候选' not in material and 'question' not in material
            return schema.model_validate({'propositions':[{'subject':'甲研究者','predicate':'共同创建',
                'object':'研究传统','fact_ids':[1]}]})
    client=Client();path=tmp_path/'propositions.json'
    props=source_propositions(client,[fact],path)
    assert source_propositions(client,[fact],path)==props and client.calls==1
    assert json.loads(path.read_text(encoding='utf-8'))['status']=='draft_requires_semantic_review'
    schema=structure_schema({1:fact['source_quote']},facts=[fact],propositions=props)
    value={'representation':'relationship','rationale':'用来源命题约束实际主谓宾角色，保留共同创建的含义。','question':'谁共同创建研究传统？',
        'nodes':[{'id':1,'label':'甲研究者','source_term':'研究者','source_id':1},
                 {'id':2,'label':'研究传统','source_term':'研究传统','source_id':1}],
        'relations':[{'id':1,'source':1,'target':2,'source_proposition_id':1}]}
    draft=resolve_design(schema.model_validate(value),{1:fact['source_quote']},facts=[fact],propositions=props)
    assert draft.relations[0].label=='共同创建'
    validate_source_propositions(draft,props)
    # A later "approved" review cannot override the independently bound claim.
    bad=TeachingDesignDraft.model_validate(value | {'relations':[{'id':1,'source':2,'target':1,
        'source_proposition_id':1,'source_id':1,'label':'共同创建'}]})
    with pytest.raises(TeachingDesignError,match='主语和宾语'):
        resolve_design(bad,{1:fact['source_quote']},facts=[fact],propositions=props)
    draft.relations[0].label='彼此创建'
    with pytest.raises(TeachingDesignError,match='不一致'):validate_source_propositions(draft,props)


def test_distinct_facts_in_one_quote_require_complete_spoken_coverage():
    from zhijiang.teaching_design import TeachingDesignDraft
    quote='首先辨认学习材料，然后记录材料来源，最后保存检查记录。'
    facts=[{'id':1,'source_id':1,'source_quote':quote,'statement':'首先辨认学习材料，确认它是当前学习所需的资料。'},
           {'id':2,'source_id':1,'source_quote':quote,'statement':'然后记录材料来源，保留原始出处供后续核对。'}]
    d=TeachingDesignDraft(representation='source_figure',question='怎样整理学习材料？',rationale='按来源操作逐步标注原页，保留每个操作。',
        nodes=[{'id':1,'label':'学习材料','source_id':1,'source_term':'学习材料'},
               {'id':2,'label':'材料来源','source_id':1,'source_term':'材料来源'}])
    d=resolve_design(d,{1:quote},facts=facts)
    schema=script_schema(d,facts)
    assert schema.model_json_schema()['properties']['steps']['minItems']==2
    with pytest.raises(ValueError):schema.model_validate({'steps':[{'fact_id':1}]})
    assert len(schema.model_validate({'steps':[{'fact_id':1},{'fact_id':2}]}).steps)==2


def test_position_extraction_preserves_example_across_font_changes():
    from io import BytesIO
    from reportlab.pdfgen import canvas
    from pypdf import PdfReader
    from zhijiang.pdf import extract_page_text
    stream=BytesIO();pdf=canvas.Canvas(stream)
    pdf.setFont('Helvetica',12);pdf.drawString(40,740,'Read')
    pdf.setFont('Helvetica-Bold',12);pdf.drawString(78,740,'these words')
    pdf.setFont('Helvetica',12);pdf.drawString(160,740,'in context.')
    pdf.drawString(40,710,'Keep the original example.')
    pdf.save()
    text=extract_page_text(PdfReader(stream).pages[0])
    assert 'Read these words in context.' in text and 'Keep the original example.' in text


def test_text_source_rejects_novel_numbers_before_diagram_design():
    from zhijiang.teaching_design import extract_source_facts
    source='The action consumes time. We consider the next best alternative.'
    class Client:
        def generate(self,schema,*_):
            return schema.model_validate({'facts':[{'source_id':1,'statement':'该行动的机会成本为75美元，需要考虑时间。'},
                {'source_id':1,'statement':'该行动会消耗时间，需要考虑最佳替代选项。'}]})
    rejected=[];facts=extract_source_facts(Client(),{1:source},rejections=rejected)
    assert len(facts)==1 and '75' not in facts[0]['statement'] and rejected


def test_original_language_graph_roles_are_fixed_and_chinese_speech_is_preserved():
    from zhijiang.teaching_graph import _checked_propositions,graph_design_schema,design_from_propositions
    source='The sender transmits the message to the receiver under the stated conditions.'
    fact={'id':1,'source_id':1,'source_quote':source,
          'statement':'在给定条件下，发送者将消息传递给接收者。'}
    props,rejected=_checked_propositions([{'subject':'sender','predicate':'transmits','object':'message',
        'fact_ids':[1],'subject_source_term':'sender','object_source_term':'message'}],[fact])
    assert not rejected
    selected=graph_design_schema(props).model_validate({'representation':'relationship',
        'rationale':'使用原语言名称保留来源角色，中文讲稿解释对应关系。','question':'消息怎样传递？','proposition_ids':[1]})
    draft=design_from_propositions(selected,props,[fact])
    draft=resolve_design(draft,{1:source},facts=[fact],propositions=props)
    draft.source_facts=[TeachingSourceFact.model_validate(fact)]
    script=bind_script_focus(script_schema(draft,[fact]).model_validate({'steps':[{'fact_id':1}]}),draft,[fact])
    complete_relation_focus(script,draft.relations);draft.steps=compose_script(script,[fact])
    assert validate_diagram(draft,source)['passed']
    assert [(n.label,n.source_term) for n in draft.nodes]==[('sender','sender'),('message','message')]
    assert draft.steps[0].narration==fact['statement']
    # Clipping an English word must not become a purported literal anchor.
    from zhijiang.teaching_design import literal_source_name
    assert literal_source_name('receiv',source) is None


def test_ollama_thinking_configuration_is_persisted_without_keys(tmp_path,monkeypatch):
    from zhijiang.config import Settings
    from zhijiang.main import model_options
    from zhijiang.pipeline import JobProcessor
    from zhijiang.storage import JobStore
    from zhijiang.models import Mode
    monkeypatch.setenv('ZHIJIANG_OLLAMA_SEMANTIC_THINKING','false')
    settings=Settings.from_env()
    options=model_options(settings,'ollama','http://localhost:11434','local-model','','')
    assert not options.semantic_thinking and 'api_key' not in options.model_dump()
    agents=JobProcessor(settings,JobStore(tmp_path))._agents(Mode.AI,options)
    assert not agents.client.semantic_thinking
    agents.client.close()


def test_condition_prefix_is_completed_and_contradictory_branch_rejected():
    from zhijiang.teaching_design import TeachingDesignDraft
    first='如果访问权限有效且令牌仍有效，客户端读取受保护数据。'
    second='如果访问权限无效或令牌已过期，客户端重新请求访问权限。'
    facts=[{'id':i,'source_id':i,'source_quote':text,'statement':text} for i,text in enumerate((first,second),1)]
    draft=TeachingDesignDraft(representation='relationship',rationale='依照完整条件规划访问与重新请求的分支。',question='条件怎样决定操作？',
        nodes=[{'id':1,'label':'访问权限有效且令牌','source_id':1,'source_term':'访问权限'},
               {'id':2,'label':'受保护数据','source_id':1,'source_term':'受保护数据'}],
        relations=[{'id':1,'source':1,'target':2,'label':'条件成立时读取','binding':'semantic','source_id':1,'source_fact_id':1}])
    resolved=resolve_design(draft,{1:first,2:second},facts=facts)
    assert resolved.nodes[0].label=='访问权限有效且令牌仍有效'
    assert resolved.nodes[0].kind=='condition'
    assert resolved.relations[0].condition=='如果访问权限有效且令牌仍有效'
    draft.relations[0].source_fact_id=2
    with pytest.raises(TeachingDesignError,match='条件分支错配'):resolve_design(draft,{1:first,2:second},facts=facts)


@pytest.mark.parametrize('phase',['layout','sequence'])
def test_geometry_contract_failures_retry_and_reselect_expression(tmp_path,sample_pdf,monkeypatch,phase):
    from zhijiang.agents import DemoAgents,GenerationError
    from zhijiang.pdf import read_pdf
    from zhijiang.models import VoiceMode
    from zhijiang.visual_planning import plan_visual_scenes
    from zhijiang.teaching_design import TeachingDesignDraft,ResolvedTeachingDesign
    from tests.test_visual_scenes import scene_for
    from tests.test_teaching_design import diagram
    document=read_pdf(sample_pdf,'sample.pdf');agents=DemoAgents();bundle=agents.extract_knowledge(document)
    lesson=agents.script(bundle,agents.plan(bundle),VoiceMode.SYSTEM)
    # A diagram replacement is independently planned and checked against the
    # current source by production code; this test isolates contract recovery.
    replacement=diagram();page=document.pages[0];replacement.representation='comparison';replacement.relations=[]
    replacement.nodes=replacement.nodes[:2]
    for node in replacement.nodes:node.source_quote=lesson.segments[0].evidence.quote
    replacement.steps=[replacement.steps[0].model_copy(update={'focus':[1,2],'relations':[]})]
    redesigns=[]
    def design(*args,force_diagram=False,**kwargs):
        redesigns.append(force_diagram)
        if force_diagram:
            return ResolvedTeachingDesign(question='观察当前来源的不同对象？',**replacement.model_dump(exclude={'source_asset','source_regions'})),{},[]
        return TeachingDesignDraft(representation='geometry',question='怎样观察图形变化？',rationale='原文提出可计算的对象变化关系。'),None,[]
    monkeypatch.setattr('zhijiang.teaching_design.plan_teaching_representation',design)
    monkeypatch.setattr('zhijiang.visual_planning.visual_capabilities',lambda:{'geometry_ready':True})
    # Only one segment is needed for this bounded recovery check.
    lesson.segments=lesson.segments[:1]
    class Client:
        failed_calls=0
        def generate(self,schema,*args):
            if schema.__name__==('VisualLayoutDraft' if phase=='layout' else 'VisualSequenceDraft'):
                self.failed_calls+=1;raise GenerationError('返回不符合数据契约的 JSON')
            return scene_for('任意主题','t',{'t':1},{'t':2})
    client=Client()
    plan_visual_scenes(client,lesson,document,'',lambda *_:None,pedagogical_design=True,draft_output=tmp_path/'visual-planning.json')
    assert client.failed_calls==5 and redesigns==[False,True]
    assert lesson.segments[0].visual_scene.diagram.representation=='comparison'
    failures=json.loads((tmp_path/'visual-planning.json').read_text(encoding='utf-8'))
    assert len([item for item in failures if item.get('phase')==phase])==5
