import pytest
from tests.test_math_construction import program,compile
from zhijiang.visual_planning import VisualSceneError,verify_visual_scene
from zhijiang.math_coverage import check_coverage,MathSourceSubject,source_scope


@pytest.mark.parametrize('fault',['none','too_few','duplicate','mixed_type','unmeasured','hidden'])
def test_multiple_subjects_are_typed_measured_and_visible(fault):
    p=program([
        {'id':'a','op':'point','expr':['u','0']},
        {'id':'b','op':'point','expr':['u+1','0']},
        {'id':'c','op':'point','expr':['0','1']},
        {'id':'d','op':'point','expr':['1','1']},
        {'id':'e','op':'point','expr':['0','2']},
        {'id':'f','op':'point','expr':['1','2']},
        {'id':'ab','op':'line','refs':['a','b']},
        {'id':'cd','op':'line','refs':['c','d'],'visible':fault!='hidden'},
        {'id':'ef','op':'line','refs':['e','f']},
        {'id':'segment','op':'segment','refs':['a','b']}],
        [{'lhs':'angle(ab,cd)','rhs':'0'}])
    s=compile(p);s.verification=verify_visual_scene(s)
    ids={'too_few':['ab'],'duplicate':['ab','ab'],'mixed_type':['ab','segment'],
         'unmeasured':['ab','ef']}.get(fault,['ab','cd'])
    requirements=[{'id':1,'statement':'两条直线的方向之间有需要测量的关系。',
        'subjects':[{'name':'这两条直线','kind':'line','count':2}]}]
    class Client:
        def generate(self,schema,*args,**kwargs):
            return schema.model_validate({'checks':[{'requirement_id':1,
                'observation':'测试替身提交来源对象与实际对象的结构绑定。',
                'supported':True,'steps':[1,2,3],'objects':ids,
                'bindings':[{'subject_index':1,'objects':ids}]}]})
    if fault=='none':
        assert check_coverage(Client(),requirements,s,p,'source').checks[0].supported
    else:
        with pytest.raises(VisualSceneError,match='来源主语'):
            check_coverage(Client(),requirements,s,p,'source')


def test_source_scope_can_preserve_four_distinct_object_types_without_mixing():
    mapping={1:{'page':1,'quote':'The figure uses a point, a line, a segment and a ray.'}}
    class Client:
        def generate(self,schema,*args,**kwargs):
            return schema.model_validate({'requirements':[{'id':1,'source_ids':[1],
                'kind':'definition','statement':'图形中分别包含点、直线、线段和射线。',
                'subjects':[{'name':name,'kind':kind} for name,kind in
                    [('点','point'),('直线','line'),('线段','segment'),('射线','ray')]]}]})
    result=source_scope(Client(),mapping,mapping[1]['quote'])
    assert [s['kind'] for s in result[0]['subjects']]==['point','line','segment','ray']
    assert all(s['count']==1 for s in result[0]['subjects'])
    assert MathSourceSubject(name='对象',kind='point').count==1


def test_coverage_aggregate_keeps_four_heterogeneous_subject_bindings():
    p=program([{'id':'a','op':'point','expr':['u','0']},
        {'id':'b','op':'point','expr':['u+1','0']},
        {'id':'segment','op':'segment','refs':['a','b']},
        {'id':'ray','op':'ray','refs':['a','b'],'color':'#6DE2C0'},
        {'id':'line','op':'line','refs':['a','b'],'color':'#FFA458'}],
        [{'lhs':'xcoord(a)','rhs':'u'},{'lhs':'length(segment)','rhs':'1'},
         {'lhs':'angle(ray,line)','rhs':'0'}])
    s=compile(p);s.verification=verify_visual_scene(s)
    ids=['a','line','segment','ray']
    requirements=[{'id':1,'statement':'四种不同的基本对象需要分别绑定。',
        'subjects':[{'name':kind,'kind':kind} for kind in ['point','line','segment','ray']]}]
    class Client:
        def generate(self,schema,*args,**kwargs):
            return schema.model_validate({'checks':[{'requirement_id':1,
                'observation':'四种对象分别参与实际坐标、长度和方向关系。',
                'supported':True,'steps':[1,2,3],'objects':ids,
                'bindings':[{'subject_index':i,'objects':[obj]} for i,obj in enumerate(ids,1)]}]})
    result=check_coverage(Client(),requirements,s,p,'source')
    assert len(result.checks[0].bindings)==4


def test_source_collection_uses_atomic_geometry_not_internal_partition_group():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):MathSourceSubject(name='若干部分',kind='group',count=6)
    assert MathSourceSubject(name='若干部分',kind='polygon',count=6).count==6
