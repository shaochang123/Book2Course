import pytest
pytest.importorskip('sympy')

from zhijiang.math_construction import MathProgramDraft, MathBehaviorDraft, MathProgramReview
from zhijiang.mathematical_planning import plan_constructed_lesson, MathConstructionIntent
from zhijiang.models import PageText, SourceDocument

CHECKS=[{'aspect':a,'observation':'测试替身记录当前来源、对象和步骤的对应关系。','supported':True} for a in ['source','geometry','motion']]


@pytest.mark.parametrize('bad_objective,graph_error',[(False,False),(True,False),(True,True)])
def test_motion_repair_preserves_valid_source_function_and_measures_drawn_point(bad_objective,graph_error):
    narration='观察函数上的点，说明位置变化与函数值的对应关系。'
    source=SourceDocument(filename='unseen-function.pdf',pages=[PageText(page=17,
        text='An exponential function maps each input to its exponential value. Domain: all real inputs.')])
    constructions=[{'id':'f','op':'function','expr':['exp(x)'],'domain':[-1,1]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}]
    claim={'source_id':1,'lhs':'ycoord(m)','rhs':'value(f,u)'}
    draft=MathProgramDraft(title='指数映射的动态点',objective='比较移动点的横坐标与实际函数值。',source_id=1,
        parameters={'u':0},constructions=constructions,operations=[{'narration':narration}]*3,claims=[claim])
    repaired=MathBehaviorDraft(operations=[{'narration':narration,'changes':{'u':v},
        'measurements':{'实际函数值':'ycoord(m)'}} for v in [.25,.5,.9]],claims=[claim])
    class Client:
        model='mock-model';calls=[]
        def generate(self,schema,instruction,material,**kwargs):
            self.calls.append(schema.__name__)
            if schema.__name__=='MathMetadataRepair':return schema.model_validate({'objective':'比较移动点的横坐标与实际函数值。'})
            if schema.__name__=='MathProgramReview' and bad_objective and self.calls.count('MathProgramReview')==1:
                return MathProgramReview(checks=[{**c,'supported':False} for c in CHECKS],approved=False,
                    issues=['objective 的范围措辞错误，需要修复教学目标。'],repair_target='construction' if graph_error else 'behavior',source_coverage=['实际指数映射。'])
            if schema.__name__=='MathConstructionIntent':return MathConstructionIntent(core_question='指数映射的变化',
                source_conditions=['任意实输入'],construction_plan='绘制函数及其上的点。',
                continuous_operations=['确定初始位置','移动点','比较输出'],actual_object_checks=['点必须在原函数上。'])
            if schema.__name__=='MathConstructionDraft':return schema.model_validate(draft.model_dump(exclude={'operations','claims','roles'}))
            if schema.__name__=='MathBehaviorDraft':return schema.model_validate({
                'operations':[{'narration':narration,'changes':{'u':v},'measurements':{
                    '实际函数值':{'terms':[{'kind':'ycoord','point':'m'}]}}} for v in [.25,.5,.9]],
                'claims':[{'source_id':1,'left':{'terms':[{'kind':'ycoord','point':'m'}]},
                    'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]})
            if schema.__name__=='MathProgramReview':return MathProgramReview(checks=CHECKS,approved=True,source_coverage=['指数函数中的输入与输出对应关系。'])
            raise AssertionError(schema.__name__)
    client=Client();lesson=plan_constructed_lesson(client,source)
    expected=['MathConstructionIntent','MathConstructionDraft','MathBehaviorDraft','MathProgramReview']
    if bad_objective:expected+=['MathConstructionDraft' if graph_error else 'MathMetadataRepair','MathBehaviorDraft','MathProgramReview']
    assert client.calls==expected
    scene=lesson.segments[0].visual_scene
    assert scene.objects[0].expression=='exp(x)'
    assert scene.verification['states'][-1]['calculations'][0]['value']==pytest.approx(2.459603111)
    assert lesson.segments[0].evidence.page==17


@pytest.mark.parametrize('duplicate_first',[False,True])
@pytest.mark.parametrize('separate_planner',[False,True])
@pytest.mark.parametrize('has_scope',[False,True])
def test_independent_text_review_roles_and_object_repair_route(duplicate_first,separate_planner,has_scope):
    source=SourceDocument(filename='mapping.pdf',pages=[PageText(page=2,
        text='This example maps a real input to four raised to that input.',
        math_reading={'verified':True} if has_scope else None)])
    calls=[];construction_count=0
    class Vision:
        model='vision-model'
        def generate(self,schema,instruction,material,**kwargs):
            calls.append(('vision',schema.__name__))
            if schema.__name__!='MathProgramReview':return Planner.generate(self,schema,instruction,material,**kwargs)
            assert 'transform refs=' in instruction and '平移横量,平移纵量' in instruction
            assert 'computed_objects' in material and 'rendered_steps' in material
            return schema.model_validate({'checks':CHECKS,'approved':True,'source_coverage':['Original exponential mapping.']})
    class Planner:
        model='text-planner'
        def generate(self,schema,instruction,material,**kwargs):
            nonlocal construction_count
            calls.append(('planner',schema.__name__))
            assert not kwargs.get('images')
            if schema.__name__=='SourceObjectIdentityGraph':
                return schema.model_validate({'entities':[],'relations':[]})
            if schema.__name__=='MathSourceScope':
                return schema.model_validate({'requirements':[{'id':1,'source_ids':[1],
                    'kind':'definition','statement':'实输入对应指数函数的真实输出值。',
                    'subjects':[{'name':'f','kind':'function'}]}]})
            if schema.__name__=='MathScopeMeaningReview':
                return schema.model_validate({'checks':[{'requirement_id':1,
                    'observation':'来源与中文清单均描述同一指数函数的映射。','supported':True}]})
            if schema.__name__=='MathConstructionReadiness':
                assert 'computed_inventory' in material and '4**x' in material
                assert '编写讲稿和操作之前' in instruction
                return schema.model_validate({'checks':[{'requirement_id':1,
                    'observation':'函数表达式与动点依赖能表达来源中的映射。','feasible':True,'objects':['f','m']}]})
            if schema.__name__=='MathCoverageReview':
                return schema.model_validate({'checks':[{'requirement_id':1,
                    'observation':'函数与动点真实参与对应输出的核心测量。','supported':True,
                    'steps':[1,2,3],'objects':['f','m'],'bindings':[{'subject_index':1,'objects':['f']}]}]})
            if schema.__name__=='MathConstructionIntent':
                return schema.model_validate({'core_question':'输入输出对应',
                    'source_conditions':['任意实输入'],'construction_plan':'函数上的动点。',
                    'continuous_operations':['初始观察','移动输入','比较输出'],
                    'actual_object_checks':['实际点符合函数。']})
            if schema.__name__=='MathConstructionPatch':
                construction_count+=1
                assert 'duplicate' in material and '不重写有效对象' in instruction
                return schema.model_validate({'remove':['duplicate']})
            if schema.__name__=='MathConstructionDraft':
                construction_count+=1
                objects=[{'id':'f','op':'function','expr':['4**x'],'domain':[-.3,1]},
                         {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}]
                if duplicate_first and construction_count==1:
                    objects.append({'id':'duplicate','op':'point_on_function','refs':['f'],'expr':['u']})
                return schema.model_validate({'title':'输入输出的对应','objective':'观察移动输入与函数输出的真实对应关系。',
                    'source_id':1,'parameters':{'u':0},'constructions':objects})
            if schema.__name__=='MathBehaviorDraft':
                return schema.model_validate({'operations':[{
                    'narration':'沿着函数曲线移动点，观察输入与输出的对应关系。',
                    'changes':{'u':v},'measurements':{'函数值':{'terms':[{'kind':'ycoord','point':'m'}]}}}
                    for v in [.25,.6,1]],'claims':[{'source_id':1,
                    'left':{'terms':[{'kind':'ycoord','point':'m'}]},
                    'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]})
            assert schema.__name__=='MathProgramReview'
            return schema.model_validate({'checks':CHECKS,'approved':True,'source_coverage':['Original exponential mapping.']})
    lesson=plan_constructed_lesson(Vision(),source,review_client=Planner(),planning_client=Planner() if separate_planner else None)
    assert construction_count==(2 if duplicate_first else 1)
    assert calls.count(('vision','MathProgramReview'))==1
    assert calls.count(('planner','MathProgramReview'))==1
    if has_scope:
        assert calls.count(('planner','MathConstructionReadiness'))==construction_count
        assert calls.count(('planner','MathCoverageReview'))==1
    expected_roles={
        'source_and_visual_review':'vision-model','construction_and_behavior':'text-planner' if separate_planner else 'vision-model',
        'text_recheck':'text-planner'}
    if has_scope:expected_roles.update(source_scope_reader='vision-model',source_scope_meaning_reviewer='text-planner')
    assert lesson.segments[0].visual_scene.mathematical_model['model_roles']==expected_roles


@pytest.mark.parametrize('bad_graphs',[1,9])
def test_last_allowed_graph_gets_behavior_and_review_and_repair_sees_candidate(bad_graphs):
    source=SourceDocument(filename='new.pdf',pages=[PageText(page=4,
        text='A function assigns one output to each input. This source does not require a geometric proof.')])
    calls=[];count=0
    class Client:
        model='mock'
        def generate(self,schema,instruction,material,**kwargs):
            nonlocal count
            calls.append(schema.__name__)
            if schema.__name__=='MathConstructionIntent':return schema.model_validate({
                'core_question':'对应关系','source_conditions':[],
                'construction_plan':'UNTRUSTED_DRAFT_NOT_SOURCE',
                'continuous_operations':['观察','移动','比较'], 'actual_object_checks':['对应值']})
            if schema.__name__=='MathConstructionDraft':
                count+=1
                if count>1:assert '上一轮被拒候选' in material and 'missing' in material
                point={'id':'m','op':'point_on_function','refs':['missing' if count<=bad_graphs else 'f'],'expr':['u']}
                return schema.model_validate({'title':'映射与运动','objective':'移动输入点并比较实际输出的变化。',
                    'source_id':1,'parameters':{'u':0},'constructions':[
                        {'id':'f','op':'function','expr':['exp(x)'],'domain':[-.2,1]},point]})
            if schema.__name__=='MathBehaviorDraft':return schema.model_validate({'operations':[{
                'narration':'沿着曲线移动输入点，观察输出值的对应变化。','changes':{'u':v},
                'measurements':{'输出值':{'terms':[{'kind':'ycoord','point':'m'}]}}}
                for v in [.2,.5,1]], 'claims':[{'source_id':1,
                    'left':{'terms':[{'kind':'ycoord','point':'m'}]},
                    'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]})
            assert schema.__name__=='MathProgramReview'
            assert 'UNTRUSTED_DRAFT_NOT_SOURCE' not in material
            return schema.model_validate({'checks':CHECKS,'approved':True,'source_coverage':['输入输出关系']})
    lesson=plan_constructed_lesson(Client(),source)
    assert count==bad_graphs+1
    assert calls[-2:]==['MathBehaviorDraft','MathProgramReview']
    assert lesson.segments[0].visual_scene.verification['passed']


def test_review_requires_all_aspects_and_consistent_approval():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        MathProgramReview(checks=CHECKS[:2]+[CHECKS[0]],approved=True,source_coverage=['映射'])
    with pytest.raises(ValidationError):
        MathProgramReview(checks=[{**c,'supported':False} for c in CHECKS],approved=True,source_coverage=['映射'])


@pytest.mark.parametrize('step_count',[3,5])
@pytest.mark.parametrize('repair_valid',[True,False])
def test_narration_repair_keeps_math_and_original_page_evidence(tmp_path,step_count,repair_valid):
    source=SourceDocument(filename='new.pdf',pages=[PageText(page=7,text='The point moves along the function y=exp(x).')])
    calls=[];seen_images=[]
    values=[.2,.5,.8] if step_count==3 else [.2,.35,.5,.65,.8]
    class Client:
        model='mock'
        def generate(self,schema,instruction,material,**kwargs):
            calls.append(schema.__name__)
            if schema.__name__=='MathConstructionIntent':return schema.model_validate({
                'core_question':'对应关系','source_conditions':[], 'construction_plan':'动态函数',
                'continuous_operations':['观察','移动','比较'],'actual_object_checks':['实际函数值']})
            if schema.__name__=='MathConstructionDraft':return schema.model_validate({
                'title':'函数的动态对应','objective':'观察输入改变时函数上的点如何移动。','source_id':1,'parameters':{'u':0},
                'constructions':[{'id':'f','op':'function','expr':['exp(x)'],'domain':[-.2,1]},
                    {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}]})
            if schema.__name__=='MathBehaviorDraft':return schema.model_validate({'operations':[{
                'narration':'观察函数上移动的点，横坐标最终等于二。','changes':{'u':v}}
                for v in values],'claims':[{'source_id':1,'left':{'terms':[{'kind':'ycoord','point':'m'}]},
                    'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]})
            if schema.__name__=='MathNarrationRepair':return schema.model_validate({
                'narration':'观察函数上移动的点，横坐标改变时函数值随之改变。' if repair_valid
                    else '观察函数上移动的点，横坐标最终等于二。'})
            assert schema.__name__=='MathProgramReview'
            assert 'transform refs=' in instruction and '平移横量,平移纵量' in instruction
            seen_images.extend(kwargs['images'])
            assert '等于二' not in material
            return schema.model_validate({'checks':CHECKS,'approved':True,'source_coverage':['对应关系']})
    loaded=[]
    if not repair_valid:
        from zhijiang.visual_planning import VisualSceneError
        with pytest.raises(VisualSceneError,match='十次修复'):
            plan_constructed_lesson(Client(),source,source_image_loader=lambda page:loaded.append(page) or b'original')
        assert calls.count('MathNarrationRepair')==30
        assert 'MathProgramReview' not in calls and not loaded
        return
    lesson=plan_constructed_lesson(Client(),source,source_image_loader=lambda page:loaded.append(page) or b'original')
    assert calls.count('MathConstructionDraft')==1
    assert calls.count('MathBehaviorDraft')==1
    assert calls.count('MathNarrationRepair')==step_count
    assert loaded==[7] and seen_images==[b'original']
    assert [b.parameters['u'] for b in lesson.segments[0].visual_scene.beats]==values
