"""Construct new values/functions and reject mathematically wrong drawn objects."""
import copy
import math

import pytest
pytest.importorskip('sympy')

from zhijiang.math_construction import (MathProgramDraft, compile_program,
    resolve_parameters, validate_actual_claims)
from zhijiang.models import Evidence
from zhijiang.visual_planning import object_geometry, verify_visual_scene, VisualSceneError


def program(constructions,claims,parameters=None,changes=None):
    return MathProgramDraft(title='通用数学构造测试',objective='检验实际对象是否保持当前数学关系。',source_id=1,
        parameters=parameters or {'u':.3},constructions=constructions,claims=[{'source_id':1,**c} for c in claims],
        operations=[{'narration':'观察实际对象的变化，并比较测量结果。','changes':v} for v in
            (changes or [{'u':.6},{'u':1.2},{'u':.8}])])


def compile(p):
    return compile_program(p,Evidence(page=1,quote='Source contains the tested mathematical construction.'),
        {1:{'page':1,'quote':'Source contains the tested mathematical construction.'}})


def geometry(scene,parameters=None):
    values=resolve_parameters(scene,parameters or scene.parameters)
    return {o.id:object_geometry(o,values) for o in scene.objects},values


def test_fixed_series_order_and_readable_ray_line_geometry():
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-.6,.6]},
        {'id':'s','op':'series','refs':['f'],'expr':['0','degree'],'domain':[-.6,.6],'color':'#0000FF'},
        {'id':'a','op':'point','expr':['0','0']},{'id':'b','op':'point','expr':['cos(u)','sin(u)']},
        {'id':'r','op':'ray','refs':['a','b']},{'id':'l','op':'line','refs':['a','b']}],
        [{'lhs':'derivative(s,0,2)','rhs':'derivative(f,0,2)'}],parameters={'degree':2,'u':.2})
    scene=compile(p);assert verify_visual_scene(scene)['passed']
    assert scene.objects[1].expression=='x**2/2 + x + 1'
    assert scene.objects[1].color!='#0000FF'
    assert scene.objects[-2].kind=='arrow' and not scene.objects[-2].double_tip
    assert scene.objects[-1].double_tip
    drawn,_=geometry(scene)
    assert drawn['r']['points'][1][0]>drawn['b']['points'][0][0]
    assert drawn['l']['points'][0][0]<drawn['a']['points'][0][0]
    p.claims[0].lhs='length(r)'
    with pytest.raises(VisualSceneError,match='无限直线和射线'):compile(p)
    p.claims[0].lhs='derivative(s,0,2)'
    p.operations[0].changes={'degree':3}
    with pytest.raises(VisualSceneError,match='离散|连续控制参数'):compile(p)


def test_noncanonical_right_triangle_squares_and_corruption():
    p=program([
        {'id':'a','op':'point','expr':['0','0']},
        {'id':'b','op':'point','expr':['5*u','0']},
        {'id':'c','op':'point','expr':['0','12*u']},
        {'id':'ab','op':'segment','refs':['a','b']},
        {'id':'ac','op':'segment','refs':['a','c']},
        {'id':'bc','op':'segment','refs':['b','c']},
        {'id':'sa','op':'square','refs':['ab'],'expr':['-1']},
        {'id':'sb','op':'square','refs':['ac']},
        {'id':'sc','op':'square','refs':['bc'],'expr':['-1']}],
        [{'lhs':'area(sa)+area(sb)','rhs':'area(sc)'}])
    scene=compile(p);verify_visual_scene(scene)
    g,values=geometry(scene)
    validate_actual_claims(scene,g,values)
    corrupt=copy.deepcopy(g);corrupt['sc']['points'][0][0]+=1
    with pytest.raises(VisualSceneError,match='实际数学关系失败') as error:
        validate_actual_claims(scene,corrupt,values,step_index=2,endpoint=True)
    assert error.value.math_failure['parameters']==p.parameters
    assert error.value.math_failure['step']==2 and error.value.math_failure['endpoint']
    assert error.value.math_failure['actual_geometry']['sc']==corrupt['sc']


def test_shifted_locus_couples_actual_point_and_foot():
    scene=compile(program([
        {'id':'f','op':'point','expr':['2','3']},
        {'id':'a','op':'point','expr':['-3','-1']},
        {'id':'b','op':'point','expr':['6','-1']},
        {'id':'line','op':'segment','refs':['a','b']},
        {'id':'curve','op':'locus','expr':['distance(p,f)','line_distance(p,line)'],'domain':[-1,5]},
        {'id':'moving','op':'point_on_function','refs':['curve'],'expr':['u']},
        {'id':'foot','op':'projection','refs':['moving','line']},
        {'id':'focus_distance','op':'segment','refs':['moving','f']},
        {'id':'directrix_distance','op':'segment','refs':['moving','foot']}],
        [{'lhs':'distance(moving,f)','rhs':'distance(moving,foot)'}]))
    verify_visual_scene(scene)
    g,values=geometry(scene,{'u':4})
    assert g['moving']['points'][0]==pytest.approx([4,1.5])
    validate_actual_claims(scene,g,values)


