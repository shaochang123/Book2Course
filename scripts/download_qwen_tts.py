"""Download a pinned official Qwen speech model into the ignored data directory."""
from __future__ import annotations

import hashlib
import argparse
import json
from pathlib import Path

REPO = 'Qwen/Qwen3-TTS-12Hz-1.7B-Base'
REVISION = 'fd4b254389122332181a7c3db7f27e918eec64e3'
MODEL_DIR = Path('data/models/qwen3-tts-1.7b-base')
WEIGHTS = {
    'model.safetensors': '38fc7fc51c5e776e840414b6fd443962e9411b9654888fd7913e4da643cb857c',
    'speech_tokenizer/model.safetensors': '836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258',
}
SMALL_REPO = 'Qwen/Qwen3-TTS-12Hz-0.6B-Base'
SMALL_REVISION = '5d83992436eae1d760afd27aff78a71d676296fc'
SMALL_WEIGHTS = {
    'model.safetensors': '180b3b10eb1c9f1b4db7806d5475bae3071c0243c299d49926bab1da3b6946f6',
    'speech_tokenizer/model.safetensors': WEIGHTS['speech_tokenizer/model.safetensors'],
}


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    from huggingface_hub import snapshot_download
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', choices=['0.6b', '1.7b'], default='0.6b')
    args = parser.parse_args()
    repo, revision, weights, folder = (SMALL_REPO, SMALL_REVISION, SMALL_WEIGHTS, Path('data/models/qwen3-tts-0.6b-base')) if args.size == '0.6b' else (REPO, REVISION, WEIGHTS, MODEL_DIR)
    snapshot_download(repo, revision=revision, local_dir=folder, max_workers=3)
    for name, expected in weights.items():
        if checksum(folder / name) != expected:
            raise RuntimeError(f'{name} SHA-256 校验失败。')
        print(f'已校验：{name}', flush=True)
    (folder / 'installation.json').write_text(json.dumps({
        'repository': repo, 'revision': revision, 'sha256': weights,
        'license': 'Apache-2.0',
    }, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
