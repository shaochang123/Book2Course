"""Check math, continuous operations, source handling, and API compatibility."""
import math
import wave
from pathlib import Path

import pytest

pytest.importorskip("sympy")

from zhijiang.math_media import synthesize_beats, math_summary_svg, render_summary_png
from zhijiang.math_planning import (ACTIONS, MathAnimationError, numeric_facts,
    symbolic_facts, verify_scene, validate_parameters, bind_verified_narration, explicit_parameters)
from zhijiang.models import (Evidence, GenerationOptions, MathBeat, MathClaim,
    MathParameters, MathScenePlan)


def make_scene(kind="basis", parameters=None):
    return MathScenePlan(kind=kind, parameters=parameters or MathParameters(),
        question="为什么基向量的像决定矩阵的列？",
        beats=[MathBeat(action=action, narration="这是教学示例，请观察几何变化与公式如何对应。") for action in ACTIONS[kind]],
        evidence=Evidence(page=3, quote="The first column contains the coordinates of T(v1)."))


def test_math_relations_and_independent_polygon_area():
    for kind in ACTIONS:
        report = verify_scene(make_scene(kind))
        assert report["passed"] and all(report["checks"].values())
    f = numeric_facts(MathParameters())
    assert f["Av"] == [4, 2]
    assert f["A_sum"] == f["sum_images"] == [5, 1]
    assert f["area"] == [2]
    assert f["P"] == [0.5]*4
    assert f["diagonal_projection"] == [1, 0, 0, 0]
    assert f["SRv"] != f["RSv"]


def test_wrong_calculation_and_missing_reasoning_are_rejected():
    scene = make_scene()
    scene.claims = [MathClaim(key="Av", values=[5, 2])]
    with pytest.raises(MathAnimationError, match="计算声明错误"):
        verify_scene(scene)
    scene.claims = []
    scene.beats = scene.beats[::-1]
    with pytest.raises(MathAnimationError, match="推理步骤"):
        verify_scene(scene)
    with pytest.raises(MathAnimationError):
        validate_parameters(MathParameters(matrix=[[1, 2, 3], [0, 1, 2]]))
    with pytest.raises(MathAnimationError):
        validate_parameters(MathParameters(vector=[float("nan"), 1]))


def test_spoken_math_is_bound_and_tampering_is_rejected():
    projection = make_scene("projection")
    bind_verified_narration(projection)
    assert "非零单位向量n垂直" in projection.beats[3].narration
    assert "零向量本身不是特征向量" in projection.beats[3].narration
    composition = make_scene("composition")
    bind_verified_narration(composition)
    assert "横坐标2、纵坐标2" in composition.beats[2].narration
    composition.beats[2].narration = "先伸缩以后横坐标是四、纵坐标是二。"
    with pytest.raises(MathAnimationError, match="口播与核验数据"):
        verify_scene(composition)
    changed = make_scene("plane", MathParameters(matrix=[[1, 0], [2, 1]]))
    bind_verified_narration(changed)
    assert "横坐标1、纵坐标4" in changed.beats[1].narration


def test_explicit_matrix_and_ambiguous_formula():
    assert explicit_parameters("教学示例A=[[1,0],[2,1]]，v=[1,2]")["matrix"] == [[1, 0], [2, 1]]
    with pytest.raises(MathAnimationError, match="有歧义"):
        explicit_parameters("A=[[x,1],[0,1]]")
    with pytest.raises(MathAnimationError, match="2×2"):
        explicit_parameters("A=[[1,0,0],[0,1,0],[0,0,1]]")
    from zhijiang.math_planning import supports_math
    from zhijiang.models import PageText, SourceDocument
    three_dimensional = SourceDocument(filename="3d.pdf",pages=[PageText(page=1,text=(
        "Linear transformations in three-dimensional space R3. A transformation T is linear. "
        "The first column represents a basis image. Given a matrix it maps the full space."))])
    assert not supports_math(three_dimensional)


def test_planner_preserves_sources_and_overrides_model_parameters():
    import json
    from zhijiang.math_planning import plan_math_lesson, MathCourseDraft, MathScriptDraft
    from zhijiang.models import PageText, SourceDocument, VoiceMode
    document = SourceDocument(filename="linear.pdf", pages=[PageText(page=1,text=(
        "Linear transformations. A transformation T is linear if addition and scaling are preserved. "
        "The first column contains the first basis image. Given a matrix we can transform a picture. "
        "This map projects every vector onto a line. The product of two transformations depends on order."))])
    class Client:
        def generate(self,schema,instruction,material):
            if schema is MathCourseDraft:
                return MathCourseDraft(title="二维线性变换教学",objective="从向量变化理解矩阵与投影的几何意义。",parameters=MathParameters())
            assert schema is MathScriptDraft
            data=json.loads(material)
            return MathScriptDraft(question="为什么同一组数学对象会这样变化？",beats=[
                MathBeat(action=action,narration="模型草稿算错了，先伸缩得到四和二；垂直方向保持不变。")
                for action in data['actions_in_order']])
    lesson = plan_math_lesson(Client(),document,"A=[[1,0],[2,1]], v=[1,2]",VoiceMode.SYSTEM)
    assert len(lesson.segments) == 5
    assert all(segment.math_scene.parameters.matrix == [[1,0],[2,1]] for segment in lesson.segments)
    assert all(segment.math_scene.verification['passed'] for segment in lesson.segments)
    assert "模型草稿算错" not in lesson.segments[3].narration
    assert lesson.animation_report['narration_bindings']['projection']['model_draft']
    assert "横坐标1、纵坐标4" in lesson.segments[2].narration