def test_series_coefficients_derive_from_unseen_function():
    scene=compile(program([
        {'id':'f','op':'function','expr':['exp(x)'],'domain':[-.5,.5]},
        {'id':'s','op':'series','refs':['f'],'expr':['0','3','w','w','w'],'domain':[-.5,.5]}],
        [{'lhs':'value(f,0)','rhs':'value(s,0)'}],parameters={'w':0},changes=[{'w':.2},{'w':.7},{'w':1}]))
    verify_visual_scene(scene)
    g,v=geometry(scene,{'w':1});validate_actual_claims(scene,g,v)
    curve=next(o for o in scene.objects if o.id=='s')
    from zhijiang.visual_planning import evaluate
    assert evaluate(curve.expression,{**v,'x':.4})==pytest.approx(1+.4+.4**2/2+.4**3/6)


def test_close_function_points_get_distinct_anchored_labels_and_curve_colors():
    scene=compile(program([
        {'id':'f','op':'function','expr':['sin(x)'],'domain':[-1,1],'color':'#FF8080'},
        {'id':'g','op':'function','expr':['x'],'domain':[-1,1],'color':'#80C0FF'},
        {'id':'a','op':'point_on_function','refs':['f'],'expr':['u'],'label':'函数点'},
        {'id':'b','op':'point_on_function','refs':['g'],'expr':['u'],'label':'直线点'}],
        [{'lhs':'xcoord(a)','rhs':'xcoord(b)'}],changes=[{'u':.1},{'u':.3},{'u':.5}]))
    verify_visual_scene(scene)
    objects={o.id:o for o in scene.objects}
    assert objects['a'].color==objects['f'].color and objects['b'].color==objects['g'].color
    from zhijiang.visual_coordinates import EuclideanViewport
    viewport=EuclideanViewport(scene.x_range,scene.y_range,1060,430,(600,310))
    for u in [.1,.2,.3,.4,.5]:
        drawn,values=geometry(scene,{'u':u})
        a=viewport.point(*drawn['a_name']['points'][0]);b=viewport.point(*drawn['b_name']['points'][0])
        assert abs(a[0]-b[0])>=66 or abs(a[1]-b[1])>=26
        assert 'a_x' in objects['a_name'].position[0] and 'b_y' in objects['b_name'].position[1]


def test_displayed_centered_series_is_identical_to_actual_expanded_curve():
    scene=compile(program([
        {'id':'f','op':'function','expr':['exp(x)'],'domain':[1,3]},
        {'id':'s','op':'series','refs':['f'],'expr':['2','3','w','w','w'],'domain':[1,3]}],
        [{'lhs':'value(f,2)','rhs':'value(s,2)'}],parameters={'w':0},changes=[{'w':.2},{'w':.7},{'w':1}]))
    from zhijiang.visual_planning import evaluate,expression_tex
    actual=next(o.expression for o in scene.objects if o.id=='s')
    shown=scene.mathematical_model['display_expressions']['s']
    assert '(x-(2))**3' in shown and 'x - 2' in expression_tex(shown)
    for w in [.1,.5,1]:
        for x in [1.2,2,2.6]:
            assert evaluate(shown,{'w':w,'x':x})==pytest.approx(evaluate(actual,{'w':w,'x':x}))


def test_equal_partition_conservation_and_rigid_transform():
    scene=compile(program([
        {'id':'whole','op':'rectangle','expr':['0','0','7','3']},
        {'id':'parts','op':'partition','refs':['whole'],'expr':['2','4'],'reference':True},
        {'id':'piece','op':'transform','refs':['parts_0_2'],'expr':['u','2','-1']}],
        [{'lhs':'area(parts)','rhs':'area(whole)'},{'lhs':'area(piece)','rhs':'area(parts_0_2)'}]))
    verify_visual_scene(scene)


