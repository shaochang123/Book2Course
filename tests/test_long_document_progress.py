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
            result = super().generate(schema, instruction, material)
            result.points[0].explanation = '原文遗漏的比例是2/5，因此可以直接相乘计算。'
            return result

    client = InventedRatio()
    with pytest.raises(GenerationError, match='来源数值'):
        AIAgents(client).extract_knowledge(document, cache_dir=tmp_path)
    assert client.calls == [1, 1]
    assert not list(tmp_path.glob('batch-*.json'))


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
