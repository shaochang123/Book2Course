import io
import json
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest
import resvg_py
from PIL import Image, ImageChops

from zhijiang.agents import GenerationError
from zhijiang.deck_planning import DeckPageChoice
from zhijiang.presentation_templates import get_template
from zhijiang.teaching_exhibits import (TeachingExhibitDraft, validate_exhibit,
    plan_exhibit, arithmetic_value, enrich_teaching_exhibits)
from zhijiang.exhibit_svg import exhibit_svg, exhibit_cues


def fixture(form):
    return {'form':form,'items':[{'label':'输入','detail':'待处理的信息','sentence_id':1},
        {'label':'结果','detail':'处理后的输出','sentence_id':1}], 'columns':[], 'rows':[],
        'links':[],'expression':'','expression_sentence_id':None,'context':'','context_sentence_id':None,'pictures':[]}


@pytest.mark.parametrize('template',['classic','paper','academic','editorial'])
@pytest.mark.parametrize('form',['contrast','record','matrix','relations','timeline','equation','annotated','statement'])
def test_open_source_exhibits_render_all_templates_without_shrinking_or_card_walls(form,template):
    exhibit=fixture(form)
    if form=='matrix':exhibit.update(items=[],columns=['输入','结果'],rows=[
        {'cells':['新信息','待处理'],'sentence_id':1},{'cells':['旧信息','已处理'],'sentence_id':2}])
    if form=='relations':exhibit['links']=[{'source':1,'target':2,'label':'产生','sentence_id':1,'kind':'directed'}]
    if form=='timeline':exhibit['items']=[{'label':'1900','detail':'事件一','sentence_id':1},{'label':'2000','detail':'事件二','sentence_id':2}]
    if form=='equation':exhibit.update(expression='(3+1)×(2+1)=12',context='计数条件保持不变')
    svg,boxes,_=exhibit_svg(exhibit,get_template(template),1080,490)
    root=ET.fromstring(svg);ns='{http://www.w3.org/2000/svg}'
    assert all(float(t.get('font-size'))>=28 for t in root.findall('.//'+ns+'text'))
    assert all(0<=x and 0<=y and x+w<=1081 and y+h<=491 for x,y,w,h in boxes)
    # Whole-height filled cards are never the representation of comparisons,
    # annotations, relations, statements, equations or time lines.
    if form not in {'record','matrix'}:
        assert not any(float(r.get('height'))>200 for r in root.findall('.//'+ns+'rect'))
    im=Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode())))
    assert im.mode=='RGBA' and im.getpixel((0,0))[3]==0


def test_matrix_requires_actual_values_and_preserves_column_pairing_for_review():
    segment=SimpleNamespace(narration='输入与结果组成记录：新信息待处理。输入与结果组成记录：旧信息已处理。')
    data=fixture('matrix');data.update(items=[],columns=['输入','结果'],rows=[
        {'cells':['新信息','待处理'],'sentence_id':1},{'cells':['旧信息','已处理'],'sentence_id':2}])
    validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)
    data['rows'][1]['cells'][1]='100'
    with pytest.raises(ValueError,match='每个表格值'):validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)


@pytest.mark.parametrize('expr',['__import__("os")','a+1','2**1000','2/0','abs(-2)'])
def test_arithmetic_language_is_bounded_data_not_model_code(expr):
    with pytest.raises((ValueError,ZeroDivisionError)):arithmetic_value(expr)


def test_computed_equality_and_its_source_are_both_required():
    segment=SimpleNamespace(narration='两个属性分别有三种和两种取值，加上各自的通配符共有十二个候选。')
    data=fixture('equation');data.update(items=[{'label':'属性','detail':'给定取值范围','sentence_id':1}],
        expression='(3+1)×(2+1)=12',expression_sentence_id=1,context='加上各自的通配符',context_sentence_id=1)
    validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)
    data['expression']='(3+1)×(2+1)=13'
    with pytest.raises(ValueError,match='计算不成立'):validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)
    data['expression']='(99+1)×(2+1)=300'
    with pytest.raises(ValueError,match='依据未提供'):validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)


def test_same_page_cooccurrence_does_not_create_exhibit_arrow():
    segment=SimpleNamespace(narration='输入需要处理。结果需要核对。')
    data=fixture('relations');data['items'][1]['sentence_id']=2
    data['links']=[{'source':1,'target':2,'label':'需要','sentence_id':1,'kind':'directed'}]
    with pytest.raises(ValueError,match='主谓宾'):validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)


