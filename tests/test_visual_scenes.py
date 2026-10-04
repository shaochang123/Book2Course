import math

import pytest

from zhijiang.models import Evidence, SceneObject, VisualBeat, VisualScenePlan, SceneCalculation, SceneCheck, ReviewResult
from zhijiang.visual_planning import (VisualSceneError, evaluate, object_geometry, verify_visual_scene,
                                     register_checker, plan_visual_scenes)


def scene_for(domain, expression, parameters, changes, checks=()):
    """The same contract works for unrelated subjects without a subject switch."""
    scene=VisualScenePlan(domain=domain, question='观察参数改变时对象如何变化？',parameters=parameters,
        objects=[SceneObject(id='moving',points=[[expression,'0']]),
                 SceneObject(id='origin',points=[['0','0']],color='#6DE2C0')],
        beats=[VisualBeat(narration='先观察初始状态，确定同一对象及其参考位置。'),
               VisualBeat(narration='依据当前教学条件改变参数，观察对应对象的连续变化。',parameters=changes),
               VisualBeat(narration='保留终点并对照初态，说明这个变化与当前概念的关系。')],
        checks=list(checks),evidence=Evidence(page=1,quote='这是一条原创测试用的教学依据。'))
    return scene


@pytest.mark.parametrize('domain,expression,parameters,changes',[
    ('微积分','a+h',{'a':1,'h':1},{'h':0.1}),
    ('概率论','p',{'p':0.2},{'p':0.8}),
    ('物理','v*t',{'v':2,'t':0},{'t':1}),
    ('化学','extent',{'extent':0},{'extent':1}),
    ('生物','substrate',{'substrate':-2},{'substrate':0}),
    ('历史与社会科学','date',{'date':-3},{'date':3}),
])
def test_subject_independent_parametric_contract(domain,expression,parameters,changes):
    scene=scene_for(domain,expression,parameters,changes)
    report=verify_visual_scene(scene)
    assert report['passed']
    assert report['states'][0]['end_geometry']['moving']!=report['states'][1]['end_geometry']['moving']


def test_calculations_and_declared_conservation_checks():
    scene=scene_for('概率论','p',{'p':0.2},{'p':0.8},[
        SceneCheck(expression='p+(1-p)',expected=1),SceneCheck(checker='nonnegative',expression='p'),
        SceneCheck(checker='at_most',expression='p',expected=1)])
    scene.beats[1].calculations=[SceneCalculation(label='事件概率',expression='p',expected=0.8)]
    assert verify_visual_scene(scene)['states'][1]['calculations'][0]['value']==0.8
    scene.beats[1].calculations[0].expected=0.3
    with pytest.raises(VisualSceneError,match='不正确'): verify_visual_scene(scene)
    scene.beats[1].calculations=[]; scene.beats[1].parameters['p']=1.5
    with pytest.raises(VisualSceneError,match='领域计算'): verify_visual_scene(scene)


def test_intermediate_invalid_state_and_no_motion_rejected():
    scene=scene_for('数学','1/h',{'h':-1},{'h':1})
    with pytest.raises(VisualSceneError,match='有限实数'): verify_visual_scene(scene)
    scene=scene_for('静态','h',{'h':1},{'h':1})
    with pytest.raises(VisualSceneError,match='逐项显现'): verify_visual_scene(scene)


@pytest.mark.parametrize('expression',["__import__('os')","x.__class__","[1][0]","10**100000","unknown+1"])
def test_model_code_and_undefined_expression_rejected(expression):
    with pytest.raises(VisualSceneError): evaluate(expression,{'x':1})


def test_numeric_curve_and_custom_checker():
    obj=SceneObject(id='wave',kind='curve',expression='a*sin(x)',domain=[-math.pi,math.pi])
    g=object_geometry(obj,{'a':2})
    assert len(g['points'])==101 and max(p[1] for p in g['points'])==pytest.approx(2)
    register_checker('unit_interval',lambda v,e,t:-t<=v<=1+t)
    scene=scene_for('任意新学科','p',{'p':0.2},{'p':0.8},[SceneCheck(checker='unit_interval',expression='p')])
    assert verify_visual_scene(scene)['passed']


