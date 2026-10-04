import pytest
from zhijiang.models import TeachingDiagram
from zhijiang.teaching_design import validate_diagram,TeachingDesignError,compile_teaching_scene,TeachingDesignDraft,ResolvedTeachingDesign
from zhijiang.visual_planning import verify_visual_scene,VisualSceneError


SOURCE='A control signal synchronizes the human hand and robotic hand. The recorded motions support dataset construction.'


def diagram():
    return TeachingDiagram(representation='process',rationale='原文说明控制信号与动作记录的关系，适合逐步追踪流程。',
        nodes=[{'id':1,'label':'控制信号','source_quote':'A control signal'},
               {'id':2,'label':'动作同步','source_quote':'synchronizes the human hand and robotic hand'},
               {'id':3,'label':'构建数据集','source_quote':'support dataset construction'}],
        relations=[{'id':1,'source':1,'target':2,'label':'用于同步','source_quote':'A control signal synchronizes'},
                   {'id':2,'source':2,'target':3,'label':'记录动作','source_quote':'The recorded motions support dataset construction'}],
        steps=[{'narration':'首先识别输入的控制信号，明确我们要解释的是信号与记录的关系。','focus':[1]},
               {'narration':'沿连线观察控制信号如何用于动作同步，保留两个端点进行比较。','focus':[1,2],'relations':[1]},
               {'narration':'随后追踪动作记录如何支持数据集构建，图中连线表示原文关系。','focus':[2,3],'relations':[2]}])


def test_non_geometric_reasoning_is_source_grounded_and_progressive():
    d=diagram();assert validate_diagram(d,SOURCE)['passed']
    d.nodes[0].source_quote='invented control mechanism'
    with pytest.raises(TeachingDesignError,match='逐字'):validate_diagram(d,SOURCE)


def test_missing_relation_endpoints_and_repeated_bullets_rejected():
    d=diagram();d.steps[1].focus=[3]
    with pytest.raises(TeachingDesignError,match='相关端点'):validate_diagram(d,SOURCE)
    d=diagram();d.steps[1].focus=[2]
    assert validate_diagram(d,SOURCE)['passed']
    d=diagram();d.steps[2]=d.steps[1].model_copy(deep=True)
    with pytest.raises(TeachingDesignError,match='重复'):validate_diagram(d,SOURCE)
    d=diagram();d.relations[0].target=6
    with pytest.raises(TeachingDesignError,match='已有'):validate_diagram(d,SOURCE)


def test_bibliography_is_not_taught_as_new_source_topics():
    from zhijiang.models import SourceDocument,PageText
    from zhijiang.agents import source_candidates
    doc=SourceDocument(filename='paper.pdf',pages=[
        PageText(page=1,text=('The method connects observations to an interpretable representation.\n'*4)),
        PageText(page=2,text='References\n[Author, 2020] A completely unrelated paper and bibliography entry.'),
        PageText(page=3,text='[Other, 2021] Further continuation of bibliographic entries and citations.')])
    assert {c['page'] for c in source_candidates(doc)}=={1}
    doc.pages.append(PageText(page=4,text='Chapter 2\nNew instructional material explains measurement and observation relationships.'))
    assert 4 in {c['page'] for c in source_candidates(doc)}


def test_compiled_diagram_preserves_sources_speech_and_svg():
    from zhijiang.models import LessonSegment,Evidence
    from zhijiang.visual_media import visual_summary_svg
    from lxml import etree
    d=diagram();draft=ResolvedTeachingDesign(question='控制信号怎样支持动作记录？',**d.model_dump(exclude={'source_asset','source_regions'}))
    segment=LessonSegment(title='动作记录流程',kind='process',narration='以原文的控制信号与记录关系说明数据流程。',bullets=['控制和记录'],
        evidence=Evidence(page=1,quote='A control signal synchronizes'))
    scene=compile_teaching_scene(draft,segment,validate_diagram(d,SOURCE),source_text=SOURCE)
    assert verify_visual_scene(scene)['states'][1]['relations']==[1]
    assert scene.parameters=={} and scene.beats[2].narration==d.steps[2].narration
    xml=etree.fromstring(visual_summary_svg(scene).encode())
    assert '控制信号' in ''.join(xml.itertext())
    scene.beats[0].narration='这是被意外替换并不匹配教学步骤的口播内容。'
    with pytest.raises(VisualSceneError,match='口播'):verify_visual_scene(scene)


def test_model_selects_source_ids_program_supplies_literal_quotes():
    from zhijiang.teaching_design import source_spans,resolve_design
    spans=source_spans(SOURCE)
    d=diagram().model_dump(exclude={'source_asset','source_regions'})
    for field in ('nodes','relations'):
        for item in d[field]:
            item.pop('source_quote');item['source_id']=1
            item['source_term']='control signal' if field=='nodes' and item['id']==1 else 'recorded motions'
    draft=TeachingDesignDraft(question='控制信号怎样支持动作记录？',**d)
    resolved=resolve_design(draft,spans)
    assert resolved.nodes[0].source_quote==spans[1]
    assert all(n.source_quote==spans[2] for n in resolved.nodes[1:])
    assert 'source_quote' not in TeachingDesignDraft.model_json_schema()['$defs']['DesignNodeDraft']['properties']
    draft.nodes[0].source_id=999
    with pytest.raises(TeachingDesignError,match='source_id'):resolve_design(draft,spans)


def test_relation_cannot_join_unrelated_source_terms_or_invent_numeric_speech():
    d=diagram()
    for node,term in zip(d.nodes,('control signal','human hand','dataset construction')):
        node.source_term=term;node.source_quote=SOURCE
    for edge in d.relations:edge.source_quote=SOURCE;edge.source_term='synchronizes' if edge.id==1 else 'support'
    assert validate_diagram(d,SOURCE)['passed']
    d.relations[0].source_quote='The recorded motions support dataset construction.'
    with pytest.raises(TeachingDesignError,match='source_term'):validate_diagram(d,SOURCE)
    d.relations[0].source_term='support'
    with pytest.raises(TeachingDesignError,match='同时支持'):validate_diagram(d,SOURCE)
    d.relations[0].source_quote=SOURCE
    d.steps[1].narration='这个过程能够保证未来五步的预测正确，可以直接跳到最终结果。'
    with pytest.raises(TeachingDesignError,match='数值'):validate_diagram(d,SOURCE)


def test_living_analogies_and_indefinite_articles_are_not_measurements():
    from zhijiang.teaching_design import has_unbound_quantity
    assert not has_unbound_quantity('就像看一个人跳舞，观察每一步，再模仿同一个动作。')
    assert not has_unbound_quantity('人机同步好比两个人配合，一个指挥，一个执行。')
    assert not has_unbound_quantity('就像孩子第一次学用筷子，需要看清示范。')
    assert has_unbound_quantity('未来五步的预测一定正确。')
    assert has_unbound_quantity('向量位于一个维度中。')
    assert has_unbound_quantity('就像等待两秒再动作。')
    assert has_unbound_quantity('系统恰好有一个目标。')
    assert has_unbound_quantity('结果有两个时间窗口。')


