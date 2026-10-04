"""Long scanned sources must report work and resume validated batches."""

from io import BytesIO
import json
from types import SimpleNamespace

import httpx
import pytest
from pypdf import PdfWriter

from zhijiang.agents import AIAgents, GenerationError, OllamaClient, source_candidates, validate_evidence
from zhijiang.models import Evidence, PageText, ReviewResult, SourceDocument
from zhijiang.pdf import PDFError, read_pdf


def blank_pdf(count):
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_interrupted_ocr_resumes_including_blank_pages_and_invalidates_changed_source(tmp_path):
    calls = []
    events = []

    def interrupted(_):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError('interruption')
        return SimpleNamespace(txts=['A complete scanned teaching definition. ' * 3] if len(calls) == 1 else [])

    original = blank_pdf(3)
    with pytest.raises(PDFError, match='OCR 失败'):
        read_pdf(original, 'scan.pdf', interrupted, cache_dir=tmp_path,
                 progress=lambda *args: events.append(args))
    assert len(list(tmp_path.glob('page-*.json'))) == 2
    assert (2, 3, '页面解析完成') in events

    def finished(_):
        calls.append(1)
        return SimpleNamespace(txts=['Another source definition that OCR recognizes. ' * 3])

    result = read_pdf(original, 'scan.pdf', finished, cache_dir=tmp_path,
                      progress=lambda *args: events.append(args))
    assert len(calls) == 4  # Neither the first nor the blank second page is re-read.
    assert [page.page for page in result.pages] == [1, 3]
    assert events[-1] == (3, 3, '本地 OCR 完成')
    read_pdf(blank_pdf(4), 'scan.pdf', finished, cache_dir=tmp_path)
    assert len(calls) == 8


def test_chinese_wrapped_definitions_and_exercise_context_are_exact_source_spans():
    document = SourceDocument(filename='textbook.pdf', pages=[
        PageText(page=1, text='ISBN 123456\n出版发行：某出版社\n责任编辑：作者\n定价：20元'),
        PageText(page=2, text='编者的话\n接下来我们一起了解本学期的知识并探索新方法。'),
        PageText(page=3, text='目录\n第一单元\n4\n第二单元\n12'),
        PageText(page=4, text='第三单元\n24\n总复习\n80'),
        PageText(page=5, text='讨论：怎样计算？\n分数乘分数，用分子\n相乘的积作分子。\n用分母相乘的积作分母。'),
        PageText(page=6, text='分数与整数相乘，是\n分数乘整数，用分子\n怎样计算的？\n乘整数的积作分子，\n分母不变。'),
        PageText(page=7, text='判断对错，对的画“√”，错的画“×”。\n(1)圆周率就是3.14。\n(2)半径相等的两个圆周长相等。'),
        PageText(page=8, text='连接圆心和圆\n上任意一点的线段叫做半径。'),
    ])
    candidates = source_candidates(document)
    assert not {1, 2, 3, 4} & {item['page'] for item in candidates}
    assert any('分数乘分数' in item['quote'] and '用分母相乘的积作分母' in item['quote'] for item in candidates)
    assert any('分数乘整数，用分子' in item['quote'] and '分母不变' in item['quote'] for item in candidates)
    judgments = [item for item in candidates if '3.14' in item['quote']]
    assert judgments and all('判断对错' in item['quote'] and item['role'] == 'exercise' for item in judgments)
    for item in candidates:
        validate_evidence(document, Evidence(**item))


def long_source():
    return SourceDocument(filename='long.pdf', pages=[PageText(page=index, text='\n'.join(
        f'Page {index} statement {part} explains a separate teaching concept and its conditions.'
        for part in range(4))) for index in range(1, 18)])


class SelectionClient:
    def __init__(self, fail_second=False):
        self.calls = []
        self.fail_second = fail_second

    def generate(self, schema, instruction, material):
        sources = json.loads(material)['sources']
        self.calls.append(sources[0]['id'])
        if self.fail_second and len(self.calls) == 2:
            raise GenerationError('temporary failure')
        return schema.model_validate({'points': [dict(title=f"来源概念 {source['id']}",
            kind='concept', explanation='根据对应原文说明这个概念及条件。', source_id=source['id'])
            for source in sources[:3]]})