def test_rotated_measurements_reduce_actual_vertices_without_relaxing_limits():
    p=program([
        {'id':'whole','op':'rectangle','expr':['-2','1','5','4'],'reference':True},
        {'id':'moved','op':'transform','refs':['whole'],'expr':['u','3','-2']},
        {'id':'a','op':'point','expr':['-2','1']},
        {'id':'b','op':'point','expr':['5','1']},
        {'id':'edge','op':'segment','refs':['a','b'],'reference':True},
        {'id':'turned','op':'transform','refs':['edge'],'expr':['u','3','-2']}],
        [{'lhs':'area(moved)','rhs':'area(whole)'},
         {'lhs':'length(turned)','rhs':'length(edge)'}])
    for op in p.operations:op.measurements={'变换后面积':'area(moved)','变换后边长':'length(turned)'}
    scene=compile(p)
    assert all(len(c.expression)<20 for b in scene.beats for c in b.calculations)
    assert verify_visual_scene(scene)['passed']
    drawn,values=geometry(scene)
    drawn['moved']['points'][0][0]+=2
    with pytest.raises(VisualSceneError,match='实际数学关系失败'):
        validate_actual_claims(scene,drawn,values)


def test_signed_coordinates_and_directed_angles_survive_quadrants():
    p=program([
        {'id':'o','op':'point','expr':['0','0']},
        {'id':'a','op':'point','expr':['2','0']},
        {'id':'p','op':'polar_point','expr':['r','u']},
        {'id':'axis','op':'segment','refs':['o','a']},
        {'id':'radial','op':'segment','refs':['o','p']}],
        [{'lhs':'xcoord(p)','rhs':'r*cos(u)'},
         {'lhs':'ycoord(p)','rhs':'r*sin(u)'}],
        parameters={'r':3,'u':.4},changes=[{'u':2.2},{'u':-1.1},{'r':-3}])
    scene=compile(p)
    assert verify_visual_scene(scene)['passed']
    from zhijiang.math_construction import Compiler
    from zhijiang.visual_planning import evaluate
    measured=Compiler(p).expression('signed_angle(axis,radial)')
    assert evaluate(measured,{'r':3,'u':-1.1})==pytest.approx(-1.1)
    drawn,values=geometry(scene,{'r':3,'u':2.2})
    assert drawn['p']['points'][0][0]<0
    validate_actual_claims(scene,drawn,values)
    drawn['p']['points'][0][0]=abs(drawn['p']['points'][0][0])
    with pytest.raises(VisualSceneError,match='实际数学关系失败'):
        validate_actual_claims(scene,drawn,values)


def test_rigid_transform_preserves_unbounded_line_semantics():
    p=program([{'id':'a','op':'point','expr':['0','0']},
        {'id':'b','op':'point','expr':['2','0']},
        {'id':'line','op':'line','refs':['a','b'],'reference':True},
        {'id':'turned','op':'transform','refs':['line'],'expr':['u','1','2']}],
        [{'lhs':'signed_angle(line,turned)','rhs':'u'}])
    scene=compile(p)
    assert verify_visual_scene(scene)['passed']
    turned=next(o for o in scene.objects if o.id=='turned')
    assert turned.kind=='arrow' and turned.double_tip
    p.claims[0].lhs='length(turned)'
    with pytest.raises(VisualSceneError,match='无限直线和射线'):compile(p)


def test_remote_function_tails_clip_without_hiding_teaching_anchors():
    p=program([{'id':'f','op':'function','expr':['5**x'],'domain':[-1,4]},
        {'id':'g','op':'inverse','refs':['f'],'domain':[.5,5]},
        {'id':'a','op':'point_on_function','refs':['f'],'expr':['u']},
        {'id':'b','op':'point_on_function','refs':['g'],'expr':['a_y']}],
        [{'lhs':'xcoord(a)','rhs':'ycoord(b)'}],changes=[{'u':.4},{'u':.7},{'u':1}])
    scene=compile(p)
    assert scene.mathematical_model['camera_policy']=='finite-anchors'
    assert scene.y_range[1]<10
    assert verify_visual_scene(scene)['passed']
    p.constructions[0].domain=[-.5,1]
    assert verify_visual_scene(compile(p))['passed']


def test_partition_child_roles_use_compiled_inventory():
    p=program([{'id':'whole','op':'rectangle','expr':['0','0','7','3']},
        {'id':'parts','op':'partition','refs':['whole'],'expr':['2','4']},
        {'id':'piece','op':'transform','refs':['parts_0_2'],'expr':['u','2','-1']}],
        [{'lhs':'area(parts)','rhs':'area(whole)'}])
    p.roles={'parts_0_2':'选中部分'}
    assert compile(p).mathematical_model['roles']['parts_0_2']=='选中部分'
    p.roles={'missing':'不存在'}
    with pytest.raises(VisualSceneError,match='真实对象'):compile(p)