def test_semantic_review_cannot_approve_with_missing_or_rejected_meanings():
    from zhijiang.teaching_design import TeachingSourceReview,validate_meaning_review,meaning_review_schema
    d=diagram()
    with pytest.raises(TeachingDesignError,match='遗漏'):validate_meaning_review(TeachingSourceReview(approved=True),d)
    value={'approved':True,'issues':[]}
    for name,ids in [('node_checks',[1,2,3]),('relation_checks',[1,2]),('step_checks',[1,2,3])]:
        value[name]=[{'id':key,'supported':True,'source_meaning':'原文描述控制与记录之间的具体关系。','reason':'候选保留原文关系与适用条件，没有添加保证。'} for key in ids]
    review=meaning_review_schema(d).model_validate(value)
    schema=meaning_review_schema(d).model_json_schema()
    assert list(schema['properties'])==['node_checks','relation_checks','step_checks','approved','issues']
    node_check=schema['$defs']['MeaningCheck_node_checks']['properties']
    assert list(node_check).index('source_meaning')<list(node_check).index('reason')<list(node_check).index('supported')
    validate_meaning_review(review,d)
    review.relation_checks[0].supported=False
    review.relation_checks[0].reason='原文只描述共现，候选却添加了因果关系。'
    with pytest.raises(TeachingDesignError,match='relation_checks'):validate_meaning_review(review,d)


@pytest.mark.parametrize('representation',['source_figure','comparison'])
@pytest.mark.parametrize('supported',[True,False])
def test_annotation_review_keeps_phrase_role_and_rejects_wrong_meaning(representation,supported):
    import json
    from zhijiang.models import SourceDocument,PageText,LessonSegment,Evidence
    from zhijiang.teaching_design import plan_teaching_representation
    source='一个数乘几分之几表示求这个数的几分之几是多少。'
    document=SourceDocument(filename='definition.pdf',pages=[PageText(page=1,text=source)])
    segment=LessonSegment(title='分数乘法含义',kind='concept',narration=source,
        bullets=['分数乘法含义'],evidence=Evidence(page=1,quote=source))
    reviews=[]
    class Client:
        def generate(self,schema,instruction,material):
            if schema.__name__=='SourceFactsDraft':
                return schema.model_validate({'facts':[{'source_id':1,'statement':source}]})
            if schema.__name__=='TeachingDesignDraft':
                chosen='source_figure' if 'representation=source_figure' in instruction else representation
                return schema.model_validate({'representation':chosen,
                    'rationale':'用原文数量短语标注定义，保留整个定义的条件。','question':'怎样理解分数乘法？',
                    'nodes':[{'id':1,'label':'一个数','source_id':1,'source_term':'一个'},
                             {'id':2,'label':'几分之几','source_id':1,'source_term':'几分之几'}],
                    'relations':[],'steps':[]})
            if schema.__name__=='TeachingScriptDraft':
                return schema.model_validate({'steps':[{'fact_id':1}],'example':None})
            candidate=json.loads(material)['design'];reviews.append(candidate)
            assert '当前表达方式：'+candidate['representation'] in instruction
            assert '没有连线时不假定节点之间存在' in instruction
            assert '共现不等于关系' in instruction
            result={'approved':supported,'issues':[],'relation_checks':[],
                'node_checks':[{'id':key,'supported':supported,'source_meaning':source,
                    'reason':'原文支持数量短语的指代，注释没有增加实体或关系。' if supported else '该标签的指代与原文不符，不能用文字出现替代含义检查。'} for key in [1,2]],
                'step_checks':[{'id':1,'supported':True,'source_meaning':source,
                    'reason':'口播使用完整原文定义，没有改变适用条件。'}]}
            return schema.model_validate(result)
    if supported:
        draft,report,_=plan_teaching_representation(Client(),segment,document,'')
        assert report['semantic_review']['approved'] and not draft.relations
        assert draft.steps[0].source_statement==source and draft.steps[0].focus==[1,2]
    else:
        with pytest.raises(TeachingDesignError,match='教学含义核对未通过'):
            plan_teaching_representation(Client(),segment,document,'')
    assert reviews and all(not review['relations'] for review in reviews)


def test_path_focus_completion_changes_only_display_emphasis():
    from types import SimpleNamespace
    from zhijiang.teaching_design import complete_relation_focus
    d=diagram();script=SimpleNamespace(steps=d.steps)
    script.steps[1].focus=[3]
    before=script.steps[1].narration
    changes=complete_relation_focus(script,d.relations)
    assert changes[0]['added_focus']==1 and script.steps[1].focus==[3,1,2]
    assert script.steps[1].narration==before and script.steps[1].relations==[1]
    d.steps=script.steps
    assert validate_diagram(d,SOURCE)['passed']


def test_source_annotation_does_not_invent_relations_and_marks_analogies():
    from zhijiang.teaching_design import TeachingScriptDraft,compose_script,script_schema,meaning_review_schema
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:1];d.relations=[]
    facts=['原文说明控制信号用于动作同步，可以先辨认这个操作的对象。',
           '原文记录人的手与机器人的手之间的同步关系，讲解时保留对象身份。',
           '原文还说明记录的动作支持数据构建，讲解必须保留这个使用范围。']
    raw={'steps':[{'source_statement':fact,'analogy':'就像舞伴在同一个节奏下配合。','focus':[1],'relations':[]} for fact in facts]}
    script=script_schema(d).model_validate(raw)
    d.steps=compose_script(script)
    assert validate_diagram(d,SOURCE)['passed']
    assert all('做个生活类比：' in step.narration and step.analogy for step in d.steps)
    assert meaning_review_schema(d).model_json_schema()['properties']['relation_checks']['maxItems']==0


def test_source_fact_selection_cannot_rewrite_narration_or_invent_values():
    from zhijiang.teaching_design import script_schema,compose_script,bind_script_focus
    from zhijiang.models import TeachingSourceFact
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:1];d.relations=[]
    facts=[{'id':1,'source_id':1,'source_quote':SOURCE,
            'statement':'原文说明控制信号用于人手与机器人手的动作同步。'}]
    d.nodes[0].source_quote=SOURCE
    script=script_schema(d,facts).model_validate({'steps':[{'fact_id':1,'focus':[1],'relations':[],'analogy':''}]})
    script=bind_script_focus(script,d,facts)
    d.source_facts=[TeachingSourceFact.model_validate(f) for f in facts]
    d.nodes[0].source_quote=SOURCE
    d.steps=compose_script(script,facts)
    assert validate_diagram(d,SOURCE)['passed'] and len(d.steps)==1
    d.steps[0].source_statement='控制信号必然使所有未来动作成功，完全不会出错。'
    with pytest.raises(TeachingDesignError,match='独立'):validate_diagram(d,SOURCE)
    d.steps=compose_script(script,facts)
    d.source_facts[0].statement='原文说明控制信号同步动作的时间恰好为30秒。'
    with pytest.raises(TeachingDesignError,match='数值'):validate_diagram(d,SOURCE)


