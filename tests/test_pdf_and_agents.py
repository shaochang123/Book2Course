from io import BytesIO

import httpx
import pytest
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter

from zhijiang.agents import (
    AIAgents,
    DemoAgents,
    GenerationError,
    KnowledgeSelection,
    KnowledgeSelectionPoint,
    OpenAICompatibleClient,
    ScriptDraft,
    ScriptDraftSegment,
    source_candidates,
    validate_evidence,
    validate_lesson,
)
from zhijiang.models import CourseOutline, Evidence, Mode, PageText, ReviewResult, SourceDocument, VoiceMode
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


def test_scanned_pdf_uses_local_ocr_and_keeps_page_number():
    image = Image.new("RGB", (1500, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    for index in range(4):
        draw.text((70, 75 + index * 170),
                  f"Binary search requires sorted input. Compare the middle value. Step {index + 1}.",
                  font=font, fill="black")
    output = BytesIO()
    image.save(output, format="PDF", resolution=150)
    document = read_pdf(output.getvalue(), "scanned.pdf")
    assert document.pages[0].page == 1
    assert document.pages[0].ocr
    assert "Binary search" in document.pages[0].text
    assert all(point.evidence.ocr for point in DemoAgents().extract_knowledge(document).points)


def test_more_than_100_pages_are_accepted(sample_pdf):
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(sample_pdf))
    writer = PdfWriter()
    for _ in range(101):
        writer.add_page(reader.pages[0])
    output = BytesIO()
    writer.write(output)
    document = read_pdf(output.getvalue(), "long.pdf")
    assert document.pages[-1].page == 101
    assert source_candidates(document)[-1]["page"] == 101
    agents = DemoAgents()
    bundle = agents.extract_knowledge(document)
    lesson = agents.script(bundle, agents.plan(bundle), VoiceMode.SYSTEM)
    assert len(lesson.segments) > 6


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


def test_ai_source_selection_uses_exact_pdf_text_and_rejects_unknown_ids(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    candidates = source_candidates(document)
    assert len(candidates) >= 3
    for item in candidates:
        validate_evidence(document, Evidence(page=item["page"], quote=item["quote"]))

    class BadClient:
        calls = 0

        def generate(self, schema, instruction, material):
            self.calls += 1
            return KnowledgeSelection(points=[
                KnowledgeSelectionPoint(
                    title=f"知识点 {index}", kind="concept", explanation="用于测试错误编号。",
                    source_id=900 + index,
                ) for index in range(3)
            ])

    client = BadClient()
    with pytest.raises(GenerationError, match="片段编号"):
        AIAgents(client).extract_knowledge(document)
    assert client.calls == 2


def test_ai_selection_reaches_pages_after_twelve():
    document = SourceDocument(filename="long.pdf", pages=[
        PageText(page=page, text="\n".join(
            f"第 {page} 页知识点 {line}：二分查找需要有序序列，并通过比较中间元素逐步缩小查找范围。"
            for line in range(6)))
        for page in range(1, 14)
    ])

    class SelectionClient:
        calls = 0

        def generate(self, schema, instruction, material):
            import json
            self.calls += 1
            sources = json.loads(material)["sources"]
            return KnowledgeSelection(points=[
                KnowledgeSelectionPoint(title=f"知识点 {item['id']}", kind="concept",
                                        explanation="讲解有序序列和中间元素。", source_id=item["id"])
                for item in sources[:3]
            ])

    client = SelectionClient()
    bundle = AIAgents(client).extract_knowledge(document)
    assert client.calls == 2
    assert {point.evidence.page for point in bundle.points} >= {1, 9}
    assert source_candidates(document)[-1]["page"] == 13


def test_long_ai_course_is_batched_without_segment_cap():
    import json
    document = SourceDocument(filename="book.pdf", pages=[
        PageText(page=page, text="\n".join(
            f"第 {page} 页知识点 {line}：在有序数据中比较中间元素，缩小范围，直到找到目标或范围为空。"
            for line in range(6)))
        for page in range(1, 51)
    ])

    class BatchClient:
        def generate(self, schema, instruction, material):
            data = json.loads(material)
            if schema is KnowledgeSelection:
                return KnowledgeSelection(points=[
                    KnowledgeSelectionPoint(title=f"知识点 {item['id']}", kind="concept",
                                            explanation="说明输入条件和比较步骤。", source_id=item["id"])
                    for item in data["sources"][:3]
                ])
            if schema is CourseOutline:
                return CourseOutline(title="完整课程", objective="理解全部相关知识和典型步骤。",
                                     point_titles=[point["title"] for point in data["points"]])
            if schema is ScriptDraft:
                return ScriptDraft(segments=[
                    ScriptDraftSegment(source_id=point["source_id"], title=point["title"],
                                       kind="concept", narration="结合原文核对条件，并用具体例子逐步解释。" * 10,
                                       bullets=["条件", "例子"])
                    for point in data["points"][:3]
                ])
            return ReviewResult(approved=True)

    agents = AIAgents(BatchClient())
    bundle = agents.extract_knowledge(document)
    lesson = agents.script(bundle, agents.plan(bundle), VoiceMode.SYSTEM)
    validate_lesson(document, lesson)
    agents.review(lesson)
    assert len(lesson.segments) == 12
    assert lesson.segments[-1].evidence.page > 40


def test_ai_agents_use_four_stages_and_validate_citations(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    demo = DemoAgents()
    bundle = demo.extract_knowledge(document)
    candidates = source_candidates(document)
    selection = KnowledgeSelection(points=[
        KnowledgeSelectionPoint(
            title=point.title, kind=point.kind, explanation=point.explanation,
            source_id=next(
                item["id"] for item in candidates
                if item["page"] == point.evidence.page and item["quote"] == point.evidence.quote
            ),
        ) for point in bundle.points
    ])
    outline = demo.plan(bundle)
    lesson = demo.script(bundle, outline, VoiceMode.SYSTEM)
    lesson.mode = Mode.AI
    lesson.segments = lesson.segments[:3]
    for segment in lesson.segments:
        while len(segment.narration) < 180:
            segment.narration += "结合原文中的条件，逐步检查当前范围与比较结果。"
    script_draft = ScriptDraft(segments=[
        ScriptDraftSegment(
            source_id=index, title=segment.title, kind=segment.kind,
            narration=segment.narration, bullets=segment.bullets,
        ) for index, segment in enumerate(lesson.segments, start=1)
    ])
    results = [selection, outline, script_draft, ReviewResult(approved=True)]
    received = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        received.append(payload)
        result = results.pop(0)
        return httpx.Response(200, json={"choices": [{"message": {"content": result.model_dump_json()}}]})

    transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport) as http_client:
        agents = AIAgents(OpenAICompatibleClient("https://example.invalid/v1", "fake", "fake", http_client),
                          "面向初学者，多举例子。")
        knowledge = agents.extract_knowledge(document)
        plan = agents.plan(knowledge)
        scripted = agents.script(knowledge, plan, VoiceMode.SYSTEM)
        agents.review(scripted)
    validate_lesson(document, scripted)
    assert scripted.mode == Mode.AI
    assert [segment.evidence for segment in scripted.segments] == [
        point.evidence for point in bundle.points[:3]
    ]
    assert len(received) == 4
    assert all("<source_data>" in item["messages"][1]["content"] for item in received)
    assert "面向初学者" in received[1]["messages"][0]["content"]
    assert "面向初学者" in received[2]["messages"][0]["content"]


def test_script_rejects_unknown_source_ids(sample_pdf):
    document = read_pdf(sample_pdf, "original.pdf")
    bundle = DemoAgents().extract_knowledge(document)
    outline = DemoAgents().plan(bundle)

    class BadScriptClient:
        calls = 0

        def generate(self, schema, instruction, material):
            self.calls += 1
            return ScriptDraft(segments=[
                ScriptDraftSegment(
                    source_id=900 + index, title=f"片段 {index}", kind="concept",
                    narration="学习这一知识点时，需要结合原文和例子逐步理解。" * 9,
                    bullets=["要点"],
                ) for index in range(3)
            ])

    client = BadScriptClient()
    with pytest.raises(GenerationError, match="知识点编号"):
        AIAgents(client).script(bundle, outline, VoiceMode.SYSTEM)
    assert client.calls == 2


def test_model_failure_does_not_expose_upstream_body():
    transport = httpx.MockTransport(lambda _: httpx.Response(500, text="secret upstream body"))
    with httpx.Client(transport=transport) as http_client:
        client = OpenAICompatibleClient("https://example.invalid/v1", "fake", "fake", http_client)
        with pytest.raises(GenerationError, match="模型服务不可用") as error:
            client.generate(ReviewResult, "review", "source")
    assert "secret upstream body" not in str(error.value)
