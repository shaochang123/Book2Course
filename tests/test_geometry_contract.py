import math
import xml.etree.ElementTree as ET

import pytest

from zhijiang.models import Evidence, SceneObject, VisualBeat, VisualScenePlan
from zhijiang.visual_coordinates import EuclideanViewport
from zhijiang.visual_planning import VisualSceneError,validate_motion_layout,plan_visual_scenes


@pytest.mark.parametrize('bounds',[([-5,5],[-3,3]),([-1,12],[-2,2]),([-2,2],[-10,10])])
def test_equal_units_preserve_distances_angles_and_circle_radius(bounds):
    for width,height,center,flip in [(10.6,4.3,(0,.35),False),(1060,430,(600,310),True)]:
        viewport=EuclideanViewport(*bounds,width,height,center,flip)
        a,b,c=[viewport.point(*p) for p in [(0,0),(3,0),(0,3)]]
        assert math.dist(a,b)==pytest.approx(math.dist(a,c))
        u=[b[i]-a[i] for i in range(2)];v=[c[i]-a[i] for i in range(2)]
        assert sum(x*y for x,y in zip(u,v))==pytest.approx(0)
        assert math.dist(a,b)==pytest.approx(3*viewport.scale)


def mathematical_scene():
    return VisualScenePlan(domain='原创契约测试',question='保持实际圆与点的坐标关系？',parameters={'t':0},
        objects=[SceneObject(id='circle',kind='circle',position=['0','0'],radius='1'),
                 SceneObject(id='point',position=['cos(t)','sin(t)'])],
        x_range=[-2,2],y_range=[-1.5,1.5],evidence=Evidence(page=1,quote='点位于实际圆周上且圆的半径保持不变。'),
        beats=[VisualBeat(narration='先观察圆周上的点以及固定的圆心位置。'),
               VisualBeat(narration='移动圆周上的点，保持它与圆心的距离不变。',parameters={'t':1}),
               VisualBeat(narration='保留最后的位置，观察点仍然位于原来的圆周上。')])


def test_svg_circle_and_point_use_identical_scale():
    from zhijiang.visual_media import visual_summary_svg
    scene=mathematical_scene();root=ET.fromstring(visual_summary_svg(scene));ns={'s':'http://www.w3.org/2000/svg'}
    circles=root.findall('.//s:circle',ns);circle,point=circles
    distance=math.dist([float(circle.get(k)) for k in ('cx','cy')],[float(point.get(k)) for k in ('cx','cy')])
    assert distance==pytest.approx(float(circle.get('r')))
    assert root.get('viewBox')=='0 0 1200 675'


def test_motion_layout_rejects_parameters_that_do_not_drive_geometry():
    scene=mathematical_scene();validate_motion_layout(scene)
    scene.objects[1].position=['1','0']
    with pytest.raises(VisualSceneError,match='没有对象依赖'):validate_motion_layout(scene)


def test_layout_checks_free_variables_and_domain_before_motion_call():
    scene=mathematical_scene();scene.parameters={'x':0}
    with pytest.raises(VisualSceneError,match='保留变量'):validate_motion_layout(scene)
    scene=mathematical_scene();scene.objects[1].position=['y','0']
    with pytest.raises(VisualSceneError,match='未定义'):validate_motion_layout(scene)
    scene.objects[1]=SceneObject(id='log',kind='curve',expression='log(x)',domain=[-1,1])
    with pytest.raises(VisualSceneError,match='有限实数'):validate_motion_layout(scene)


def test_inverse_trig_preserves_quadrants_and_rejects_invalid_real_domain():
    from zhijiang.visual_planning import evaluate,expression_tex
    assert evaluate('atan2(vertical,horizontal)',{'vertical':1,'horizontal':-1})==pytest.approx(3*math.pi/4)
    assert evaluate('acos(0)',{})==pytest.approx(math.pi/2)
    assert expression_tex('atan2(vertical,horizontal)')
    with pytest.raises(VisualSceneError,match='有限实数'):evaluate('acos(2)',{})


def test_json_decoding_still_rejects_undeclared_motion_parameters():
    import json
    from types import SimpleNamespace
    from zhijiang.agents import OllamaClient
    from zhijiang.visual_planning import sequence_schema
    scene=mathematical_scene();schema=sequence_schema(SimpleNamespace(parameters=scene.parameters,objects=scene.objects,step_count=3))
    client=OllamaClient('http://127.0.0.1:11434','mock');client._model_info={'capabilities':['completion']}
    payloads=[]
    def request(endpoint,payload,stage):
        payloads.append(payload)
        name='unknown' if len(payloads)==1 else 't'
        value={'beats':[{'narration':b.narration,'parameter_changes':([{'name':name,'value':1}] if i==1 else [])} for i,b in enumerate(scene.beats)]}
        return {'message':{'content':json.dumps(value)},'done_reason':'stop'}
    client._request=request
    try:result=client.generate(schema,'测试受限字段。','测试原文。')
    finally:client.close()
    assert result.beats[1].parameters=={'t':1}
    assert len(payloads)==2 and all(p['format']=='json' for p in payloads)
    assert client.call_metrics[0]['validation_error']


