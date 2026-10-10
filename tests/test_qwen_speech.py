import hashlib
import io
import json
import wave
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from zhijiang.config import Settings
from zhijiang.main import create_app as create_web_app
from zhijiang.qwen_tts_service import BackendError, MODEL_NAME, VoiceSettings, check_generation_budget, create_app, split_text, validate_model_identity, wav_bytes
from zhijiang.speech_preview import preview_info
from zhijiang.models import SpeechOptions, VoiceMode
from zhijiang.pipeline import JobProcessor


@pytest.fixture
def voice_settings(tmp_path):
    model = tmp_path / 'model'
    for name in ['config.json', 'model.safetensors', 'speech_tokenizer/config.json', 'speech_tokenizer/model.safetensors']:
        target = model / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'test model placeholder')
    folder = tmp_path / 'reference'
    folder.mkdir()
    samples = .1 * np.sin(np.arange(24000 * 4) * 2 * np.pi * 200 / 24000)
    content = wav_bytes(samples, 24000)
    (folder / 'reference.wav').write_bytes(content)
    (folder / 'voice.json').write_text(json.dumps({
        'voice_id': 'notebook-reference', 'audio_file': 'reference.wav', 'transcript': '',
        'sha256': hashlib.sha256(content).hexdigest(),
    }), encoding='utf-8')
    return VoiceSettings(model, folder / 'voice.json', 'cpu', 0)


class FakeEngine:
    device = 'cpu'
    def __init__(self, settings, profile):
        self.texts = []
        self.closed = False
        self.profile = profile
    def synthesize(self, text):
        self.texts.append(text)
        return .1 * np.sin(np.arange(8000) * 2 * np.pi * 200 / 24000), 24000
    def close(self):
        self.closed = True


def payload(text='我们用一个例子解释这个概念。'):
    return {'model': MODEL_NAME, 'voice': 'notebook-reference', 'input': text}


@pytest.mark.parametrize('frames', [127, 128])
def test_token_budget_does_not_accept_truncated_audio(frames):
    with pytest.raises(BackendError, match='截断'):
        check_generation_budget([np.zeros((frames, 16))], 128)
    check_generation_budget([np.zeros((80, 16))], 128)


def test_model_alias_must_match_real_weight_config(voice_settings):
    path = voice_settings.model_dir / 'config.json'
    path.write_text(json.dumps({'tts_model_size': '0b6', 'tts_model_type': 'base'}), encoding='utf-8')
    validate_model_identity(voice_settings)
    path.write_text(json.dumps({'tts_model_size': '1b7', 'tts_model_type': 'base'}), encoding='utf-8')
    with pytest.raises(BackendError, match='不一致'):
        validate_model_identity(voice_settings)


def test_local_speech_wait_budget_reaches_pipeline_client():
    processor = JobProcessor(Settings(tts_timeout_seconds=900), None)
    speech = processor._speech(VoiceMode.AI, SpeechOptions(base_url='http://127.0.0.1:8766/v1', model=MODEL_NAME, voice='notebook-reference'))
    try:
        assert speech.http_client.timeout.read == 900
    finally:
        speech.close()


def test_health_is_available_while_a_long_request_runs(voice_settings):
    started, proceed = threading.Event(), threading.Event()
    replies = []
    class SlowEngine(FakeEngine):
        def synthesize(self, text):
            started.set()
            proceed.wait(3)
            return super().synthesize(text)
    with TestClient(create_app(voice_settings, engine_factory=SlowEngine)) as client:
        worker = threading.Thread(target=lambda: replies.append(client.post('/v1/audio/speech', json=payload())))
        worker.start()
        try:
            assert started.wait(3)
            before = time.monotonic()
            health = client.get('/health').json()
            assert health['busy'] and health['loaded']
            assert time.monotonic() - before < 1
        finally:
            proceed.set()
            worker.join(5)
        assert replies[0].status_code == 200


@pytest.mark.parametrize('text', ['你好，世界！我们继续。', 'a' * 385, '甲乙\n丙丁；' * 46, '你好🙂' * 80])
def test_speech_chunks_preserve_all_input(text):
    chunks = split_text(text)
    assert ''.join(chunks) == text
    assert max(map(len, chunks)) <= 120


def test_reference_voice_service_wav_and_lifecycle(voice_settings):
    engines = []
    def factory(settings, profile):
        engine = FakeEngine(settings, profile)
        engines.append(engine)
        return engine
    text = '这个讲解要完整保留句子。' * 35
    with TestClient(create_app(voice_settings, engine_factory=factory)) as client:
        health = client.get('/health').json()
        assert health['installed'] and health['reference_ready'] and not health['loaded']
        assert 'audio_path' not in health
        response = client.post('/v1/audio/speech', json=payload(text))
        assert response.status_code == 200
        assert response.headers['content-type'] == 'audio/wav'
        with wave.open(io.BytesIO(response.content), 'rb') as audio:
            assert audio.getframerate() == 24000 and audio.getnchannels() == 1
            assert audio.getnframes() == 8000 * len(engines[0].texts)
        assert ''.join(engines[0].texts) == text
        assert client.get('/health').json()['loaded']
    assert engines[0].closed


