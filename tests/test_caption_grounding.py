import json

import pytest

from zhijiang.agents import GenerationError
from zhijiang.caption_grounding import ground_lesson_captions, speech_sentences
from test_deck_planning import example_lesson


class Selects:
    def __init__(self): self.calls = []
    def generate(self, schema, instruction, material):
        data = json.loads(material); self.calls.append(data)
        return schema.model_validate({'pages':[
            {'segment_id':s['segment_id'], 'sentence_ids':[s['sentences'][0]['id']]}
            for s in data['segments']]})


def test_reversed_caption_is_replaced_by_a_whole_existing_sentence(tmp_path):
    lesson = example_lesson(1)
    sentence = '若甲成立能推出乙成立，则甲是乙的充分条件，乙是甲的必要条件'
    lesson.segments[0].narration = sentence+'。不能由此主张反向也成立。'
    lesson.segments[0].bullets = ['乙推甲成立：乙是甲的必要条件']
    original = lesson.segments[0].narration
    client = Selects()
    records = ground_lesson_captions(lesson,client,output=tmp_path/'captions.json')
    assert lesson.segments[0].bullets == [sentence]
    assert lesson.segments[0].narration == original
    assert records[0]['input'][0]['previous_captions'] == ['乙推甲成立：乙是甲的必要条件']
    assert not client.calls[0]['segments'][0]['sentences'][0]['text'].endswith('充分条件')


def test_punctuation_keeps_decimal_numbers_and_conditions_together():
    assert speech_sentences('温度不变时，值为0.5。否则结论不成立。') == ['温度不变时，值为0.5','否则结论不成立']
    assert speech_sentences('如果条件成立；才有这一结论。')==['如果条件成立；才有这一结论']


def test_literal_caption_and_computed_animation_do_not_call_a_model():
    lesson = example_lesson(2)
    lesson.segments[0].bullets = [speech_sentences(lesson.segments[0].narration)[0]]
    lesson.animation_report = {'prepared_scenes':[2]}
    before = lesson.model_dump_json()
    client = Selects()
    assert ground_lesson_captions(lesson,client) == []
    assert not client.calls and lesson.model_dump_json() == before


def test_literal_substring_cannot_drop_a_condition_or_misconception_qualifier():
    lesson=example_lesson(1)
    sentence='一个常见误解是，认为电压就是流动的电荷'
    lesson.segments[0].narration=sentence+'。电压和电流是不同物理量。'
    lesson.segments[0].bullets=['认为电压就是流动的电荷']
    client=Selects();ground_lesson_captions(lesson,client)
    assert len(client.calls)==1 and lesson.segments[0].bullets==[sentence]


def test_visual_details_never_cut_off_a_scope_qualifier():
    from zhijiang.deck_planning import visual_details
    lesson=example_lesson(1)
    lesson.segments[0].narration='常见误解是，电压等于电荷。温度不变时，结论才成立。'
    details=[s['text'] for s in visual_details(lesson.segments[0])]
    assert details==['常见误解是，电压等于电荷','温度不变时，结论才成立']
    assert '电压等于电荷' not in details and '结论才成立' not in details


def test_computed_scene_preserved_but_qualitative_captions_are_grounded():
    from test_visual_scenes import scene_for
    from test_teaching_design import diagram
    lesson=example_lesson(2)
    lesson.segments[0].visual_scene=scene_for('数学','t',{'t':0},{'t':1})
    lesson.segments[1].visual_scene=scene_for('关系','t',{'t':0},{'t':1})
    lesson.segments[1].visual_scene.diagram=diagram()
    first=lesson.segments[0].model_dump_json()
    second_scene=lesson.segments[1].visual_scene.model_dump_json()
    client=Selects()
    ground_lesson_captions(lesson,client)
    assert lesson.segments[0].model_dump_json()==first
    assert lesson.segments[1].visual_scene.model_dump_json()==second_scene
    assert [s['segment_id'] for s in client.calls[0]['segments']]==[2]


def test_invalid_selection_fails_without_partial_changes(tmp_path):
    lesson = example_lesson(7); before = lesson.model_dump_json()
    class BadAfterFirst(Selects):
        def generate(self,schema,instruction,material):
            if not self.calls: return super().generate(schema,instruction,material)
            self.calls.append(json.loads(material))
            return schema.model_validate({'pages':[{'segment_id':7,'sentence_ids':[999]}]})
    client = BadAfterFirst()
    with pytest.raises(GenerationError,match='两次'):
        ground_lesson_captions(lesson,client,output=tmp_path/'captions.json')
    assert lesson.model_dump_json() == before and len(client.calls) == 3
    assert 'error' in json.loads((tmp_path/'captions.json').read_text())[-1]


def test_service_failure_is_not_an_accepted_caption():
    class Fails:
        def generate(self,*args): raise GenerationError('服务不可用')
    lesson=example_lesson(1);before=lesson.model_dump_json()
    with pytest.raises(GenerationError,match='服务不可用'):
        ground_lesson_captions(lesson,Fails())
    assert lesson.model_dump_json()==before


def test_repeated_sentence_ids_are_repaired_with_bounded_attempts():
    lesson=example_lesson(1)
    lesson.segments[0].narration='先比较给定输入的前提。再观察相应结果的变化。'
    class Repeats(Selects):
        def generate(self,schema,instruction,material):
            if not self.calls:
                self.calls.append(json.loads(material))
                return schema.model_validate({'pages':[{'segment_id':1,'sentence_ids':[1,1]}]})
            return super().generate(schema,instruction,material)
    client=Repeats()
    records=ground_lesson_captions(lesson,client)
    assert len(client.calls)==2 and 'error' in records[0]
    assert lesson.segments[0].bullets==['先比较给定输入的前提']