def test_explicit_object_coordinates_and_legacy_compatibility():
    obj=SceneObject(id='point',position=['t','t**2'])
    assert object_geometry(obj,{'t':2})['points']==[[2,4]]
    line=SceneObject(id='line',kind='line',start=['0','0'],end=['t','t**2'])
    assert object_geometry(line,{'t':2})['points']==[[0,0],[2,4]]
    line.end=['t','2*t*(x-t)+t**2']
    with pytest.raises(VisualSceneError,match='对象line.*自由变量x.*curve'):
        object_geometry(line,{'t':2})
    obj.points=[['0','0']]
    with pytest.raises(VisualSceneError,match='矛盾'): object_geometry(obj,{'t':2})
    scene=scene_for('通用过程','t',{'t':1},{'t':2})
    scene.objects[0].points.append(['0','0'])
    with pytest.raises(VisualSceneError,match='恰好1'): verify_visual_scene(scene)


def test_model_schema_excludes_program_and_legacy_fields():
    from zhijiang.visual_planning import VisualSceneDraft
    schema=VisualSceneDraft.model_json_schema()
    assert 'evidence' not in schema['properties'] and 'verification' not in schema['properties']
    assert 'narration_binding' not in schema['properties']
    objects=schema['$defs']['SceneObjectDraft']['properties']
    assert 'points' not in objects and all(k in objects for k in ['position','start','end','vertices'])
    assert 'tolerance' not in schema['$defs']['SceneCheckDraft']['properties']
    from zhijiang.visual_planning import SceneCheckDraft
    check=SceneCheckDraft.model_validate({'expression':'t','expected':999,'tolerance':999})
    assert check.tolerance==1e-6
    scene=scene_for('数值过程','t',{'t':1},{'t':2},[check])
    with pytest.raises(VisualSceneError,match='领域计算'): verify_visual_scene(scene)


def test_model_numeric_narration_cannot_bypass_correct_calculations():
    scene=scene_for('任意学科','t',{'t':1},{'t':2})
    scene.narration_binding='computed'
    scene.beats[1].calculations=[SceneCalculation(label='当前位置',expression='t')]
    # Qualitative semantics require source review; numeric prose is not accepted
    # just because the calculation or a separate model review is correct.
    scene.beats[1].narration='此时实际位置为3，观察它与参考对象之间的对应关系。'
    with pytest.raises(VisualSceneError,match='口播数字未绑定'): verify_visual_scene(scene)
    scene.beats[1].narration='此时实际位置为三，观察它与参考对象之间的对应关系。'
    with pytest.raises(VisualSceneError,match='口播数字未绑定'): verify_visual_scene(scene)
    scene.beats[1].narration='此时观察运动点的位置，计算结果由当前参数决定。'
    assert verify_visual_scene(scene)['states'][1]['calculations'][0]['value']==2
    scene.objects[0].text='H2O'
    scene.beats[1].narration='观察H2O标识对应的同一对象，参数控制当前几何位置。'
    scene.beats[1].calculations[0].label='H2O对象位置'
    assert verify_visual_scene(scene)['passed']
    from zhijiang.visual_planning import sequence_schema
    from pydantic import ValidationError
    schema=sequence_schema(scene)
    data={'beats':[b.model_dump() for b in scene.beats]}
    assert schema.model_validate(data).beats[1].narration==scene.beats[1].narration
    data['beats'][1]['narration']='此时实际位置为3，观察它与参考对象之间的对应关系。'
    with pytest.raises(ValidationError,match='string_pattern_mismatch'): schema.model_validate(data)
    data['beats'][1]['narration']='观察同一对象的位置变化。'*12
    with pytest.raises(ValidationError,match='string_too_long'): schema.model_validate(data)
    scene.beats[1].narration=r'绿色曲线表示函数y=x^\text{\text{\text{\text{}}}}'
    with pytest.raises(VisualSceneError,match='口播格式无效'): verify_visual_scene(scene)
    data['beats'][1]['narration']=scene.beats[1].narration
    with pytest.raises(ValidationError,match='string_pattern_mismatch'): schema.model_validate(data)
    data={'beats':[b.model_dump() for b in scene_for('任意学科','t',{'t':1},{'t':2}).beats]}
    data['beats']+=data['beats'][:2]
    with pytest.raises(ValidationError,match='too_long'): schema.model_validate(data)
    from zhijiang.visual_planning import VisualLayoutDraft, LAYOUT_FIELDS
    layout=VisualLayoutDraft.model_validate({**scene.model_dump(include=LAYOUT_FIELDS),'step_count':5})
    assert len(sequence_schema(layout).model_validate(data).beats)==5


def test_cyclic_motion_and_all_frame_conditions():
    scene=scene_for('周期过程','sin(t)',{'t':0},{'t':2*math.pi})
    assert verify_visual_scene(scene)['passed']
    scene.checks=[SceneCheck(expression='t',expected=2*math.pi)]
    with pytest.raises(VisualSceneError,match='所有步骤及中间帧'): verify_visual_scene(scene)


