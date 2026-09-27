"""提取普通 PDF 和扫描页的文字，并保留原始页码。"""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from zhijiang.models import PageText, SourceDocument


class PDFError(ValueError):
    """PDF 无法作为首版文本资料处理。"""


def validate_pdf(data: bytes) -> None:
    """上传时只做快速校验；耗时 OCR 在后台任务中执行。"""
    if not data.startswith(b"%PDF-"):
        raise PDFError("文件不是有效的 PDF。")
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise PDFError("暂不支持加密 PDF。")
        if not reader.pages:
            raise PDFError("PDF 没有页面。")
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError("PDF 损坏或无法读取。") from exc


def read_pdf(data: bytes, filename: str, ocr_engine=None) -> SourceDocument:
    """无可用文字的页面逐页 OCR。"""
    validate_pdf(data)
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        pages = []
        rendered = None
        for index, page in enumerate(reader.pages, start=1):
            try:
                raw = page.extract_text() or ""
            except Exception:
                raw = ""
            text = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
            used_ocr = False
            if len("".join(text.split())) < 80:
                if rendered is None:
                    import pypdfium2
                    rendered = pypdfium2.PdfDocument(data)
                if ocr_engine is None:
                    from rapidocr import RapidOCR
                    ocr_engine = RapidOCR()
                image = rendered[index - 1].render(scale=2.5).to_pil()
                buffer = BytesIO()
                image.save(buffer, format="PNG")
                result = ocr_engine(buffer.getvalue())
                recognized = "\n".join(item.strip() for item in (result.txts or ()) if item.strip())
                if len("".join(recognized.split())) > len("".join(text.split())):
                    text = recognized
                    used_ocr = True
            if text:
                pages.append(PageText(page=index, text=text, ocr=used_ocr))
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError("PDF 文字提取或 OCR 失败，请检查文件和 OCR 依赖。") from exc
    if not pages:
        raise PDFError("扫描件未识别到文字；请检查扫描清晰度。")
    return SourceDocument(filename=filename, pages=pages)
