from types import SimpleNamespace
import pytest

from tests.test_math_construction import program, compile
from zhijiang.math_identity import (validate_translation_narration, hide_incidental_points,
    validate_identity_bindings, apply_identity_colours, legend_entries)
from zhijiang.math_coverage import MathSubjectBindingError
from zhijiang.visual_planning import verify_visual_scene, VisualSceneError


def moving_shape(narration, expr):
    p=program([
        {'id':'base','op':'rectangle','expr':['0','0','2','1'],'visible':False},
        {'id':'piece','op':'transform','refs':['base'],'expr':expr}],
        [{'lhs':'area(piece)','rhs':'area(base)'}])
    for op in p.operations: op.narration=narration
    for op,value in zip(p.operations,[.5,.8,1.1]): op.changes={'u':value}
    s=compile(p);s.verification=verify_visual_scene(s)
    return p,s


def test_direction_guard_rejects_downward_narration_for_horizontal_translation():
    _,s=moving_shape('向下平移此部分，保持实际面积不变。',['0','u','0'])
    with pytest.raises(VisualSceneError,match='口播平移方向无效'):validate_translation_narration(s)


def test_direction_guard_accepts_actual_horizontal_translation():
    _,s=moving_shape('向右平移此部分，保持实际面积不变。',['0','u','0'])
    validate_translation_narration(s)


def test_direction_guard_cannot_substitute_rotation_for_translation():
    _,s=moving_shape('向下平移此部分，保持实际面积不变。',['-u','0','0'])
    with pytest.raises(VisualSceneError,match='口播平移方向无效'):validate_translation_narration(s)


def identity_scene():
    p=program([
        {'id':'a','op':'point','expr':['0','0'],'label':'辅助坐标'},
        {'id':'whole','op':'rectangle','expr':['0','0','2','2'],'reference':True},
        {'id':'lower','op':'rectangle','expr':['0','0','2','1'],'visible':False},
        {'id':'upper','op':'rectangle','expr':['0','1','2','2']},
        {'id':'moved','op':'transform','refs':['lower'],'expr':['0','u','0']}],
        [{'lhs':'area(moved)','rhs':'area(lower)'}])
    p.roles={'moved':'移动部分','upper':'固定部分'}
    s=compile(p);s.verification=verify_visual_scene(s)
    graph={'entities':[{'id':'lo','name':'原图下部','kind':'polygon'},
        {'id':'hi','name':'原图上部','kind':'polygon'},
        {'id':'w','name':'整体','kind':'polygon'},
        {'id':'one','name':'类别甲','kind':'category'},
        {'id':'two','name':'类别乙','kind':'category'}],
        'relations':[{'first':'lo','second':'hi','predicate':'below','statement':'下部在同一图形上部的下方。'},
            {'first':'lo','second':'w','predicate':'part_of','statement':'下部是整体中划分出的部分。'},
            {'first':'hi','second':'w','predicate':'part_of','statement':'上部是整体中划分出的部分。'},
            {'first':'lo','second':'one','predicate':'member_of','statement':'下部属于类别甲。'},
            {'first':'hi','second':'two','predicate':'member_of','statement':'上部属于类别乙。'}]}
    bindings=[SimpleNamespace(entity_id=n,object_id=o,step=1) for n,o in [('lo','lower'),('hi','upper'),('w','whole')]]
    return p,s,graph,bindings


def test_same_area_is_not_enough_to_swap_source_parts():
    p,s,g,b=identity_scene()
    validate_identity_bindings(g,b,s,p)
    b[0].object_id='upper';b[1].object_id='lower'
    with pytest.raises(MathSubjectBindingError,match='来源身份关系'):validate_identity_bindings(g,b,s,p)


