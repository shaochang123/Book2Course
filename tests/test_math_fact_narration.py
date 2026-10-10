from types import SimpleNamespace

import pytest

from tests.test_math_construction import compile,program
from zhijiang.math_fact_narration import (bind_source_fact_schedule,source_facts,
    validate_source_fact_schedule,display_source_statement,speak_source_statement)
from zhijiang.visual_planning import VisualSceneError,verify_visual_scene


def fact_scene():
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-1,2]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(m)','rhs':'value(f,u)'}])
    return compile(p)


def requirements():
    return [{'id':7,'kind':'condition','statement':'输入必须大于零且不取单位值。',
        'source_excerpts':[{'source_id':3,'page':2,'quote':'The input must be positive and different from one.'}]},
        {'id':9,'kind':'example','statement':'已解算例的原函数与对应点需要一起观察。',
        'source_excerpts':[{'source_id':4,'page':3,'quote':'Observe the function and its matching point.'}]}]


def test_reviewed_facts_are_literal_complete_and_conditions_precede_motion():
    scene=fact_scene();facts=requirements()
    review=SimpleNamespace(checks=[SimpleNamespace(requirement_id=i,supported=True,steps=[3]) for i in [7,9]])
    bind_source_fact_schedule(scene,facts,review)
    assert scene.mathematical_model['source_fact_schedule']==[[7],[],[9]]
    assert source_facts(scene,0)[0]['statement']==facts[0]['statement']
    assert source_facts(scene,2)[0]['source_excerpts'][0]['page']==3
    verify_visual_scene(scene)
    scene.beats[0].narration='观察函数上的点，其坐标最终等于二。'
    with pytest.raises(VisualSceneError,match='数字未绑定'):verify_visual_scene(scene)


def test_fact_schedule_rejects_omission_unknown_ids_and_unapproved_content():
    scene=fact_scene()
    bad=SimpleNamespace(checks=[SimpleNamespace(requirement_id=i,supported=i!=9,steps=[1]) for i in [7,9]])
    with pytest.raises(VisualSceneError,match='未通过'):bind_source_fact_schedule(scene,requirements(),bad)
    good=SimpleNamespace(checks=[SimpleNamespace(requirement_id=i,supported=True,steps=[1]) for i in [7,9]])
    bind_source_fact_schedule(scene,requirements(),good)
    scene.mathematical_model['source_fact_schedule']=[[7],[],[]]
    with pytest.raises(VisualSceneError,match='遗漏'):validate_source_fact_schedule(scene)
    scene.mathematical_model['source_fact_schedule']=[[7,12],[],[]]
    with pytest.raises(VisualSceneError,match='编号无效'):validate_source_fact_schedule(scene)


def test_source_math_formatting_preserves_fraction_order_and_inequalities():
    statement=r'对于 $x > 0, b > 0, b \neq 1$，份额为 $\frac{2}{3}$。'
    display=display_source_statement(statement)
    spoken=speak_source_statement(statement)
    assert 'b ≠ 1' in display and '(2)/(3)' in display
    assert 'b 大于 0' in spoken and 'b 不等于 1' in spoken
    assert '(2)除以(3)' in spoken
    # Unknown commands remain inert text; they never enter MathTex or eval.
    assert r'\write18{test}' in display_source_statement(r'\write18{test}')
