"""Do not let plentiful prose hide unreadable mathematical glyphs."""
from io import BytesIO

import pytest
from pypdf import PdfWriter


def one_page():
    writer=PdfWriter(); writer.add_blank_page(width=595,height=842)
    output=BytesIO(); writer.write(output)
    return output.getvalue()


def test_control_and_replacement_glyphs_need_recovery_but_whitespace_does_not():
    from zhijiang.pdf import unusable_glyphs
    assert unusable_glyphs('x\x00a\x14b\ufffd') == 3
    assert unusable_glyphs('x − a ≤ b\n公式\t说明\r') == 0


def test_damaged_formula_text_uses_a_second_native_decoder(monkeypatch,tmp_path):
    from zhijiang import pdf
    import pypdfium2
    original='A complete paragraph about the conditions for a mathematical theorem. '*3+' f(b)\x00f(a)'
    repaired=original.replace('\x00','−')
    monkeypatch.setattr(pdf,'extract_page_text',lambda _:original)
    class Text:
        def get_text_range(self):return repaired
        def close(self):pass
    class Page:
        def get_textpage(self):return Text()
        def close(self):pass
    class Document:
        def __init__(self,*_):pass
        def __getitem__(self,_):return Page()
        def close(self):pass
    monkeypatch.setattr(pypdfium2,'PdfDocument',Document)
    def no_ocr(_):raise AssertionError('Clean native recovery should not use OCR')
    document=pdf.read_pdf(one_page(),'unseen.pdf',ocr_engine=no_ocr,cache_dir=tmp_path)
    assert 'f(b)−f(a)' in document.pages[0].text
    assert not document.pages[0].ocr
    assert pdf.read_pdf(one_page(),'unseen.pdf',ocr_engine=no_ocr,cache_dir=tmp_path)==document


@pytest.mark.parametrize('better', [True,False])
def test_broken_native_glyphs_trigger_ocr_even_with_long_prose(monkeypatch,better):
    from zhijiang import pdf
    from PIL import Image
    import pypdfium2
    damaged=('A complete paragraph about a source condition. '*4)+' a\x00b'
    repaired='Correct mathematical condition with a minus sign: a−b.'
    monkeypatch.setattr(pdf,'extract_page_text',lambda _:damaged)
    class Text:
        def get_text_range(self):return damaged
        def close(self):pass
    class Bitmap:
        def to_pil(self):return Image.new('RGB',(100,100),'white')
        def close(self):pass
    class Page:
        def get_textpage(self):return Text()
        def render(self,**_):return Bitmap()
        def close(self):pass
    class Document:
        def __init__(self,*_):pass
        def __getitem__(self,_):return Page()
        def close(self):pass
    monkeypatch.setattr(pypdfium2,'PdfDocument',Document)
    calls=[]
    def ocr(_):
        calls.append(1)
        from types import SimpleNamespace
        return SimpleNamespace(txts=[repaired if better else damaged])
    result=pdf.read_pdf(one_page(),'source.pdf',ocr_engine=ocr)
    assert calls==[1]
    assert result.pages[0].ocr==better
    assert result.pages[0].text==(repaired if better else damaged)
