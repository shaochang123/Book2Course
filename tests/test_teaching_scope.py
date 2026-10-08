import json

import pytest
from PIL import Image

from zhijiang.models import Evidence, LessonSegment, PageText, SourceDocument
from zhijiang.teaching_design import TeachingDesignError, source_reading, source_spans
from zhijiang.teaching_scope import select_topic_sources, source_literals, literal_issues, validate_cached_scope


def segment(page=2):
    return LessonSegment(title='一种新概念的完整定义', kind='concept',
        narration='根据原文定义解释这个新概念的含义及适用条件。', bullets=['完整定义'],
        evidence=Evidence(page=page, quote='This page only shows a worked example.'))


def test_scope_retrieves_definition_outside_old_sentence_window_and_previous_page(tmp_path):
    doc = SourceDocument(filename='new.pdf', pages=[
        PageText(page=1, text=' '.join(['Some independent observation is explained here.'] * 12) +
            ' The complete definition includes both relevant components.'),
        PageText(page=2, text=segment().evidence.quote),
        PageText(page=7, text='This unrelated page must not enter the local retrieval catalog.')])
    class Client:
        calls = 0
        def generate(self, schema, instruction, material):
            self.calls += 1
            if schema.__name__ == 'TopicScopeReview':
                return schema.model_validate({'reason':'所选的完整定义涵盖当前标题的全部组成部分。','missing':[]})
            sources = json.loads(material)['sources']
            assert {s['page'] for s in sources} == {1, 2}
            chosen = next(s['id'] for s in sources if 'complete definition' in s['text'])
            return schema.model_validate({'topic_term':'complete definition','source_ids': [chosen], 'reason': '前一页的定义完整包含当前标题需要的组成部分。', 'missing': []})
    client = Client()
    scope = select_topic_sources(client, segment(), doc, tmp_path/'scope.json')
    assert scope['page'] == 1 and scope['source_ids'] == [13]
    assert scope['original_evidence']['page'] == 2
    assert select_topic_sources(client, segment(), doc, tmp_path/'scope.json') == scope
    assert client.calls == 2


def test_incomplete_title_cannot_be_approved_or_retried_into_completeness():
    doc = SourceDocument(filename='new.pdf', pages=[PageText(page=2, text=segment().evidence.quote)])
    class Client:
        calls = 0
        def generate(self, schema, *args):
            self.calls += 1
            return schema.model_validate({'topic_term':'example','source_ids': [1], 'reason': '来源只有例子，缺少标题要求的完整定义条件。', 'missing': ['输入未包含完整定义']})
    client = Client()
    with pytest.raises(TeachingDesignError, match='输入未包含完整定义'):
        select_topic_sources(client, segment(), doc)
    assert client.calls == 1


def test_scope_rejects_cross_page_provenance_in_single_page_scene():
    doc = SourceDocument(filename='new.pdf', pages=[
        PageText(page=1, text='A preceding condition applies to the example.'),
        PageText(page=2, text=segment().evidence.quote)])
    class Client:
        def generate(self, schema, *args):
            return schema.model_validate({'topic_term':'example','source_ids': [1, 2], 'reason': '两个片段分别给出前提与实例，但位于不同页。', 'missing': []})
    with pytest.raises(TeachingDesignError, match='跨页联合讲解'):
        select_topic_sources(Client(), segment(), doc)


def test_failed_scope_review_is_not_reused_as_approved_cache(tmp_path):
    doc = SourceDocument(filename='new.pdf', pages=[PageText(page=2,
        text='An example is shown here. The definition applies only in a stated condition.')])
    class Client:
        calls = 0
        def generate(self, schema, *args):
            self.calls += 1
            if schema.__name__ == 'TopicScopeReview':
                return schema.model_validate({'reason':'所选示例遗漏标题所需要的定义与必要条件。', 'missing':['没有包含定义条件']})
            return schema.model_validate({'topic_term':'example', 'source_ids':[1],
                'reason':'当前示例给出了教学主题的一个具体展示。','missing':[]})
    path = tmp_path/'scope.json'; client = Client()
    for _ in range(2):
        with pytest.raises(TeachingDesignError, match='定义条件'):
            select_topic_sources(client, segment(), doc, path)
    assert client.calls == 8
    assert json.loads(path.read_text(encoding='utf-8'))['status'] != 'scope_checked_not_truth_guarantee'