def test_source_facts_reading_is_isolated_from_candidate_and_style():
    from zhijiang.teaching_design import extract_source_facts
    class Client:
        def generate(self,schema,instruction,material):
            import json
            assert list(json.loads(material))==['sources']
            assert '候选' in instruction and '生活例子' not in material
            return schema.model_validate({'facts':[{'source_id':1,'statement':'原文说明控制信号用于人手与机器人手的动作同步。'}]})
    facts=extract_source_facts(Client(),{1:SOURCE})
    assert facts[0]['source_quote']==SOURCE and facts[0]['id']==1


def test_source_spans_keep_subject_predicate_and_conditions_together():
    from zhijiang.teaching_design import source_spans
    text='The data is enriched\nby visual observations. This collection supports\ntraining under the stated conditions.'
    spans=source_spans(text)
    assert list(spans.values())==['The data is enriched by visual observations.',
                                  'This collection supports training under the stated conditions.']
    assert all(len(quote)<=300 for quote in source_spans(('Long source words and clauses, '*40)).values())
    assert all(len(quote)<=300 for quote in source_spans('a'*300+', followed by a condition.').values())
    cited='Some methods [Alpha et al., 2022; Beta et al., 2023; Gamma et al., 2024] use recorded data.'
    assert list(source_spans(cited).values())==[cited]


def test_diagram_steps_do_not_borrow_unrelated_source_facts():
    from zhijiang.teaching_design import diagram_source_facts,script_schema
    from pydantic import ValidationError
    d=diagram()
    facts=[{'id':1,'source_id':1,'source_quote':d.nodes[0].source_quote,'statement':'原文说明控制信号与动作同步之间的关系。'},
           {'id':2,'source_id':2,'source_quote':'An unrelated experiment supports another conclusion.',
            'statement':'另一个实验描述的是不同的对象与研究结论。'}]
    selected=diagram_source_facts(d,facts)
    assert [fact['id'] for fact in selected]==[1]
    with pytest.raises(ValidationError):
        script_schema(d,selected).model_validate({'steps':[{'fact_id':2,'focus':[1],'relations':[]}]})


def test_source_fact_sequence_rejects_repetition_and_honors_analogy_request():
    from zhijiang.teaching_design import script_schema
    from pydantic import ValidationError
    facts=[{'id':1,'statement':'原文说明控制信号与动作同步之间的关系。'},
           {'id':2,'statement':'记录的动作同步描述原文中所记录的具体关系。'}]
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:2];d.relations=[]
    for node in d.nodes:node.source_quote=SOURCE
    for fact in facts:fact['source_quote']=SOURCE
    schema=script_schema(d,facts,require_analogy=True)
    step={'fact_id':1,'focus':[1],'relations':[]}
    example={'fact_id':1,'analogy':'就像舞伴对照对方的动作保持配合。'}
    with pytest.raises(ValidationError):schema.model_validate({'steps':[step]})
    with pytest.raises(ValidationError,match='只讲解一次'):schema.model_validate({'steps':[step,{**step,'focus':[2]}],'example':example})
    assert len(schema.model_validate({'steps':[step,{**step,'fact_id':2,'focus':[2]}],'example':example}).steps)==2
    with pytest.raises(ValidationError,match='pattern'):
        schema.model_validate({'steps':[step],'example':{**example,'analogy':'就像舞伴对照对方的动作保持配合'}})
    with pytest.raises(ValidationError,match='已选择'):
        schema.model_validate({'steps':[step],'example':{**example,'fact_id':2}})


def test_source_reading_cache_is_unapproved_and_invalidates_on_new_source(tmp_path):
    from zhijiang.teaching_design import source_reading
    import json
    class Client:
        calls=0
        def generate(self,schema,instruction,material):
            self.calls+=1
            return schema.model_validate({'facts':[{'source_id':1,'statement':'原文说明控制信号与动作同步之间的关系。'}]})
    c=Client();path=tmp_path/'reading.json'
    _,cached=source_reading(c,{1:SOURCE},path);assert not cached
    _,cached=source_reading(c,{1:SOURCE},path);assert cached and c.calls==1
    assert json.loads(path.read_text(encoding='utf-8'))['status']=='draft_requires_semantic_review'
    source_reading(c,{1:SOURCE+' Updated condition.'},path);assert c.calls==2


def test_failed_relation_planning_can_select_original_page_without_fake_edges():
    from zhijiang.teaching_design import structure_schema
    from pydantic import ValidationError
    schema=structure_schema({1:SOURCE},source_annotation=True)
    value={'representation':'source_figure','rationale':'关系设计未通过，保留原页及独立来源注释。','question':'原文记录了什么动作？',
           'nodes':[{'id':1,'label':'动作记录','source_id':1,'source_term':'recorded motions'}],
           'relations':[],'steps':[]}
    assert schema.model_validate(value).representation=='source_figure'
    value['representation']='relationship'
    with pytest.raises(ValidationError):schema.model_validate(value)


def test_three_node_branch_does_not_draw_through_another_concept_card():
    from zhijiang.teaching_layout import layout_diagram
    d=diagram();d.relations[1].source=1;d.relations[1].target=3
    nodes,edges=layout_diagram(d)
    for relation in d.relations:
        edge=edges[relation.id]
        other=next(key for key in nodes if key not in (relation.source,relation.target))
        center=nodes[other]['position']
        for index in range(101):
            t=index/100
            x=(1-t)*edge['start'][0]+t*edge['end'][0]
            y=(1-t)*edge['start'][1]+t*edge['end'][1]
            assert not (abs(x-center[0])<nodes[other]['width']/2 and abs(y-center[1])<nodes[other]['height']/2)


def test_source_alphabet_and_reference_repairs_preserve_actual_text():
    from zhijiang.teaching_design import structure_schema,resolve_design
    from pydantic import ValidationError
    spans={1:'A control signal drives the human hand.',2:'Recorded motions support dataset construction.'}
    schema=structure_schema(spans)
    value={'representation':'process','rationale':'根据来源中的动作记录说明数据构建过程。','question':'记录如何支持数据构建？',
        'nodes':[{'id':1,'label':'动作记录','source_id':1,'source_term':'Recorded motions'},
                 {'id':2,'label':'数据集','source_id':2,'source_term':'dataset construction'}],
        'relations':[{'id':1,'source':1,'target':2,'label':'支持构建','source_id':2,'source_term':'support'}],
        'steps':[]}
    draft=schema.model_validate(value);repairs=[]
    resolved=resolve_design(draft,spans,repairs)
    assert resolved.nodes[0].source_quote==spans[2] and repairs[0]['to_source_id']==2
    assert validate_diagram(resolved,' '.join(spans.values()),require_steps=False)['passed']
    value['nodes'][0]['source_term']='动作记录'
    with pytest.raises(ValidationError):schema.model_validate(value)
    value['nodes'][0]['source_term']='Recorded motions';value['nodes'][0]['source_id']=999
    with pytest.raises(ValidationError):schema.model_validate(value)