def test_expanded_point_annotations_survive_renderer_serialization():
    items=[{'id':f'p{i}','op':'point','expr':[str(i),'u'],'label':'端点'} for i in range(16)]
    scene=compile(program(items,[{'lhs':'ycoord(p0)','rhs':'ycoord(p1)'}]))
    from zhijiang.models import VisualScenePlan
    roundtrip=VisualScenePlan.model_validate_json(scene.model_dump_json())
    assert len(roundtrip.objects)==32
    assert len(roundtrip.mathematical_model['point_labels'])==16


def test_endpoint_claim_is_checked_at_its_real_step_and_cannot_be_skipped():
    p=program([{'id':'a','op':'point','expr':['u','0']},{'id':'b','op':'point','expr':['1','0']}],
        [{'lhs':'xcoord(a)','rhs':'1','phase':'endpoint','steps':[3]}],changes=[{'u':.4},{'u':.7},{'u':1}])
    scene=compile(p);assert verify_visual_scene(scene)['passed']
    drawn,values=geometry(scene,{'u':.9})
    assert validate_actual_claims(scene,drawn,values,step_index=2,endpoint=True)==[]
    with pytest.raises(VisualSceneError,match='实际数学关系失败'):
        validate_actual_claims(scene,drawn,values,step_index=3,endpoint=True)
    p.claims[0].steps=[4]
    with pytest.raises(VisualSceneError,match='步骤编号'):compile(p)


def test_anchored_point_label_can_use_equal_unit_letterbox_without_clipping():
    scene=compile(program([{'id':'a','op':'point','expr':['0','u'],'label':'左端点'},
        {'id':'b','op':'point','expr':['.03','u'],'label':'右端点'},
        {'id':'c','op':'point','expr':['0','6']}],
        [{'lhs':'xcoord(b)-xcoord(a)','rhs':'.03'}]))
    from zhijiang.visual_geometry_checks import check_geometry_visibility
    drawn,_=geometry(scene)
    check_geometry_visibility(scene,drawn,{o.id for o in scene.objects})


@pytest.mark.parametrize('theta',[.9,-.9,2.4,-2.4])
def test_arc_endpoint_matches_actual_ray_in_both_directions(theta):
    scene=compile(program([
        {'id':'o','op':'point','expr':['0','0']},
        {'id':'a','op':'point','expr':['2','0']},
        {'id':'b','op':'polar_point','expr':['2','u']},
        {'id':'first','op':'segment','refs':['o','a']},
        {'id':'second','op':'segment','refs':['o','b']},
        {'id':'arc','op':'angle_arc','refs':['first','second'],'expr':['.5']}],
        [{'lhs':'distance(o,b)','rhs':'2'}]))
    g,_=geometry(scene,{'u':theta})
    assert g['arc']['points'][-1]==pytest.approx([.5*math.cos(theta),.5*math.sin(theta)])


def test_inverse_uses_source_function_not_prebuilt_base():
    scene=compile(program([
        {'id':'f','op':'function','expr':['7**x'],'domain':[-.5,1]},
        {'id':'g','op':'inverse','refs':['f'],'domain':[.4,7]},
        {'id':'a','op':'point_on_function','refs':['f'],'expr':['u']},
        {'id':'b','op':'point_on_function','refs':['g'],'expr':['a_y']}],
        [{'lhs':'xcoord(a)','rhs':'ycoord(b)'},{'lhs':'ycoord(a)','rhs':'xcoord(b)'}],
        changes=[{'u':.6},{'u':.9},{'u':.8}]))
    verify_visual_scene(scene)


def test_tautology_and_non_square_and_derived_cycles_rejected():
    p=program([{'id':'a','op':'point','expr':['u','0']},{'id':'b','op':'point','expr':['1','0']}],
        [{'lhs':'u-u','rhs':'0'}])
    with pytest.raises(VisualSceneError,match='实际对象'):compile(p)
    scene=compile(program([{'id':'a','op':'point','expr':['u','0']},{'id':'b','op':'point','expr':['1','0']}],
        [{'lhs':'ycoord(a)','rhs':'0'}]))
    scene.derived_parameters={'a_x':'b_x','b_x':'a_x'}
    with pytest.raises(VisualSceneError,match='循环'):resolve_parameters(scene,scene.parameters)


def test_inventory_does_not_freeze_coincident_controlled_ray_origins():
    from zhijiang.math_construction import MathConstructionDraft,Compiler
    draft=MathConstructionDraft(title='方向关系',objective='观察共同端点的两条射线及其夹角。',source_id=1,
        parameters={'u':0},constructions=[
            {'id':'a','op':'point','expr':['0','0']},
            {'id':'b','op':'point','expr':['1','0']},
            {'id':'c','op':'point','expr':['u','0']},
            {'id':'d','op':'point','expr':['u','1']},
            {'id':'first','op':'segment','refs':['a','b']},
            {'id':'second','op':'segment','refs':['c','d']},
            {'id':'arc','op':'angle_arc','refs':['first','second'],'expr':['.5']}])
    with pytest.raises(VisualSceneError,match='共端点'):Compiler(draft)
    draft.constructions[5].refs[0]='a'
    assert Compiler(draft).items['arc']['type']=='parametric'