def test_failed_knowledge_batch_resumes_only_completed_batches_and_rechecks_cache(tmp_path):
    document = long_source()
    client = SelectionClient(fail_second=True)
    events = []
    with pytest.raises(GenerationError, match='第 2/2 批失败'):
        AIAgents(client).extract_knowledge(document, cache_dir=tmp_path, cache_fingerprint='model-v1',
                                         progress=lambda *args: events.append(args))
    assert len(list(tmp_path.glob('batch-*.json'))) == 1
    assert events[-2][0:2] == (1, 2)
    resumed = SelectionClient()
    bundle = AIAgents(resumed).extract_knowledge(document, cache_dir=tmp_path, cache_fingerprint='model-v1')
    assert len(bundle.points) == 6 and resumed.calls == [17]
    first = tmp_path / 'batch-0001.json'
    corrupt = json.loads(first.read_text(encoding='utf-8'))
    corrupt['data']['points'][0]['source_id'] = 900
    first.write_text(json.dumps(corrupt), encoding='utf-8')
    rechecked = SelectionClient()
    AIAgents(rechecked).extract_knowledge(document, cache_dir=tmp_path, cache_fingerprint='model-v1')
    assert rechecked.calls == [1]
    changed = SelectionClient()
    AIAgents(changed).extract_knowledge(document, cache_dir=tmp_path, cache_fingerprint='different-model')
    assert changed.calls == [1, 17]


def test_knowledge_rejects_an_ocr_missing_ratio_without_blocking_later_scene_examples(tmp_path):
    document = long_source()

    class InventedRatio(SelectionClient):
        def generate(self, schema, instruction, material):
            if schema.__name__ == 'KnowledgePageQuoteRepair':
                self.calls.append('page-quote')
                points = schema.model_fields['quotations'].annotation.__args__[0]
                return schema.model_construct(quotations=[points.model_construct(point_id=item['point_id'],quote_id=999)
                    for item in json.loads(material)['points']])
            if schema.__name__ == 'KnowledgeExplanationRepair':
                self.calls.append('repair')
                # A deliberately nonconforming client must not bypass the
                # backend's source checks even if schema validation was skipped.
                from zhijiang.agents import KnowledgeExplanationPoint
                return schema.model_construct(explanations=[KnowledgeExplanationPoint.model_construct(
                    point_id=item['point_id'], explanation='仍猜测原文遗漏的比例是2/5，并据此计算。')
                    for item in json.loads(material)['repairs']])
            result = super().generate(schema, instruction, material)
            result.points[0].explanation = '原文遗漏的比例是2/5，因此可以直接相乘计算。'
            return result

    client = InventedRatio()
    with pytest.raises(GenerationError, match='来源数值'):
        AIAgents(client).extract_knowledge(document, cache_dir=tmp_path)
    assert client.calls == [1, 'repair', 'repair', 'page-quote', 'page-quote']
    assert not [path for path in tmp_path.glob('batch-*.json') if not path.name.endswith('.draft.json')]
    assert (tmp_path/'batch-0001.draft.json').is_file()


def test_repairs_only_invalid_explanations_and_preserves_every_topic_and_valid_field(tmp_path):
    document = long_source()

    class RepairClient(SelectionClient):
        initial = None

        def generate(self, schema, instruction, material):
            if schema.__name__ == 'KnowledgeExplanationRepair':
                self.calls.append('repair')
                repairs = json.loads(material)['repairs']
                assert [item['point_id'] for item in repairs] == [2]
                assert repairs[0]['unsupported_numbers'] == ['9.99']
                return schema.model_validate({'explanations': [dict(point_id=2,
                    explanation='这段文字讨论概念和适用条件，具体数量需要回看原文核对。')]})
            result = super().generate(schema, instruction, material)
            if self.initial is None:
                result.points[1].source_id = result.points[0].source_id
                result.points[1].explanation = '根据原文，具体参数必然等于9.99。'
                self.initial = result.model_dump()
            return result

    client = RepairClient()
    bundle = AIAgents(client).extract_knowledge(document, cache_dir=tmp_path)
    assert client.calls == [1, 'repair', 17]
    assert len(bundle.points) == 6
    saved = json.loads((tmp_path/'batch-0001.json').read_text(encoding='utf-8'))['data']
    assert saved['points'][0] == client.initial['points'][0]
    assert saved['points'][2] == client.initial['points'][2]
    for key in ('title','kind','source_id'):
        assert saved['points'][1][key] == client.initial['points'][1][key]
    assert '9.99' not in saved['points'][1]['explanation']


