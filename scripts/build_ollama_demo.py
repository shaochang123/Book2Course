"""用本机 Ollama 与原创讲义生成并保存可复现的真实 AI Demo。"""

from dataclasses import replace
from pathlib import Path
from shutil import copy2

from zhijiang.config import Settings
from zhijiang.models import Mode, VoiceMode
from zhijiang.pipeline import JobProcessor
from zhijiang.storage import JobStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = ROOT / "examples" / "binary_search_original.pdf"
    settings = replace(Settings.from_env(), data_dir=ROOT / "data" / "ollama-build")
    if settings.llm_provider != "ollama" or not settings.llm_ready:
        raise SystemExit("请先配置本机 Ollama：复制 .env.local.example 为 .env.local")
    if not source.is_file():
        raise SystemExit("缺少原创示例 PDF；先运行 scripts/generate_sample_pdf.py")

    store = JobStore(settings.data_dir)
    job = store.create(source.name, Mode.AI, VoiceMode.SYSTEM, True, False, source.read_bytes())
    print(f"job={job['id']}; model={settings.llm_model}; voice=Windows system", flush=True)
    JobProcessor(settings, store).process(job["id"])
    final = store.get(job["id"])
    if final is None or final["status"] != "completed":
        raise SystemExit(f"Ollama Demo 生成失败：{final['error'] if final else '任务丢失'}")

    target = ROOT / "demo" / "zhijiang_ollama_demo.mp4"
    target.parent.mkdir(parents=True, exist_ok=True)
    copy2(store.jobs_dir / job["id"] / "lesson.mp4", target)
    lesson = store.lesson(job["id"])
    (target.parent / "zhijiang_ollama_lesson.json").write_text(
        lesson.model_dump_json(indent=2), encoding="utf-8"
    )
    print(f"video={target}; bytes={target.stat().st_size}; segments={len(lesson.segments)}")


if __name__ == "__main__":
    main()
