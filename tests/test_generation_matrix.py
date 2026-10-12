"""File acceptance, provider switching, audio recovery and duration boundaries."""
from io import BytesIO
import json
import subprocess
import math
from array import array
import wave

import imageio_ffmpeg
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
import pytest

from zhijiang.config import Settings
from zhijiang.main import create_app
from zhijiang.speech_cache import synthesize_cached


class QueuedRunner:
    def __init__(self):self.ids=[]
    def submit(self, job_id):self.ids.append(job_id)
    def shutdown(self): pass


@pytest.mark.parametrize('filename,mime,accepted', [
    ('lesson.pdf','application/pdf',True), ('中文教材.PDF','application/octet-stream',True),
    ('lesson.pdf','text/plain',True), ('lesson.docx','application/pdf',False),
    ('lesson.pptx','application/pdf',False), ('lesson.txt','text/plain',False),
    ('lesson.png','image/png',False), ('lesson.pdf.exe','application/pdf',False)])
def test_supported_file_matrix(tmp_path,sample_pdf,filename,mime,accepted):
    app=create_app(Settings(data_dir=tmp_path/'data'),QueuedRunner())
    with TestClient(app) as client:
        r=client.post('/api/jobs',files={'file':(filename,sample_pdf,mime)},
                      data={'mode':'demo','rights_confirmed':'true'})
        assert r.status_code==(202 if accepted else 400),r.text
        assert len(app.state.runner.ids)==(1 if accepted else 0)


@pytest.mark.parametrize('kind',['disguised','encrypted','empty','oversized'])
def test_unusable_pdf_never_enters_generation(tmp_path,sample_pdf,kind):
    payload=sample_pdf;limit=200*1024*1024
    if kind=='disguised':payload=b'<html>not a PDF</html>'
    if kind in {'encrypted','empty'}:
        writer=PdfWriter()
        if kind=='encrypted':writer.add_blank_page(width=200,height=200);writer.encrypt('test-password')
        buffer=BytesIO();writer.write(buffer);payload=buffer.getvalue()
    if kind=='oversized':limit=len(payload)-1
    app=create_app(Settings(data_dir=tmp_path/'data',max_pdf_bytes=limit),QueuedRunner())
    with TestClient(app) as client:
        r=client.post('/api/jobs',files={'file':('lesson.pdf',payload)},
                      data={'mode':'demo','rights_confirmed':'true'})
        assert r.status_code==(413 if kind=='oversized' else 400)
        assert not app.state.runner.ids


def test_switch_provider_requires_matching_endpoint_and_model(tmp_path,sample_pdf):
    app=create_app(Settings(data_dir=tmp_path/'data',llm_provider='ollama',
                           llm_base_url='http://localhost:11434',llm_model='local-model'),QueuedRunner())
    with TestClient(app) as client:
        for values in ({},{'llm_base_url':'https://example.invalid/v1'}, {'llm_model':'remote-model'}):
            r=client.post('/api/jobs',files={'file':('lesson.pdf',sample_pdf)},
                          data={'mode':'ai','rights_confirmed':'true','remote_consent':'true',
                                'llm_provider':'openai','llm_api_key':'test-key',**values})
            assert r.status_code==400
            assert '切换模型提供方' in r.json()['detail']
        assert not app.state.runner.ids


def test_speech_resume_invalidates_text_voice_and_corrupted_audio(tmp_path):
    class Voice:
        voice='one'
        calls=0
        def synthesize(self,text,output):
            self.calls+=1
            with wave.open(str(output),'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0\0'*2400)
    service=Voice();path=tmp_path/'audio.wav'
    synthesize_cached(service,'原始讲稿',path);synthesize_cached(service,'原始讲稿',path)
    assert service.calls==1
    synthesize_cached(service,'修改讲稿',path);assert service.calls==2
    service.voice='two';synthesize_cached(service,'修改讲稿',path);assert service.calls==3
    path.write_bytes(b'broken');synthesize_cached(service,'修改讲稿',path);assert service.calls==4
    path.with_suffix('.voice.json').write_text('[]')
    synthesize_cached(service,'修改讲稿',path);assert service.calls==5
    assert '讲稿' not in path.with_suffix('.voice.json').read_text()


def test_shared_media_exceeds_four_minutes_and_preserves_final_picture_and_audio(tmp_path):
    from zhijiang.page_media import narrated_pages,clip_duration
    states=[]
    for i,color in enumerate(['#c02f24','#256a39']):
        path=tmp_path/f'frame-{i}.png';Image.new('RGB',(320,180),color).save(path);states.append(path)
    path=tmp_path/'long.wav';seconds=301
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
        # Audible tail detects accidental empty/cut audio; this is a test signal.
        tone=array('h',(int(5000*math.sin(2*math.pi*440*i/24000)) for i in range(24000))).tobytes()
        for _ in range(seconds):w.writeframes(tone)
    output=tmp_path/'long.mp4';narrated_pages(states,path,output)
    assert clip_duration(output)==pytest.approx(seconds,abs=.15)
    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss','300','-i',str(output),
                           '-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True)
    im=Image.frombytes('RGB',(320,180),result.stdout)
    assert im.getpixel((10,10))[1]>im.getpixel((10,10))[0]
    audio=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss','300','-i',str(output),
                          '-t','0.5','-vn','-f','s16le','-ac','1','-ar','24000','-'],capture_output=True,check=True)
    assert len(audio.stdout)>=20000 and any(audio.stdout)


@pytest.mark.parametrize('status',[400,401,403,404,429,503])
def test_model_http_error_is_actionable_without_exposing_upstream_body(status):
    import httpx
    from zhijiang.agents import OpenAICompatibleClient,GenerationError
    from pydantic import BaseModel
    class Reply(BaseModel):value:str
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(status,text='private source and credential'))) as http:
        client=OpenAICompatibleClient('https://example.invalid/v1','test-key','remote-model',http)
        with pytest.raises(GenerationError,match=f'HTTP {status}') as caught:client.generate(Reply,'task','input')
        assert 'private source' not in str(caught.value)