def test_identity_colours_follow_transformed_actor_and_both_legends():
    p,s,g,b=identity_scene();validate_identity_bindings(g,b,s,p)
    apply_identity_colours(g,b,s,p)
    shapes={o.id:o for o in s.objects}
    assert shapes['moved'].color==shapes['lower'].color
    assert shapes['moved'].color!=shapes['upper'].color
    assert dict(legend_entries(s,{'moved','upper'}))=={'类别甲':shapes['moved'].color,'类别乙':shapes['upper'].color}
    from zhijiang.visual_media import visual_summary_svg
    svg=visual_summary_svg(s,0)
    assert '类别甲' in svg and '类别乙' in svg
    assert p.constructions[-1].color==shapes['moved'].color


def test_auxiliary_points_hidden_without_removing_computational_dependencies():
    p,s,g,b=identity_scene()
    hidden=hide_incidental_points(p,[{'subjects':[{'kind':'polygon'}]}])
    assert not hidden.constructions[0].visible
    assert hidden.constructions[0].expr==p.constructions[0].expr
    assert 'a_name' not in compile(hidden).verification.get('visible',[])
    assert hide_incidental_points(p,[{'subjects':[{'kind':'point'}]}]) is p


def test_declared_teaching_point_is_retained():
    p,*_=identity_scene();p.roles['a']='实际顶点'
    assert hide_incidental_points(p,[]).constructions[0].visible


def test_distinct_source_nodes_cannot_bind_one_object():
    p,s,g,b=identity_scene();b[1].object_id='lower'
    with pytest.raises(MathSubjectBindingError,match='同一几何对象'):validate_identity_bindings(g,b,s,p)


def test_unique_spatial_permutation_repairs_identities_without_changing_geometry():
    from zhijiang.math_identity import repair_spatial_identity_permutation
    import copy
    p,s,g,b=identity_scene();before=copy.deepcopy(s.verification)
    b[0].object_id='upper';b[1].object_id='lower'
    repaired=repair_spatial_identity_permutation(g,b,s,p)
    assert repaired and repaired[0].object_id=='lower' and repaired[1].object_id=='upper'
    assert s.verification==before
    assert {x.object_id for x in repaired}=={x.object_id for x in b}


def test_ambiguous_spatial_permutation_remains_rejected():
    from zhijiang.math_identity import repair_spatial_identity_permutation
    p,s,g,b=identity_scene()
    g['relations']=[r for r in g['relations'] if r['predicate']!='below']
    assert repair_spatial_identity_permutation(g,b,s,p) is None


def test_single_transform_hides_nonreference_original_and_records_edit():
    from zhijiang.math_identity import normalize_single_actor_visibility
    p=program([{'id':'base','op':'rectangle','expr':['0','0','2','1']},
        {'id':'moved','op':'transform','refs':['base'],'expr':['0','u','0']}],
        [{'lhs':'area(moved)','rhs':'area(base)'}])
    fixed,history=normalize_single_actor_visibility(p)
    s=compile(fixed);s.verification=verify_visual_scene(s)
    assert history and history[0]['source']=='base'
    assert all('base' not in state['visible'] and 'moved' in state['visible'] for state in s.verification['states'])
    assert p.constructions==fixed.constructions


def test_actor_visibility_keeps_explicit_reference_and_rejects_multiple_copies():
    from zhijiang.math_identity import normalize_single_actor_visibility
    p,s=moving_shape('移动部分并比较实际面积关系。',['0','u','0'])
    p.constructions[0].visible=True;p.constructions[0].reference=True
    fixed,history=normalize_single_actor_visibility(p)
    assert not history and verify_visual_scene(compile(fixed))['passed']
    p.constructions[0].reference=False
    p.constructions.append(p.constructions[1].model_copy(update={'id':'another','expr':['0','-u','0']}))
    fixed,history=normalize_single_actor_visibility(p)
    assert not history
    with pytest.raises(VisualSceneError,match='同一数学对象'):verify_visual_scene(compile(fixed))


def test_source_identity_display_names_are_chinese():
    from zhijiang.math_identity import SourceEntity
    from pydantic import ValidationError
    with pytest.raises(ValidationError):SourceEntity(id='a',name='Person 1',kind='category')
    assert SourceEntity(id='a',name='领取者甲',kind='category').name=='领取者甲'