def test_foreign_text_quantity_translation_does_not_require_chinese_verbatim_and_ocr_stays_strict():
    from zhijiang.teaching_design import scanned_fact_issues
    quote = 'Working for 5 hours earns $75.'
    statement = '按原文的工资条件，工作5小时能够获得75美元。'
    assert scanned_fact_issues(statement, quote, ocr=False) == []
    assert scanned_fact_issues(statement, quote, ocr=True)
    assert scanned_fact_issues(statement.replace('75', '750'), quote, ocr=False)
    assert scanned_fact_issues('按原文工资条件，工作五小时可获得七十五美元。', quote, ocr=False)


def test_font_boundaries_preserve_novel_example_without_subject_rules(tmp_path):
    import pymupdf
    path = tmp_path/'inline.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 100), 'The string ', fontname='tiro')
        page.insert_text((105, 100), 'rivers carry sediments', fontname='tiit')
        page.insert_text((210, 100), ' is an example.', fontname='tiro')
        page.insert_text((50, 150), 'An Entire Emphasized Heading', fontname='tiit')
        pdf.save(path)
    spans = {1: 'The string rivers carry sediments is an example.', 2: 'An Entire Emphasized Heading'}
    found = source_literals(path, 1, spans)
    assert found == {1: ['rivers carry sediments'], 2: []}
    assert literal_issues('原文给出的 rivers carry sediments 是完整示例。', found[1]) == []
    assert literal_issues('原文示例是 sediments is 这一字符串。', found[1])


def test_region_matching_survives_font_boundary_spaces_without_word_bag_fallback(tmp_path):
    import pymupdf
    from zhijiang.teaching_design import quote_rects
    with pymupdf.open() as pdf:
        page=pdf.new_page();page.insert_text((50,100),'A red fox observes a distant object.')
        assert quote_rects(page,'A redfox observes a distant object.')
        assert not quote_rects(page,'A distant fox observes a red object.')
        assert not quote_rects(page,'A red fox observes an invented object.')
        page.insert_text((50,150),'A red fox observes a distant object.')
        assert not quote_rects(page,'A redfox observes a distant object.')
        assert not quote_rects(page,'A red fox observes a distant object.')


def test_reading_repairs_literal_loss_and_does_not_reuse_corrupted_cache(tmp_path):
    spans = {4: 'The string rivers carry sediments is an example.'}
    protected = {4: ['rivers carry sediments']}
    class Client:
        calls = 0
        def generate(self, schema, instruction, material):
            self.calls += 1
            assert json.loads(material)['sources'][0]['protected_literals'] == protected[4]
            text = ('原文示例是 sediments is 这一字符串。' if self.calls == 1 else
                    '原文给出的 rivers carry sediments 是完整示例。')
            # A legacy/unvalidated client can still bypass native decoding;
            # runtime and cache checks must reject its changed source object.
            from types import SimpleNamespace
            from zhijiang.teaching_design import SourceFactDraft
            return SimpleNamespace(facts=[SourceFactDraft(source_id=4,statement=text)])
    client = Client(); path = tmp_path/'reading.json'
    facts, cached = source_reading(client, spans, path, literals=protected, required_sources=[4])
    assert client.calls == 2 and not cached and protected[4][0] in facts[0]['statement']
    assert json.loads(path.read_text(encoding='utf-8'))['rejected_facts']
    saved = json.loads(path.read_text(encoding='utf-8'))
    saved['facts'][0]['statement'] = '原文示例是 sediments is 这一字符串。'
    path.write_text(json.dumps(saved), encoding='utf-8')
    assert not source_reading(client, spans, path, literals=protected, required_sources=[4])[1]
    assert client.calls == 3