def test_bad_model_voice_and_missing_reference_are_explicit(voice_settings):
    with TestClient(create_app(voice_settings, engine_factory=FakeEngine)) as client:
        request = payload()
        request['model'] = 'wrong'
        assert client.post('/v1/audio/speech', json=request).status_code == 400
        request = payload(); request['voice'] = 'other'
        assert client.post('/v1/audio/speech', json=request).status_code == 400
        assert client.post('/v1/audio/speech', json=payload(' ')).status_code == 400
        (voice_settings.reference_file.parent / 'reference.wav').write_bytes(b'broken')
        assert not client.get('/health').json()['reference_ready']
        assert client.post('/v1/audio/speech', json=payload()).status_code == 503


def test_reference_cannot_escape_its_folder(voice_settings):
    path = voice_settings.reference_file
    profile = json.loads(path.read_text())
    profile['audio_file'] = '../other.wav'
    path.write_text(json.dumps(profile))
    with TestClient(create_app(voice_settings, engine_factory=FakeEngine)) as client:
        assert not client.get('/health').json()['reference_ready']
        assert client.post('/v1/audio/speech', json=payload()).status_code == 503


def test_reference_transcript_change_invalidates_prompt(voice_settings):
    engines = []
    def factory(settings, profile):
        engine = FakeEngine(settings, profile); engines.append(engine); return engine
    with TestClient(create_app(voice_settings, engine_factory=factory)) as client:
        assert client.post('/v1/audio/speech', json=payload()).status_code == 200
        path = voice_settings.reference_file
        profile = json.loads(path.read_text())
        profile['transcript'] = '这是参考声音的准确转录。'
        path.write_text(json.dumps(profile), encoding='utf-8')
        assert client.post('/v1/audio/speech', json=payload()).status_code == 200
        assert len(engines) == 2 and engines[0].closed


@pytest.mark.parametrize('samples', [np.zeros(8000), np.full(8000, np.nan), np.array([])])
def test_invalid_audio_is_not_success(voice_settings, samples):
    class InvalidEngine(FakeEngine):
        def synthesize(self, text):
            return samples, 24000
    with TestClient(create_app(voice_settings, engine_factory=InvalidEngine)) as client:
        response = client.post('/v1/audio/speech', json=payload())
        assert response.status_code == 503
        assert response.headers['content-type'] != 'audio/wav'


def test_backend_failure_does_not_leak_or_fallback(voice_settings):
    class FailedEngine(FakeEngine):
        def synthesize(self, text):
            raise RuntimeError('secret upstream failure')
    with TestClient(create_app(voice_settings, engine_factory=FailedEngine)) as client:
        response = client.post('/v1/audio/speech', json=payload())
        assert response.status_code == 503
        assert 'secret' not in response.text
        assert not client.get('/health').json()['loaded']


def test_configured_preview_has_exact_voice_and_no_arbitrary_file(tmp_path):
    settings = Settings(data_dir=tmp_path, tts_base_url='http://127.0.0.1:8766/v1',
                        tts_model=MODEL_NAME, tts_voice='notebook-reference', default_voice_mode='ai')
    folder = tmp_path / 'voice-preview'; folder.mkdir()
    data = wav_bytes(.1 * np.sin(np.arange(8000) * .05), 24000)
    (folder / 'preview.wav').write_bytes(data)
    profile = {'model': MODEL_NAME, 'voice': 'notebook-reference', 'base_url': settings.tts_base_url,
               'text': '原创试听讲稿。', 'sha256': hashlib.sha256(data).hexdigest(), 'path': '../private.wav'}
    (folder / 'preview.json').write_text(json.dumps(profile), encoding='utf-8')
    with TestClient(create_web_app(settings)) as client:
        config = client.get('/api/config').json()
        assert config['default_voice_mode'] == 'ai'
        assert config['speech_preview']['voice'] == 'notebook-reference'
        response = client.get(config['speech_preview']['url'])
        assert response.status_code == 200 and response.content == data
        assert response.headers['content-type'] == 'audio/wav'
        profile['voice'] = 'changed'
        (folder / 'preview.json').write_text(json.dumps(profile), encoding='utf-8')
        assert preview_info(settings) is None
        assert client.get('/api/speech-preview').status_code == 404


def test_voice_preference_without_service_defaults_to_system(tmp_path):
    with TestClient(create_web_app(Settings(data_dir=tmp_path, default_voice_mode='ai'))) as client:
        config = client.get('/api/config').json()
        assert config['default_voice_mode'] == 'system' and config['speech_preview'] is None
