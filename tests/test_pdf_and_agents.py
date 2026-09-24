from io import BytesIO

import httpx
import pytest
from pypdf import PdfWriter

from zhijiang.agents import (
    AIAgents,
    DemoAgents,
    GenerationError,
    OpenAICompatibleClient,
    validate_lesson,
)
from zhijiang.models import Mode, ReviewResult, VoiceMode
from zhijiang.pdf import PDFError, read_pdf


def test_pdf_keeps_original_page_numbers(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    assert [page.page for page in document.pages] == [1, 2]
    assert "二分查找" in document.pages[0].text
    assert "O(log n)" in document.pages[1].text


def test_invalid_and_scanned_like_pdf_are_rejected():
    with pytest.raises(PDFError, match="有效的 PDF"):
        read_pdf(b"not-a-pdf", "wrong.pdf")
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buffer = BytesIO()
    writer.write(buffer)
    with pytest.raises(PDFError, match="扫描件"):
        read_pdf(buffer.getvalue(), "blank.pdf")


def test_demo_workflow_is_grounded_and_labeled(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    agents = DemoAgents()
    points = agents.extract_knowledge(document)
    outline = agents.plan(points)
    lesson = agents.script(points, outline, VoiceMode.SYSTEM)
    validate_lesson(document, lesson)
    assert lesson.mode == Mode.DEMO
    assert "确定性规则" in lesson.notice
    assert len(lesson.segments) == 6
    assert {segment.evidence.page for segment in lesson.segments} == {1, 2}
    assert {segment.kind for segment in lesson.segments} >= {"concept", "process", "formula"}


def test_fabricated_source_quote_is_rejected(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    agents = DemoAgents()
    bundle = agents.extract_knowledge(document)
    lesson = agents.script(bundle, agents.plan(bundle), VoiceMode.SYSTEM)
    lesson.segments[0].evidence.quote = "原文没有的这段伪造引文内容"
    with pytest.raises(GenerationError, match="引用无法"):
        validate_lesson(document, lesson)


def test_ai_agents_use_four_stages_and_validate_citations(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    demo = DemoAgents()
    bundle = demo.extract_knowledge(document)
    outline = demo.plan(bundle)
    lesson = demo.script(bundle, outline, VoiceMode.SYSTEM)
    lesson.mode = Mode.AI
    lesson.segments = lesson.segments[:3]
    for segment in lesson.segments:
        while len(segment.narration) < 180:
            segment.narration += "结合原文中的条件，逐步检查当前范围与比较结果。"
    results = [bundle, outline, lesson, ReviewResult(approved=True)]
    received = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        received.append(payload)
        result = results.pop(0)
        return httpx.Response(200, json={"choices": [{"message": {"content": result.model_dump_json()}}]})

    transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport) as http_client:
        agents = AIAgents(OpenAICompatibleClient("https://example.invalid/v1", "fake", "fake", http_client))
        knowledge = agents.extract_knowledge(document)
        plan = agents.plan(knowledge)
        scripted = agents.script(knowledge, plan, VoiceMode.SYSTEM)
        agents.review(scripted)
    validate_lesson(document, scripted)
    assert scripted.mode == Mode.AI
    assert len(received) == 4
    assert all("<source_data>" in item["messages"][1]["content"] for item in received)


def test_model_failure_does_not_expose_upstream_body():
    transport = httpx.MockTransport(lambda _: httpx.Response(500, text="secret upstream body"))
    with httpx.Client(transport=transport) as http_client:
        client = OpenAICompatibleClient("https://example.invalid/v1", "fake", "fake", http_client)
        with pytest.raises(GenerationError, match="模型服务不可用") as error:
            client.generate(ReviewResult, "review", "source")
    assert "secret upstream body" not in str(error.value)
