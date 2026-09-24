"""Windows 系统语音与可选在线 AI 语音适配器。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx


class SpeechError(RuntimeError):
    pass


class SystemSpeech:
    """本机 Windows SAPI 语音。此语音不标称为 AI 语音。"""

    def __init__(self, voice_name: str = "Microsoft Huihui Desktop"):
        self.voice_name = voice_name

    def synthesize(self, text: str, output: Path) -> None:
        if sys.platform != "win32":
            raise SpeechError("演示模式系统配音首版仅支持 Windows。")
        source = output.with_suffix(".txt")
        source.write_text(text, encoding="utf-8")
        script = Path(__file__).parent / "powershell" / "speak.ps1"
        try:
            result = subprocess.run(
                [
                    "powershell.exe", "-NoProfile", "-NonInteractive",
                    "-ExecutionPolicy", "Bypass", "-File", str(script),
                    "-TextPath", str(source), "-OutputPath", str(output),
                    "-VoiceName", self.voice_name,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode != 0 or not output.is_file() or output.stat().st_size < 100:
                raise SpeechError("Windows 系统语音合成失败；请检查中文语音包。")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SpeechError("无法启动 Windows 系统语音服务。") from exc
        finally:
            source.unlink(missing_ok=True)


class AISpeech:
    """使用兼容的 /audio/speech HTTP 端点，响应格式为 WAV。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        voice: str,
        http_client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.http_client = http_client or httpx.Client(timeout=120)
        self._owns_client = http_client is None

    def close(self) -> None:
        if self._owns_client:
            self.http_client.close()

    def synthesize(self, text: str, output: Path) -> None:
        try:
            response = self.http_client.post(
                f"{self.base_url}/audio/speech",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "voice": self.voice,
                    "input": text,
                    "response_format": "wav",
                },
            )
            response.raise_for_status()
            if not response.content.startswith(b"RIFF"):
                raise SpeechError("语音服务未返回 WAV 音频。")
            output.write_bytes(response.content)
        except httpx.HTTPError as exc:
            raise SpeechError("AI 语音服务不可用；请检查地址、密钥和网络。") from exc
