import subprocess
import wave
from io import BytesIO

import httpx
import imageio_ffmpeg
import pytest

from zhijiang.agents import DemoAgents
from zhijiang.models import VoiceMode
from zhijiang.pdf import read_pdf
from zhijiang.speech import AISpeech, SpeechError
from zhijiang.video import render_video


def test_ai_speech_rejects_service_failure(tmp_path):
    transport = httpx.MockTransport(lambda _: httpx.Response(503, text="secret upstream body"))
    with httpx.Client(transport=transport) as http_client:
        service = AISpeech("https://example.invalid/v1", "fake", "fake", "voice", http_client)
        with pytest.raises(SpeechError, match="语音服务不可用") as error:
            service.synthesize("你好", tmp_path / "audio.wav")
    assert "secret upstream body" not in str(error.value)


def test_ai_speech_accepts_wav_response(tmp_path):
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 2400)
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=buffer.getvalue()))
    with httpx.Client(transport=transport) as http_client:
        service = AISpeech("https://example.invalid/v1", "fake", "fake", "voice", http_client)
        output = tmp_path / "audio.wav"
        service.synthesize("你好", output)
    assert output.read_bytes().startswith(b"RIFF")


def test_video_renderer_creates_decodable_mp4(tmp_path, sample_pdf):
    document = read_pdf(sample_pdf, "source.pdf")
    agents = DemoAgents()
    bundle = agents.extract_knowledge(document)
    lesson = agents.script(bundle, agents.plan(bundle), VoiceMode.SYSTEM)
    lesson.segments = lesson.segments[:3]
    audio_files = []
    for index in range(3):
        path = tmp_path / f"audio-{index}.wav"
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(24000)
            audio.writeframes(b"\x00\x00" * 12000)
        audio_files.append(path)
    output = tmp_path / "lesson.mp4"
    render_video(lesson, audio_files, output)
    assert output.stat().st_size > 5000
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i",
                             str(output), "-f", "null", "NUL"],
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