def test_relation_label_tracks_its_own_curved_branch_instead_of_floating_above_the_source():
    data=fixture('relations');data['items'].append({'label':'第二结果','detail':'','sentence_id':1})
    for item in data['items']:item['detail']=''
    data['links']=[{'source':1,'target':2,'label':'提供','sentence_id':1,'kind':'directed'},
        {'source':1,'target':3,'label':'产生','sentence_id':1,'kind':'directed'}]
    svg,_,_=exhibit_svg(data,get_template('editorial'),1080,490)
    root=ET.fromstring(svg);ns='{http://www.w3.org/2000/svg}'
    labels=[t for t in root.findall('.//'+ns+'text') if t.text in {'提供','产生'}]
    assert all(t.get('text-anchor')=='middle' for t in labels)
    assert float(labels[0].get('y'))<float(labels[1].get('y'))
    assert all(350<float(t.get('x'))<730 for t in labels)


def test_recent_forms_never_force_new_facts_or_shapes_and_cached_acceptance_is_reviewed(tmp_path):
    calls=[]
    class Model:
        model='mock';base_url='local'
        def generate(self,schema,instruction,material):
            calls.append((schema.__name__,json.loads(material)))
            if schema.__name__=='TeachingExhibitIntent':return schema.model_validate({'form':'contrast','focus_sentence_ids':[1],'reason':'输入与结果存在明确差异'})
            if schema.__name__=='TeachingExhibitDraft':
                data=fixture('contrast')
                for item in data['items']:item['detail']=''
                return schema.model_validate(data)
            return schema.model_validate({**{n:'faithful' for n in schema.model_fields if n!='issues'},'issues':''})
    segment=SimpleNamespace(title='输入和结果',narration='输入经过处理产生结果。')
    choice=DeckPageChoice(segment_id=1,role='comparison',layout='wide',bullet_ids=[1])
    path=tmp_path/'scene.json'
    saved=plan_exhibit(segment,choice,[],Model(),previous_forms=['contrast']*3,path=path)
    assert saved['accepted'] and saved['exhibit']['form']=='contrast'
    assert calls[0][1]['recent_forms']==['contrast']*3
    assert plan_exhibit(segment,choice,[],Model(),path=path)==saved and len(calls)==3
    saved['review']['item_1']='unsupported';path.write_text(json.dumps(saved),encoding='utf-8')
    plan_exhibit(segment,choice,[],Model(),path=path)
    assert len(calls)==6


def test_rejected_richer_example_is_logged_not_marked_accepted(tmp_path):
    class Model:
        def generate(self,schema,*args):
            if schema.__name__=='TeachingExhibitIntent':return schema.model_validate({'form':'contrast','focus_sentence_ids':[1],'reason':'输入与结果存在明确差异'})
            if schema.__name__=='TeachingExhibitDraft':
                data=fixture('contrast')
                for item in data['items']:item['detail']=''
                return schema.model_validate(data)
            return schema.model_validate({**{n:'unsupported' for n in schema.model_fields if n!='issues'},'issues':'例子没有依据'})
    result=plan_exhibit(SimpleNamespace(title='输入和结果',narration='输入经过处理产生结果。'),
        DeckPageChoice(segment_id=1,role='comparison',layout='wide',bullet_ids=[1]),[],Model(),path=tmp_path/'scene.json')
    assert not result['accepted'] and len(result['attempts'])==3 and 'exhibit' not in result
    assert result['fallback']=='previous_reviewed_visual'


def test_model_transport_failure_does_not_become_demo_or_safe_example(tmp_path):
    class Model:
        def generate(self,*args):raise GenerationError('模型离线')
    with pytest.raises(GenerationError,match='模型离线'):
        plan_exhibit(SimpleNamespace(title='输入和结果',narration='输入经过处理产生结果。'),
            DeckPageChoice(segment_id=1,role='comparison',layout='wide',bullet_ids=[1]),[],Model(),path=tmp_path/'scene.json')
    assert not (tmp_path/'scene.json').exists()


