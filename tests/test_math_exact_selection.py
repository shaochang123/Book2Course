from tests.test_math_construction import program,compile
from zhijiang.visual_planning import verify_visual_scene
from zhijiang.math_coverage import check_coverage


def test_incomplete_binding_repairs_only_exact_selections_preserving_math_and_valid_item():
    p=program([{'id':'a','op':'point','expr':['u','0']},
        {'id':'b','op':'point','expr':['u+1','0']},
        {'id':'edge','op':'segment','refs':['a','b']},
        {'id':'ray','op':'ray','refs':['a','b'],'color':'#6DE2C0'}],
        [{'lhs':'length(edge)','rhs':'1'},{'lhs':'angle(edge,ray)','rhs':'0'}])
    s=compile(p);s.verification=verify_visual_scene(s)
    requirements=[{'id':1,'statement':'此处需要保留原点与有限边的实际对应。',
        'subjects':[{'name':'实际点','kind':'point'},{'name':'有限边','kind':'segment'}]},
        {'id':2,'statement':'此处还需保留已有正确的射线对应关系。',
         'subjects':[{'name':'射线','kind':'ray'}]}]
    calls=[]
    class Client:
        def generate(self,schema,instruction,material):
            calls.append(schema.__name__)
            if schema.__name__=='MathExactSubjectSelection':
                assert '固定顺序' in instruction
                return schema.model_validate({'bindings':[{'subject_index':1,'objects':['a']},
                    {'subject_index':2,'objects':['edge']}]})
            return schema.model_validate({'checks':[
                {'requirement_id':1,'observation':'此测试替身故意漏掉第二项主语选择。','supported':True,
                 'steps':[1,2,3],'objects':['a','edge'],'bindings':[{'subject_index':1,'objects':['a']}]},
                {'requirement_id':2,'observation':'已有正确的射线对应应完整保留。','supported':True,
                 'steps':[1,2,3],'objects':['ray'],'bindings':[{'subject_index':1,'objects':['ray']}]}]})
    before=p.model_dump()
    result=check_coverage(Client(),requirements,s,p,'actual source')
    assert calls==['MathCoverageReview','MathExactSubjectSelection']
    assert [b.subject_index for b in result.checks[0].bindings]==[1,2]
    assert result.checks[1].bindings[0].objects==['ray']
    assert p.model_dump()==before
    assert s.mathematical_model['coverage_binding_attempts'][0]['selection_repairs'][0]['requirement_id']==1


def test_patch_duplicate_edit_rejected_before_geometry_planning():
    import pytest
    from pydantic import ValidationError
    from zhijiang.math_graph_repair import MathConstructionPatch
    obj={'id':'a','op':'point','expr':['0','0']}
    with pytest.raises(ValidationError,match='每个对象ID'):MathConstructionPatch(upserts=[obj,obj])
    with pytest.raises(ValidationError,match='每个对象ID'):MathConstructionPatch(upserts=[obj],remove=['a'])
