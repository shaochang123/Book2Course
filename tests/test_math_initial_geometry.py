import pytest
from tests.test_math_construction import program
from zhijiang.math_construction import Compiler
from zhijiang.math_inventory import computed_inventory,validate_initial_geometry
from zhijiang.visual_planning import VisualSceneError


@pytest.mark.parametrize('initial',[0,1])
def test_undefined_intersection_is_rejected_before_readiness(initial):
    p=program([
        {'id':'a','op':'point','expr':['0','0']},
        {'id':'b','op':'point','expr':['1','0']},
        {'id':'c','op':'point','expr':['0','1']},
        {'id':'d','op':'point','expr':['1','u+1']},
        {'id':'ab','op':'line','refs':['a','b']},
        {'id':'cd','op':'line','refs':['c','d']},
        {'id':'i','op':'intersection','refs':['ab','cd'],'visible':False}],
        [{'lhs':'line_distance(i,ab)','rhs':'0'}],parameters={'u':initial})
    ledger=computed_inventory(Compiler(p))
    if initial==0:
        assert ledger['objects']['i']['coordinates'][0]['initial'] is None
        with pytest.raises(VisualSceneError,match='i.coordinates'):
            validate_initial_geometry(ledger)
    else:
        validate_initial_geometry(ledger)
        assert ledger['objects']['i']['coordinates'][0]['initial']==-1
