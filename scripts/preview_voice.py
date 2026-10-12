"""Generate an original audition through the configured local speech service."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from zhijiang.config import Settings
from zhijiang.speech import AISpeech
from zhijiang.speech_preview import PREVIEW_TEXT

TEXT = PREVIEW_TEXT


def main():
    settings = Settings.from_env()
    if not settings.ai_tts_ready or not settings.tts_is_local:
        raise RuntimeError('此试听工具只调用已配置的本机语音服务。')
    folder = settings.data_dir / 'voice-preview'
    folder.mkdir(parents=True, exist_ok=True)
    pending = folder / 'preview.pending.wav'
    speech = AISpeech(settings.tts_base_url, settings.tts_api_key, settings.tts_model, settings.tts_voice,
                      timeout_seconds=settings.tts_timeout_seconds)
    try:
        speech.synthesize(TEXT, pending)
    finally:
        speech.close()
    output = folder / 'preview.wav'
    pending.replace(output)
    (folder / 'preview.json').write_text(json.dumps({
        'model': settings.tts_model, 'voice': settings.tts_voice, 'base_url': settings.tts_base_url,
        'text': TEXT, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'generated_at': datetime.now(timezone.utc).isoformat(), 'local_only': True,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'试听已生成：{output}')


if __name__ == '__main__':
    main()
