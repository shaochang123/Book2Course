import copy
import json
import pytest
from zhijiang.agents import ModelContractError,GenerationError
from zhijiang.math_behavior import behavior_schema,repair_behavior_contract,decode_behavior
from zhijiang.math_construction import MathProgramDraft


def candidate():
    p=MathProgramDraft(title='新函数的实际对应',objective='观察实际指数曲线与动点的输入输出对应。',source_id=1,
        parameters={'u':.2},constructions=[{'id':'f','op':'function','expr':['3**x'],'domain':[-1,2]},
            {'id':'p','op':'point_on_function','refs':['f'],'expr':['u']}],
        operations=[{'narration':'沿函数曲线移动，观察实际输入输出关系。'}]*3,
        claims=[{'source_id':1,'lhs':'ycoord(p)','rhs':'value(f,u)'}])
    schema=behavior_schema(p,{1:{}})
    data={'operations':[{'narration':'沿函数曲线移动，观察实际输入输出关系。','changes':{'u':u}}
        for u in [.3,.5,.8]],'claims':[{'source_id':1,'left':{'terms':[{'kind':'ycoord','point':'p'}]},
        'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}], 'roles':{'p':'实际动点'}}
    return p,schema,data


def test_complete_contract_repairs_only_bad_operations_and_retains_relationships():
    p,schema,data=candidate();bad=copy.deepcopy(data);bad['operations']=bad['operations'][:2]
    history={};calls=[]
    class Client:
        def generate(self,partial,instruction,material):
            calls.append(partial.__name__)
            assert '三至十步' in instruction and '不放宽' in instruction
            return partial.model_validate({'operations':data['operations']})
    repaired=repair_behavior_contract(Client(),schema,ModelContractError('bad',content=json.dumps(bad)),
        'original instruction','actual source graph',history)
    assert calls==['MathOperationsRepair']
    assert repaired.model_dump()['claims']==schema.model_validate(data).model_dump()['claims']
    assert repaired.roles==data['roles']
    assert len(history['behavior_format_repairs'])==1
    from zhijiang.math_construction import compile_program
    from zhijiang.models import Evidence
    def compile(program):
        return compile_program(program,Evidence(page=1,quote='The curve maps each input to three raised to that input.'),
            {1:{'quote':'The curve maps each input to three raised to that input.','page':1}})
    from zhijiang.visual_planning import verify_visual_scene,VisualSceneError
    operations,claims=decode_behavior(repaired)
    valid=p.model_copy(update={'operations':operations,'claims':claims})
    assert verify_visual_scene(compile(valid))['passed']
    wrong=claims[0].model_copy(update={'rhs':'0'})
    with pytest.raises(VisualSceneError,match='实际数学关系失败'):
        verify_visual_scene(compile(valid.model_copy(update={'claims':[wrong]})))


@pytest.mark.parametrize('label',['直线ℓ₁夹角','输出值10','x坐标'])
def test_measurement_label_is_rejected_in_behavior_contract(label):
    from pydantic import ValidationError
    _,schema,data=candidate()
    data['operations'][0]['measurements']={label:{'terms':[{'kind':'ycoord','point':'p'}]}}
    with pytest.raises(ValidationError):schema.model_validate(data)


def test_subscript_label_repairs_operation_field_and_preserves_math_claims():
    _,schema,data=candidate();bad=copy.deepcopy(data)
    measurement={'terms':[{'kind':'ycoord','point':'p'}]}
    bad['operations'][0]['measurements']={'点P₁纵坐标':measurement}
    fixed=copy.deepcopy(data);fixed['operations'][0]['measurements']={'实际纵坐标':measurement}
    calls=[];history={}
    class Client:
        def generate(self,partial,*args):
            calls.append(partial.__name__)
            return partial.model_validate({'operations':fixed['operations']})
    repaired=repair_behavior_contract(Client(),schema,
        ModelContractError('label invalid',content=json.dumps(bad,ensure_ascii=False)),
        'instruction','actual graph',history)
    assert calls==['MathOperationsRepair']
    assert repaired.operations[0].measurements['实际纵坐标'].terms[0].point=='p'
    assert repaired.model_dump()['claims']==schema.model_validate(data).model_dump()['claims']
    assert repaired.roles==data['roles']


@pytest.mark.parametrize('content',['{"operations":[', '{}', '{"claims":[]}',
    '{"operations":[],"claims":[],"unexpected":true}', '[]'])
def test_incomplete_or_unknown_response_never_recovered_as_partial(content):
    _,schema,_=candidate()
    class Client:
        def generate(self,*args):raise AssertionError('Must not call model on partial JSON')
    error=ModelContractError('rejected',content=content)
    with pytest.raises(ModelContractError):repair_behavior_contract(Client(),schema,error,'','',{})


def test_wrong_measurement_type_repairs_claim_field_without_changing_operations():
    _,schema,data=candidate();bad=copy.deepcopy(data)
    bad['claims'][0]['left']['terms'][0]['point']='f'
    calls=[]
    class Client:
        def generate(self,partial,*args):
            calls.append(partial.__name__)
            return partial.model_validate({'claims':data['claims']})
    result=repair_behavior_contract(Client(),schema,ModelContractError('bad',content=json.dumps(bad)),'','',{})
    assert calls==['MathClaimsRepair']
    assert result.model_dump()['operations']==schema.model_validate(data).model_dump()['operations']


def test_field_repair_does_not_hide_service_failure():
    _,schema,data=candidate();data['operations']=data['operations'][:2]
    class Client:
        def generate(self,*args):raise GenerationError('service unavailable')
    with pytest.raises(GenerationError,match='service unavailable'):
        repair_behavior_contract(Client(),schema,ModelContractError('bad',content=json.dumps(data)),'','',{})
