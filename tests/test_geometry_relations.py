import pytest

from zhijiang.models import GeometryConstraint,SceneObject
from zhijiang.visual_planning import verify_visual_scene,VisualSceneError
from test_geometry_contract import mathematical_scene


def test_actual_circle_membership_checks_continuous_motion():
    scene=mathematical_scene()
    scene.geometry_constraints=[GeometryConstraint(kind='on_circle',objects=['point','circle'],source_quote=scene.evidence.quote)]
    assert verify_visual_scene(scene)['states'][1]['geometry_relations']
    scene.objects[1].position=['t','0'];scene.parameters={'t':1};scene.beats[1].parameters={'t':-1}
    with pytest.raises(VisualSceneError,match='实际几何关系失败'):verify_visual_scene(scene)


def test_point_must_follow_the_function_not_an_unrelated_horizontal_path():
    scene=mathematical_scene();scene.y_range=[-3,3];scene.objects=[SceneObject(id='a',kind='dot',position=['t','1']),
        SceneObject(id='b',kind='curve',expression='x**2',domain=[-2,2])]
    scene.parameters={'t':1};scene.beats[1].parameters={'t':1.5}
    scene.geometry_constraints=[GeometryConstraint(kind='on_function',objects=['a','b'],source_quote=scene.evidence.quote)]
    with pytest.raises(VisualSceneError,match='实际几何关系失败'):verify_visual_scene(scene)
    scene.objects[0].position=['t','t**2']
    assert verify_visual_scene(scene)['passed']


def test_distance_is_measured_from_point_and_line_not_from_parameter_labels():
    scene=mathematical_scene();scene.y_range=[-3,3];scene.objects=[SceneObject(id='a',kind='dot',position=['t','2']),
        SceneObject(id='b',kind='dot',position=['0','2']),
        SceneObject(id='c',kind='line',start=['-5','-1.5'],end=['5','-1.5'])]
    scene.parameters={'t':0};scene.beats[1].parameters={'t':1}
    scene.geometry_constraints=[GeometryConstraint(kind='equal_distance',objects=['a','b','c'],source_quote=scene.evidence.quote)]
    with pytest.raises(VisualSceneError,match='实际几何关系失败'):verify_visual_scene(scene)
    scene.objects[0].position=['t','t**2/4'];scene.objects[1].position=['0','1']
    scene.objects[2].start=['-5','-1'];scene.objects[2].end=['5','-1']
    assert verify_visual_scene(scene)['passed']


def test_relation_binding_uses_existing_ids_and_program_owned_source_quote():
    from zhijiang.visual_geometry_checks import plan_geometry_constraints
    scene=mathematical_scene();quote=scene.evidence.quote
    class Client:
        def generate(self,schema,*args):
            with pytest.raises(ValueError):schema.model_validate({'constraints':[{'kind':'on_circle','objects':['unknown','circle'],'source_id':1}]})
            return schema.model_validate({'constraints':[{'kind':'on_circle','objects':['point','circle'],'source_id':1}]})
    plan_geometry_constraints(Client(),scene,quote,'')
    assert scene.geometry_constraints[0].source_quote==quote
    assert verify_visual_scene(scene)['passed']


def test_modified_geometry_constraint_invalidates_reviewed_cache(tmp_path):
    import json
    from zhijiang.models import SourceDocument,PageText,LessonSegment
    from zhijiang.visual_planning import save_planned_scene,load_planned_scene
    scene=mathematical_scene();scene.geometry_constraints=[GeometryConstraint(kind='on_circle',objects=['point','circle'],source_quote=scene.evidence.quote)]
    doc=SourceDocument(filename='test.pdf',pages=[PageText(page=1,text=scene.evidence.quote)])
    segment=LessonSegment(title='圆周点',kind='concept',narration='观察圆周上随角度变化的点及保持固定的圆。',bullets=['圆周'],evidence=scene.evidence)
    path=tmp_path/'planned.json';save_planned_scene(path,'test',scene,{'approved':True})
    assert load_planned_scene(path,'test',doc,segment)
    saved=json.loads(path.read_text(encoding='utf-8'));saved['scene']['geometry_constraints']=[]
    path.write_text(json.dumps(saved),encoding='utf-8')
    assert load_planned_scene(path,'test',doc,segment) is None


def test_visible_point_cannot_leave_plot_even_when_its_relation_stays_true():
    scene=mathematical_scene()
    scene.geometry_constraints=[GeometryConstraint(kind='on_circle',objects=['point','circle'],source_quote=scene.evidence.quote)]
    scene.y_range=[-.1,.1]
    with pytest.raises(VisualSceneError,match='超出坐标窗口'):verify_visual_scene(scene)
    scene.y_range=[-1.5,1.5]
    assert verify_visual_scene(scene)['passed']


def test_hidden_point_outside_plot_is_allowed_but_visible_label_is_checked():
    scene=mathematical_scene()
    scene.geometry_constraints=[GeometryConstraint(kind='on_circle',objects=['point','circle'],source_quote=scene.evidence.quote)]
    scene.objects.append(SceneObject(id='hidden',kind='dot',position=['0','4'],visible=False))
    assert verify_visual_scene(scene)['passed']
    scene.objects.append(SceneObject(id='label',kind='label',position=['0','4'],text='数学对象'))
    with pytest.raises(VisualSceneError,match='超出坐标窗口'):verify_visual_scene(scene)