def test_failed_explanation_repair_resumes_draft_without_regenerating_valid_points(tmp_path):
    document = long_source()

    class RepairClient(SelectionClient):
        fail_repairs = True

        def generate(self, schema, instruction, material):
            if schema.__name__ == 'KnowledgeExplanationRepair':
                self.calls.append('repair')
                if self.fail_repairs:
                    raise GenerationError('repair service unavailable')
                return schema.model_validate({'explanations': [dict(point_id=item['point_id'],
                    explanation='概念依据当前引文讲解，不清晰的数量需要核对原始图示。')
                    for item in json.loads(material)['repairs']]})
            result = super().generate(schema, instruction, material)
            if self.calls == [1]:
                result.points[0].explanation = '该材料使用了未经来源提供的参数9.99。'
            return result

    client = RepairClient()
    with pytest.raises(GenerationError,match='unavailable'):
        AIAgents(client).extract_knowledge(document, cache_dir=tmp_path,cache_fingerprint='same')
    assert client.calls == [1, 'repair']
    draft = tmp_path/'batch-0001.draft.json'
    assert json.loads(draft.read_text(encoding='utf-8'))['approved'] is False
    client.fail_repairs = False
    client.calls.clear()
    bundle = AIAgents(client).extract_knowledge(document, cache_dir=tmp_path,cache_fingerprint='same')
    assert len(bundle.points) == 6 and client.calls == ['repair',17]


def test_summary_rejects_chinese_fraction_and_new_formula_using_only_source_digits():
    from zhijiang.agents import KnowledgeSelection, _selection_number_issues
    sources = {1: {'quote': '音符表示不同的时值，OCR将部分分数识别成24与16。'},
               2: {'quote': '引桥的长度是正桥的257 578，桥全长1670m。'},
               3: {'quote': '两个数的比表示两个数相除。15比10记作15:10。'}}
    selection = KnowledgeSelection.model_validate({'points': [
        dict(title='时值关系',kind='concept',source_id=1,explanation='四分音符是全音符的四分之一。'),
        dict(title='长度关系',kind='formula',source_id=2,explanation='引桥与正桥的比例为578，可设引桥为578x。'),
        dict(title='比的定义',kind='concept',source_id=3,explanation='两个数的比表示两个数相除。15比10记作15:10。'),
    ]})
    assert set(_selection_number_issues(selection,sources)) == {1,2}


def test_stubborn_fraction_repair_selects_literal_readable_source_without_rewriting_topics():
    from zhijiang.agents import KnowledgeSelection, _selection_number_issues
    source = {'quote': '不同音符表示不同的时值（即音的长短），部分时值为24 16。'}
    sources = {1: source, 2: {'quote': '物体运动的方向需要结合参考对象描述。'}}
    selection = KnowledgeSelection.model_validate({'points': [
        dict(title='音符时值',kind='concept',source_id=1,explanation='四分音符的时值是全音符的四分之一。'),
        dict(title='参考对象',kind='concept',source_id=2,explanation='运动方向依赖所选参考对象。'),
        dict(title='运动描述',kind='process',source_id=2,explanation='描述运动时应说明参考对象。'),
    ]})

    class Client:
        def generate(self, schema, instruction, material):
            data = json.loads(material)
            if schema.__name__ == 'KnowledgeExplanationRepair':
                return schema.model_validate({'explanations': [dict(point_id=1,
                    explanation='四分音符的时值是全音符的四分之一。')]})
            assert schema.__name__ == 'KnowledgeSourceClauseRepair'
            candidates = data['clauses']
            assert all('24' not in item['text'] for item in candidates.values())
            return schema.model_validate({'selections': [dict(point_id=1,clause_id=int(next(iter(candidates))))]})

    agent = AIAgents(Client())
    result = agent._repair_knowledge_explanations(selection,sources,6,15)
    assert result.points[0].explanation == '不同音符表示不同的时值（即音的长短）'
    assert result.points[1:] == selection.points[1:]
    assert result.points[0].source_id == 1 and result.points[0].title == selection.points[0].title
    assert not _selection_number_issues(result,sources)
    assert agent.knowledge_drafts[-1]['repair_method'] == 'literal_source_clause'


