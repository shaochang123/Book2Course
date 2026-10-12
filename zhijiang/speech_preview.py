"""Auditions for the configured Windows voice and selected compatible AI voices."""
from __future__ import annotations

import hashlib
import json
import wave
import sys
import threading
from pathlib import Path

from zhijiang.credentials import endpoint
from zhijiang.speech import AISpeech, SpeechError


PREVIEW_TEXT='学机器学习，可以先问一个简单的问题：电脑怎样从例子中学会判断？我们先看一个具体例子，再把它背后的思路讲清楚。'
_system_lock=threading.Lock()
_ai_lock=threading.Lock()


def preview_info(settings, mode='ai') -> dict | None:
    if mode=='system':
        if sys.platform!='win32':return None
        key=hashlib.sha256((settings.system_voice+PREVIEW_TEXT).encode()).hexdigest()[:12]
        return {'mode':'system','voice':settings.system_voice,'text':PREVIEW_TEXT,
                'url':f'/api/speech-preview?mode=system&v={key}'}
    folder = settings.data_dir / 'voice-preview'
    path = folder / 'preview.wav'
    try:
        info = json.loads((folder / 'preview.json').read_text(encoding='utf-8'))
        if (info['model'] != settings.tts_model or info['voice'] != settings.tts_voice
                or info['base_url'].rstrip('/') != settings.tts_base_url.rstrip('/')):
            return None
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != info['sha256']:
            return None
        with wave.open(str(path), 'rb') as audio:
            if audio.getframerate() < 8000 or audio.getnframes() == 0:
                return None
        return {'model': info['model'], 'voice': info['voice'], 'text': info['text'],
                'url': f'/api/speech-preview?v={digest[:12]}'}
    except (OSError, ValueError, KeyError, TypeError, wave.Error):
        return None


def preview_path(settings,mode='ai') -> Path:
    return settings.data_dir / 'voice-preview' / ('system.wav' if mode=='system' else 'preview.wav')


def ensure_system_preview(settings):
    from zhijiang.speech import SystemSpeech
    from zhijiang.speech_cache import synthesize_cached
    path=preview_path(settings,'system');path.parent.mkdir(parents=True,exist_ok=True)
    with _system_lock:synthesize_cached(SystemSpeech(settings.system_voice),PREVIEW_TEXT,path)
    return path


def _selection(base_url, model, voice):
    return {'base_url': endpoint(base_url), 'model': model.strip(), 'voice': voice.strip(),
            'text': PREVIEW_TEXT, 'version': 1}


def _selection_id(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def selected_preview_path(settings, preview_id):
    return settings.data_dir / 'voice-preview' / 'ai' / (preview_id + '.wav')


def _validate_wave(path):
    with wave.open(str(path), 'rb') as sound:
        if (sound.getnchannels() not in {1, 2} or sound.getsampwidth() not in {1, 2, 3, 4}
                or sound.getframerate() < 8000 or sound.getnframes() <= 0):
            raise ValueError('Invalid audition audio')
        expected = sound.getnframes() * sound.getnchannels() * sound.getsampwidth()
        if len(sound.readframes(sound.getnframes())) != expected:
            raise ValueError('Incomplete audition audio')


def cached_preview_info(settings, preview_id):
    path = selected_preview_path(settings, preview_id)
    try:
        info = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        profile = _selection(info['base_url'], info['model'], info['voice'])
        if info['text'] != PREVIEW_TEXT or _selection_id(profile) != preview_id:
            return None
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != info['sha256']:
            return None
        _validate_wave(path)
        return {'model': profile['model'], 'voice': profile['voice'], 'text': PREVIEW_TEXT,
                'url': f'/api/speech-previews/{preview_id}?v={digest[:12]}'}
    except (OSError, ValueError, KeyError, TypeError, EOFError, wave.Error):
        return None


def selected_preview_info(settings, base_url, model, voice):
    profile = _selection(base_url, model, voice)
    cached = cached_preview_info(settings, _selection_id(profile))
    if cached:
        return cached
    if settings.tts_base_url and profile['base_url'] == endpoint(settings.tts_base_url):
        if profile['model'] == settings.tts_model and profile['voice'] == settings.tts_voice:
            return preview_info(settings)
    return None


def generate_ai_preview(settings, options, *, force=False):
    """Use the same API adapter as lesson narration; never fall back to another voice."""
    profile = _selection(options.base_url, options.model, options.voice)
    preview_id = _selection_id(profile)
    with _ai_lock:
        if not force:
            existing = selected_preview_info(settings, options.base_url, options.model, options.voice)
            if existing:
                return existing
        path = selected_preview_path(settings, preview_id)
        pending = path.with_suffix('.pending.wav')
        pending_info = path.with_suffix('.pending.json')
        service = AISpeech(profile['base_url'], options.api_key, profile['model'], profile['voice'],
                           timeout_seconds=settings.tts_timeout_seconds)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            service.synthesize(PREVIEW_TEXT, pending)
            _validate_wave(pending)
            info = {**profile, 'sha256': hashlib.sha256(pending.read_bytes()).hexdigest()}
            pending_info.write_text(json.dumps(info, ensure_ascii=False), encoding='utf-8')
            pending.replace(path)
            pending_info.replace(path.with_suffix('.json'))
            return cached_preview_info(settings, preview_id)
        except (SpeechError, OSError, ValueError, EOFError, wave.Error) as exc:
            raise SpeechError('当前模型和音色的试听生成失败，请检查语音设置与服务。') from exc
        finally:
            service.close()
            pending.unlink(missing_ok=True)
            pending_info.unlink(missing_ok=True)