def test_movie_marker_check_rejects_a_cached_old_position(monkeypatch):
    pytest.importorskip('av')
    from PIL import Image, ImageDraw
    from scripts import verify_teaching_artifacts as verifier
    from zhijiang.visual_planning import states
    scene=scene_for('运动回归','t',{'t':0},{'t':2})
    before,after,_=list(states(scene))[1]
    ghost=[True]
    def frame(_path,_time):
        picture=Image.new('RGB',(1280,720),'#081623')
        def pixel(t):
            return (640+90*(-5.3+10.6*(t+5)/10),360-90*(-1.8+4.3*3/6))
        centers=[pixel((before['t']+after['t'])/2)]
        if ghost[0]: centers.append(pixel(before['t']))
        for x,y in centers:
            ImageDraw.Draw(picture).ellipse((x-6,y-6,x+6,y+6),fill=scene.objects[0].color)
        return picture
    monkeypatch.setattr(verifier,'frame_at',frame)
    asset={'timing':[{'start':i,'duration':1} for i in range(3)]}
    with pytest.raises(AssertionError,match='Stale marker'):
        verifier.check_moving_marker_pixels(scene,asset,None)
    ghost[0]=False
    checked=verifier.check_moving_marker_pixels(scene,asset,None)
    assert len(checked)==1 and checked[0]['old_position_pixels']==0


def test_generic_planner_keeps_authoritative_sources_and_repairs(tmp_path,sample_pdf):
    from zhijiang.agents import DemoAgents
    from zhijiang.pdf import read_pdf
    from zhijiang.models import VoiceMode
    doc=read_pdf(sample_pdf,'sample.pdf'); agents=DemoAgents(); bundle=agents.extract_knowledge(doc)
    lesson=agents.script(bundle,agents.plan(bundle),VoiceMode.SYSTEM)
    from zhijiang.visual_planning import VisualSequenceDraft
    class Client:
        calls=0
        def generate(self,schema,instruction,material):
            if schema is ReviewResult: return ReviewResult(approved=True)
            assert '用户的教学偏好：自定义主题要求' in instruction
            assert '自定义主题要求' not in material
            scene=scene_for('没有列入任何学科白名单的新领域','t',{'t':-2},{'t':2})
            if schema.__name__ == 'VisualSequenceDraft':
                self.calls+=1
            if schema.__name__ == 'VisualSequenceDraft' and self.calls==1: scene.checks=[SceneCheck(expression='t',expected=999)]
            if schema.__name__ == 'VisualSequenceDraft' and self.calls==2:
                assert '必须修正上一稿' in instruction and '所有步骤及中间帧' in instruction
                assert '旧草稿数据' in material
            return scene
    plan_visual_scenes(Client(),lesson,doc,'自定义主题要求',lambda *_:None)
    assert lesson.animation_report['scene_type']=='general'
    assert all(s.visual_scene.evidence==s.evidence for s in lesson.segments)


def test_source_coverage_repair_keeps_only_authoritative_ids(sample_pdf):
    from zhijiang.agents import DemoAgents
    from zhijiang.pdf import read_pdf
    from zhijiang.models import VoiceMode
    from zhijiang.visual_planning import plan_general_lesson, VisualCoursePlan
    doc=read_pdf(sample_pdf,'sample.pdf');bundle=DemoAgents().extract_knowledge(doc)
    class Client:
        def generate(self,schema,instruction,material):
            if schema.__name__=='SourceFactsDraft':
                import json
                source_id=json.loads(material)['sources'][0]['id']
                return schema.model_validate({'facts':[{'source_id':source_id,'statement':'原文说明当前知识点的对象、关系及对应条件。'}]})
            if schema is VisualCoursePlan:
                return VisualCoursePlan(title='完整来源课程',objective='保留所有真实来源依据，按连续过程组织教学。',point_ids=[2,2,999])
            if schema is ReviewResult: return ReviewResult(approved=True)
            if schema.__name__=='TeachingDesignDraft':
                from zhijiang.teaching_design import TeachingDesignDraft
                return TeachingDesignDraft(representation='geometry',rationale='来源给出了可计算的参数变化关系。',question='观察参数变化与图形位置的对应关系？')
            return scene_for('通用过程','t',{'t':1},{'t':2})
    lesson=plan_general_lesson(Client(),bundle,doc,'',VoiceMode.SYSTEM,lambda *_:None)
    assert lesson.animation_report['source_point_ids']==[2]+[i for i in range(1,len(bundle.points)+1) if i!=2]
    assert len(lesson.segments)==len(bundle.points)
    from zhijiang.visual_planning import general_source_attribution
    from zhijiang.models import SourceDocument, PageText
    ligature_source=SourceDocument(filename='derivative.pdf',pages=[
        PageText(page=1,text='Geometric deﬁnition of the derivative'),
        PageText(page=2,text='MIT OpenCourseWare ocw.mit.edu')])
    assert general_source_attribution(ligature_source)['author']=='MIT OpenCourseWare, 18.01SC'