def test_literal_repair_rejects_a_clause_belonging_to_another_topic():
    from zhijiang.agents import KnowledgeSelection
    sources = {1: {'quote': '不同音符表示不同的时值（即音的长短）。'},
               2: {'quote': '运动方向依赖所选定的参考对象。'}}
    selection = KnowledgeSelection.model_validate({'points': [
        dict(title='音符时值',kind='concept',source_id=1,explanation='全音符时值是一半。'),
        dict(title='参考对象',kind='concept',source_id=2,explanation='参考对象数量是三。'),
        dict(title='运动描述',kind='process',source_id=2,explanation='描述运动时应说明参考对象。'),
    ]})

    class Client:
        def generate(self, schema, instruction, material):
            data = json.loads(material)
            if schema.__name__ == 'KnowledgeExplanationRepair':
                return schema.model_validate({'explanations': [dict(point_id=item['point_id'],
                    explanation=selection.points[item['point_id']-1].explanation)
                    for item in data['repairs']]})
            candidates = data['clauses']
            first = {item['point_id']: int(key) for key,item in candidates.items()}
            return schema.model_validate({'selections': [dict(point_id=1,clause_id=first[2]),
                                                         dict(point_id=2,clause_id=first[1])]})

    with pytest.raises(GenerationError,match='来源数值'):
        AIAgents(Client())._repair_knowledge_explanations(selection,sources,6,15)


def test_repair_recovers_a_literal_conclusion_outside_the_sampled_excerpt_on_same_page():
    from zhijiang.agents import KnowledgeSelection, _selection_structure_issue
    sources = {1: {'quote': '1 2 4 8 16 从第二个数开始，规律?',
                   'page_text': '1 2 4 8 16 从第二个数开始，规律? 后面观察：分数越来越接\n近于1。'},
               2: {'quote': '运动方向依赖所选定的参考对象。'}}
    selection = KnowledgeSelection.model_validate({'points': [
        dict(title='分数累加',kind='process',source_id=1,explanation='相邻项是前一项的二倍。'),
        dict(title='参考对象',kind='concept',source_id=2,explanation='运动方向依赖所选参考对象。'),
        dict(title='运动描述',kind='process',source_id=2,explanation='描述运动时应说明参考对象。'),
    ]})

    class Client:
        def generate(self, schema, instruction, material):
            if schema.__name__ == 'KnowledgeExplanationRepair':
                if json.loads(material)['repairs'][0]['source']['quote']=='分数越来越接近于1':
                    return schema.model_validate({'explanations': [dict(point_id=1,explanation='通过逐项累加，观察分数总和逐渐接近某个固定值。')]})
                return schema.model_validate({'explanations': [dict(point_id=1,explanation='相邻项是前一项的二倍。')]})
            assert schema.__name__ == 'KnowledgePageQuoteRepair'
            quotes = json.loads(material)['quotes']
            quote_id = next(int(key) for key,item in quotes.items() if item['text']=='分数越来越接近于1')
            return schema.model_validate({'quotations': [dict(point_id=1,quote_id=quote_id)]})

    agent = AIAgents(Client())
    result = agent._repair_knowledge_explanations(selection,sources,14,15)
    assert result.points[0].source_quote == '分数越来越接近于1'
    assert result.points[0].explanation == '通过逐项累加，观察分数总和逐渐接近某个固定值。'
    assert result.points[0].source_id == selection.points[0].source_id
    assert result.points[1:] == selection.points[1:]
    assert not _selection_structure_issue(result,sources)
    assert agent.knowledge_drafts[-1]['repair_method'] == 'literal_same_page_quote'
    result.points[0].source_quote = '这是来自其他页面的断言。'
    assert _selection_structure_issue(result,sources)


def test_same_page_quote_candidates_keep_the_specific_topic_instead_of_adjacent_background():
    from zhijiang.agents import _page_quote_focus, _page_source_quotes
    page = '观察奇数求和规律，正方形面积是这些数的和。你能发现什么规律？分数越来越接近于1。'
    focus = _page_quote_focus('分数累加的收敛规律',page)
    assert focus == {'分数'}
    quotes = _page_source_quotes(page,focus)
    assert quotes and all('分数' in quote for quote in quotes)
    assert not any('正方形' in quote for quote in quotes)