def test_object_picture_must_match_candidate_identity_not_nearby_entity():
    segment=SimpleNamespace(narration='电池为灯泡提供电能。')
    data=fixture('statement');data['items']=[{'label':'电池','detail':'提供电能','sentence_id':1}]
    data['pictures']=[{'asset_id':'bulb','item_id':1,'object_name':'灯泡','sentence_id':1}]
    with pytest.raises(ValueError,match='绑定的项目'):
        validate_exhibit(TeachingExhibitDraft.model_validate(data),segment,[{'id':'bulb','entity_aliases':['灯泡']}])
    data['pictures'][0]['asset_id']='wrong'
    with pytest.raises(ValueError,match='检索候选'):
        validate_exhibit(TeachingExhibitDraft.model_validate(data),segment,[{'id':'bulb','entity_aliases':['灯泡']}])


def test_cues_follow_complete_source_sentences_and_end_at_shared_static_page():
    exhibit=fixture('record');exhibit['items'][1]['sentence_id']=2
    cues=exhibit_cues(exhibit,'输入先接受信息。结果在处理后产生。最后检查。')
    assert cues[0]['fraction']==0 and cues[-1]['active'] is None and cues[-1]['reveal']==2
    assert all(a['fraction']<b['fraction'] for a,b in zip(cues,cues[1:]))
    assert cues[1]['source_sentence_id']==2
    same=fixture('record');same['items']*=2
    assert len(exhibit_cues(same,'输入与结果由当前信息表示。'))==5


def test_relation_drawing_changes_intermediate_frames_without_moving_object_identity():
    exhibit=fixture('relations');exhibit['links']=[{'source':1,'target':2,'label':'产生','sentence_id':1,'kind':'directed'}]
    frames=[];geometry=[]
    for progress in [.2,.6,1.]:
        svg,boxes,_=exhibit_svg(exhibit,get_template('editorial'),1080,490,active=2,progress=progress)
        frames.append(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode()))));geometry.append(boxes)
    assert geometry[0]==geometry[1]==geometry[2]
    assert all(box[2]<300 for box in geometry[0])
    root=ET.fromstring(exhibit_svg(exhibit,get_template('editorial'),1080,490)[0])
    ns='{http://www.w3.org/2000/svg}'
    arrow=next(p for p in root.findall('.//'+ns+'path') if p.get('marker-end'))
    start=float(arrow.get('d').split('M',1)[1].split(',',1)[0])
    assert 0<start-(geometry[0][0][0]+geometry[0][0][2])<20
    assert ImageChops.difference(frames[0],frames[-1]).getbbox() is not None


def test_director_wide_and_captioned_compositions_survive_not_only_template_colors():
    exhibit=fixture('contrast')
    _,cols,_=exhibit_svg(exhibit,get_template('editorial'),1080,490,layout='wide')
    _,rows,_=exhibit_svg(exhibit,get_template('editorial'),1080,490,layout='captioned')
    assert cols[0][1]==cols[1][1] and cols[0][0]!=cols[1][0]
    assert rows[0][0]==rows[1][0] and rows[0][1]!=rows[1][1]


def test_literal_fragment_and_attribution_repair_preserves_actual_source_roles():
    from zhijiang.teaching_exhibits import normalize_exhibit
    segment=SimpleNamespace(narration='资料把温度描述为：物体的冷热程度。流体从高压区域流向低压区域。')
    data=fixture('statement');data['items']=[{'label':'资料','detail':'把温度描述','sentence_id':1},
        {'label':'流体','detail':'从高压区域流向','sentence_id':2}]
    fixed=normalize_exhibit(TeachingExhibitDraft.model_validate(data),segment)
    assert fixed.items[0].label=='温度' and fixed.items[0].detail=='物体的冷热程度'
    assert fixed.items[1].detail=='流体从高压区域流向低压区域'
    validate_exhibit(fixed,segment)


def test_explicit_field_value_repair_does_not_embed_a_specific_textbook_rule():
    from zhijiang.teaching_exhibits import normalize_exhibit
    segment=SimpleNamespace(narration='设备记录可以写成：温度适中，状态正常。温度和状态是字段。')
    data=fixture('record');data['items']=[{'label':'设备记录','detail':'温度适中','sentence_id':1},
        {'label':'状态','detail':'正常','sentence_id':2}]
    fixed=normalize_exhibit(TeachingExhibitDraft.model_validate(data),segment)
    assert [(i.label,i.detail,i.sentence_id) for i in fixed.items]==[('温度','适中',1),('状态','正常',1)]


