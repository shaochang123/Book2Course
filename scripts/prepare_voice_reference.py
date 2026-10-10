"""Extract a local voice prompt. Neither the source nor its audio leaves this machine."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--start', type=float, required=True)
    parser.add_argument('--duration', type=float, default=12)
    parser.add_argument('--transcript', default='')
    parser.add_argument('--output', type=Path, default=Path('data/voice-reference'))
    args = parser.parse_args()
    if not args.input.is_file() or args.start < 0 or not 3 <= args.duration <= 25:
        parser.error('需要存在的输入文件、非负起点和 3–25 秒参考段。')
    args.output.mkdir(parents=True, exist_ok=True)
    audio_path = args.output / 'reference.wav'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-v', 'error',
                    '-ss', str(args.start), '-i', str(args.input), '-t', str(args.duration),
                    '-vn', '-ac', '1', '-ar', '24000', str(audio_path)], check=True)
    with wave.open(str(audio_path), 'rb') as audio:
        if audio.getnframes() < 3 * audio.getframerate():
            raise RuntimeError('参考段不足三秒。')
    manifest = {
        'voice_id': 'notebook-reference', 'display_name': '参考片讲解声线',
        'audio_file': 'reference.wav', 'transcript': args.transcript.strip(),
        'sha256': hashlib.sha256(audio_path.read_bytes()).hexdigest(),
        'source_start_seconds': args.start, 'source_duration_seconds': args.duration,
        'local_only': True,
    }
    (args.output / 'voice.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'参考声音已准备：{args.output / "voice.json"}')


if __name__ == '__main__':
    main()
