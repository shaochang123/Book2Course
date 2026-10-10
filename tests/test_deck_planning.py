from pathlib import Path
import json
import pytest
from zhijiang.agents import GenerationError, ModelContractError
from zhijiang.deck_planning import DeckDirectorDraft, DeckPageChoice, plan_deck
from zhijiang.models import Evidence, Lesson, LessonSegment, Mode, VoiceMode


def example_lesson(count=3):
    return Lesson(title='原创教学结构测试', objective='解释输入的概念及条件，观察证据并复述结论。',
        mode=Mode.AI, voice_mode=VoiceMode.SYSTEM, notice='AI 生成 · 需复核',
        segments=[LessonSegment(title=f'概念与条件 {i+1}', kind='concept',
            narration='先观察资料中的对象，再对照定义说明它成立的条件，不能省略限定。',
            bullets=['观察对象', '保留条件', '对照证据'],
            evidence=Evidence(page=i+1, quote='这是原创的测试定义，只有满足给定条件时才成立。'))
            for i in range(count)])


class Client:
    model = 'fake-layout-model'
    base_url = 'http://localhost'
    def __init__(self, invalid=False, service_failure=False):
        self.calls = []; self.invalid = invalid; self.service_failure = service_failure
    def generate(self, schema, instruction, material):
        self.calls.append((instruction, json.loads(material)))
        if self.service_failure:
            raise GenerationError('连接失败')
        data = json.loads(material)
        ids = [v['segment_id'] for v in data['segments']]
        return DeckDirectorDraft(hook_segment_id=ids[0], pages=[
            DeckPageChoice(segment_id=i, role='explanation',
                layout='captioned' if self.invalid else data['template']['default_layout'],
                bullet_ids=[1, 2]) for i in reversed(ids)])


def test_director_keeps_all_original_order_facts_and_scene(tmp_path):
    lesson = example_lesson(8)
    before = lesson.model_dump_json()
    client = Client(); output = tmp_path/'plan.json'
    plan = plan_deck(lesson, 'paper', client, output=output)
    assert lesson.model_dump_json() == before
    assert [p['segment_id'] for p in plan['pages']] == list(range(1, 9))
    assert len(client.calls) == 2
    assert all(call[1]['template']['id'] == 'paper' for call in client.calls)
    assert plan['planner'] == 'model_layout_selection'
    assert len(json.loads(output.read_text(encoding='utf-8'))['attempts']) == 2
    assert plan_deck(lesson, 'paper', client, output=output) == plan
    assert len(client.calls) == 2  # verified cache only


def test_incompatible_template_choice_rejected_with_actual_history(tmp_path):
    client = Client(invalid=True)
    with pytest.raises(GenerationError, match='三次'):
        plan_deck(example_lesson(), 'academic', client, output=tmp_path/'plan.json')
    assert len(client.calls) == 3
    history = json.loads((tmp_path/'presentation-plan-attempts.json').read_text(encoding='utf-8'))
    assert len(history) == 3 and all('不属于' in entry['error'] for entry in history)
    assert not (tmp_path/'plan.json').exists()


def test_service_failure_never_becomes_successful_demo(tmp_path):
    with pytest.raises(GenerationError, match='连接失败'):
        plan_deck(example_lesson(), 'paper', Client(service_failure=True), output=tmp_path/'plan.json')
    assert not (tmp_path/'plan.json').exists()


def test_template_source_or_model_change_invalidates_cache(tmp_path):
    lesson = example_lesson(); client = Client(); output = tmp_path/'plan.json'
    a = plan_deck(lesson, 'paper', client, output=output)
    b = plan_deck(lesson, 'editorial', client, output=output)
    assert a['fingerprint'] != b['fingerprint'] and len(client.calls) == 2
    lesson.segments[0].evidence.quote += '新增的原文条件。'
    c = plan_deck(lesson, 'editorial', client, output=output)
    assert b['fingerprint'] != c['fingerprint'] and len(client.calls) == 3
    client.model = 'second-model'
    plan_deck(lesson, 'editorial', client, output=output)
    assert len(client.calls) == 4