def test_actual_relations_are_selected_from_literal_options_not_generated_coordinate_code(tmp_path):
    from zhijiang.exhibit_relations import relation_options, prefer_relation_exhibit
    segment=SimpleNamespace(title='从信号到指令',narration='传感器采集温度信号。控制器利用温度信号产生指令。')
    options=relation_options(segment)
    chosen=[o['id'] for o in options if (o['subject'],o['predicate'],o['object']) in {
        ('控制器','利用','温度信号'),('控制器','产生','指令')}]
    assert len(chosen)==2
    assert not any(o['subject']=='控制器' and o['predicate']=='利用' and o['object']=='指令' for o in options)
    class Model:
        def generate(self,schema,*args):
            if schema.__name__=='TeachingRelationSelection':return schema.model_validate({'option_ids':chosen,'reason':'信号使用与指令产生是本页主要关系'})
            return schema.model_validate({**{n:'faithful' for n in schema.model_fields if n!='issues'},'issues':''})
    previous={'accepted':False,'reason':'原稿拒绝'}
    result=prefer_relation_exhibit(segment,previous,Model(),tmp_path/'graph.json')
    assert result['accepted'] and result['exhibit']['form']=='relations'
    assert len(result['exhibit']['links'])==2 and result['previous_exhibit']==previous
    assert prefer_relation_exhibit(segment,previous,Model(),tmp_path/'graph.json')['accepted']


def test_long_explanation_paginated_without_losing_any_source_item():
    from zhijiang.exhibit_svg import exhibit_pages
    data=fixture('statement');data['items']=[{'label':'完整名称较长的讲解对象'+str(i),
        'detail':'这是较长但完整的实际说明，不以缩小字号或截断文字的方式强行填入单页。','sentence_id':i+1} for i in range(4)]
    parts=exhibit_pages(data,get_template('editorial'),1080,490)
    assert len(parts)==2 and [i for _,ids in parts for i in ids]==[1,2,3,4]
    assert [i for p,_ in parts for i in p['items']]==data['items']


def test_listed_nouns_and_serial_verb_objects_cannot_become_actors():
    from zhijiang.exhibit_relations import relation_options
    segment=SimpleNamespace(title='数据处理',narration='发展历程、应用和阅读材料帮助理解。色泽、根蒂和敲声是特征。控制器利用温度信号产生指令。')
    options=relation_options(segment)
    assert not any(o['predicate'] in {'应用','敲','敲声'} for o in options)
    assert not any(o['subject']=='温度信号' and o['predicate']=='产生' for o in options)
    assert any((o['subject'],o['predicate'],o['object'])==('控制器','产生','指令') for o in options)


def test_complete_nominal_compounds_are_not_copular_or_causative_fragments():
    from zhijiang.slide_story import visual_object_name, ordered_source_relation
    assert visual_object_name('监督学习','监督学习与无监督学习是不同设置。')
    assert visual_object_name('无监督学习','监督学习与无监督学习是不同设置。')
    assert not visual_object_name('分类和回归是监督','分类和回归是监督学习的代表。')
    assert not visual_object_name('使模型','而是使模型适用于新情况。')
    assert not ordered_source_relation('表示方式能够表达候选规则','表示方式','能够','候选规则')
    assert visual_object_name('气体交换','气体交换涉及氧气跨膜扩散。')
    assert not visual_object_name('温度信号产生','温度信号产生指令。')


def test_matrix_multi_sentence_sources_keep_literal_rows_and_reject_new_values():
    data=fixture('matrix');data.update(items=[],columns=['组合','错误个数'],rows=[
        {'cells':['零零','零'],'sentence_id':1,'source_ids':[1,2]},
        {'cells':['一一','二'],'sentence_id':1,'source_ids':[1,2]}])
    segment=SimpleNamespace(narration='组合有零零、一一。错误个数依次为零、二。')
    validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)
    data['rows'][1]['cells'][1]='三'
    with pytest.raises(ValueError,match='每个表格值'):validate_exhibit(TeachingExhibitDraft.model_validate(data),segment)


def test_equation_without_redundant_labels_renders_and_starts_at_zero():
    data=fixture('equation');data.update(items=[],expression='3+1=4',context='计数条件保持不变')
    svg,boxes,_=exhibit_svg(data,get_template('editorial'),1080,490)
    assert '3+1=4' in svg.decode() and boxes==[]
    cues=exhibit_cues(data,'先计数，再加一。')
    assert cues[0]['fraction']==0 and cues[-1]['fraction']<1
    assert [(c['reveal'],c['active']) for c in cues]==[(0,None),(1,1),(1,None)]
    first,_,_=exhibit_svg(data,get_template('editorial'),1080,490,reveal=0)
    assert '3+1 = ?' in first.decode() and '3+1=4' not in first.decode()


