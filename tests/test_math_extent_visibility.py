import pytest
from tests.test_math_construction import program,compile
from zhijiang.visual_planning import verify_visual_scene,VisualSceneError
from zhijiang.math_coverage import check_coverage


@pytest.mark.parametrize('variant',['occluded','different_color','hidden','separate_carrier','isolated_step','partial_overlap','transformed_identity'])
def test_extent_identity_is_visible_in_at_least_one_claimed_step(variant):
    constructions=[{'id':'a','op':'point','expr':['u','0'],'visible':False},
        {'id':'b','op':'point','expr':['u+1','0'],'visible':False},
        {'id':'c','op':'point','expr':['u+1/2','0'] if variant=='partial_overlap' else ['u','1'],'visible':False},
        {'id':'d','op':'point','expr':['u+1','1'],'visible':False},
        {'id':'segment','op':'segment','refs':['a','b'],'visible':variant!='transformed_identity'},
        {'id':'carrier','op':'ray' if variant=='partial_overlap' else 'line',
            'refs':['c','b'] if variant=='partial_overlap' else ['c','d'] if variant=='separate_carrier' else ['a','b'],
            'color':'#FFA458' if variant=='different_color' else '#78BAFF',
            'visible':variant!='hidden'}]
    if variant=='transformed_identity':constructions.append(
        {'id':'moved','op':'transform','refs':['segment'],'expr':['0','u','1']})
    p=program(constructions,[{'lhs':'length(segment)','rhs':'1'}])
    if variant=='isolated_step':p.operations[-1].hide=['carrier']
    s=compile(p);s.verification=verify_visual_scene(s)
    requirements=[{'id':1,'statement':'有限线段必须在图中保留可区分的端点范围。',
        'subjects':[{'name':'有限线段','kind':'segment'}]}]
    class Client:
        def generate(self,schema,*args,**kwargs):
            return schema.model_validate({'checks':[{'requirement_id':1,
                'observation':'测试替身提交线段来源与实际对象的绑定。',
                'supported':True,'steps':[1,2,3],'objects':['segment'],
                'bindings':[{'subject_index':1,'objects':['segment']}]}]})
    if variant=='occluded':
        with pytest.raises(VisualSceneError,match='同色共线对象遮蔽') as error:
            check_coverage(Client(),requirements,s,p,'original')
        assert error.value.repair_target=='behavior'
    else:assert check_coverage(Client(),requirements,s,p,'original').checks[0].supported