def test_stage_checkpoint_reuses_only_matching_completed_input(tmp_path):
    from zhijiang.pipeline import checkpoint
    from zhijiang.models import SourceDocument,PageText
    calls=[]
    def build():
        calls.append(True)
        return SourceDocument(filename='input.pdf',pages=[PageText(page=1,text='Original source content')])
    path=tmp_path/'stage.json'
    assert checkpoint(path,'hash-a',SourceDocument,build)==checkpoint(path,'hash-a',SourceDocument,build)
    assert len(calls)==1
    checkpoint(path,'hash-b',SourceDocument,build);assert len(calls)==2
    path.write_text('interrupted partial JSON',encoding='utf-8')
    checkpoint(path,'hash-b',SourceDocument,build);assert len(calls)==3


def test_scene_checkpoint_revalidates_source_and_input(tmp_path):
    from zhijiang.visual_planning import save_planned_scene,load_planned_scene
    from zhijiang.models import SourceDocument,PageText,LessonSegment,Evidence
    d=diagram();draft=ResolvedTeachingDesign(question='控制信号怎样支持动作记录？',**d.model_dump(exclude={'source_asset','source_regions'}))
    segment=LessonSegment(title='控制与记录',kind='process',narration='来源记录控制信号与动作记录之间的关系，请核对这段真实的文字依据。',bullets=['记录'],evidence=Evidence(page=1,quote='A control signal synchronizes'))
    document=SourceDocument(filename='input.pdf',pages=[PageText(page=1,text=SOURCE)])
    scene=compile_teaching_scene(draft,segment,validate_diagram(d,SOURCE),source_text=SOURCE)
    semantic={'approved':True,'issues':[]}
    for name,ids in [('node_checks',[1,2,3]),('relation_checks',[1,2]),('step_checks',[1,2,3])]:
        semantic[name]=[{'id':key,'supported':True,'source_meaning':'原文描述控制与记录之间的具体关系。','reason':'候选保留原文关系与适用条件，没有添加保证。'} for key in ids]
    path=tmp_path/'scene.json';save_planned_scene(path,'input-a',scene,{'semantic_review':semantic})
    assert load_planned_scene(path,'input-a',document,segment)[0].diagram==scene.diagram
    assert load_planned_scene(path,'input-b',document,segment) is None
    document.pages[0].text='A control signal synchronizes. Unrelated text replaces the relation evidence.'
    assert load_planned_scene(path,'input-a',document,segment) is None


def test_source_catalog_cannot_generate_spliced_terms_across_definitions():
    from zhijiang.teaching_design import source_terms,structure_schema
    from pydantic import ValidationError
    spans={1:'Hand poses p and joint features f describe the trajectory.',
           2:'Pose history q is collected over time.'}
    terms=source_terms(spans)
    assert 'Hand poses' in terms and 'joint features' in terms
    assert 'Hand poses q' not in terms
    chinese={1:'材料先经过加热，再发生相变。温度影响材料的状态。'}
    assert source_terms(chinese) and all(term in chinese[1] for term in source_terms(chinese))
    d=diagram();d.relations=d.relations[:1]
    with pytest.raises(TeachingDesignError,match='孤立'):validate_diagram(d,SOURCE,require_steps=False)


def test_relation_predicate_and_endpoints_are_bound_to_independent_fact():
    from zhijiang.teaching_design import structure_schema,resolve_design
    from pydantic import ValidationError
    spans={1:'Recorded observations support the training objective.'}
    facts=[{'id':1,'source_id':1,'source_quote':spans[1],
            'statement':'记录的观测数据仅支持训练目标，不保证所有任务成功。'}]
    schema=structure_schema(spans,facts=facts)
    value={'representation':'relationship','rationale':'依据独立来源事实解释数据与目标之间的关系。','question':'观测数据怎样支持训练？',
        'nodes':[{'id':1,'label':'观测数据','source_id':1,'source_term':'observations'},
                 {'id':2,'label':'训练目标','source_id':1,'source_term':'training objective'}],
        'relations':[{'id':1,'source':1,'target':2,'source_fact_id':1}],'steps':[]}
    resolved=resolve_design(schema.model_validate(value),spans,facts=facts)
    assert resolved.relations[0].label=='仅支持'
    from zhijiang.models import TeachingSourceFact
    resolved.source_facts=[TeachingSourceFact.model_validate(fact) for fact in facts]
    assert validate_diagram(resolved,spans[1],require_steps=False)['passed']
    value['relations'][0].update(source=2,target=1)
    with pytest.raises(TeachingDesignError,match='主语'):
        resolve_design(schema.model_validate(value),spans,facts=facts)
    value['nodes'][0]['label']='必然保证'
    with pytest.raises(ValidationError):schema.model_validate(value)


def test_cached_relation_cannot_drop_qualifier_or_change_subject():
    from zhijiang.models import TeachingSourceFact
    d=diagram();d.representation='relationship';d.nodes=d.nodes[:2];d.relations=d.relations[:1]
    source='Recorded observations support the training objective.'
    d.nodes[0].label='观测数据';d.nodes[0].source_term='observations';d.nodes[0].source_quote=source
    d.nodes[1].label='训练目标';d.nodes[1].source_term='training objective';d.nodes[1].source_quote=source
    fact=TeachingSourceFact(id=1,source_id=1,source_quote=source,statement='记录的观测数据仅支持训练目标，不保证所有任务成功。')
    d.source_facts=[fact];d.relations[0].source_fact_id=1;d.relations[0].source_quote=source;d.relations[0].label='仅支持'
    assert validate_diagram(d,source,require_steps=False)['passed']
    d.relations[0].label='保证'
    with pytest.raises(TeachingDesignError,match='一致'):validate_diagram(d,source,require_steps=False)