def test_shared_segment_endpoint_arc_and_explicit_vertex_angles():
    items=[{'id':'a','op':'point','expr':['0','0']},
        {'id':'b','op':'point','expr':['5','0']},
        {'id':'c','op':'point','expr':['1.2','u']},
        {'id':'ab','op':'segment','refs':['a','b']},
        {'id':'bc','op':'segment','refs':['b','c']},
        {'id':'ca','op':'segment','refs':['c','a']},
        {'id':'arc','op':'angle_arc','refs':['ab','ca'],'expr':['.5']}]
    scene=compile(program(items,[{'lhs':'angle_at(a,ab,ca)+angle_at(b,ab,bc)+angle_at(c,bc,ca)',
        'rhs':'pi'}],changes=[{'u':1.1},{'u':2.3},{'u':3.4}]))
    assert verify_visual_scene(scene)['passed']
    g,_=geometry(scene,{'u':2.3})
    assert g['arc']['points'][0]==pytest.approx([.5,0])
    assert g['arc']['points'][-1]==pytest.approx([.5*1.2/math.hypot(1.2,2.3),.5*2.3/math.hypot(1.2,2.3)])


def test_angle_at_rejects_unrelated_vertex_and_a_ray_target_as_origin():
    from zhijiang.math_construction import Compiler
    p=program([{'id':'a','op':'point','expr':['0','0']},
        {'id':'b','op':'point','expr':['1','0']},
        {'id':'c','op':'point','expr':['0','u']},
        {'id':'wrong','op':'point','expr':['3','3']},
        {'id':'ab','op':'segment','refs':['a','b']},
        {'id':'ac','op':'segment','refs':['a','c']}],
        [{'lhs':'distance(a,b)','rhs':'1'}])
    compiler=Compiler(p)
    with pytest.raises(VisualSceneError,match='顶点'):compiler.parse('angle_at(wrong,ab,ac)')
    p.constructions[4].op='ray'
    with pytest.raises(VisualSceneError,match='起点'):Compiler(p).parse('angle_at(b,ab,ac)')


def test_actual_power_claim_accepts_numeric_runtime_controls():
    p=program([{'id':'f','op':'function','expr':['b**x'],'domain':[-.2,1]},
        {'id':'a','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(a)','rhs':'b**u'}],changes=[{'u':.4},{'u':.7},{'u':1}])
    p.parameters['b']=3
    scene=compile(p)
    assert verify_visual_scene(scene)['passed']


def test_computed_expression_dag_keeps_limits_and_actual_geometry():
    from zhijiang.visual_planning import expression_tree
    import sympy as sp
    from zhijiang.math_construction import Compiler
    p=program([{'id':'a','op':'point','expr':['u','0']},
        {'id':'b','op':'point','expr':['u','1']}],[{'lhs':'xcoord(a)','relation':'positive'}])
    compiler=Compiler(p);u=compiler.symbols['u'];expr=sp.sin(u)
    for _ in range(12):expr=sp.sin(expr)+sp.cos(u)
    rendered=compiler.render_expression(expr)
    scene=compile(p);scene.derived_parameters.update(compiler.derived)
    scene.objects[0].position[0]=rendered
    assert any(name.startswith('zbc_aux_') for name in scene.derived_parameters)
    for expr in scene.derived_parameters.values():
        assert len(expr)<=220
        expression_tree(expr)
    drawn,_=geometry(scene,{'u':.3})
    expected=math.sin(.3)
    for _ in range(12):expected=math.sin(expected)+math.cos(.3)
    assert drawn['a']['points'][0][0]==pytest.approx(expected)


def test_angle_display_has_units_without_mislabeling_degrees():
    from zhijiang.math_construction import measurement_label
    assert measurement_label('夹角','angle_at(a,ab,ac)')=='夹角（弧度）'
    assert measurement_label('角度','angle_at(a,ab,ac)*180/pi')=='角度'
    assert measurement_label('夹角和','angle(a,b)+angle(b,c)')=='夹角和（弧度）'
    assert measurement_label('角差','abs(angle(a,b)-signed_angle(b,c))')=='角差（弧度）'
    assert measurement_label('角差','angle(a,b)+(-1)*(angle(b,c))')=='角差（弧度）'


