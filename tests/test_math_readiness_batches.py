import json

import pytest

from zhijiang.agents import GenerationError
from zhijiang.math_inventory import check_construction_readiness, computed_inventory
from zhijiang.math_construction import Compiler
from tests.test_math_graph_repair import source_graph


def test_readiness_batches_preserve_all_ids_and_infeasible_subjects():
    graph=source_graph();ledger=computed_inventory(Compiler(graph))
    requirements=[{'id':i,'statement':'必须表达输入教材的实际条件。'} for i in [1,4,7]]
    calls=[]
    class Client:
        def generate(self,schema,instruction,material):
            batch=json.loads(material.split('独立来源要求：')[1].split('\n实际对象')[0])
            calls.append([r['id'] for r in batch])
            assert len(batch)<=2
            return schema.model_validate({'checks':[{'requirement_id':r['id'],
                'observation':'现有对象没有必要的独立自由度。' if r['id']==4 else '实际函数及动点能表达本项条件。',
                'feasible':r['id']!=4,'objects':['f','p']} for r in batch]})
    result=check_construction_readiness(Client(),requirements,graph,ledger,'original','tools')
    assert calls==[[1,4],[7]]
    assert [c.requirement_id for c in result.checks]==[1,4,7]
    assert not result.checks[1].feasible


def test_readiness_batch_service_failure_never_returns_partial_success():
    graph=source_graph();ledger=computed_inventory(Compiler(graph))
    calls=[]
    class Client:
        def generate(self,schema,instruction,material):
            calls.append(schema.__name__)
            if len(calls)>1:raise GenerationError('service unavailable')
            return schema.model_validate({'checks':[{'requirement_id':i,
                'observation':'实际函数动点能够表达当前要求。','feasible':True,'objects':['f','p']} for i in [1,2]]})
    with pytest.raises(GenerationError,match='unavailable'):
        check_construction_readiness(Client(),[{'id':i} for i in [1,2,3]],graph,ledger,'original','tools')
    assert len(calls)==2