def test_node_source_name_and_original_term_are_one_constrained_choice():
    from zhijiang.teaching_design import structure_schema
    from pydantic import ValidationError
    spans={1:'Observed data describes the initial state.',2:'A separate experiment reports an outcome.'}
    facts=[{'id':1,'source_id':1,'source_quote':spans[1],'statement':'观测数据描述原文记录的初始状态。'},
           {'id':2,'source_id':2,'source_quote':spans[2],'statement':'另一个独立实验记录的是不同的结果。'}]
    schema=structure_schema(spans,facts=facts,source_annotation=True)
    value={'representation':'source_figure','rationale':'按原文标注不同实验所描述的独立事实。','question':'原文记录了哪些事实？',
           'nodes':[{'id':1,'label':'初始状态','source_id':1,'source_term':'initial state'}],'relations':[],'steps':[]}
    assert schema.model_validate(value).nodes[0].label=='初始状态'
    value['nodes'][0]['source_id']=2
    with pytest.raises(ValidationError):schema.model_validate(value)
    value['nodes'][0].update(label='结果',source_term='outcome')
    assert schema.model_validate(value).nodes[0].source_id==2


def test_planner_does_not_publish_unbound_claims_in_heading_or_rationale():
    import json
    from zhijiang.models import SourceDocument,PageText,LessonSegment,Evidence
    from zhijiang.teaching_design import plan_teaching_representation
    source='Recorded observations support the training objective.'
    document=SourceDocument(filename='source.pdf',pages=[PageText(page=1,text=source)])
    segment=LessonSegment(title='观测与目标',kind='concept',narration='说明观测数据与原文训练目标之间的限定关系。',bullets=['观测与目标'],evidence=Evidence(page=1,quote=source))
    class Client:
        def generate(self,schema,instruction,material):
            if schema.__name__=='SourceFactsDraft':
                return schema.model_validate({'facts':[{'source_id':1,'statement':'记录的观测数据仅支持训练目标，不保证所有任务成功。'}]})
            if schema.__name__=='TeachingDesignDraft':
                return schema.model_validate({'representation':'relationship','rationale':'数据必然保证所有任务成功，已经完全证明这一普遍结果。','question':'数据为什么必然保证所有任务成功？',
                    'nodes':[{'id':1,'label':'观测数据','source_id':1,'source_term':'observations'},
                             {'id':2,'label':'训练目标','source_id':1,'source_term':'training objective'}],
                    'relations':[{'id':1,'source':1,'target':2,'source_fact_id':1}],'steps':[]})
            if schema.__name__=='TeachingScriptDraft':
                return schema.model_validate({'steps':[{'fact_id':1,'analogy':'','focus':[1,2],'relations':[1]}]})
            candidate=json.loads(material)['design']
            assert '必然保证' not in candidate['question']+candidate['rationale']
            result={'approved':True,'issues':[]}
            for name,ids in [('node_checks',[1,2]),('relation_checks',[1]),('step_checks',[1])]:
                result[name]=[{'id':key,'supported':True,'source_meaning':'原文说明观测数据支持训练目标。','reason':'候选保留支持关系和适用限制，未增加保证。'} for key in ids]
            return schema.model_validate(result)
    draft,report,_=plan_teaching_representation(Client(),segment,document,'')
    assert draft.relations[0].label=='仅支持' and report['passed']
    assert '必然保证' not in draft.question+draft.rationale


def test_unapproved_structure_cache_is_rechecked_without_claiming_approval(tmp_path):
    import json
    from zhijiang.teaching_design import save_structure,load_structure
    d=diagram();draft=ResolvedTeachingDesign(question='原文如何描述控制与记录？',**d.model_dump(exclude={'source_asset','source_regions'}))
    path=tmp_path/'structure.json';save_structure(path,'same-source',draft)
    assert json.loads(path.read_text(encoding='utf-8'))['status']=='draft_requires_semantic_review'
    assert load_structure(path,'same-source',SOURCE).steps==[]
    assert load_structure(path,'different-input',SOURCE) is None
    assert load_structure(path,'same-source','The original source has been replaced.') is None


def test_spoken_fact_binds_visual_focus_and_its_single_example():
    from zhijiang.teaching_design import bind_script_focus,script_schema,compose_script
    from zhijiang.models import TeachingSourceFact
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:2];d.relations=[]
    sources=['A control signal is recorded.','The synchronized motion is described.']
    facts=[{'id':1,'source_id':1,'source_quote':sources[0],'statement':'原文记录控制信号及其适用的观察条件。'},
           {'id':2,'source_id':2,'source_quote':sources[1],'statement':'原文描述动作同步及其对应的记录条件。'}]
    for node,source in zip(d.nodes,sources):node.source_quote=source
    script=script_schema(d,facts,require_analogy=True).model_validate({'steps':[{'fact_id':1},{'fact_id':2}],
        'example':{'fact_id':2,'analogy':'就像舞伴对照对方的动作来保持配合。'}})
    bound=bind_script_focus(script,d,facts)
    assert [step.focus for step in bound.steps]==[[1],[2]]
    d.source_facts=[TeachingSourceFact.model_validate(fact) for fact in facts];d.steps=compose_script(bound,facts)
    assert not d.steps[0].analogy and d.steps[1].analogy
    assert validate_diagram(d,' '.join(sources))['passed']
    d.steps[0].focus=[2]
    with pytest.raises(TeachingDesignError,match='焦点'):validate_diagram(d,' '.join(sources))


def test_office_fallback_preserves_source_diagram_canvas_and_footer(tmp_path):
    from PIL import Image
    from zhijiang.math_media import render_summary_png
    svg=tmp_path/'summary.svg';png=tmp_path/'summary.png'
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675"><rect width="1200" height="675" fill="#081623"/><rect x="45" y="630" width="100" height="25" fill="#FFFFFF"/></svg>',encoding='utf-8')
    render_summary_png(svg,png)
    with Image.open(png) as result:
        assert result.size==(1200,675) and result.getpixel((50,640))==(255,255,255)


def test_analogy_cannot_return_to_source_entities_or_add_guarantees():
    from zhijiang.teaching_design import check_analogy
    facts=[{'statement':'原文描述机器人模仿人类动作，但仍然存在适用条件。'}]
    check_analogy('就像舞伴对照对方的动作，更容易理解彼此的节奏。',facts)
    with pytest.raises(TeachingDesignError,match='技术对象'):
        check_analogy('就像舞伴互相观察，机器人就会觉得配合很舒服。',facts)
    with pytest.raises(TeachingDesignError,match='保证'):
        check_analogy('就像从不同方向看传球，这样才不会丢球。',facts)
    with pytest.raises(TeachingDesignError,match='保证'):
        check_analogy('就像换个厨房做菜，只要步骤对，就能做出一样的味道。',facts)