def test_landmark_alignment_uses_actual_directions_and_preserves_rigid_length():
    p=program([
        {'id':'a','op':'point','expr':['3','5'],'visible':False},
        {'id':'b','op':'point','expr':['5','7'],'visible':False},
        {'id':'t','op':'point','expr':['-2','2'],'visible':False},
        {'id':'d','op':'point','expr':['-5','4'],'visible':False},
        {'id':'source','op':'segment','refs':['a','b'],'visible':False},
        {'id':'target','op':'segment','refs':['t','d'],'visible':False},
        {'id':'moving','op':'align','refs':['source','a','b','t','d'],'expr':['u']},
        {'id':'anchor','op':'align','refs':['a','a','b','t','d'],'expr':['u'],'visible':False}],
        [{'lhs':'length(moving)','rhs':'length(source)'},
         {'lhs':'distance(anchor,t)','rhs':'0','phase':'endpoint','steps':[3]},
         {'lhs':'signed_angle(moving,target)','rhs':'0','phase':'endpoint','steps':[3]}],
        parameters={'u':0},changes=[{'u':.2},{'u':.65},{'u':1}])
    scene=compile(p);assert verify_visual_scene(scene)['passed']
    drawn,values=geometry(scene,{'u':1})
    assert drawn['moving']['points'][0]==pytest.approx([-2,2])
    # Target direction length differs; alignment rotates without scaling.
    assert math.dist(*drawn['moving']['points'])==pytest.approx(math.sqrt(8))
    corrupt=copy.deepcopy(drawn);corrupt['moving']['points'][1][0]+=1
    with pytest.raises(VisualSceneError,match='实际数学关系失败'):
        validate_actual_claims(scene,corrupt,values,step_index=3,endpoint=True)
    p.operations[-1].changes={'u':1.1}
    with pytest.raises(VisualSceneError,match='对齐进度'):verify_visual_scene(compile(p))
    p.constructions[6].refs[-1]='t'
    with pytest.raises(VisualSceneError,match='方向不能退化'):compile(p)


def test_directed_arc_keeps_major_and_negative_sweep_and_checks_endpoint():
    p=program([{'id':'o','op':'point','expr':['0','0']},
        {'id':'a','op':'point','expr':['2','0']},
        {'id':'b','op':'polar_point','expr':['2','u']},
        {'id':'first','op':'ray','refs':['o','a']},
        {'id':'second','op':'ray','refs':['o','b']},
        {'id':'arc','op':'angle_arc','refs':['first','second'],'expr':['.5','u']}],
        [{'lhs':'distance(o,b)','rhs':'2'}],changes=[{'u':4},{'u':-4},{'u':-1}])
    scene=compile(p)
    assert verify_visual_scene(scene)['passed']
    g,values=geometry(scene,{'u':4})
    assert g['arc']['points'][50][1]>0
    validate_actual_claims(scene,g,values,step_index=1)
    p.constructions[-1].expr=['.5','u*2']
    with pytest.raises(VisualSceneError,match='实际角弧端点'):verify_visual_scene(compile(p))


def test_transform_subject_identity_rejects_duplicate_material_and_allows_reference():
    p=program([{'id':'part','op':'rectangle','expr':['0','0','2','3'],'label':'原图'},
        {'id':'moving','op':'transform','refs':['part'],'expr':['0','u','0'],'label':'移动图'}],
        [{'lhs':'area(part)','rhs':'area(moving)'}])
    with pytest.raises(VisualSceneError,match='同时作为主体'):verify_visual_scene(compile(p))
    p.constructions[0].reference=True
    scene=compile(p)
    assert verify_visual_scene(scene)['passed']
    assert scene.mathematical_model['roles']['part']=='参照·原图'
    from zhijiang.visual_media import visual_summary_svg
    svg=visual_summary_svg(scene)
    assert 'opacity=".45"' in svg and '参照·原图' in svg
    p.constructions[0].reference=False;p.constructions[0].visible=False
    assert verify_visual_scene(compile(p))['passed']
    p.operations[1].show=['part']
    with pytest.raises(VisualSceneError,match='同时作为主体'):verify_visual_scene(compile(p))


