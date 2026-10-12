import json
from zipfile import ZipFile

from pypdf import PdfReader
import pytest
from reportlab.pdfgen import canvas

from scripts import benchmark_textbooks as benchmark


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    root = tmp_path / 'benchmark'; sources = root / 'sources'; sources.mkdir(parents=True)
    source = sources / 'unseen.pdf'
    pdf = canvas.Canvas(str(source), invariant=1)
    for n in range(4):
        pdf.drawString(42, 780, f'Original textbook page {n + 1}')
        pdf.drawString(42, 740, 'A unit test paragraph with enough extractable words and a source reference.')
        pdf.showPage()
    pdf.save()
    spec = {'version': 'test', 'page_counts': [2, 4], 'formats': ['text','ocr'], 'scan_dpi': 100,
        'scan_jpeg_quality': 85, 'prompt': 'A shared preference', 'preset': {}, 'sources': [{
            'id': 'unseen', 'domain': 'Test subject', 'title': 'Original test notes', 'author': 'Test author',
            'year': 2026, 'section': 'Example section', 'start_page': 1, 'url': 'https://example.invalid/book',
            'pdf_url': 'https://example.invalid/book.pdf', 'license': 'MIT', 'license_url': 'https://example.invalid/license',
            'license_page': 1, 'sha256': benchmark.digest(source)}]}
    spec_path = tmp_path / 'spec.json'; rubric_path = tmp_path / 'rubric.json'
    benchmark.write_json(spec_path, spec)
    benchmark.write_json(rubric_path, {'anchors': {'unseen': [{'id':'claim','page':1,'claim':'Original note','groups':['note']}]}})
    monkeypatch.setattr(benchmark, 'SPEC', spec_path); monkeypatch.setattr(benchmark, 'RUBRIC', rubric_path)
    return root, source


def test_paired_corpus_preserves_page_map_and_removes_all_text_layers(corpus):
    root, _ = corpus
    data = benchmark.prepare(root)
    assert len(data['cases']) == 4
    for case in data['cases']:
        reader = PdfReader(root / case['input'])
        assert len(reader.pages) == case['pages']
        assert case['original_pages'] == list(range(1, case['pages'] + 1))
        texts = [page.extract_text() or '' for page in reader.pages]
        assert all(texts) if case['format'] == 'text' else not any(texts)
        assert benchmark.digest(root / case['input']) == case['sha256']


def test_changed_source_version_is_rejected_before_preparation(corpus):
    root, source = corpus
    source.write_bytes(source.read_bytes() + b'changed-version')
    with pytest.raises(ValueError, match='fingerprint'): benchmark.prepare(root)


def test_measured_inputs_cannot_be_silently_rebuilt(corpus):
    root, _ = corpus
    benchmark.prepare(root)
    benchmark.write_json(root / 'results.json', {'unseen-02-text': {'status': 'failed'}})
    with pytest.raises(ValueError, match='measured'): benchmark.prepare(root)


def test_overlap_and_keyword_metrics_do_not_claim_semantic_correctness():
    assert benchmark.word_f1('A causes B', 'B causes A') == 1
    assert benchmark.word_f1('Alpha beta gamma', 'Alpha missing') < 1
    anchors = [{'id': 'direction', 'page': 1, 'claim': 'A causes B', 'groups': ['A', 'B']}]
    assert benchmark.anchor_mentions(anchors, 'B causes A')[0]['mentioned']
    assert not benchmark.anchor_mentions(anchors, 'A only')[0]['mentioned']


def test_report_keeps_failed_and_unexecuted_cases_visible(corpus):
    root, _ = corpus
    data = benchmark.prepare(root); case = data['cases'][0]
    benchmark.write_json(root / 'results.json', {case['id']: {**case, 'status': 'failed',
        'error': 'Test failure', 'generation_seconds': 12.5}})
    result = benchmark.report(root)
    assert result['expected'] == 4 and result['executed'] == 1 and result['completed'] == 0
    assert not result['complete_run']
    text = (root / 'REPORT.md').read_text(encoding='utf-8')
    assert 'Test failure' in text and '待运行' in text and '未复核' in text


def test_completion_does_not_bypass_media_audit_and_recovery_keeps_first_failure(corpus):
    root, _ = corpus
    data = benchmark.prepare(root); case = data['cases'][0]
    row = {**case, 'status': 'failed', 'error': 'Export failed', 'generation_seconds': 12}
    benchmark.write_json(root / 'results.json', {case['id']: row})
    benchmark.write_json(root / 'recovery-results.json', {case['id']: {'status': 'completed',
        'export_seconds': 4, 'engineering_passed': True, 'notes': 'Re-exported retained course'}})
    overview = benchmark.report(root)
    assert overview['completed'] == 0 and overview['failed'] == 1 and overview['recovery_completed'] == 1
    assert not benchmark.engineering_ok({**row, 'status': 'completed'})
    assert benchmark.read_json(root / 'results.json')[case['id']]['status'] == 'failed'


def test_grouped_latency_includes_failed_attempts_and_unknown_tokens_remain_unknown():
    rows = [{'pages': 2, 'status': 'failed', 'generation_seconds': 10},
            {'pages': 2, 'status': 'completed', 'generation_seconds': 30}]
    group = benchmark.grouped_metrics(rows, 'pages')['2']
    assert group['median_attempt_seconds'] == 20 and group['median_completed_seconds'] == 30
    assert group['median_input_tokens'] is None and group['median_generated_tokens'] is None


def test_review_bundle_whitelists_media_and_excludes_model_logs_databases_and_env(corpus):
    root, _ = corpus
    data = benchmark.prepare(root); case = data['cases'][0]
    folder = root / 'tasks/jobs/test-job'; folder.mkdir(parents=True)
    for name in ('lesson.pptx','lesson.mp4','model-calls.json'):
        (folder / name).write_bytes(b'benchmark test artifact')
    (root / '.env').write_text('private fixture', encoding='utf-8')
    (root / 'tasks/jobs.sqlite3').write_bytes(b'private fixture')
    benchmark.write_json(root / 'results.json', {case['id']: {**case, 'job_id':'test-job',
        'status':'completed','generation_seconds':20}})
    benchmark.package(root, include_media=True)
    with ZipFile(root / 'benchmark-full-review.zip') as archive:
        names = archive.namelist()
        assert 'tasks/jobs/test-job/lesson.pptx' in names and 'tasks/jobs/test-job/lesson.mp4' in names
        assert not any('.env' in name or 'sqlite' in name or 'model-calls' in name for name in names)
        assert len([name for name in names if name.startswith('inputs/') and name.endswith('.pdf')]) == 4
