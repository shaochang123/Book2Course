import json
import pytest
from zhijiang.math_coverage import source_scope,check_coverage,ground_requirements
from zhijiang.visual_planning import VisualSceneError,verify_visual_scene
from tests.test_math_construction import program,compile


def test_source_scope_requires_literal_source_and_unique_ids():
    mapping={4:{'page':2,'quote':'The mapping is defined only for positive inputs.'}}
    class Client:
        source_id=4
        def generate(self,schema,instruction,material):
            assert '不要重打' in instruction
            return schema.model_validate({'requirements':[{'id':1,'source_ids':[self.source_id],
                'kind':'condition','statement':'输入必须保持为正值。'}]})
    c=Client();result=source_scope(c,mapping,mapping[4]['quote'])[0]
    assert result['source_id']==4 and result['source_quote']==mapping[4]['quote']
    assert result['source_excerpts']==[{'source_id':4,'page':2,'quote':mapping[4]['quote']}]
    from pydantic import ValidationError
    c.source_id=8
    with pytest.raises(ValidationError):source_scope(c,mapping,mapping[4]['quote'])


def test_literal_scope_quote_can_span_same_page_chunks_but_not_different_pages():
    from pydantic import BaseModel
    class Requirement(BaseModel):
        source_id:int
        source_quote:str
    r=Requirement(source_id=2,source_quote='only for positive inputs.')
    mapping={1:{'page':7,'quote':'The mapping is defined only for '},
        2:{'page':7,'quote':'positive inputs.'}}
    fixed=ground_requirements([r],mapping)[0]
    assert fixed['source_id']==1 and fixed['source_page']==7 and fixed['citation_repair']['before']==2
    mapping[2]['page']=8
    with pytest.raises(VisualSceneError,match='唯一定位'):ground_requirements([r],mapping)
    mapping[1]={'page':7,'quote':'only for positive inputs.'}
    mapping[2]={'page':8,'quote':'only for positive inputs.'}
    r.source_id=3;mapping[3]={'page':9,'quote':'An unrelated source.'}
    with pytest.raises(VisualSceneError,match='唯一定位'):ground_requirements([r],mapping)


def test_coverage_uses_actual_endpoint_geometry_and_rejects_missing_requirement():
    p=program([{'id':'c','op':'parametric','expr':['cos(x)','sin(x)'],'domain':[0,1]},
        {'id':'m','op':'point_on_curve','refs':['c'],'expr':['u']}],
        [{'lhs':'distance(m,m)','rhs':'0'}],changes=[{'u':.6},{'u':.9},{'u':.8}])
    s=compile(p);s.verification=verify_visual_scene(s)
    requirements=[{'id':2,'kind':'condition','statement':'必须说明输入条件。'}]
    class Client:
        def generate(self,schema,instruction,material):
            data=json.loads(material.split('实际候选及逐步渲染几何：')[1])
            assert data['geometry'][0]['step']==1
            assert data['geometry'][0]['objects']['c']['endpoints'][0]==[1,0]
            assert '不是教材事实' in instruction
            return schema.model_validate({'checks':[{'requirement_id':2,
                'observation':'实际口播遗漏了清单中的必要输入条件。','supported':False,'bindings':[]}],
                'repair_target':'behavior'})
    result=check_coverage(Client(),requirements,s,p,'original')
    assert not result.checks[0].supported and result.repair_target=='behavior'


@pytest.mark.parametrize('fault',['none','equivalent_function','missing','unrelated','wrong_vertices'])
def test_source_subject_must_exist_and_participate_in_measured_dependency_graph(fault):
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-.1,1.4]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']},
        {'id':'placeholder','op':'rectangle','expr':['0','0','1','1']}],
        [{'lhs':'ycoord(m)','rhs':'value(f,u)'}])
    s=compile(p);s.verification=verify_visual_scene(s)
    subject={'name':'教材实际函数','kind':'function','vertices':None}
    obj='f'
    if fault=='equivalent_function':subject={'name':'参数曲线','kind':'parametric','vertices':None}
    if fault=='unrelated':subject={'name':'教材多边形','kind':'polygon','vertices':4};obj='placeholder'
    if fault=='wrong_vertices':subject={'name':'教材多边形','kind':'polygon','vertices':5};obj='placeholder'
    requirements=[{'id':4,'statement':'核心关系必须涉及教材实际主语。','subjects':[subject]}]
    class Client:
        def generate(self,schema,*args,**kwargs):
            return schema.model_validate({'checks':[{'requirement_id':4,'observation':'测试替身尝试批准指定主语的结构绑定。',
                'steps':[1,2,3],'objects':[obj],'supported':True,
                'bindings':[] if fault=='missing' else [{'subject_index':1,'objects':[obj]}]}]})
    if fault in {'none','equivalent_function'}:assert check_coverage(Client(),requirements,s,p,'original').checks[0].supported
    else:
        with pytest.raises(VisualSceneError,match='来源主语'):check_coverage(Client(),requirements,s,p,'original')


