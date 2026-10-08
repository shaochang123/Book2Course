"""Check actual PDF text, pagination and navigation rather than Markdown snapshots."""

from pypdf import PdfReader
import pytest

from scripts.build_documents import export_pdf


def test_manual_pdf_preserves_chinese_tables_code_and_navigation(tmp_path):
    source = tmp_path / "guide.md"
    source.write_text(
        "# 项目指南\n\n## 1. 上传资料\n\n"
        "| 输入 | 状态 |\n| --- | --- |\n| 授权教材 | 待审阅 |\n\n"
        "```powershell\npython -m uvicorn zhijiang.main:app\n```\n\n"
        "## 2. 核对来源\n\nA < B & C，不应变成 PDF 标记。\n", encoding="utf-8")
    output = tmp_path / "guide.pdf"
    export_pdf(source, output)
    reader = PdfReader(output)
    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in ["项目指南", "授权教材", "待审阅", "python -m uvicorn", "A < B & C"]:
        assert expected in text
    assert len(reader.pages) >= 3
    assert [entry.title for entry in reader.outline] == ["1. 上传资料", "2. 核对来源"]
    assert "Placeholder for table of contents" not in text


def test_long_table_repeats_header_and_does_not_lose_last_row(tmp_path):
    source = tmp_path / "table.md"
    rows = "\n".join(f"| 来源第 {i} 项 | 已核对第 {i} 页 |" for i in range(100))
    source.write_text("# 长表指南\n\n## 来源\n\n| 来源名称 | 核对结果 |\n| --- | --- |\n" + rows,
                      encoding="utf-8")
    output = tmp_path / "table.pdf"
    export_pdf(source, output)
    reader = PdfReader(output)
    pages = [page.extract_text() for page in reader.pages]
    table_pages = [page for page in pages if "来源第" in page]
    assert len(table_pages) >= 2
    assert all("来源名称" in page and "核对结果" in page for page in table_pages)
    assert "来源第 99 项" in "\n".join(pages)


def test_invalid_markdown_table_fails_instead_of_exporting_missing_cells(tmp_path):
    source = tmp_path / "bad.md"
    source.write_text("# 指南\n\n| 输入 | 输出 |\n| --- | --- |\n| 只有一列 |", encoding="utf-8")
    with pytest.raises(ValueError, match="列数不一致"):
        export_pdf(source, tmp_path / "bad.pdf")
