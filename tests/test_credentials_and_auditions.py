import hashlib
import json
import sys
import wave

from fastapi.testclient import TestClient
import pytest

from zhijiang.config import Settings
from zhijiang.main import create_app


class Queue:
    def submit(self, job_id):pass
    def shutdown(self):pass


@pytest.mark.skipif(sys.platform!='win32',reason='Windows user-bound encryption')
def test_credential_survives_restart_encrypted_and_bound_to_destination(tmp_path):
    from zhijiang.credentials import LocalCredentials
    first=LocalCredentials(tmp_path)
    key='test-only-not-an-api-credential'
    first.save('llm','openai','https://example.invalid/v1/',key)
    assert key.encode() not in first.path.read_bytes()
    second=LocalCredentials(tmp_path)
    assert second.get('llm','openai','https://example.invalid/v1')==key
    assert second.get('llm','openai','https://other.invalid/v1') is None
    assert second.get('tts','openai','https://example.invalid/v1') is None
    assert second.get('llm','ollama','https://example.invalid/v1') is None
    second.remove('llm','openai','https://example.invalid/v1')
    assert LocalCredentials(tmp_path).get('llm','openai','https://example.invalid/v1') is None


@pytest.mark.skipif(sys.platform!='win32',reason='Windows user-bound encryption')
def test_saved_key_used_after_refresh_without_being_returned_or_put_in_job_db(tmp_path,sample_pdf):
    settings=Settings(data_dir=tmp_path/'data')
    key='test-only-api-placeholder'
    profile={'kind':'llm','provider':'openai','base_url':'https://example.invalid/v1'}
    with TestClient(create_app(settings,Queue())) as client:
        r=client.post('/api/credentials',json={**profile,'api_key':key})
        assert r.status_code==200,r.text
        assert key not in r.text
    app=create_app(settings,Queue())
    with TestClient(app) as client:
        r=client.get('/api/credentials/status',params=profile)
        assert r.json()['saved'] and key not in r.text
        r=client.post('/api/jobs',files={'file':('source.pdf',sample_pdf)},data={
            'rights_confirmed':'true','remote_consent':'true','mode':'ai',
            'llm_provider':'openai','llm_base_url':profile['base_url'],'llm_model':'mock-model'})
        assert r.status_code==202,r.text
        assert app.state.store.get_options(r.json()['id']).api_key==key
        assert key not in r.text
        assert key.encode() not in app.state.store.db_path.read_bytes()
        other=client.post('/api/jobs',files={'file':('source.pdf',sample_pdf)},data={
            'rights_confirmed':'true','remote_consent':'true','mode':'ai',
            'llm_provider':'openai','llm_base_url':'https://different.invalid/v1','llm_model':'mock-model'})
        assert other.status_code==400


def test_credential_api_rejects_foreign_origin_and_sensitive_url(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path),Queue())) as client:
        data={'kind':'llm','provider':'openai','base_url':'https://example.invalid/v1','api_key':'test-key'}
        assert client.post('/api/credentials',json=data,headers={'Origin':'https://other.invalid'}).status_code==403
        for url in ['https://user:pass@example.invalid','https://example.invalid?key=private','file:///tmp/key']:
            r=client.post('/api/credentials',json={**data,'base_url':url})
            assert r.status_code==422 and data['api_key'] not in r.text and 'private' not in r.text
        r=client.post('/api/credentials',json={'api_key':data['api_key']})
        assert r.status_code==422 and data['api_key'] not in r.text


def test_environment_keys_follow_endpoint_when_model_or_voice_changes(tmp_path):
    from fastapi import HTTPException
    from zhijiang.main import model_options, speech_options
    settings=Settings(data_dir=tmp_path,llm_provider='openai',llm_base_url='https://example.invalid/v1',
        llm_model='first',llm_api_key='test-placeholder-env-model-key',tts_base_url='https://example.invalid/v1',
        tts_model='first-voice-model',tts_voice='first-voice',tts_api_key='test-placeholder-env-voice-key')
    assert model_options(settings,'openai',settings.llm_base_url,'second','','').api_key==settings.llm_api_key
    assert speech_options(settings,settings.tts_base_url,'second-voice-model','second-voice','').api_key==settings.tts_api_key
    with pytest.raises(HTTPException):model_options(settings,'openai','https://other.invalid/v1','second','','')
    with pytest.raises(HTTPException):speech_options(settings,'https://other.invalid/v1','second','second','')