def test_generic_arithmetic_candidates_are_computed_not_source_approved():
    from zhijiang.teaching_exhibits import arithmetic_options
    options=arithmetic_options({0.,1.,2.,3.,37.},37.)
    assert '(2+1)*(2+1)*(3+1)+1=37' in options
    assert all(abs(arithmetic_value(x.split('=')[0])-37)<1e-8 for x in options)
    assert all('37' not in x.split('=')[0] for x in options)
    assert '8-1=7' in arithmetic_options({1.,3.,4.,7.,8.},7.)


def test_literal_record_uses_other_source_mentions_when_tokenizer_merges_value():
    from zhijiang.teaching_exhibits import literal_record_pairs
    sentences=['记录可以写成：温度适中，状态正常。','温度和状态是字段。']
    assert [(p['label'],p['detail']) for p in literal_record_pairs(sentences)]==[('温度','适中'),('状态','正常')]


def test_record_does_not_treat_a_merged_action_word_as_a_field():
    segment=SimpleNamespace(narration='实验中要严格控制温度不变，并记录电压。')
    draft=TeachingExhibitDraft(form='record',items=[
        {'label':'严格控制','detail':'温度不变','sentence_id':1},
        {'label':'电压','detail':'记录电压','sentence_id':1}])
    with pytest.raises(ValueError,match='字段名不能是动作'):validate_exhibit(draft,segment)


def test_unique_literal_item_source_id_is_repaired_before_semantic_review():
    from zhijiang.teaching_exhibits import normalize_exhibit
    segment=SimpleNamespace(narration='训练样本用于训练。这里解释未知分布。')
    draft=TeachingExhibitDraft(form='statement',items=[{'label':'训练样本','detail':'用于训练','sentence_id':2}])
    fixed=normalize_exhibit(draft,segment)
    assert fixed.items[0].sentence_id==1 and fixed.items[0].label==draft.items[0].label
    validate_exhibit(fixed,segment)


def test_coordinated_category_names_remain_complete_names():
    from zhijiang.slide_story import visual_object_name
    assert visual_object_name('分类和回归','分类和回归是监督学习的代表。')
    assert not visual_object_name('分类和回归是监督','分类和回归是监督学习的代表。')


def test_relation_cannot_remove_negation_from_actor_or_predicate():
    from zhijiang.slide_story import ordered_source_relation
    assert not ordered_source_relation('控制器不产生指令','控制器','产生','指令')
    assert not ordered_source_relation('不等于控制器产生指令','控制器','产生','指令')
    assert ordered_source_relation('控制器产生指令','控制器','产生','指令')
    assert not ordered_source_relation('定律只适用于温度等条件保持不变的导体',
        '温度等条件','保持不变','导体')


def test_relation_options_do_not_turn_a_reporting_verb_or_noun_modifier_into_the_actor():
    from zhijiang.exhibit_relations import relation_options
    a=relation_options(SimpleNamespace(title='样本来源',narration='教材通常假设样本独立地来自同一个未知分布。'))
    assert not any(x['subject'] in {'假设样本','教材通常假设'} for x in a)
    b=relation_options(SimpleNamespace(title='表示与规则',narration='所选表示方式能够表达的候选规则集合。'))
    assert not any(x['predicate']=='候选' for x in b)
    c=relation_options(SimpleNamespace(title='通气与交换',narration='空气在肺泡处完成气体交换。气体交换涉及氧气跨膜扩散。'))
    assert not any(x['subject']=='肺泡处' and x['predicate']=='完成' for x in c)
    assert not any((x['subject'],x['predicate'])==('气体','交换') for x in c)


def test_preposition_guard_does_not_mistake_a_comparison_verb_suffix_for_a_location():
    from zhijiang.slide_story import ordered_source_relation
    from zhijiang.exhibit_relations import relation_options
    text='各元件的电压之和正好等于电源提供的总电压。'
    assert ordered_source_relation(text,'电源','提供','总电压')
    options=relation_options(SimpleNamespace(title='电压关系',narration=text))
    assert any((x['subject'],x['predicate'],x['object'])==('电源','提供','总电压') for x in options)
    assert not ordered_source_relation('空气在肺泡处完成气体交换','肺泡处','完成','气体交换')


