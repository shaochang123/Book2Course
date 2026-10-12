import io
import math
import struct
import sys
import wave

from fastapi.testclient import TestClient
import pytest

from zhijiang.config import Settings
from zhijiang.main import create_app
from zhijiang.speech import SpeechError
from zhijiang.speech_preview import PREVIEW_TEXT


class Queue:
    def submit(self, job_id): pass
    def shutdown(self): pass


def audio_bytes(frequency=300):
    out = io.BytesIO()
    with wave.open(out, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b''.join(struct.pack('<h', int(6000 * math.sin(i * frequency / 24000))) for i in range(2400)))
    return out.getvalue()


@pytest.fixture
def audition(tmp_path, monkeypatch):
    calls = []
    def synthesize(self, text, output):
        calls.append((self.base_url, self.model, self.voice, text, self.api_key))
        output.write_bytes(audio_bytes(300 + 100 * len(calls)))
    monkeypatch.setattr('zhijiang.speech.AISpeech.synthesize', synthesize)
    settings = Settings(data_dir=tmp_path, tts_base_url='http://127.0.0.1:8766/v1',
                        tts_model='model-a', tts_voice='voice-a')
    return settings, calls


def test_selected_models_voices_and_endpoints_have_independent_playable_previews(audition):
    settings, calls = audition
    profiles = [
        {'base_url': settings.tts_base_url, 'model': 'model-a', 'voice': 'voice-a'},
        {'base_url': settings.tts_base_url, 'model': 'model-a', 'voice': 'voice-b'},
        {'base_url': settings.tts_base_url, 'model': 'model-b', 'voice': 'voice-b'},
        {'base_url': 'http://127.0.0.1:8768/v1', 'model': 'model-b', 'voice': 'voice-b'},
    ]
    urls, audio = [], []
    with TestClient(create_app(settings, Queue())) as client:
        for profile in profiles:
            assert client.get('/api/speech-preview/selected', params=profile).json()['preview'] is None
            reply = client.post('/api/speech-preview', json=profile)
            assert reply.status_code == 200, reply.text
            info = reply.json()
            assert info['voice'] == profile['voice'] and info['model'] == profile['model']
            urls.append(info['url'])
            result = client.get(info['url'])
            assert result.status_code == 200 and result.headers['content-type'] == 'audio/wav'
            with wave.open(io.BytesIO(result.content)) as sound:
                assert sound.getnframes() > 0
            audio.append(result.content)
            assert client.get('/api/speech-preview/selected', params=profile).json()['preview']['url'] == info['url']
        assert len(set(urls)) == len(profiles) and len(set(audio)) == len(profiles)
        assert [call[:4] for call in calls] == [(p['base_url'], p['model'], p['voice'], PREVIEW_TEXT) for p in profiles]


def test_cache_survives_restart_and_explicit_regeneration_replaces_audio(audition):
    settings, calls = audition
    profile = {'base_url': settings.tts_base_url + '/', 'model': 'model-a', 'voice': 'voice-a'}
    with TestClient(create_app(settings, Queue())) as client:
        info = client.post('/api/speech-preview', json=profile).json()
        original = client.get(info['url']).content
    with TestClient(create_app(settings, Queue())) as client:
        assert client.post('/api/speech-preview', json=profile).json()['url'] == info['url']
        assert len(calls) == 1
        changed = client.post('/api/speech-preview', json={**profile, 'force': True})
        assert changed.status_code == 200 and changed.json()['url'] != info['url']
        assert client.get(changed.json()['url']).content != original and len(calls) == 2


@pytest.mark.parametrize('failure', ['service', 'invalid-wave'])
def test_failed_selected_voice_never_returns_default_or_partial_audio(audition, monkeypatch, failure):
    settings, _ = audition
    def fail(self, text, output):
        output.write_bytes(b'RIFFinvalid')
        if failure == 'service': raise SpeechError('upstream test-placeholder-secret')
    monkeypatch.setattr('zhijiang.speech.AISpeech.synthesize', fail)
    profile = {'base_url': settings.tts_base_url, 'model': 'broken-model', 'voice': 'broken-voice'}
    with TestClient(create_app(settings, Queue())) as client:
        response = client.post('/api/speech-preview', json=profile)
        assert response.status_code == 503 and 'upstream' not in response.text
        assert client.get('/api/speech-preview/selected', params=profile).json()['preview'] is None
        assert not list(settings.data_dir.rglob('*.pending.wav'))


def test_remote_preview_requires_consent_and_does_not_leak_key(audition):
    settings, calls = audition
    profile = {'base_url': 'https://example.invalid/v1', 'model': 'remote-model',
               'voice': 'remote-voice', 'api_key': 'test-placeholder-preview-key'}
    with TestClient(create_app(settings, Queue())) as client:
        assert client.post('/api/speech-preview', json=profile).status_code == 400
        assert not calls
        response = client.post('/api/speech-preview', json={**profile, 'remote_consent': True})
        assert response.status_code == 200 and profile['api_key'] not in response.text
        assert calls[-1][-1] == profile['api_key']
        assert calls[-1][3] == PREVIEW_TEXT
        for path in settings.data_dir.rglob('*.json'):
            assert profile['api_key'] not in path.read_text(encoding='utf-8')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows encrypted credentials')
def test_preview_resolves_saved_speech_key_without_input(audition):
    settings, calls = audition
    with TestClient(create_app(settings, Queue())) as client:
        assert client.post('/api/credentials', json={'kind': 'tts', 'provider': 'openai',
            'base_url': 'https://example.invalid/v1', 'api_key': 'test-placeholder-saved-preview-key'}).status_code == 200
        response = client.post('/api/speech-preview', json={'base_url': 'https://example.invalid/v1',
            'model': 'new-model', 'voice': 'new-voice', 'remote_consent': True})
        assert response.status_code == 200
        assert calls[-1][-1] == 'test-placeholder-saved-preview-key'


def test_preview_rejects_foreign_origin_malformed_input_and_arbitrary_file(audition):
    settings, calls = audition
    with TestClient(create_app(settings, Queue())) as client:
        profile = {'base_url': settings.tts_base_url, 'model': 'model-a', 'voice': 'voice-a'}
        assert client.post('/api/speech-preview', json=profile, headers={'Origin': 'https://other.invalid'}).status_code == 403
        invalid = client.post('/api/speech-preview', json={**profile, 'model': [], 'api_key': 'test-placeholder-sensitive-key'})
        assert invalid.status_code == 422 and 'test-placeholder-sensitive-key' not in invalid.text
        assert client.get('/api/speech-previews/not-a-cache-id').status_code == 422
        assert client.get('/api/speech-previews/' + 'a' * 64).status_code == 404
        assert not calls


def test_corrupted_preview_is_invalidated_and_rebuilt(audition):
    settings, calls = audition
    profile = {'base_url': settings.tts_base_url, 'model': 'model-a', 'voice': 'voice-a'}
    with TestClient(create_app(settings, Queue())) as client:
        info = client.post('/api/speech-preview', json=profile).json()
        files = list((settings.data_dir / 'voice-preview' / 'ai').glob('*.wav'))
        assert len(files) == 1
        files[0].write_bytes(b'RIFFcorrupted')
        assert client.get(info['url']).status_code == 404
        assert client.get('/api/speech-preview/selected', params=profile).json()['preview'] is None
        response = client.post('/api/speech-preview', json=profile)
        assert response.status_code == 200 and len(calls) == 2
