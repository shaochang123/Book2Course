import pytest
from zhijiang.math_graph_repair import MathConstructionPatch,apply_construction_patch
from zhijiang.math_construction import MathConstructionDraft,Compiler
from zhijiang.visual_planning import VisualSceneError


def source_graph():
    return MathConstructionDraft(title='函数与实际动点',objective='保持原函数并扩展实际对象之间的对应演示。',
        source_id=4,parameters={'u':.3},constructions=[
            {'id':'f','op':'function','expr':['exp(x)'],'domain':[-1,1]},
            {'id':'p','op':'point_on_function','refs':['f'],'expr':['u']}])


def test_patch_preserves_valid_source_function_and_orders_new_dependencies():
    base=source_graph();original=base.model_dump()
    patch=MathConstructionPatch(parameters={'v':.2},upserts=[
        {'id':'edge','op':'segment','refs':['p','q']},
        {'id':'q','op':'point','expr':['p_x+v','p_y']}])
    changed=apply_construction_patch(base,patch)
    assert base.model_dump()==original
    assert changed.constructions[0]==base.constructions[0] and changed.source_id==4
    assert [x.id for x in changed.constructions]==['f','p','q','edge']
    compiled=Compiler(changed)
    assert str(compiled.items['f']['expr'])=='exp(x)'
    assert str(compiled.items['q']['p'][0])=='u + v'


@pytest.mark.parametrize('patch',[
    {'remove':['missing']},
    {'remove':['f']},
    {'upserts':[{'id':'q','op':'midpoint','refs':['p','q']}]},
    {'upserts':[{'id':'q','op':'point','expr':['p_x','0']},
        {'id':'p','op':'point','expr':['q_x','0']}]},
    {'parameters':{'p':1}},
])
def test_patch_rejects_missing_dependencies_cycles_and_ambiguous_names(patch):
    with pytest.raises(VisualSceneError):apply_construction_patch(source_graph(),MathConstructionPatch.model_validate(patch))


def test_32_definition_graph_remains_bounded_and_compiles():
    from pydantic import ValidationError
    p=source_graph()
    full=MathConstructionDraft.model_validate({**p.model_dump(),'constructions':p.model_dump()['constructions']+
        [{'id':f'a{i}','op':'point','expr':[str(i),'u']} for i in range(30)]})
    assert len(Compiler(full).items)==32
    with pytest.raises(ValidationError):MathConstructionDraft.model_validate({**full.model_dump(),
        'constructions':full.model_dump()['constructions']+[{'id':'overflow','op':'point','expr':['0','u']}]})


def test_partition_member_dependency_preserved_when_new_motion_is_added():
    p=MathConstructionDraft.model_validate({**source_graph().model_dump(),
        'constructions':[{'id':'box','op':'rectangle','expr':['0','0','2','2']},
            {'id':'pieces','op':'partition','refs':['box'],'expr':['2','2']}]})
    changed=apply_construction_patch(p,MathConstructionPatch(upserts=[
        {'id':'moving','op':'transform','refs':['pieces_0_1'],'expr':['0','u','0']}]))
    compiled=Compiler(changed)
    assert compiled.items['moving']['type']=='polygon'
    with pytest.raises(VisualSceneError):
        Compiler(apply_construction_patch(p,MathConstructionPatch(upserts=[
            {'id':'moving','op':'transform','refs':['pieces_7_8'],'expr':['0','u','0']}])))


def test_control_suffix_does_not_create_false_line_coordinate_cycle():
    patch=MathConstructionPatch(parameters={'span_y':2},upserts=[
        {'id':'span','op':'segment','refs':['lo','hi']},
        {'id':'hi','op':'point','expr':['u','span_y']},
        {'id':'lo','op':'point','expr':['0','0']}])
    result=apply_construction_patch(source_graph(),patch)
    compiled=Compiler(result)
    assert compiled.items['span']['type']=='line'
    assert str(compiled.items['hi']['p'][1])=='span_y'
    assert [c.id for c in result.constructions].index('span')>[c.id for c in result.constructions].index('hi')


def test_actual_point_coordinate_control_collision_still_rejected():
    patch=MathConstructionPatch(parameters={'q_y':2},upserts=[
        {'id':'q','op':'point','expr':['u','q_y']}])
    result=apply_construction_patch(source_graph(),patch)
    with pytest.raises(VisualSceneError,match='命名冲突'):
        Compiler(result)


def test_different_repeated_behavior_errors_escalate_to_graph_patch():
    from zhijiang.mathematical_planning import plan_constructed_lesson
    from zhijiang.models import SourceDocument,PageText
    from tests.test_mathematical_planning import CHECKS
    source=SourceDocument(filename='different.pdf',pages=[PageText(page=1,
        text='A point on the function follows its actual input and output.',math_reading={'verified':True})])
    calls=[];reviews=0
    class Client:
        model='mock'
        def generate(self,schema,instruction,material,**kwargs):
            nonlocal reviews
            calls.append(schema.__name__)
            if schema.__name__=='MathSourceScope':return schema.model_validate({'requirements':[{'id':1,
                'source_ids':[1],'kind':'definition','statement':'动点的实际坐标保持函数的输入输出关系。'}]})
            if schema.__name__=='MathScopeMeaningReview':return schema.model_validate({'checks':[{'requirement_id':1,
                'observation':'来源函数与动点关系在清单中保持完整。','supported':True}]})
            if schema.__name__=='MathConstructionIntent':return schema.model_validate({'core_question':'函数动点关系',
                'source_conditions':[],'construction_plan':'函数及真实曲线上动点。',
                'continuous_operations':['观察','移动','比较'],'actual_object_checks':['对应关系']})
            if schema.__name__=='MathConstructionDraft':return schema.model_validate({**source_graph().model_dump(),'source_id':1})
            if schema.__name__=='MathConstructionPatch':return schema.model_validate({'parameters':{'u':.3}})
            if schema.__name__=='MathConstructionReadiness':return schema.model_validate({'checks':[{'requirement_id':1,
                'observation':'函数与实际动点的控制量足以表达关系。','feasible':True,'objects':['f','p']}]})
            if schema.__name__=='MathBehaviorDraft':return schema.model_validate({'operations':[
                {'narration':'移动实际函数动点，比较输入输出的变化。','changes':{'u':u}} for u in [.4,.6,.8]],
                'claims':[{'source_id':1,'left':{'terms':[{'kind':'ycoord','point':'p'}]},
                    'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]})
            if schema.__name__=='MathProgramReview':
                reviews+=1
                if reviews<=2:return schema.model_validate({'checks':[
                    {**c,'supported':False if c['aspect']=='motion' else c['supported']} for c in CHECKS],
                    'issues':[f'不同错误描述第{reviews}轮，现有操作不足以解释关系。'],
                    'approved':False,'repair_target':'behavior','source_coverage':[]})
                return schema.model_validate({'checks':CHECKS,'approved':True,'source_coverage':['actual point relation']})
            if schema.__name__=='MathCoverageReview':return schema.model_validate({'checks':[{'requirement_id':1,
                'observation':'实际函数关系参与动点运动和测量。','supported':True,'steps':[1,2,3],
                'objects':['f','p'],'bindings':[]}]})
            raise AssertionError(schema.__name__)
    assert plan_constructed_lesson(Client(),source).segments
    assert calls.count('MathConstructionDraft')==1
    assert calls.count('MathConstructionPatch')==1
    assert calls.count('MathBehaviorDraft')==3