def test_explicit_count_example_offers_computed_equations_but_not_unsupported_claims():
    from zhijiang.teaching_exhibits import explicit_count_equations
    assert '(2+1)*(2+1)*(3+1)+1=37' in explicit_count_equations(
        '三个属性分别有三、二、二种取值，加上各自的通配符，再加空假设，共三十七个候选。')
    assert explicit_count_equations('三位同学读二本书，共五种意见。')==[]
    assert '8-1=7' in explicit_count_equations('共有八个选择。删掉一个不合格的，剩七个。')


def test_subtraction_keeps_the_removed_case_visible_as_source_context():
    from zhijiang.teaching_exhibits import normalize_exhibit
    segment=SimpleNamespace(narration='共有八个选择。全选方案不合格，必须删掉；其余剩七个。')
    draft=TeachingExhibitDraft(form='equation',expression='8-1=7',expression_sentence_id=2,
        context='共有八个选择',context_sentence_id=1)
    fixed=normalize_exhibit(draft,segment)
    assert fixed.context=='全选方案不合格，必须删掉' and fixed.context_sentence_id==2
    validate_exhibit(fixed,segment)


def test_parallel_enumerations_form_a_conditioned_matrix_without_invented_values():
    from zhijiang.teaching_exhibits import literal_parallel_matrix
    segment=SimpleNamespace(narration='两个点有零零、零一、一零、一一四种组合。'
        '如果固定预测为零零，错误个数依次是零、一、一、二。')
    draft=literal_parallel_matrix(segment)
    assert draft is not None and draft.form=='matrix'
    assert draft.columns==['组合','错误个数']
    assert [r.cells for r in draft.rows]==[['零零','零'],['零一','一'],['一零','一'],['一一','二']]
    assert draft.context=='如果固定预测为零零'
    validate_exhibit(draft,segment)
    assert literal_parallel_matrix(SimpleNamespace(narration='有甲、乙、丙三种方案。结果依次为好、差。')) is None


def test_explicit_alternatives_keep_complete_conditions_without_fabricated_captions():
    from zhijiang.teaching_exhibits import literal_alternatives
    segment=SimpleNamespace(narration='方案剩下三个选择：只要求温度适中，只要求湿度合适，或者两个条件同时满足。')
    draft=literal_alternatives(segment)
    assert [i.label for i in draft.items]==['只要求温度适中','只要求湿度合适','两个条件同时满足']
    assert all(i.detail=='' for i in draft.items)
    validate_exhibit(draft,segment)
    assert literal_alternatives(SimpleNamespace(narration='记录：温度适中，湿度合适。')) is None
    defined=literal_alternatives(SimpleNamespace(narration='可行方案是满足测试条件的选择。'
        '当前剩下三种方案：只要求温度适中，只要求湿度合适，或者两个条件同时满足。'))
    assert defined.context=='可行方案是满足测试条件的选择'


def test_literal_alternatives_override_a_misclassified_relation_intent(tmp_path):
    segment=SimpleNamespace(title='剩余条件',narration='方案剩下三个选择：只要求温度适中，只要求湿度合适，或者两个条件同时满足。')
    class Model:
        def generate(self,schema,*args):
            if schema.__name__=='TeachingExhibitIntent':
                return schema.model_validate({'form':'relations','focus_sentence_ids':[1],'reason':'模型误判为箭头'})
            if schema.__name__=='TeachingExhibitReview':
                return schema.model_validate({**{n:'faithful' for n in schema.model_fields if n!='issues'},'issues':''})
            raise AssertionError('明确列举无需模型补写对象或连线')
    result=plan_exhibit(segment,DeckPageChoice(segment_id=1,role='explanation',layout='wide',bullet_ids=[1]),[],Model(),
        path=tmp_path/'alternatives.json')
    assert result['accepted'] and result['exhibit']['form']=='annotated'
    assert len(result['exhibit']['items'])==3 and not result['exhibit']['links']


def test_annotated_options_can_use_complete_literal_conditions_not_bare_verbs():
    segment=SimpleNamespace(narration='方案可以是：只使用传感器，或者同时使用传感器和控制器。')
    draft=TeachingExhibitDraft(form='annotated',items=[{'label':'只使用传感器','detail':'','sentence_id':1}])
    validate_exhibit(draft,segment)
    draft.items[0].label='只使用'
    with pytest.raises(ValueError):validate_exhibit(draft,segment)


