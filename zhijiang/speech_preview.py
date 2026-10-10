"""Serve a pre-generated audition only when it matches current voice configuration."""
from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path


def preview_info(settings) -> dict | None:
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


def preview_path(settings) -> Path:
    return settings.data_dir / 'voice-preview' / 'preview.wav'
