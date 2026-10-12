"""Serve a pre-generated audition only when it matches current voice configuration."""
from __future__ import annotations

import hashlib
import json
import wave
import sys
import threading
from pathlib import Path


PREVIEW_TEXT='学机器学习，可以先问一个简单的问题：电脑怎样从例子中学会判断？我们先看一个具体例子，再把它背后的思路讲清楚。'
_system_lock=threading.Lock()


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
