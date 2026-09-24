"""应用配置。密钥只从环境变量读取，不持久化到仓库或任务记录。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path("data").resolve())
    max_pdf_bytes: int = 20 * 1024 * 1024
    max_pdf_pages: int = 100
    llm_provider: str = "openai"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    tts_base_url: str = ""
    tts_api_key: str = ""
    tts_model: str = ""
    tts_voice: str = "alloy"
    system_voice: str = "Microsoft Huihui Desktop"

    @classmethod
    def from_env(cls) -> "Settings":
        local_file = Path(os.getenv("ZHIJIANG_ENV_FILE", ".env.local"))
        local = dotenv_values(local_file) if local_file.is_file() else {}

        def value(name: str, default: str = "") -> str:
            item = os.getenv(name)
            if item is None:
                item = local.get(name)
            return (item if item is not None else default).strip()

        return cls(
            data_dir=Path(value("ZHIJIANG_DATA_DIR", "data")).resolve(),
            llm_provider=value("ZHIJIANG_LLM_PROVIDER", "openai").lower(),
            llm_base_url=value("ZHIJIANG_LLM_BASE_URL"),
            llm_api_key=value("ZHIJIANG_LLM_API_KEY"),
            llm_model=value("ZHIJIANG_LLM_MODEL"),
            tts_base_url=value("ZHIJIANG_TTS_BASE_URL"),
            tts_api_key=value("ZHIJIANG_TTS_API_KEY"),
            tts_model=value("ZHIJIANG_TTS_MODEL"),
            tts_voice=value("ZHIJIANG_TTS_VOICE", "alloy"),
            system_voice=value("ZHIJIANG_SYSTEM_VOICE", "Microsoft Huihui Desktop"),
        )

    @property
    def llm_ready(self) -> bool:
        if self.llm_provider == "ollama":
            return bool(self.llm_base_url and self.llm_model and self.llm_is_local)
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def ai_tts_ready(self) -> bool:
        return bool(self.tts_base_url and self.tts_api_key and self.tts_model)

    @staticmethod
    def _is_loopback(url: str) -> bool:
        return urlparse(url).hostname in {"127.0.0.1", "localhost", "::1"}

    @property
    def llm_is_local(self) -> bool:
        return self._is_loopback(self.llm_base_url)

    @property
    def tts_is_local(self) -> bool:
        return self._is_loopback(self.tts_base_url)