def test_source_example_is_preserved_instead_of_inventing_technical_analogy():
    from zhijiang.teaching_design import prefer_source_example,script_schema,bind_script_focus,compose_script
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:1];d.relations=[]
    facts=[{'id':1,'source_id':1,'source_quote':d.nodes[0].source_quote,'statement':'原文记录控制信号及其适用的观察条件。'},
           {'id':2,'source_id':2,'source_quote':'For instance, people pick up a cup by its handle.',
            'statement':'例如，人们通常通过杯子把手拿起杯子，保持原文所描述的使用习惯。'}]
    examples=prefer_source_example(d,facts,'解释时多用生活例子')
    assert examples==[2] and len(d.nodes)==2 and d.nodes[1].label in facts[1]['statement']
    schema=script_schema(d,facts,require_analogy=True,source_examples=examples)
    script=schema.model_validate({'steps':[{'fact_id':1},{'fact_id':2}],'example':None})
    narration=compose_script(bind_script_focus(script,d,facts),facts)
    assert narration[1].narration==facts[1]['statement'] and not narration[1].analogy
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        schema.model_validate({'steps':[{'fact_id':1},{'fact_id':2}],'example':{'fact_id':1,'analogy':'就像机器人伸手时不观察目标。'}})


def test_old_reviewed_scene_must_satisfy_current_source_example_policy():
    from types import SimpleNamespace
    from zhijiang.teaching_design import cached_source_examples_covered
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:1];d.relations=[]
    facts=[{'id':1,'source_id':1,'source_quote':d.nodes[0].source_quote,'statement':'原文记录控制信号及其适用的观察条件。'},
           {'id':2,'source_id':2,'source_quote':'For instance, people pick up a cup by its handle.','statement':'例如，人们通过杯子把手拿起杯子，使用习惯对应原文的例子。'}]
    assert not cached_source_examples_covered(SimpleNamespace(diagram=d),facts,'多用生活例子')
    assert cached_source_examples_covered(SimpleNamespace(diagram=d),facts,'不用类比')


def test_untranslated_or_truncated_reading_cache_is_regenerated(tmp_path):
    import json
    from zhijiang.teaching_design import source_reading,source_reading_fingerprint,SourceFactDraft
    from pydantic import ValidationError
    spans={1:'Observed data describes the initial state.'}
    class Client:
        calls=0
        def generate(self,schema,instruction,material):
            self.calls+=1
            return schema.model_validate({'facts':[{'source_id':1,'statement':'观测数据描述原文记录的初始状态。'}]})
    client=Client();path=tmp_path/'reading.json'
    path.write_text(json.dumps({'fingerprint':source_reading_fingerprint(client,spans),'facts':[
        {'id':1,'source_id':1,'source_quote':spans[1],'statement':'Observed data describes the initial state.'}]}),encoding='utf-8')
    facts,cached=source_reading(client,spans,path)
    assert not cached and client.calls==1 and facts[0]['statement']=='观测数据描述原文记录的初始状态。'
    assert source_reading(client,spans,path)[1] and client.calls==1
    with pytest.raises(ValidationError):
        SourceFactDraft(source_id=1,statement='观测数据描述原文记录的初始状态及其适用条-')


def test_source_fact_bounds_keep_chinese_and_scientific_names_without_unbounded_output():
    from zhijiang.teaching_design import SourceFactDraft
    from pydantic import ValidationError
    assert SourceFactDraft(source_id=1,statement='原文讨论水的化学名称H2O。').statement.endswith('H2O。')
    assert len(SourceFactDraft(source_id=1,statement='中'*119+'。').statement) == 120
    for statement in ('Observed state remains bounded。','中'*120+'。','中'*10+'。'):
        with pytest.raises(ValidationError):
            SourceFactDraft(source_id=1,statement=statement)


def test_source_fact_punctuation_normalization_preserves_words_and_rejects_clipped_endings():
    from zhijiang.teaching_design import SourceFactDraft
    from pydantic import ValidationError
    text='能先约分的可以先约分，再计算，结果相同'
    assert SourceFactDraft(source_id=3,statement=text).statement == text+'。'
    for clipped in ('观测数据描述原文记录的初始状态及其适用条-',
                    '观测数据描述原文记录的初始状态及其适用条=', '乘整数'):
        with pytest.raises(ValidationError):
            SourceFactDraft(source_id=3,statement=clipped)


def test_unrequested_analogy_is_rejected_without_losing_source_fact_steps():
    from zhijiang.teaching_design import script_schema
    from pydantic import ValidationError
    d=diagram();d.nodes=d.nodes[:1];d.relations=[]
    fact={'id':1,'source_id':1,'source_quote':d.nodes[0].source_quote,
          'statement':d.nodes[0].label+'描述原文记录的初始状态及其适用条件。'}
    schema=script_schema(d,[fact])
    assert schema.model_validate({'steps':[{'fact_id':1}],'example':None}).steps[0].fact_id==1
    for analogy in ('就像舞伴对照对方的动作保持配合。','三个人一起分一个披萨，每人分得三分之一。'):
        with pytest.raises(ValidationError):
            schema.model_validate({'steps':[{'fact_id':1}],'example':{'fact_id':1,'analogy':analogy}})


def test_scanned_quantity_question_is_not_taught_as_fact_and_cache_keeps_readable_method(tmp_path):
    import json
    from zhijiang.teaching_design import source_reading,source_reading_fingerprint,scanned_fact_issues
    spans={1:'每人取2个，3人一共取多少个?',2:'用分子乘整数的积作分子，分母不变。'}
    question='每人取2个，3人一共取多少个。'
    assert scanned_fact_issues(question,spans[1])
    assert not scanned_fact_issues('用分子乘整数的积作分子，分母不变。',spans[2])
    class Client:
        def generate(self,*args):raise AssertionError('Valid remaining facts should be reused.')
    client=Client();path=tmp_path/'source-reading.json'
    facts=[{'id':i,'source_id':i,'source_quote':spans[i],'statement':text}
           for i,text in [(1,question),(2,spans[2])]]
    path.write_text(json.dumps({'fingerprint':source_reading_fingerprint(client,spans,ocr=True),
        'facts':facts,'status':'draft_requires_semantic_review'}),encoding='utf8')
    kept,cached=source_reading(client,spans,path,ocr=True)
    assert cached and kept==facts[1:]
    saved=json.loads(path.read_text(encoding='utf8'))
    assert saved['rejected_facts'][0]['statement']==question and saved['facts']==kept


def test_literal_node_name_repairs_wrong_numeric_anchor_and_rechecks_cached_structure(tmp_path):
    from zhijiang.teaching_design import resolve_design,save_structure,load_structure
    source='分数乘整数，用分子乘整数的积作分子，分母不变；式子包含数字2。'
    draft=TeachingDesignDraft(representation='source_figure',rationale='保留原文页面逐步讲解运算方法。',question='怎样理解运算方法？',
        nodes=[{'id':1,'label':'整数','source_id':1,'source_term':'2'},
               {'id':2,'label':'分母','source_id':1,'source_term':'分母'}])
    repairs=[];resolved=resolve_design(draft,{1:source},repairs)
    assert draft.nodes[0].source_term=='2' and resolved.nodes[0].source_term=='整数'
    assert repairs[0]['repair']=='literal_node_name' and repairs[0]['from_source_term']=='2'
    assert validate_diagram(resolved,source,require_steps=False)['passed']
    resolved.nodes[0].source_term='2'
    with pytest.raises(TeachingDesignError,match='节点名称'):
        validate_diagram(resolved,source,require_steps=False)
    path=tmp_path/'structure.json';save_structure(path,'input',resolved);repairs=[]
    cached=load_structure(path,'input',source,repairs=repairs)
    assert cached.nodes[0].source_term=='整数' and repairs[0]['repair']=='literal_node_name'