def test_rigid_transform_of_arc_and_function_keeps_curve_domain_and_coordinates():
    p=program([{'id':'o','op':'point','expr':['0','0']},
        {'id':'a','op':'point','expr':['2','0']},{'id':'b','op':'point','expr':['0','2']},
        {'id':'ab','op':'segment','refs':['o','a']},{'id':'bc','op':'segment','refs':['o','b']},
        {'id':'arc','op':'angle_arc','refs':['ab','bc'],'expr':['.5'],'reference':True},
        {'id':'turned','op':'transform','refs':['arc'],'expr':['u','3','1']},
        {'id':'f','op':'function','expr':['sin(x)'],'domain':[-.6,.8],'reference':True},
        {'id':'rotated','op':'transform','refs':['f'],'expr':['u','3','1']}],
        [{'lhs':'distance(o,a)','rhs':'2'}])
    scene=compile(p);assert verify_visual_scene(scene)['passed']
    g,_=geometry(scene,{'u':.4})
    assert g['turned']['points'][0]==pytest.approx([3+.5*math.cos(.4),1+.5*math.sin(.4)])
    assert g['rotated']['points'][0]==pytest.approx([3-.6*math.cos(.4)-math.sin(-.6)*math.sin(.4),
        1-.6*math.sin(.4)+math.sin(-.6)*math.cos(.4)])
    assert next(o for o in scene.objects if o.id=='rotated').domain==[-.6,.8]


def test_svg_preserves_full_objective_and_places_reference_point_label_below_header():
    p=program([{'id':'a','op':'point','expr':['0','0'],'label':'上端点'},
        {'id':'b','op':'point','expr':['1','u'],'label':'动点'}],[{'lhs':'xcoord(b)','rhs':'1'}])
    p.objective='观察实际数学对象变化，先说明当前定义域及符号条件，再比较各个连续位置的测量值，保留原始条件并核对来源。'
    scene=compile(p)
    from zhijiang.visual_media import visual_summary_svg
    import xml.etree.ElementTree as ET
    root=ET.fromstring(visual_summary_svg(scene))
    texts=root.findall('{http://www.w3.org/2000/svg}text')
    headings=[node.text for node in texts if node.attrib.get('y') in {'24','46','68'}]
    assert ''.join(headings)==p.objective


def test_parametric_endpoint_measurement_detects_false_rigid_join():
    p=program([{'id':'curve','op':'parametric','expr':['cos(x)','sin(x)'],'domain':[0,1],'visible':False},
        {'id':'moved','op':'transform','refs':['curve'],'expr':['0','u','0']},
        {'id':'end','op':'point_on_curve','refs':['curve'],'expr':['1'],'visible':False},
        {'id':'start','op':'point_on_curve','refs':['moved'],'expr':['0'],'visible':False}],
        [{'lhs':'distance(end,start)','rhs':'0','phase':'endpoint','steps':[3]}])
    with pytest.raises(VisualSceneError,match='实际数学关系失败'):verify_visual_scene(compile(p))
    p.constructions[1].expr=['1+u-0.8','0','0']
    assert verify_visual_scene(compile(p))['passed']


def test_computed_inventory_reports_actual_noncanonical_geometry():
    from zhijiang.math_construction import Compiler
    from zhijiang.math_inventory import computed_inventory
    p=program([{'id':'a','op':'point','expr':['-2','1'],'visible':False},
        {'id':'b','op':'point','expr':['4','1'],'visible':False},
        {'id':'c','op':'point','expr':['-2','1+u'],'visible':False},
        {'id':'ab','op':'segment','refs':['a','b']},
        {'id':'ac','op':'segment','refs':['a','c']},
        {'id':'poly','op':'polygon','refs':['a','b','c']},
        {'id':'f','op':'function','expr':['cos(x)'],'domain':[-3,3]},
        {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}],
        [{'lhs':'ycoord(m)','rhs':'value(f,u)'}],parameters={'u':2},
        changes=[{'u':.6},{'u':.9},{'u':.8}])
    ledger=computed_inventory(Compiler(p))
    assert ledger['objects']['poly']['area']['initial']==pytest.approx(6)
    assert ledger['objects']['ab']['length']['initial']==pytest.approx(6)
    assert ledger['objects']['c']['coordinates'][1]['initial']==pytest.approx(3)
    assert 'u' in ledger['objects']['poly']['area']['formula']
    angle=next(a for a in ledger['vertex_angles'] if a['expression']=='angle_at(a,ab,ac)')
    assert angle['radians']['initial']==pytest.approx(math.pi/2)