def test_authored_cross_subject_processes_and_conservation():
    from scripts.build_general_examples import fixtures
    scenes=fixtures()
    assert len(scenes)==5
    for scene in scenes:
        assert verify_visual_scene(scene)['passed']
    assert verify_visual_scene(scenes[0])['states'][-1]['calculations'][0]['value']==pytest.approx(2.1)
    assert verify_visual_scene(scenes[2])['states'][-1]['calculations'][0]['value']==pytest.approx(2.5)
    atoms=[obj for obj in scenes[3].objects if obj.id.startswith('atom_')]
    assert len(atoms)==6 and all(obj.visible for obj in atoms)


def test_full_context_domain_validator():
    from zhijiang.visual_planning import register_domain_validator
    scene=scene_for('物理','v*t',{'v':1,'t':0},{'t':1})
    scene.domain_data={'velocity_unit':'m/s','time_unit':'s'}
    register_domain_validator('example_units',lambda s,p:{'passed':s.domain_data=={'velocity_unit':'m/s','time_unit':'s'}})
    scene.domain_validators=['example_units']; assert verify_visual_scene(scene)['passed']
    scene.domain_data['time_unit']='kg'
    with pytest.raises(VisualSceneError,match='领域核验'): verify_visual_scene(scene)
    scene.domain_validators=['not_installed']
    with pytest.raises(VisualSceneError,match='未安装'): verify_visual_scene(scene)


def test_auto_uses_general_graph_for_unlisted_subject(tmp_path,sample_pdf,monkeypatch):
    from zhijiang.agents import DemoAgents
    from zhijiang.models import GenerationOptions,Mode,VoiceMode
    from zhijiang.config import Settings
    from zhijiang.storage import JobStore
    from zhijiang.pipeline import JobProcessor
    from zhijiang.visual_planning import VisualCoursePlan
    from tests.test_api import FakeSpeech
    class Client:
        count=3
        def generate(self,schema,instruction,material):
            if schema.__name__=='SourceFactsDraft':
                import json
                source_id=json.loads(material)['sources'][0]['id']
                return schema.model_validate({'facts':[{'source_id':source_id,'statement':'原文说明当前知识点的对象、关系及对应条件。'}]})
            if schema is ReviewResult: return ReviewResult(approved=True)
            if schema.__name__=='TeachingDesignDraft':
                from zhijiang.teaching_design import TeachingDesignDraft
                return TeachingDesignDraft(representation='geometry',rationale='来源给出了可计算的参数变化关系。',question='观察参数变化与图形位置的对应关系？')
            if schema is VisualCoursePlan:
                return VisualCoursePlan(title='新的跨学科课程',objective='依照可核查来源设计连续过程。',point_ids=list(range(1,self.count+1)))
            return scene_for('新领域','t',{'t':-2},{'t':2})
    class Agents(DemoAgents):
        client=Client()
        def extract_knowledge(self,doc):
            b=super().extract_knowledge(doc); self.client.count=len(b.points); return b
    settings=Settings(data_dir=tmp_path); store=JobStore(tmp_path)
    job=store.create('source.pdf',Mode.AI,VoiceMode.SYSTEM,True,False,sample_pdf,
                     GenerationOptions(provider='ollama',base_url='http://localhost',model='test'))
    monkeypatch.setattr('zhijiang.pipeline.supports_math',lambda _:False)
    monkeypatch.setattr('zhijiang.pipeline.math_capabilities',lambda:{'ready':True})
    rendered=[]
    monkeypatch.setattr('zhijiang.pipeline.render_visual_assets',lambda l,s,f,p:rendered.extend(x.visual_scene.domain for x in l.segments))
    processor=JobProcessor(settings,store,agent_factory=lambda _:Agents(),speech_factory=lambda _:FakeSpeech(),
        video_renderer=lambda l,a,p:p.write_bytes(b'video'),presentation_renderer=lambda l,p:p.write_bytes(b'pptx'))
    processor.process(job['id']); assert store.get(job['id'])['status']=='completed'
    assert rendered and all(d=='新领域' for d in rendered)
    assert store.lesson(job['id']).animation_report['scene_type']=='general'
