import pytest
from pydantic import TypeAdapter,ValidationError
from zhijiang.math_tool_schema import typed_construction


@pytest.mark.parametrize('op,refs,expr',[
    ('point_on_function',[],['u']),('point_on_curve',['f','g'],['u']),
    ('transform',['shape'],['u','0']),('align',['shape','a','b','c'],['u']),
    ('rectangle',[],['0','0','1']),('segment',['a'],[]),
    ('polygon',['a','b'],[]),('series',['f'],['0'])])
def test_operator_arity_rejected_in_planning_contract(op,refs,expr):
    with pytest.raises(ValidationError):TypeAdapter(typed_construction()).validate_python(
        {'id':'obj','op':op,'refs':refs,'expr':expr})


@pytest.mark.parametrize('op,refs,expr',[
    ('point_on_function',['f'],['u']),('point_on_curve',['f'],['u']),
    ('transform',['shape'],['u','0','0']),('align',['shape','a','b','c','d'],['u']),
    ('rectangle',[],['0','0','1','1']),('segment',['a','b'],[]),
    ('polygon',['a','b','c'],[]),('series',['f'],['0','3']),
    ('intersection',['a','b'],[]),('intersection',['a','b'],['1'])])
def test_valid_operator_tools_preserve_data(op,refs,expr):
    item=TypeAdapter(typed_construction()).validate_python({'id':'obj','op':op,'refs':refs,'expr':expr})
    assert item.op==op and item.refs==refs and item.expr==expr