def test_source_subject_allows_single_character_mathematical_names():
    from zhijiang.math_coverage import MathSourceSubject
    assert MathSourceSubject(name='点',kind='point').name=='点'
    assert MathSourceSubject(name='f',kind='function').name=='f'


def test_binding_correction_reuses_candidate_and_preserves_rejected_review():
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-.1,1.4]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(m)','rhs':'value(f,u)'}])
    s=compile(p);s.verification=verify_visual_scene(s)
    requirements=[{'id':1,'statement':'函数上的点满足实际函数关系。',
        'subjects':[{'name':'f','kind':'function'}]}]
    original=p.model_dump();calls=[]
    class Client:
        def generate(self,schema,instruction,material):
            calls.append(instruction)
            if len(calls)>1:
                assert schema.__name__=='MathExactSubjectSelection'
                assert '不修改原来源、对象、步骤、测量' in instruction
                return schema.model_validate({'bindings':[{'subject_index':1,'objects':['f']}]})
            return schema.model_validate({'checks':[{'requirement_id':1,'observation':'实际函数对象参与核心函数值的测量关系。',
                'steps':[1,2,3],'objects':['f'],'supported':True,
                'bindings':[] if len(calls)==1 else [{'subject_index':1,'objects':['f']}]}]})
    assert check_coverage(Client(),requirements,s,p,'original').checks[0].supported
    assert len(calls)==2 and p.model_dump()==original
    history=s.mathematical_model['coverage_binding_attempts']
    assert len(history)==1 and 'error' in history[0] and history[0]['passed']
    assert history[0]['review']['checks'][0]['bindings']==[]
    assert history[0]['selection_repaired_review']['checks'][0]['bindings'][0]['objects']==['f']


def test_batched_coverage_keeps_every_obligation_and_construction_rejection():
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-.1,1.4]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(m)','rhs':'value(f,u)'}])
    s=compile(p);s.verification=verify_visual_scene(s)
    requirements=[{'id':i,'statement':'教材的每项要求必须独立核验。'} for i in [1,3,5,7,9]]
    calls=[]
    class Client:
        def generate(self,schema,instruction,material):
            batch=json.loads(material.split('独立来源清单：')[1].split('\n实际候选')[0])
            calls.append([r['id'] for r in batch])
            assert len(batch)<=2
            return schema.model_validate({'checks':[{'requirement_id':r['id'],
                'observation':'实际候选仍缺少必要构造。' if r['id']==3 else '实际关系和口播已表达当前要求。',
                'supported':r['id']!=3,'bindings':[]} for r in batch],
                'repair_target':'construction' if any(r['id']==3 for r in batch) else 'behavior'})
    result=check_coverage(Client(),requirements,s,p,'original')
    assert calls==[[1,3],[5,7],[9]]
    assert [c.requirement_id for c in result.checks]==[1,3,5,7,9]
    assert not result.checks[1].supported and result.repair_target=='construction'


def test_later_coverage_service_failure_retains_prior_review_without_approval():
    from zhijiang.agents import GenerationError
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-.1,1.4]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(m)','rhs':'value(f,u)'}])
    s=compile(p);s.verification=verify_visual_scene(s)
    calls=[]
    requirements=[{'id':i,'statement':'教材各项要求不得被删除。'} for i in [1,2,4]]
    class Client:
        def generate(self,schema,instruction,material):
            calls.append(schema.__name__)
            if len(calls)>1:raise GenerationError('review output budget exhausted')
            return schema.model_validate({'checks':[{'requirement_id':i,
                'observation':'实际候选表达了当前核验要求。','supported':True,'bindings':[]} for i in [1,2]]})
    with pytest.raises(GenerationError,match='budget') as caught:
        check_coverage(Client(),requirements,s,p,'original')
    history=caught.value.binding_attempts
    assert len(calls)==2 and history[0]['passed']
    assert history[1]['requirement_ids']==[4] and 'error' in history[1]