def test_quantitative_summary_checks_keep_sourced_chemical_and_scientific_names():
    from zhijiang.agents import KnowledgeSelection, _selection_number_issues
    sources = {1: {'quote': 'CO2 and H2O are named compounds considered in this source.'},
               2: {'quote': 'Vitamin B12 is the named vitamin examined in the study.'},
               3: {'quote': 'A velocity of 15cm/s was measured under stated conditions.'}}
    selection = KnowledgeSelection.model_validate({'points': [
        dict(title='材料对象',kind='concept',source_id=1,explanation='原文讨论CO2和H2O这两种化合物。'),
        dict(title='维生素对象',kind='concept',source_id=2,explanation='文中研究的是Vitamin B12这种维生素。'),
        dict(title='测量结果',kind='process',source_id=3,explanation='所测速度一定等于15cm/s，不依赖测量条件。'),
    ]})
    assert set(_selection_number_issues(selection,sources)) == {3}


def test_generic_chinese_articles_and_definition_terms_are_not_specific_quantities():
    from zhijiang.agents import KnowledgeSelection, _selection_number_issues
    sources = {1: {'quote': '一个数乘几分之几表示的是求这个数的几分之几是多少。'},
               2: {'quote': '两个数的比表示两个数相除。'},
               3: {'quote': '这里讨论数和分数之间的关系。'}}
    selection = KnowledgeSelection.model_validate({'points': [
        dict(title='分数乘法意义',kind='concept',source_id=1,explanation='当一个数乘以分数时，其结果表示这个数的几分之几。'),
        dict(title='比的定义',kind='concept',source_id=2,explanation='两个数的比表示这两个数相除。'),
        dict(title='无依据的精确个数',kind='concept',source_id=3,explanation='其中恰好只有一个数满足条件。'),
    ]})
    assert set(_selection_number_issues(selection,sources)) == {3}


def test_ollama_stream_reports_counts_and_validates_only_completed_output():
    events = []
    requests = []

    def handler(request):
        if request.url.path == '/api/show':
            return httpx.Response(200, json={})
        body = json.loads(request.content)
        requests.append(body)
        assert body['stream'] is True
        records = [dict(message={'thinking': 'private reasoning', 'content': '{"approved":'}),
                   dict(message={'content': 'true}'}, done=True, eval_count=12)]
        return httpx.Response(200, text='\n'.join(json.dumps(record) for record in records))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient('http://localhost:11434', 'model', http_client,
                              progress=lambda *args: events.append(args))
        assert client.generate(ReviewResult, 'review', 'source').approved
        assert events[0] == ('ReviewResult', 0, 0)
        assert events[-1][2] == len('{"approved":true}')
        assert client.call_metrics[-1]['eval_count'] == 12
    assert len(requests) == 1


def test_ollama_incomplete_stream_is_not_accepted_even_when_json_is_valid():
    def handler(request):
        if request.url.path == '/api/show':
            return httpx.Response(200, json={})
        return httpx.Response(200, text=json.dumps({'message': {'content': '{"approved":true}'}}))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient('http://localhost:11434', 'model', http_client, progress=lambda *args: None)
        with pytest.raises(GenerationError, match='输出中断'):
            client.generate(ReviewResult, 'review', 'source')


def test_native_stream_error_retries_once_with_generation_endpoint_without_echoing_body():
    paths = []

    def handler(request):
        if request.url.path == '/api/show':
            return httpx.Response(200, json={})
        paths.append(request.url.path)
        body = json.loads(request.content)
        if len(paths) == 1:
            return httpx.Response(200, text=json.dumps({'error': 'private parser output'}))
        assert body['stream'] is True and 'private parser output' not in body['prompt']
        return httpx.Response(200, text=json.dumps({'response': '{"approved":true}', 'done': True}))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient('http://localhost:11434', 'model', http_client, progress=lambda *args: None)
        assert client.generate(ReviewResult, 'review', 'source').approved
        assert client.call_metrics[0]['error'] == 'upstream_stream_error'
    assert paths == ['/api/chat', '/api/generate']