def test_parametric_arc_has_correct_radius_and_continuous_endpoints():
    from zhijiang.visual_planning import object_geometry,verify_visual_scene
    scene=mathematical_scene()
    arc=SceneObject(id='arc',kind='parametric_curve',domain=[0,1],
        parametric_expression=['cos(t*x)','sin(t*x)'])
    scene.objects.append(arc)
    for t in [0,.3,.5,1]:
        geometry=object_geometry(arc,{'t':t})
        assert len(geometry['points'])==101
        assert all(math.hypot(*p)==pytest.approx(1) for p in geometry['points'])
        assert geometry['points'][-1]==pytest.approx([math.cos(t),math.sin(t)])
    assert verify_visual_scene(scene)['passed']
    arc.parametric_expression=['cos(x)']
    with pytest.raises(VisualSceneError,match='两个表达式'):verify_visual_scene(scene)


def test_scaling_rays_cannot_be_narrated_as_rotation():
    from zhijiang.visual_planning import verify_visual_scene
    scene=mathematical_scene()
    scene.objects=[SceneObject(id='fixed',kind='line',start=['0','0'],end=['1','0']),
        SceneObject(id='changing',kind='line',start=['0','0'],end=['-t','0'])]
    scene.parameters={'t':.5}
    scene.beats[1].narration='保持参照射线不动，旋转另一条射线来改变它们的夹角。'
    with pytest.raises(VisualSceneError,match='没有方向变化'):verify_visual_scene(scene)
    scene.objects[1].end=['cos(t)','sin(t)']
    assert verify_visual_scene(scene)['states'][1]['motion']['changing']['direction_changed']


def test_collinear_collapse_and_reversal_is_not_a_rotation():
    from zhijiang.visual_planning import verify_visual_scene
    scene=mathematical_scene();scene.parameters={'t':1}
    scene.objects=[SceneObject(id='fixed',kind='line',start=['0','0'],end=['1','0']),
        SceneObject(id='changing',kind='line',start=['0','0'],end=['t','0'])]
    scene.beats[1].parameters={'t':-1}
    scene.beats[1].narration='保持参照射线不动，旋转另一条射线来改变它们的夹角。'
    with pytest.raises(VisualSceneError,match='口播运动不一致'):verify_visual_scene(scene)
    scene.objects[1].end=['cos(t)','sin(t)'];scene.parameters={'t':0};scene.beats[1].parameters={'t':math.pi}
    assert verify_visual_scene(scene)['states'][1]['motion']['changing']['angular_sweep']


def test_unsupported_template_is_not_a_dynamic_geometry_label():
    from zhijiang.visual_planning import verify_visual_scene
    scene=mathematical_scene();scene.objects.append(SceneObject(id='label',kind='label',position=['0','1'],text='${t}°'))
    with pytest.raises(VisualSceneError,match='动态模板'):verify_visual_scene(scene)


def test_repair_keeps_bound_objects_and_stops_identical_failures(monkeypatch):
    from zhijiang.models import Lesson,LessonSegment,Mode,VoiceMode,SourceDocument,PageText
    scene=mathematical_scene();layout_calls=[];sequence_calls=[]
    class Client:
        def generate(self,schema,*args):
            if schema.__name__=='VisualLayoutDraft':
                layout_calls.append(args)
                return schema.model_validate(scene.model_dump(include={'domain','question','parameters','objects','x_range','y_range','axes'}))
            assert schema.__name__=='VisualSequenceDraft';sequence_calls.append(args)
            return schema.model_validate({'beats':[{'narration':b.narration,'parameter_changes':[]} for b in scene.beats]})
    lesson=Lesson(title='测试数学对象',objective='检查不修改参数的失败如何修复。',mode=Mode.AI,voice_mode=VoiceMode.SYSTEM,notice='test',
        segments=[LessonSegment(title='测试圆周',kind='concept',narration='检查没有任何参数变更的无效候选是否被反复绘制同样的对象。',bullets=['圆周'],evidence=scene.evidence)])
    document=SourceDocument(filename='test.pdf',pages=[PageText(page=1,text=scene.evidence.quote)])
    monkeypatch.setattr('zhijiang.visual_planning.visual_capabilities',lambda:{'geometry_ready':True})
    with pytest.raises(VisualSceneError,match='修正无进展'):
        plan_visual_scenes(Client(),lesson,document,'',lambda *v:None,geometry_only=True)
    assert len(layout_calls)==1 and len(sequence_calls)==3
    assert 'parameter_changes' in sequence_calls[-1][0]


