import pytest
pytest.importorskip('sympy')
from pydantic import ValidationError
from zhijiang.math_construction import MathProgramDraft
from zhijiang.math_behavior import behavior_schema,decode_behavior,attach_measurement_glyphs


def test_typed_tools_reject_curve_as_point_and_bind_difference_to_real_curves():
    narration='移动观察点，比较实际曲线对应的函数值差异。'
    program=MathProgramDraft(title='不同函数值的测量',objective='比较来自不同函数曲线的实际函数值。',source_id=1,
        parameters={'u':.2},constructions=[{'id':'f','op':'function','expr':['sin(x)'],'domain':[-1,1]},
            {'id':'g','op':'function','expr':['x'],'domain':[-1,1]},
            {'id':'p','op':'point_on_function','refs':['f'],'expr':['u']}],
        operations=[{'narration':narration}]*3,claims=[{'source_id':1,'lhs':'ycoord(p)','rhs':'value(f,u)'}])
    schema=behavior_schema(program,{1:{}})
    data={'operations':[{'narration':narration,'changes':{'u':v},'measurements':{'实际误差':{
        'terms':[{'kind':'value','function':'f','at':'u'},
            {'kind':'value','function':'g','at':'u','factor':'-1'}],'absolute':True}}} for v in [.3,.5,.7]],
        'claims':[{'source_id':1,'left':{'terms':[{'kind':'ycoord','point':'p'}]},
            'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]}
    draft=schema.model_validate(data);operations,claims=decode_behavior(draft)
    assert operations[-1].measurements['实际误差']=='abs(value(f,u)+(-1)*(value(g,u)))'
    assert claims[0].lhs=='ycoord(p)'
    program=program.model_copy(update={'operations':operations,'claims':claims})
    drawn=attach_measurement_glyphs(program,draft)
    assert len(drawn.constructions)==len(program.constructions)+2
    assert drawn.constructions[-1].refs==['p','measure_0_b']
    assert 'measure_0_line' in drawn.operations[0].show
    from zhijiang.models import Evidence
    from zhijiang.math_construction import compile_program
    from zhijiang.visual_planning import verify_visual_scene
    scene=compile_program(drawn,Evidence(page=1,quote='这是未曾固定的正弦函数与线性函数比较示例。'),
        {1:{'quote':'这是未曾固定的正弦函数与线性函数比较示例。'}})
    result=verify_visual_scene(scene)
    end=result['states'][-1]['end_geometry']['measure_0_line']['points']
    import math
    assert end[0][0]==pytest.approx(.7)
    assert end[0][1]==pytest.approx(math.sin(.7))
    assert end[1][1]==pytest.approx(.7)
    data['claims'][0]['left']['terms']=[{'kind':'distance','first':'f','second':'p'}]
    with pytest.raises(ValidationError):schema.model_validate(data)


def test_measured_ratio_uses_real_reference_area_and_survives_rescaling():
    program=MathProgramDraft(title='实际部分面积的比例',objective='检验等面积部分占实际整体面积的比例。',source_id=1,
        parameters={'scale':1},constructions=[{'id':'whole','op':'rectangle','expr':['0','0','7*scale','3*scale']},
            {'id':'parts','op':'partition','refs':['whole'],'expr':['2','4']}],
        operations=[{'narration':'同步改变整体尺寸，观察实际部分占整体的比例。','changes':{'scale':v}} for v in [1,1.3,1.8]],
        claims=[{'source_id':1,'lhs':'area(parts)','rhs':'area(whole)'}])
    ratio={'terms':[{'kind':'area','polygon':'parts_0_1'}],'divisor':[{'kind':'area','polygon':'whole'}]}
    draft=behavior_schema(program,{1:{}}).model_validate({'operations':[
        {'narration':op.narration,'changes':op.changes,'measurements':{'部分占比':ratio}} for op in program.operations],
        'claims':[{'source_id':1,'left':ratio,'right':{'terms':[{'kind':'scalar','expr':'1/8'}]}}]})
    operations,claims=decode_behavior(draft)
    from zhijiang.math_construction import compile_program
    from zhijiang.models import Evidence
    from zhijiang.visual_planning import verify_visual_scene
    scene=compile_program(program.model_copy(update={'operations':operations,'claims':claims}),
        Evidence(page=1,quote='检验八个等面积部分占整体的比例，与整体缩放无关。'),{1:{'quote':'检验八个等面积部分占整体的比例，与整体缩放无关。'}})
    result=verify_visual_scene(scene)
    assert all(s['calculations'][0]['value']==pytest.approx(1/8) for s in result['states'])


def test_gap_closes_at_end_but_has_real_visible_motion():
    # A measured difference can legitimately vanish at a common expansion point.
    # It must not be rejected merely because its only visible endpoint is zero.
    from zhijiang.models import VisualScenePlan,SceneObject,VisualBeat,Evidence
    from zhijiang.visual_planning import verify_visual_scene,VisualSceneError
    scene=VisualScenePlan(domain='通用几何',question='实际间距怎样收合到共同位置？',
        evidence=Evidence(page=1,quote='测量线段的实际间距，并把端点移动到同一个位置。'),parameters={'u':.4},objects=[
        SceneObject(id='a',kind='dot',position=['0','0']),
        SceneObject(id='b',kind='dot',position=['u','0']),
        SceneObject(id='gap',kind='line',start=['0','0'],end=['u','0'])],
        beats=[VisualBeat(narration='移动端点，使实际间距收合到共同位置。',parameters={'u':0})])
    assert verify_visual_scene(scene)['passed']
    stuck=scene.model_copy(deep=True)
    stuck.objects[-1].end=['0','0']
    with pytest.raises(VisualSceneError,match='退化为一点'):verify_visual_scene(stuck)