def test_line_intersection_derives_point_and_checks_parallel_or_reversed_ray():
    p=program([{'id':'a','op':'point','expr':['-1','0'],'visible':False},
        {'id':'b','op':'point','expr':['0','u'],'visible':False},
        {'id':'c','op':'point','expr':['2','0'],'visible':False},
        {'id':'d','op':'point','expr':['1','2'],'visible':False},
        {'id':'first','op':'ray','refs':['a','b']},
        {'id':'second','op':'ray','refs':['c','d']},
        {'id':'cross','op':'intersection','refs':['first','second']},
        {'id':'foot','op':'projection','refs':['cross','first'],'visible':False}],
        [{'lhs':'distance(cross,foot)','rhs':'0'}],parameters={'u':1},
        changes=[{'u':.8},{'u':1.2},{'u':1}])
    scene=compile(p);assert verify_visual_scene(scene)['passed']
    g,values=geometry(scene,{'u':1})
    assert g['cross']['points'][0]==pytest.approx([1,2])
    # The actual ray must reach the visible intersection, beyond its direction
    # anchor, rather than stopping at the old fixed quarter extension.
    assert g['first']['points'][1][0]>=g['cross']['points'][0][0]
    assert g['first']['points'][1][1]>=g['cross']['points'][0][1]
    corrupt=copy.deepcopy(g);corrupt['cross']['points'][0][0]+=.2
    with pytest.raises(VisualSceneError,match='交点'):validate_actual_claims(scene,corrupt,values)
    p.operations[-1].changes={'u':-2}
    with pytest.raises(VisualSceneError):verify_visual_scene(compile(p))
    p.operations[-1].changes={'u':-1}
    with pytest.raises(VisualSceneError,match='射线'):verify_visual_scene(compile(p))


def test_two_circle_intersection_preserves_actual_radii_and_rejects_impossible_state():
    p=program([{'id':'a','op':'point','expr':['-2','1'],'visible':False},
        {'id':'b','op':'point','expr':['2','1'],'visible':False},
        {'id':'first','op':'circle','refs':['a'],'expr':['u']},
        {'id':'second','op':'circle','refs':['b'],'expr':['3']},
        {'id':'cross','op':'intersection','refs':['first','second'],'expr':['1']}],
        [{'lhs':'distance(cross,a)','rhs':'u'}, {'lhs':'distance(cross,b)','rhs':'3'}],
        parameters={'u':3},changes=[{'u':2},{'u':4},{'u':3}])
    scene=compile(p);assert verify_visual_scene(scene)['passed']
    g,values=geometry(scene,{'u':3})
    assert g['cross']['points'][0]==pytest.approx([0,1+math.sqrt(5)])
    corrupt=copy.deepcopy(g);corrupt['cross']['points'][0][1]+=.3
    with pytest.raises(VisualSceneError,match='交点'):validate_actual_claims(scene,corrupt,values)
    p.operations[-1].changes={'u':.1}
    with pytest.raises(VisualSceneError):verify_visual_scene(compile(p))


@pytest.mark.parametrize('op',['point_on_curve','point_on_function'])
def test_point_parameter_stays_on_referenced_drawn_domain_even_for_hidden_points(op):
    curve={'id':'f','op':'parametric','expr':['cos(x)','sin(x)'],'domain':[-1,1]} if op=='point_on_curve' else {
        'id':'f','op':'function','expr':['x**2'],'domain':[-1,1]}
    p=program([curve,{'id':'m','op':op,'refs':['f'],'expr':['u**2'],'visible':False}],
        [{'lhs':'distance(m,m)','rhs':'0'}])
    with pytest.raises(VisualSceneError,match='点参数超出实际绘图域'):verify_visual_scene(compile(p))


def test_unicode_pi_is_exact_in_actual_measured_angle_claim():
    p=program([{'id':'a','op':'point','expr':['0','0']},
        {'id':'b','op':'point','expr':['1','0']},
        {'id':'c','op':'point','expr':['0','u']},
        {'id':'ab','op':'segment','refs':['a','b']},
        {'id':'ac','op':'segment','refs':['a','c']}],
        [{'lhs':'angle_at(a,ab,ac)','rhs':'π/2'}])
    assert verify_visual_scene(compile(p))['passed']


def test_parametric_control_point_is_rejected_before_typed_behavior():
    p=program([{'id':'f','op':'function','expr':['exp(x)'],'domain':[-1,2]},
        {'id':'moving','op':'parametric','expr':['u','exp(u)']}],
        [{'lhs':'value(f,u)','rhs':'exp(u)'}])
    with pytest.raises(VisualSceneError,match='单个控制点'):compile(p)
    p.constructions[1].op='point'
    assert verify_visual_scene(compile(p))['passed']


@pytest.mark.parametrize('start,end,ray,expected',[
    ([0,0],[0,2],False,[[0,-3],[0,4]]),
    ([1,1],[-1,1],True,[[1,1],[-2,1]]),
    ([0,0],[1,2],False,[[-1.5,-3],[2,4]])])
def test_mathematical_line_window_preserves_direction_and_ray_origin(start,end,ray,expected):
    from zhijiang.visual_coordinates import extend_line_to_window
    result=extend_line_to_window(start,end,[-2,3,-3,4],ray=ray)
    for actual,target in zip(result,expected):assert actual==pytest.approx(target)