def test_literal_node_binding_keeps_translations_and_preserves_source_spacing():
    from zhijiang.teaching_design import bind_literal_node_terms
    from zhijiang.models import TeachingNode
    nodes=[TeachingNode(id=1,label='温度',source_quote='温 度与3秒后的状态均有记录。',source_term='3'),
           TeachingNode(id=2,label='观测数据',source_quote='Recorded observations support the training objective.',source_term='observations')]
    bind_literal_node_terms(nodes)
    assert nodes[0].source_term=='温 度' and nodes[1].source_term=='observations'


def test_rejected_ocr_draft_recovers_literal_definition_without_numeric_rewrite(tmp_path):
    import json
    from zhijiang.teaching_design import source_reading
    source='4 想：求12L的 是多少 在这里，一个数乘几分之几表示的是求这个数的几分之几是多少。'
    class Client:
        stages=[]
        def generate(self,schema,instruction,material):
            self.stages.append(schema.__name__)
            if schema.__name__=='SourceFactsDraft':
                return schema.model_validate({'facts':[{'source_id':6,'statement':'求12L的1/4是多少，一个数乘几分之几表示求这个数的几分之几是多少。'}]})
            assert schema.__name__=='SourceFactClauseSelection'
            candidates=json.loads(material)['source_clauses']
            assert all('12' not in item['statement'] and '1/4' not in item['statement'] for item in candidates)
            chosen=next(item['id'] for item in candidates if item['statement'].startswith('一个数'))
            return schema.model_validate({'clause_ids':[chosen]})
    client=Client();path=tmp_path/'reading.json'
    facts,cached=source_reading(client,{6:source},path,ocr=True)
    assert not cached and len(facts)==1 and facts[0]['source_id']==6
    assert facts[0]['statement']=='一个数乘几分之几表示的是求这个数的几分之几是多少。'
    saved=json.loads(path.read_text(encoding='utf8'))
    assert len(saved['rejected_facts'])==1 and saved['repairs'][0]['method']=='literal_source_fact_clauses'
    assert source_reading(client,{6:source},path,ocr=True)[1]
    assert client.stages==['SourceFactsDraft','SourceFactClauseSelection']


def test_annotation_labels_allow_quantity_phrases_and_actions_without_subject_vocabulary():
    from zhijiang.teaching_design import fact_labels,structure_schema
    definition='一个数乘几分之几表示的是求这个数的几分之几是多少。'
    facts=[{'id':1,'source_id':6,'source_quote':definition,'statement':definition}]
    labels=fact_labels(facts)
    assert '一个数' in labels and '几分之几' in labels and all(label in definition for label in labels)
    schema=structure_schema({6:definition},source_annotation=True,facts=facts)
    draft=schema.model_validate({'representation':'source_figure','rationale':'逐步标注原文的数量短语及其含义。','question':'怎样理解原文定义？',
        'nodes':[{'id':1,'label':'几分之几','source_id':6,'source_term':'几分之几'}],'relations':[],'steps':[]})
    assert draft.nodes[0].label=='几分之几'
    action='先增加再减少，随后继续改变。'
    action_labels=fact_labels([{'statement':action}])
    assert '增加' in action_labels and all(label in action for label in action_labels)


def test_ocr_fact_format_failure_recovers_only_literal_source_and_does_not_mask_transport_error(tmp_path):
    import json
    from zhijiang.agents import GenerationError
    from zhijiang.teaching_design import source_reading
    source='分数乘分数，用分子相乘的积作分子，用分母相乘的积作分母。'
    class Client:
        def __init__(self,error):self.error=error;self.calls=0
        def generate(self,schema,instruction,material):
            self.calls+=1
            if schema.__name__=='SourceFactsDraft':raise GenerationError(self.error)
            clauses=json.loads(material)['source_clauses']
            key=next(item['id'] for item in clauses if item['statement']==source)
            return schema.model_validate({'clause_ids':[key]})
    client=Client('本机 Ollama 返回不符合数据契约的 JSON：facts.1.statement:string_too_short')
    path=tmp_path/'reading.json';facts,cached=source_reading(client,{1:source},path,ocr=True)
    assert not cached and facts[0]['statement']==source and client.calls==2
    saved=json.loads(path.read_text(encoding='utf8'))
    assert saved['rejected_facts'][0]['kind']=='fact_format_error'
    client=Client('本机 Ollama 推理超时')
    with pytest.raises(GenerationError,match='超时'):
        source_reading(client,{1:source},ocr=True)
    assert client.calls==1


def test_fact_container_keeps_valid_definition_when_optional_records_fail_statement_contract(tmp_path):
    import json
    from zhijiang.teaching_design import source_reading
    spans={1:'怎样计算分数乘法？',2:'一个整数乘分数有时表示几个相同的分数相加，有时表示这个整数的几分之几。',
           3:'8 ×5 2.4× 3 18×14'}
    class Client:
        calls=0
        def generate(self,schema,instruction,material):
            self.calls+=1
            return schema.model_validate({'facts':[{'source_id':i,'statement':text} for i,text in spans.items()]})
    client=Client();path=tmp_path/'reading.json'
    facts,cached=source_reading(client,spans,path,ocr=True)
    assert not cached and len(facts)==1 and facts[0]['source_id']==2 and facts[0]['statement']==spans[2]
    rejected=json.loads(path.read_text(encoding='utf8'))['rejected_facts']
    assert {item['source_id'] for item in rejected}=={1,3}
    assert source_reading(client,spans,path,ocr=True)[1] and client.calls==1


def test_single_character_predicate_is_preserved_but_conjunction_is_not_a_relation():
    from zhijiang.teaching_design import structure_schema,resolve_design
    from zhijiang.models import TeachingSourceFact
    source='正方形是矩形，但其边长条件更严格。'
    facts=[{'id':1,'source_id':1,'source_quote':source,'statement':source}]
    schema=structure_schema({1:source},facts=facts)
    raw={'representation':'relationship','rationale':'按原文明确的类别关系讲解概念。','question':'两种图形有什么关系？',
         'nodes':[{'id':1,'label':'正方形','source_id':1,'source_term':'正方形'},
                  {'id':2,'label':'矩形','source_id':1,'source_term':'矩形'}],
         'relations':[{'id':1,'source':1,'target':2,'source_fact_id':1}],'steps':[]}
    draft=resolve_design(schema.model_validate(raw),{1:source},facts=facts)
    draft.source_facts=[TeachingSourceFact.model_validate(fact) for fact in facts]
    assert draft.relations[0].label=='是' and validate_diagram(draft,source,require_steps=False)['passed']
    source='温度和湿度分别记录在不同表格中。'
    facts=[{'id':1,'source_id':1,'source_quote':source,'statement':source}]
    raw['nodes']=[{'id':1,'label':'温度','source_id':1,'source_term':'温度'},
                  {'id':2,'label':'湿度','source_id':1,'source_term':'湿度'}]
    with pytest.raises(TeachingDesignError,match='主语'):
        resolve_design(structure_schema({1:source},facts=facts).model_validate(raw),{1:source},facts=facts)


