import base64
import json

import httpx
import pytest

from zhijiang.agents import OllamaClient, OpenAICompatibleClient
from zhijiang.math_sources import read_math_pdf
from zhijiang.models import PageText


@pytest.mark.parametrize('provider',['ollama','openai'])
def test_visual_reading_sends_actual_page_and_keeps_native_text(monkeypatch,tmp_path,provider):
    import zhijiang.math_sources as sources
    monkeypatch.setattr(sources,'page_png',lambda data,page:b'original-page-image')
    requests=[]
    def handler(request):
        if request.url.path=='/api/show':return httpx.Response(200,json={'capabilities':['vision']})
        body=json.loads(request.content);requests.append(body)
        user=body['messages'][1]
        if provider=='ollama':assert base64.b64decode(user['images'][0])==b'original-page-image'
        else:assert user['content'][1]['image_url']['url'].endswith(base64.b64encode(b'original-page-image').decode())
        if len(requests)==1:
            result={'text':'A test function is f(x)=exp(x), centred at a=0.',
                'core_ideas':['从原页读取函数与展开中心。'],'uncertain':[]}
        else:result={'approved':True,'issues':[]}
        content=json.dumps(result)
        return httpx.Response(200,json=({'message':{'content':content}} if provider=='ollama'
            else {'choices':[{'message':{'content':content}}]}))
    from io import BytesIO
    from reportlab.pdfgen.canvas import Canvas
    output=BytesIO();canvas=Canvas(output);canvas.drawString(40,700,'Native source text without the formula.');canvas.save()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client=(OllamaClient('http://localhost:11434','vision-test',http_client,prefer_json=True)
            if provider=='ollama' else OpenAICompatibleClient('https://model.invalid/v1','secret','vision-test',http_client))
        document=read_math_pdf(client,output.getvalue(),'source.pdf',cache_dir=tmp_path)
        assert document.pages[0].math_reading['native_text'].startswith('Native source')
        assert 'exp(x)' in document.pages[0].text
        assert document.pages[0].ocr is True
        read_math_pdf(client,output.getvalue(),'source.pdf',cache_dir=tmp_path)
        assert len(requests)==2


def test_page_text_backward_compatible():
    assert PageText(page=1,text='Old task source').math_reading is None


def test_english_source_cannot_be_replaced_by_a_translated_summary():
    from zhijiang.math_sources import native_prose_coverage
    prose=' '.join('word'+chr(97+i//26)+chr(97+i%26) for i in range(80))
    assert native_prose_coverage(prose,'这是一个中文摘要，不能当作英文原文。')==0
    assert native_prose_coverage(prose,prose)==1


@pytest.mark.parametrize('text_correction',[True,False])
def test_source_review_can_clear_a_hallucinated_diagram(monkeypatch,text_correction):
    import zhijiang.math_sources as sources
    monkeypatch.setattr(sources,'page_png',lambda data,page:b'page-with-no-diagram')
    class Client:
        model='mock';calls=0
        def generate(self,schema,*args,**kwargs):
            self.calls+=1
            if schema is sources.MathSourceReading:return schema(text='The page defines an exponential function and refers to a figure on another page.',
                diagram_description='An invented graph is on this page.',core_ideas=['指数函数的定义。'])
            if self.calls==2:return schema(approved=False,issues=['The figure is referenced, not present.'],
                corrected_text='The page defines an exponential function and refers to a figure on another page.' if text_correction else '',corrected_diagram_description='')
            assert 'An invented graph' not in args[1]
            return schema(approved=True,issues=[])
    from io import BytesIO
    from reportlab.pdfgen.canvas import Canvas
    output=BytesIO();canvas=Canvas(output);canvas.drawString(40,700,'This page has no diagram.');canvas.save()
    document=sources.read_math_pdf(Client(),output.getvalue(),'unseen.pdf')
    assert not document.pages[0].math_reading['reading']['diagram_description']


def test_blank_math_pdf_is_rejected_before_sending_to_model():
    from zhijiang.math_sources import read_math_pdf
    from zhijiang.pdf import PDFError
    from pypdf import PdfWriter
    from io import BytesIO
    writer=PdfWriter();writer.add_blank_page(600,800);output=BytesIO();writer.write(output)
    class NoCalls:
        def generate(self,*args,**kwargs):raise AssertionError('Blank source must not call a model')
    with pytest.raises(PDFError,match='空白'):read_math_pdf(NoCalls(),output.getvalue(),'blank.pdf')
