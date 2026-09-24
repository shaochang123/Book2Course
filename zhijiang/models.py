"""各阶段共享的严格数据契约。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Mode(StrEnum):
    DEMO = "demo"
    AI = "ai"


class VoiceMode(StrEnum):
    SYSTEM = "system"
    AI = "ai"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


VisualKind = Literal["concept", "formula", "process"]


class PageText(BaseModel):
    page: int = Field(ge=1)
    text: str = Field(min_length=1)


class SourceDocument(BaseModel):
    filename: str
    pages: list[PageText] = Field(min_length=1)


class Evidence(BaseModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=8, max_length=300)


class KnowledgePoint(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    kind: VisualKind
    explanation: str = Field(min_length=8, max_length=500)
    evidence: Evidence


class KnowledgeBundle(BaseModel):
    points: list[KnowledgePoint] = Field(min_length=3, max_length=6)


class CourseOutline(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    objective: str = Field(min_length=8, max_length=240)
    point_titles: list[str] = Field(min_length=3, max_length=6)


class LessonSegment(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    kind: VisualKind
    narration: str = Field(min_length=20, max_length=1100)
    bullets: list[str] = Field(min_length=1, max_length=4)
    evidence: Evidence


class Lesson(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    objective: str = Field(min_length=8, max_length=240)
    segments: list[LessonSegment] = Field(min_length=3, max_length=6)
    mode: Mode
    voice_mode: VoiceMode
    notice: str


class ReviewResult(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list, max_length=8)