def test_fallback_opening_question_and_numbered_route_use_literal_source_instead_of_scatters():
    from zhijiang.exhibit_svg import legacy_exhibit
    story={'representation':'annotated','items':[{'label':'教材','caption':'回顾','sentence_id':1}],
        'links':[],'context':'','context_sentence_id':None}
    question=legacy_exhibit(story,[], '为什么天空会变蓝？接下来学习散射。')
    assert question['form']=='statement' and question['items'][0]['label']=='为什么天空会变蓝？'
    assert question['pictures']==[]
    route=legacy_exhibit(story,[], '先记住三条主线。第一，认识输入与输出。第二，比较两个方案。第三，检查结果。')
    assert [v['detail'] for v in route['items']]==['认识输入与输出','比较两个方案','检查结果']
    assert [v['label'] for v in route['items']]==['01','02','03']


@pytest.mark.parametrize('template',['classic','paper','academic','editorial'])
def test_explicit_transport_captions_keep_material_origin_and_direction_in_two_arrow_lanes(template):
    from zhijiang.exhibit_svg import literal_transport_rows
    data=fixture('contrast');data['items']=[
        {'label':'氧气','detail':'氧气从肺泡扩散进入血液','sentence_id':1},
        {'label':'二氧化碳','detail':'二氧化碳则从血液扩散进入肺泡','sentence_id':2}]
    rows=literal_transport_rows(data)
    assert [(r['mover'],r['origin'],r['target']) for r in rows]==[
        ('氧气','肺泡','血液'),('二氧化碳','血液','肺泡')]
    svg,boxes,_=exhibit_svg(data,get_template(template),1080,490)
    root=ET.fromstring(svg);ns='{http://www.w3.org/2000/svg}'
    labels=[n.text for n in root.findall('.//'+ns+'text')]
    assert labels==['氧气','肺泡','血液','扩散进入','二氧化碳','血液','肺泡','扩散进入']
    assert sum(bool(p.get('marker-end')) for p in root.findall('.//'+ns+'path'))==2
    assert all(x+w<=1080 and y+h<=490 for x,y,w,h in boxes)
    png=resvg_py.svg_to_bytes(svg_string=svg.decode())
    assert Image.open(io.BytesIO(png)).getbbox() is not None


def test_transport_grammar_is_domain_independent_and_never_drops_conditions_or_negation():
    from zhijiang.exhibit_svg import literal_transport_rows
    data=fixture('contrast');data['items']=[
        {'label':'包裹','detail':'包裹由仓库运输到商店','sentence_id':1},
        {'label':'信息','detail':'信息从传感器传输到控制器','sentence_id':2}]
    assert len(literal_transport_rows(data))==2
    for text in ['信息不能从传感器传输到控制器','若系统启动，信息从传感器传输到控制器',
                 '信息从传感器传输到控制器，但是系统可能停止','信息和控制器同时出现在教材中']:
        data['items'][1]['detail']=text
        assert literal_transport_rows(data)==[]


@pytest.mark.parametrize('template',['classic','paper','academic','editorial'])
def test_explicit_named_parts_are_readable_peers_without_an_invented_sequence_or_duplicate_footer(template):
    from zhijiang.exhibit_svg import literal_named_parts
    data=fixture('statement');data.update(items=[{'label':'采集、处理和存储',
        'detail':'是不同环节：数据在处理后进入存储','sentence_id':1}],
        context='采集、处理和存储是不同环节：数据在处理后进入存储',context_sentence_id=1)
    assert literal_named_parts(data)==['采集','处理','存储']
    svg,_,_=exhibit_svg(data,get_template(template),1080,490)
    root=ET.fromstring(svg);ns='{http://www.w3.org/2000/svg}'
    labels=[n.text for n in root.findall('.//'+ns+'text')]
    assert labels[:3]==['采集','处理','存储']
    assert sum('数据在处理后' in (t or '') for t in labels)==1
    assert not any(p.get('marker-end') for p in root.findall('.//'+ns+'path'))
    data['context']='只有系统正常时才执行这些环节'
    svg,_,_=exhibit_svg(data,get_template(template),1080,490)
    assert data['context'] in svg.decode()