@pytest.mark.parametrize('all_bad',[False,True])
def test_ocr_fact_reading_records_unbound_calculations_without_accepting_them(tmp_path,all_bad):
    import json
    from zhijiang.teaching_design import source_reading
    spans={1:'×3=(个)9 6 3 3 1'}
    if not all_bad:spans[2]='用分子乘整数的积作分子，分母不变。'
    class Client:
        calls=0
        def generate(self,schema,instruction,material):
            self.calls+=1
            facts=[{'source_id':1,'statement':'3×1/9等于6/9个。'}]
            if not all_bad:
                facts.append({'source_id':2,'statement':spans[2]})
            return schema.model_validate({'facts':facts})
    client=Client();path=tmp_path/'reading.json'
    if all_bad:
        with pytest.raises(TeachingDesignError,match='OCR数值'):
            source_reading(client,spans,path,ocr=True)
    else:
        facts,cached=source_reading(client,spans,path,ocr=True)
        assert not cached and len(facts)==1 and facts[0]['source_id']==2
        assert source_reading(client,spans,path,ocr=True)[1] and client.calls==1
    saved=json.loads(path.read_text(encoding='utf8'))
    assert saved['rejected_facts'][0]['source_id']==1
    assert saved['rejected_facts'][0]['statement']=='3×1/9等于6/9个。'
    assert saved['facts']==[] if all_bad else len(saved['facts'])==1


def test_empty_chinese_label_catalog_is_rejected_before_schema_construction():
    from zhijiang.teaching_design import structure_schema
    spans={1:'Observed data describes the initial state.'}
    with pytest.raises(TeachingDesignError,match='中文对象'):
        structure_schema(spans,facts=[{'id':1,'source_id':1,'source_quote':spans[1],
            'statement':'Observed data describes the initial state.'}])
    with pytest.raises(TeachingDesignError,match='中文对象'):structure_schema(spans,facts=[])
    with pytest.raises(TeachingDesignError,match='来源片段'):structure_schema({})


def test_review_preserves_short_object_meanings_without_inventing_a_statement():
    from zhijiang.teaching_design import MeaningCheck
    from pydantic import ValidationError
    result=MeaningCheck(id=1,supported=True,source_meaning='复杂物体。',
        reason='原文仅提及复杂物体，没有额外声明其运动或效果。')
    assert result.source_meaning=='复杂物体。'
    assert 'pattern' not in MeaningCheck.model_json_schema()['properties']['source_meaning']
    with pytest.raises(ValidationError):
        MeaningCheck(id=1,supported=True,source_meaning='复杂物体。',reason='正确')


def test_explicit_source_operations_cannot_skip_the_follow_up_or_reverse_order():
    from zhijiang.teaching_design import preserve_source_sequence,script_schema,cached_source_sequence_covered
    from types import SimpleNamespace
    from pydantic import ValidationError
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:1];d.relations=[]
    first='The process starts with heating the material for the initial preparation.'
    second='We then measure the sample under the stated conditions.'
    d.nodes[0].label='材料';d.nodes[0].source_quote=first
    facts=[{'id':1,'source_id':8,'source_quote':first,'statement':'这一过程开始于加热材料，进行初始准备。'},
           {'id':2,'source_id':9,'source_quote':second,'statement':'随后按原文条件测量样品，保留原文的操作次序。'}]
    assert not cached_source_sequence_covered(SimpleNamespace(diagram=d),facts)
    required=preserve_source_sequence(d,facts)
    assert required==[1,2] and len(d.nodes)==2
    schema=script_schema(d,facts,source_sequence=required)
    assert schema.model_validate({'steps':[{'fact_id':1},{'fact_id':2}]}).example is None
    with pytest.raises(ValidationError,match='source_sequence_order'):
        schema.model_validate({'steps':[{'fact_id':2},{'fact_id':1}]})


def test_annotation_terms_do_not_include_citation_punctuation_and_use_free_ids():
    from zhijiang.teaching_design import fact_labels,prefer_source_example
    facts=[{'id':1,'source_id':1,'source_quote':'For example, the material is compared with a reference.',
        'statement':'例如，使用测量方法[Author和Other, 2020]比较材料与参照物。'}]
    assert not any('[' in label or ']' in label for label in fact_labels(facts))
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:1];d.nodes[0].id=6;d.relations=[]
    # Explicit numeric examples are intentionally left to numeric scenes.
    facts[0]['statement']='例如，使用测量方法比较材料与参照物，保留原文条件。'
    assert prefer_source_example(d,facts,'生活例子')==[1]
    assert [node.id for node in d.nodes]==[6,1]


def test_topic_fact_is_required_even_when_neighboring_facts_are_grounded():
    from zhijiang.teaching_design import preserve_topic_focus,script_schema,cached_topic_focus_covered
    from types import SimpleNamespace
    from pydantic import ValidationError
    d=diagram();d.representation='source_figure';d.nodes=d.nodes[:1];d.nodes[0].label='测量结果';d.relations=[]
    facts=[{'id':1,'source_id':1,'source_quote':d.nodes[0].source_quote,'statement':'测量结果记录了观察条件和可比较的结果。'},
           {'id':2,'source_id':2,'source_quote':'Repeated sampling reduces the stated measurement uncertainty.',
            'statement':'重复采样有助于降低所描述的测量不确定性。'}]
    assert not cached_topic_focus_covered(SimpleNamespace(diagram=d),facts,'测量不确定性的作用')
    required=preserve_topic_focus(d,facts,'测量不确定性的作用')
    assert required==[2] and d.nodes[1].label=='测量不确定性'
    schema=script_schema(d,facts,topic_facts=required)
    assert schema.model_validate({'steps':[{'fact_id':1},{'fact_id':2}]}).steps[1].fact_id==2
    with pytest.raises(ValidationError):schema.model_validate({'steps':[{'fact_id':1}]})


def test_source_phrase_modifiers_are_not_dropped_from_topic_name():
    from zhijiang.teaching_design import fact_labels
    assert '多模态大语言模型' in fact_labels([{'statement':'使用多模态大语言模型来比较候选结果与人的偏好。'}])
