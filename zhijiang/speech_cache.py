"""Resume interrupted production without resynthesizing unchanged narration."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path


def synthesize_cached(service, text: str, output: Path) -> None:
    identity={'service': type(service).__name__, 'text': text,
              **{key:getattr(service,key,'') for key in ('base_url','model','voice','voice_name')}}
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    record=output.with_suffix('.voice.json')
    try:
        saved=json.loads(record.read_text(encoding='utf-8'))
        audio=output.read_bytes()
        if (isinstance(saved,dict) and saved.get('fingerprint')==fingerprint and len(audio)>44 and audio.startswith(b'RIFF')
                and saved.get('sha256')==hashlib.sha256(audio).hexdigest()):
            return
    except (OSError,ValueError):pass
    temporary=output.with_suffix('.tmp.wav')
    try:
        service.synthesize(text,temporary)
        digest=hashlib.sha256(temporary.read_bytes()).hexdigest()
        os.replace(temporary,output)
        record.write_text(json.dumps({'fingerprint':fingerprint,'sha256':digest}),encoding='utf-8')
    finally:
        temporary.unlink(missing_ok=True)