def test_native_statement_contract_binds_original_example_spelling():
    from zhijiang.teaching_design import extract_source_facts
    class Client:
        def generate(self,schema,instruction,material):
            row=json.loads(material)['sources'][0]
            assert row['literal_prefix']=='原文中的“rivers carry sediments”'
            with pytest.raises(ValueError):
                schema.model_validate({'facts':[{'source_id':4,'continuation':'sediments is 是原文的完整字符串。'}]})
            return schema.model_validate({'facts':[{'source_id':4,
                'continuation':'是原文提供的完整示例字符串。'}]})
    facts=extract_source_facts(Client(),{4:'The string rivers carry sediments is an example.'},
        literals={4:['rivers carry sediments']})
    assert 'rivers carry sediments' in facts[0]['statement']


def test_reading_rejects_missing_required_source_and_has_bounded_retries():
    spans = {1: 'This is only a worked example.', 9: 'This is the required definition.'}
    class Client:
        calls = 0
        def generate(self, schema, *args):
            self.calls += 1
            return schema.model_validate({'facts': [{'source_id': 1, 'statement': '当前来源只描述一个具体示例，没有给出定义。'}]})
    client = Client()
    with pytest.raises(TeachingDesignError, match='遗漏标题所需来源编号'):
        source_reading(client, spans, required_sources=[9])
    assert client.calls == 2


def test_scope_survives_compile_and_cache_rechecks_actual_page_and_spoken_coverage(tmp_path):
    from tests.test_teaching_design import diagram
    from zhijiang.teaching_design import ResolvedTeachingDesign, compile_teaching_scene
    from zhijiang.visual_planning import load_planned_scene, save_planned_scene
    d = diagram()
    source = d.nodes[0].source_quote + '. ' + d.nodes[1].source_quote + '. ' + d.nodes[2].source_quote + '.'
    doc = SourceDocument(filename='new.pdf', pages=[PageText(page=1, text=source),
        PageText(page=2, text=segment().evidence.quote)])
    original = segment()
    scope = {'page': 1, 'ocr': False, 'topic': original.title, 'missing': [],
        'original_evidence': original.evidence.model_dump(), 'sources': {1: source_spans(source)[1]}, 'source_ids': [1]}
    # The existing fixture has no independent fact bindings; missing coverage
    # must invalidate the scope even if an approval flag is present.
    draft = ResolvedTeachingDesign(question='怎样理解原文中的完整定义？', **d.model_dump())
    scene = compile_teaching_scene(draft, original, {'topic_scope': scope}, source_text=source)
    assert scene.evidence.page == original.evidence.page == 1
    assert not validate_cached_scope(scene, scope, doc, segment())
    scope['original_evidence']['page'] = 7
    assert not validate_cached_scope(scene, scope, doc, segment())


def test_source_crop_is_pixel_exact_enlarged_and_shared_with_svg(tmp_path):
    from tests.test_teaching_design import diagram
    from zhijiang.teaching_design import ResolvedTeachingDesign, compile_teaching_scene
    from zhijiang.source_detail import source_detail
    from zhijiang.visual_media import teaching_summary_svg
    path = tmp_path/'page.png'; Image.new('RGB', (800, 1200), 'white').save(path)
    d = diagram(); d.representation = 'source_figure'; d.source_asset = str(path)
    d.source_regions = {'1': [.1, .2, .8, .25]}; d.steps[-1].focus = [1]
    detail = source_detail(d, [1])
    assert detail['enlargement'] > 2 and detail['pixel_box'] == (68, 225, 652, 315)
    assert source_detail(d, [6]) is None
    draft = ResolvedTeachingDesign(question='怎样观察当前来源的原文依据？', **d.model_dump())
    scene = compile_teaching_scene(draft, segment(), {})
    # Assets are execution data, attached after design resolution.
    scene.diagram.source_asset = d.source_asset; scene.diagram.source_regions = d.source_regions
    assert 'data-source-focus="1"' in teaching_summary_svg(scene)
    d.source_regions['1'] = [.8, .2, .1, .25]
    with pytest.raises(ValueError, match='坐标无效'): source_detail(d, [1])
