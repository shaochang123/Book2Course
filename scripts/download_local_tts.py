"""Download the CPU-sized Chinese Kokoro model into the ignored data directory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import numpy as np


MODEL_DIR = Path("data/models/kokoro")
BASE_URL = (
    "https://modelscope.cn/models/onnx-community/"
    "Kokoro-82M-v1.1-zh-ONNX/resolve/master"
)
FILES = {
    "kokoro-v1.1-zh-int8.onnx": (
        "onnx/model_uint8.onnx",
        "a39469be791eeaa3089c1ed5e58b8731d1f2462ea0e7dae2bc44388e58f973d8",
    ),
    "tokenizer.json": (
        "tokenizer.json",
        "5715a60b09d5e4b9074435d68c6ccd5675b9d48b220e109fdea3cda681e23d15",
    ),
    "voices/zf_001.bin": (
        "voices/zf_001.bin",
        "0a89ec12bb93fb9c74077924daf02568baad64e1f869389f5aaee01a386035f8",
    ),
    "voices/zf_002.bin": (
        "voices/zf_002.bin",
        "452f96e1e3c20b14b228b5336a8d7e833b105f837d98ef53b4ddfce18eed39bf",
    ),
    "voices/zm_009.bin": (
        "voices/zm_009.bin",
        "7b74d6ed22f201e2fa28758e78ce6197082779f2b80e69ea1bf877908609514a",
    ),
    "voices/zm_010.bin": (
        "voices/zm_010.bin",
        "73b088f7e0dc47adca4d6a642ee68843df90ff56ec2800c29d96609989d6de0a",
    ),
}


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        for name, (remote, expected_hash) in FILES.items():
            target = MODEL_DIR / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file() and checksum(target) == expected_hash:
                print(f"已验证：{target}")
                continue
            pending = target.with_suffix(target.suffix + ".part")
            try:
                with client.stream("GET", f"{BASE_URL}/{remote}") as response:
                    response.raise_for_status()
                    with pending.open("wb") as output:
                        for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                            output.write(chunk)
                if checksum(pending) != expected_hash:
                    raise RuntimeError(f"{name} 校验失败。")
                pending.replace(target)
                print(f"已下载：{target}")
            finally:
                pending.unlink(missing_ok=True)

    vocabulary = json.loads((MODEL_DIR / "tokenizer.json").read_text(encoding="utf-8"))["model"]["vocab"]
    (MODEL_DIR / "config.json").write_text(
        json.dumps({"vocab": vocabulary}, ensure_ascii=False), encoding="utf-8"
    )
    voice_styles = {
        path.stem: np.fromfile(path, dtype="<f4").reshape(-1, 1, 256)
        for path in sorted((MODEL_DIR / "voices").glob("*.bin"))
    }
    with (MODEL_DIR / "voices-v1.1-zh.bin").open("wb") as output:
        np.savez(output, **voice_styles)
    print("可用音色：" + ", ".join(voice_styles))


if __name__ == "__main__":
    main()