def test_short_source_selection_cannot_be_monopolized_by_intro_keyword():
    from zhijiang.agents import source_candidates
    from zhijiang.models import SourceDocument,PageText
    intro=['Space is a repeated introductory word about background and people.']*8
    tail=['The central definition describes equal distances to two reference objects.',
          'The reference condition excludes a coincident point and fixed line.']
    doc=SourceDocument(filename='chapter.pdf',pages=[PageText(page=1,text='\n'.join(intro+tail))])
    candidates=source_candidates(doc,complete=True)
    assert any('central definition' in c['quote'] for c in candidates)
    assert any('reference condition' in c['quote'] for c in candidates)


def test_worded_numeric_angle_is_not_unchecked_narration():
    from zhijiang.visual_planning import verify_visual_scene
    scene=mathematical_scene();scene.narration_binding='computed'
    scene.beats[0].narration='观察这个零度角，确定两个对象初始的位置与方向。'
    with pytest.raises(VisualSceneError,match='口播数字未绑定'):verify_visual_scene(scene)


def test_sequence_uses_declared_parameter_change_list():
    from zhijiang.visual_planning import sequence_schema
    from types import SimpleNamespace
    scene=mathematical_scene();schema=sequence_schema(SimpleNamespace(parameters=scene.parameters,objects=scene.objects,step_count=3))
    payload={'beats':[{'narration':b.narration,'parameter_changes':([{'name':'t','value':1}] if i==1 else [])}
                      for i,b in enumerate(scene.beats)]}
    sequence=schema.model_validate(payload)
    assert sequence.beats[1].parameters=={'t':1}
    payload['beats'][1]['parameter_changes'][0]['name']='undeclared'
    with pytest.raises(ValueError):schema.model_validate(payload)
    assert 'parameters' not in schema.model_json_schema()['$defs']['VisualBeatDraft']['properties']


def test_cosmetic_marker_radius_is_not_mathematical_motion():
    from zhijiang.visual_planning import verify_visual_scene
    scene=mathematical_scene()
    scene.objects[1].position=['1','0'];scene.objects[1].radius='t'
    scene.parameters={'t':.1};scene.beats[1].parameters={'t':.2}
    with pytest.raises(VisualSceneError,match='不能只逐项'):verify_visual_scene(scene)


def test_symbolic_binding_repair_uses_only_existing_fields():
    from zhijiang.visual_planning import bind_motion_parameters
    scene=mathematical_scene();scene.objects[1].position=['1','0']
    class Client:
        def generate(self,schema,*args):
            return schema.model_validate({'bindings':[
                {'target':'point.position.0','expression':'cos(t)'},
                {'target':'point.position.1','expression':'sin(t)'}]})
    binding=bind_motion_parameters(Client(),scene,'独立测试资料。','修复变化量与图形绑定。')
    assert scene.objects[0].position==['0','0']
    assert scene.objects[1].position==['cos(t)','sin(t)']
    assert len(binding['bindings'])==2


def test_strict_geometry_does_not_fall_back_to_diagram(monkeypatch):
    from zhijiang.agents import GenerationError
    from zhijiang.models import Lesson,LessonSegment,Mode,VoiceMode,SourceDocument,PageText
    from zhijiang.visual_planning import VisualLayoutDraft
    scene=mathematical_scene()
    class Client:
        def generate(self,schema,*args):
            assert schema is VisualLayoutDraft
            raise GenerationError('模拟模型无法构造数学对象')
    lesson=Lesson(title='测试数学对象',objective='检查真实数学演示失败时的表现。',mode=Mode.AI,voice_mode=VoiceMode.SYSTEM,notice='test',
        segments=[LessonSegment(title='测试圆周',kind='concept',narration='检查真实数学演示失败时是否明确报错并保留实际失败原因。',bullets=['圆周'],evidence=scene.evidence)])
    document=SourceDocument(filename='test.pdf',pages=[PageText(page=1,text=scene.evidence.quote)])
    monkeypatch.setattr('zhijiang.visual_planning.visual_capabilities',lambda:{'geometry_ready':True})
    def forbidden(*a,**k):raise AssertionError('strict math requested a diagram fallback')
    monkeypatch.setattr('zhijiang.teaching_design.plan_teaching_representation',forbidden)
    with pytest.raises(VisualSceneError,match='无法构造数学对象'):
        plan_visual_scenes(Client(),lesson,document,'',lambda *v:None,geometry_only=True)


def test_strict_geometry_requires_tex_before_model_calls(monkeypatch):
    monkeypatch.setattr('zhijiang.visual_planning.visual_capabilities',lambda:{'geometry_ready':False,'geometry_reason':'缺少 latex'})
    with pytest.raises(VisualSceneError,match='latex'):
        plan_visual_scenes(None,None,None,'',lambda *v:None,geometry_only=True)