@pytest.mark.skipif(sys.platform!='win32',reason='Windows user-bound encryption')
def test_unwritable_credential_storage_reports_safe_error_without_key(tmp_path,monkeypatch):
    def fail(*args,**kwargs):raise PermissionError('test-placeholder-key-in-unsafe-detail')
    monkeypatch.setattr('zhijiang.credentials.os.replace',fail)
    with TestClient(create_app(Settings(data_dir=tmp_path),Queue())) as client:
        r=client.post('/api/credentials',json={'kind':'llm','provider':'openai',
            'base_url':'https://example.invalid/v1','api_key':'test-placeholder-key-in-unsafe-detail'})
        assert r.status_code==503 and 'test-placeholder-key-in-unsafe-detail' not in r.text
        assert not (tmp_path/'private'/'credentials.pending').exists()


@pytest.mark.skipif(sys.platform!='win32',reason='Windows user-bound encryption')
def test_saved_keys_override_defaults_and_voice_key_survives_failed_job_retry(tmp_path,sample_pdf):
    settings=Settings(data_dir=tmp_path/'data',llm_provider='openai',llm_base_url='https://example.invalid/v1',
        llm_model='mock',llm_api_key='test-placeholder-default-model-key',tts_base_url='https://example.invalid/v1',
        tts_model='mock-voice',tts_voice='voice',tts_api_key='test-placeholder-default-voice-key')
    app=create_app(settings,Queue())
    profile={'provider':'openai','base_url':settings.llm_base_url}
    with TestClient(app) as client:
        assert client.post('/api/credentials',json={**profile,'kind':'llm','api_key':'test-placeholder-saved-model-key'}).status_code==200
        assert client.post('/api/credentials',json={**profile,'kind':'tts','api_key':'test-placeholder-saved-voice-key'}).status_code==200
        r=client.post('/api/jobs',files={'file':('source.pdf',sample_pdf)},data={
            'rights_confirmed':'true','remote_consent':'true','mode':'ai','voice_mode':'ai'})
        assert r.status_code==202,r.text
        job_id=r.json()['id']
        assert app.state.store.get_options(job_id).api_key=='test-placeholder-saved-model-key'
        assert app.state.store.get_speech_options(job_id).api_key=='test-placeholder-saved-voice-key'
        app.state.store.clear_api_key(job_id);app.state.store.fail(job_id,'test failure')
        assert client.post(f'/api/jobs/{job_id}/retry').status_code==202
        assert app.state.store.get_options(job_id).api_key=='test-placeholder-saved-model-key'
        assert app.state.store.get_speech_options(job_id).api_key=='test-placeholder-saved-voice-key'
        assert client.delete('/api/credentials',params={**profile,'kind':'llm'}).status_code==204
        assert not client.get('/api/credentials/status',params={**profile,'kind':'llm'}).json()['saved']


@pytest.mark.skipif(sys.platform!='win32',reason='Windows system speech audition')
def test_system_and_ai_auditions_use_different_files_and_system_cache(tmp_path,monkeypatch):
    calls=[]
    def speak(self,text,path):
        calls.append((self.voice_name,text))
        with wave.open(str(path),'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0\x01'*12000)
    monkeypatch.setattr('zhijiang.speech.SystemSpeech.synthesize',speak)
    folder=tmp_path/'voice-preview';folder.mkdir()
    path=folder/'preview.wav'
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0\x02'*12000)
    settings=Settings(data_dir=tmp_path,tts_model='test-model',tts_voice='test-ai',tts_base_url='http://localhost:8766/v1')
    (folder/'preview.json').write_text(json.dumps({'model':settings.tts_model,'voice':settings.tts_voice,
        'base_url':settings.tts_base_url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'text':'测试试听'}))
    with TestClient(create_app(settings,Queue())) as client:
        config=client.get('/api/config').json()
        assert config['speech_previews']['system']['url']!=config['speech_previews']['ai']['url']
        system=client.get('/api/speech-preview?mode=system')
        ai=client.get('/api/speech-preview?mode=ai')
        assert system.status_code==ai.status_code==200
        assert system.content!=ai.content
        assert client.get('/api/speech-preview?mode=system').content==system.content
        assert len(calls)==1 and calls[0][0]==settings.system_voice
        assert client.get('/api/speech-preview?mode=invalid').status_code==422
    with TestClient(create_app(Settings(data_dir=tmp_path,system_voice='Another voice'),Queue())) as client:
        assert client.get('/api/speech-preview?mode=system').status_code==200
        assert len(calls)==2 and calls[-1][0]=='Another voice'
