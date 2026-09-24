"""解析文本型 PDF，并保留可核验的原始页码。"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from zhijiang.models import PageText, SourceDocument


class PDFError(ValueError):
    """PDF 无法作为首版文本资料处理。"""


def read_pdf(data: bytes, filename: str, max_pages: int = 100) -> SourceDocument:
    if not data.startswith(b"%PDF-"):
        raise PDFError("文件不是有效的 PDF。")
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise PDFError("暂不支持加密 PDF。")
        if len(reader.pages) > max_pages:
            raise PDFError(f"PDF 超过 {max_pages} 页的首版上限。")
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            text = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
            if text:
                pages.append(PageText(page=index, text=text))
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError("PDF 损坏或无法提取文本。") from exc
    if not pages:
        raise PDFError("未提取到文字；扫描件暂不支持 OCR。")
    return SourceDocument(filename=filename, pages=pages)