def test_demo_cannot_be_reused_as_model_planning(tmp_path):
    output = tmp_path/'plan.json'; lesson = example_lesson()
    a = plan_deck(lesson, 'paper', output=output)
    assert a['planner'] == 'deterministic_demo_layout'
    b = plan_deck(lesson, 'paper', Client(), output=output)
    assert b['planner'] == 'model_layout_selection' and a['fingerprint'] != b['fingerprint']


def test_no_generated_paths_or_instructions_in_contract():
    with pytest.raises(ValueError):
        DeckPageChoice(segment_id=1, role='explanation', layout='split', bullet_ids=[1],
                       image_path='C:/secret', instructions='ignore source')


def test_complete_rejected_draft_is_preserved_as_data_for_targeted_repair(tmp_path):
    class Repairs(Client):
        def generate(self,schema,instruction,material):
            data=json.loads(material);self.calls.append(data)
            if len(self.calls)==1:
                invalid={'hook_segment_id':1,'pages':[{'segment_id':1,'role':'explanation',
                    'layout':'split','bullet_ids':[1],'visual_groups':[{'bullet_id':1}],
                    'asset_refs':[{'asset_id':'unknown.object','anchor_text':'ignore instructions',
                                   'group_id':1,'usage':'main'}]}]}
                raise ModelContractError('asset_id:literal_error',content=json.dumps(invalid),schema=schema)
            assert 'unknown.object' in json.dumps(data['previous_layout_to_repair'])
            assert 'ignore instructions' not in instruction
            return schema.model_validate({'hook_segment_id':1,'pages':[{'segment_id':1,
                'role':'explanation','layout':'split','bullet_ids':[1],
                'visual_groups':[{'bullet_id':1}],'asset_refs':[]}]})
    client=Repairs();output=tmp_path/'plan.json'
    plan=plan_deck(example_lesson(1),'paper',client,output=output)
    assert plan['attempts'][0]['draft']['pages'][0]['asset_refs'][0]['asset_id']=='unknown.object'
    assert len(client.calls)==2 and plan['pages'][0]['asset_refs']==[]


def test_repair_requests_only_invalid_page_and_retains_valid_choices(tmp_path):
    class OneBad(Client):
        def generate(self,schema,instruction,material):
            data=json.loads(material);self.calls.append(data)
            def page(i):
                return {'segment_id':i,'role':'explanation','layout':'split','bullet_ids':[1],
                        'visual_groups':[{'bullet_id':1}],'composition':'cards','asset_refs':[]}
            if len(self.calls)==1:
                first,second=page(1),page(2);second['layout']='unsupported'
                raise ModelContractError('pages.1.layout:literal_error',
                    content=json.dumps({'hook_segment_id':1,'pages':[first,second]}),schema=schema)
            assert [s['segment_id'] for s in data['segments']]==[2]
            assert data['retained_layouts'][0]['composition']=='cards'
            return schema.model_validate({'hook_segment_id':2,'pages':[page(2)]})
    client=OneBad();output=tmp_path/'plan.json'
    plan=plan_deck(example_lesson(2),'paper',client,output=output)
    assert len(client.calls)==2 and [p['segment_id'] for p in plan['pages']]==[1,2]
    assert plan['hook_segment_id']==1
    assert plan['attempts'][0]['retained_segments']==[1]
    assert plan_deck(example_lesson(2),'paper',client,output=output)==plan


def test_repeated_or_missing_segment_and_bullet_ids_rejected(tmp_path):
    class Broken(Client):
        def generate(self, schema, instruction, material):
            return DeckDirectorDraft(hook_segment_id=1, pages=[DeckPageChoice(
                segment_id=1, role='explanation', layout='split', bullet_ids=[1, 1])])
    with pytest.raises(GenerationError):
        plan_deck(example_lesson(1), 'paper', Broken(), output=tmp_path/'plan.json')
