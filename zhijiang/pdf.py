"""提取普通 PDF 和扫描页的文字，并保留原始页码。"""

from __future__ import annotations

from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
from typing import Callable

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


def read_pdf(data: bytes, filename: str, ocr_engine=None, *,
             progress: Callable[[int, int, str], None] | None = None,
             cache_dir: Path | None = None) -> SourceDocument:
    """无可用文字的页面逐页 OCR。"""
    validate_pdf(data)
    fingerprint = 'pdf-pages-v1:' + hashlib.sha256(data).hexdigest()
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
    rendered = None
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        pages = []
        total = len(reader.pages)
        for index, page in enumerate(reader.pages, start=1):
            cache_path = cache_dir / f'page-{index:05d}.json' if cache_dir else None
            cached = None
            if cache_path:
                try:
                    saved = json.loads(cache_path.read_text(encoding='utf-8'))
                    if (isinstance(saved, dict) and saved.get('fingerprint') == fingerprint and saved.get('page') == index
                            and isinstance(saved.get('text'), str) and type(saved.get('ocr')) is bool):
                        cached = saved
                except (OSError, ValueError):
                    pass
            if cached is not None:
                if cached['text']:
                    pages.append(PageText(page=index, text=cached['text'], ocr=cached['ocr']))
                if progress:
                    progress(index, total, '复用已解析页面')
                continue
            if progress:
                progress(index - 1, total, f'第 {index} 页提取文字')
            try:
                raw = page.extract_text() or ""
            except Exception:
                raw = ""
            text = "\n".join(line.strip() for line in raw.splitlines() if line.strip())
            used_ocr = False
            if len("".join(text.split())) < 80:
                if progress:
                    progress(index - 1, total, f'第 {index} 页本地 OCR')
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
            if cache_path:
                temporary = cache_path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'fingerprint': fingerprint, 'page': index,
                    'text': text, 'ocr': used_ocr}, ensure_ascii=False), encoding='utf-8')
                os.replace(temporary, cache_path)
            if text:
                pages.append(PageText(page=index, text=text, ocr=used_ocr))
            if progress:
                progress(index, total, '本地 OCR 完成' if used_ocr else '页面解析完成')
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError("PDF 文字提取或 OCR 失败，请检查文件和 OCR 依赖。") from exc
    finally:
        if rendered is not None:
            rendered.close()
    if not pages:
        raise PDFError("扫描件未识别到文字；请检查扫描清晰度。")
    return SourceDocument(filename=filename, pages=pages)
