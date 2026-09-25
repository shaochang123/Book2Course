"""单机任务状态与文件目录。每次操作使用独立 SQLite 连接。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from zhijiang.models import JobStatus, Lesson, Mode, VoiceMode


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.jobs_dir = data_dir / "jobs"
        self.db_path = data_dir / "jobs.sqlite3"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    voice_mode TEXT NOT NULL,
                    rights_confirmed INTEGER NOT NULL,
                    remote_consent INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    error TEXT,
                    lesson_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                "UPDATE jobs SET status=?, stage=?, error=?, updated_at=? "
                "WHERE status IN (?, ?)",
                (
                    JobStatus.FAILED,
                    "interrupted",
                    "服务中断，请重新提交任务。",
                    utc_now(),
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                ),
            )

    def create(
        self,
        filename: str,
        mode: Mode,
        voice_mode: VoiceMode,
        rights_confirmed: bool,
        remote_consent: bool,
        pdf: bytes,
    ) -> dict:
        job_id = uuid.uuid4().hex
        folder = self.jobs_dir / job_id
        folder.mkdir()
        (folder / "source.pdf").write_bytes(pdf)
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id, filename, mode, voice_mode, int(rights_confirmed),
                    int(remote_consent), JobStatus.QUEUED, "queued", 0, None,
                    None, now, now,
                ),
            )
        return self.get(job_id)  # type: ignore[return-value]

    def get(self, job_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["rights_confirmed"] = bool(result["rights_confirmed"])
        result["remote_consent"] = bool(result["remote_consent"])
        result["has_lesson"] = result["lesson_json"] is not None
        result["has_video"] = (self.jobs_dir / job_id / "lesson.mp4").is_file()
        result.pop("lesson_json")
        return result

    def set_progress(self, job_id: str, stage: str, progress: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status=?, stage=?, progress=?, updated_at=? WHERE id=?",
                (JobStatus.RUNNING, stage, progress, utc_now(), job_id),
            )

    def save_lesson(self, job_id: str, lesson: Lesson) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET lesson_json=?, updated_at=? WHERE id=?",
                (lesson.model_dump_json(), utc_now(), job_id),
            )

    def lesson(self, job_id: str) -> Lesson | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT lesson_json FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        if row is None or row["lesson_json"] is None:
            return None
        return Lesson.model_validate(json.loads(row["lesson_json"]))

    def complete(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status=?, stage=?, progress=100, updated_at=? WHERE id=?",
                (JobStatus.COMPLETED, "completed", utc_now(), job_id),
            )

    def fail(self, job_id: str, message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status=?, stage=?, error=?, updated_at=? WHERE id=?",
                (JobStatus.FAILED, "failed", message[:500], utc_now(), job_id),
            )

    def retry(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE jobs SET status=?, stage=?, progress=0, error=NULL, "
                "lesson_json=NULL, updated_at=? WHERE id=? AND status=?",
                (JobStatus.QUEUED, "queued", utc_now(), job_id, JobStatus.FAILED),
            )
        if cursor.rowcount != 1:
            return False
        (self.jobs_dir / job_id / "lesson.mp4").unlink(missing_ok=True)
        return True

    def delete(self, job_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        return cursor.rowcount > 0