def test_changed_matrix_changes_geometry_and_svg(tmp_path):
    first = make_scene("plane")
    second = make_scene("plane", MathParameters(matrix=[[1, 0], [2, 1]]))
    assert numeric_facts(second.parameters)["Av"] == [1, 4]
    assert numeric_facts(second.parameters)["area"] == [1]
    assert math_summary_svg(first) != math_summary_svg(second)
    svg = tmp_path/"summary.svg"
    svg.write_text(math_summary_svg(second), encoding="utf-8")
    render_summary_png(svg, tmp_path/"summary.png")
    assert (tmp_path/"summary.png").stat().st_size > 1000


def test_rotation_and_projection_at_intermediate_states():
    import sympy as s
    f = symbolic_facts(MathParameters())
    v = f["v"]
    for progress in (0, 0.25, 0.5, 0.75, 1):
        angle = s.Rational(str(progress))*s.pi/4
        R = s.Matrix([[s.cos(angle), -s.sin(angle)], [s.sin(angle), s.cos(angle)]])
        assert s.simplify((R*v).dot(R*v)-v.dot(v)) == 0
        point = (1-progress)*v+progress*f["Pv"]
        movement = point-v
        assert abs(float(movement.dot(f["parallel"]))) < 1e-9
    assert f["perpendicular_image"] == s.zeros(2, 1)


def test_beat_timeline_uses_real_audio_duration_and_preserves_old_options(tmp_path):
    class Speech:
        count = 0
        def synthesize(self, text, path):
            self.count += 1
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(24000)
                audio.writeframes(b"\0\0"*24000*self.count)
    audio, timing = synthesize_beats(make_scene(), Speech(), tmp_path)
    assert [round(item["duration"], 1) for item in timing] == [1.8, 2.8, 3.8, 4.8, 5.8]
    with wave.open(str(audio), "rb") as wav:
        assert wav.getnframes()/wav.getframerate() == pytest.approx(sum(item["duration"] for item in timing))
    assert GenerationOptions.model_validate_json('{}').animation_mode == "auto"


def test_math_api_mode_and_dependency_state(tmp_path, sample_pdf):
    from tests.test_api import make_client
    client, store = make_client(tmp_path)
    with client:
        config = client.get('/api/config').json()
        assert 'ready' in config['math_animation']
        response = client.post('/api/jobs', files={'file':('lesson.pdf', sample_pdf, 'application/pdf')},
            data={'rights_confirmed':'true','mode':'demo','animation_mode':'math'})
        assert response.status_code == 400
        response = client.post('/api/jobs', files={'file':('lesson.pdf', sample_pdf, 'application/pdf')},
            data={'rights_confirmed':'true','mode':'demo','animation_mode':'basic'})
        job = response.json()
        assert job['model_settings']['animation_mode'] == 'basic'
        assert client.get(f"/api/jobs/{job['id']}/math-scenes").status_code == 409
        assert client.get('/api/jobs/missing/math-scenes').status_code == 404


def test_auto_falls_back_but_strict_mode_fails(tmp_path, sample_pdf, monkeypatch):
    from zhijiang.config import Settings
    from zhijiang.storage import JobStore
    from zhijiang.pipeline import JobProcessor
    from zhijiang.agents import DemoAgents
    from zhijiang.models import Mode, VoiceMode
    from tests.test_api import FakeSpeech
    settings = Settings(data_dir=tmp_path)
    store = JobStore(tmp_path)
    processor = JobProcessor(settings,store,agent_factory=lambda _:DemoAgents(),
        speech_factory=lambda _:FakeSpeech(),video_renderer=lambda l,a,p:p.write_bytes(b'video'),
        presentation_renderer=lambda l,p:p.write_bytes(b'pptx'))
    monkeypatch.setattr('zhijiang.pipeline.supports_math',lambda _:True)
    monkeypatch.setattr('zhijiang.pipeline.math_capabilities',lambda:{'ready':False,'reason':'missing manim'})
    def job(mode):
        return store.create('source.pdf',Mode.AI,VoiceMode.SYSTEM,True,False,sample_pdf,
                            GenerationOptions(provider='ollama',base_url='http://localhost',model='test',animation_mode=mode))
    auto=job('auto'); processor.process(auto['id'])
    assert store.get(auto['id'])['status'] == 'completed'
    assert '自动模式' in store.lesson(auto['id']).animation_report['reason']
    strict=job('math'); processor.process(strict['id'])
    assert store.get(strict['id'])['status'] == 'failed'
    assert 'math-animation' in store.get(strict['id'])['error']
    monkeypatch.setattr('zhijiang.pipeline.supports_math',lambda _:False)
    unsupported=job('math'); processor.process(unsupported['id'])
    assert '仅支持' in store.get(unsupported['id'])['error']
