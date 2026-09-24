"""使用已提交的原创 PDF，重新生成可提交的本地 Demo 视频。"""

from pathlib import Path
from shutil import copy2

from zhijiang.config import Settings
from zhijiang.models import Mode, VoiceMode
from zhijiang.pipeline import JobProcessor
from zhijiang.storage import JobStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = ROOT / "examples" / "binary_search_original.pdf"
    if not source.is_file():
        raise SystemExit("请先运行 python scripts/generate_sample_pdf.py")
    settings = Settings(data_dir=ROOT / "data" / "demo-build")
    store = JobStore(settings.data_dir)
    job = store.create(source.name, Mode.DEMO, VoiceMode.SYSTEM, True, False,
                       source.read_bytes())
    JobProcessor(settings, store).process(job["id"])
    final = store.get(job["id"])
    if final is None or final["status"] != "completed":
        raise SystemExit(f"演示视频生成失败：{final['error'] if final else '任务丢失'}")
    target = ROOT / "demo" / "zhijiang_demo.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    copy2(store.jobs_dir / job["id"] / "lesson.mp4", target)
    lesson = store.lesson(job["id"])
    (target.parent / "zhijiang_demo_lesson.json").write_text(
        lesson.model_dump_json(indent=2), encoding="utf-8"
    )
    print(target)
    print(f"size={target.stat().st_size} bytes; segments={len(lesson.segments)}")


if __name__ == "__main__":
    main()
