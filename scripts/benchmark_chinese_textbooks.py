"""Prepare local PEP reader excerpts and evaluate with the production benchmark.

No scraping, CAPTCHA handling, OCR text-layer creation, or remote model calls.
Official page images are imported from a separately recorded local acquisition.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scripts import benchmark_textbooks as base

SUITE = REPO / "benchmarks/textbooks_v3"


def selection_fingerprint(assets, numbers):
    pages = {item["reader_page"]: item for item in assets if item["kind"] == "pages"}
    if set(pages) != set(numbers) or len(pages) != len([a for a in assets if a["kind"] == "pages"]):
        raise ValueError("Selected source pages are missing or duplicated")
    return hashlib.sha256(b"".join(bytes.fromhex(pages[p]["sha256"]) for p in numbers)).hexdigest()


def checked_source_pages(source, source_root):
    source_root = Path(source_root).resolve()
    record = base.read_json(source_root / "sources" / source["id"] / "acquisition.json")
    if not record or record.get("source_id") != source["id"]:
        raise ValueError("Missing source acquisition: " + source["id"])
    assets = record["assets"]
    if record["selected_reader_pages"] != source["reader_pages"]:
        raise ValueError("Source selection changed: " + source["id"])
    if selection_fingerprint(assets, source["reader_pages"]) != source["sha256"]:
        raise ValueError("Source fingerprint differs: " + source["id"])
    pages = {}
    prefix = f"https://book.pep.com.cn/{source['book_id']}/files/mobile/"
    for item in assets:
        if item["kind"] != "pages":
            continue
        path = (source_root / item["file"]).resolve()
        if not path.is_relative_to(source_root):
            raise ValueError("Acquisition file escapes source directory")
        if not item["url"].startswith(prefix) or base.digest(path) != item["sha256"]:
            raise ValueError("Source image changed: " + item["file"])
        with Image.open(path) as img:
            img.verify()
        pages[item["reader_page"]] = path
    return pages


def image_pdf(paths, destination, title, dpi):
    """Embed original image bytes; preserve proportions, page marks and watermark."""
    out = canvas.Canvas(str(destination), invariant=1, pageCompression=1)
    out.setTitle(title)
    out.setAuthor("人民教育出版社；选页转换供本机个人学习")
    for path in paths:
        with Image.open(path) as image:
            width, height = image.size
        width, height = width * 72 / dpi, height * 72 / dpi
        out.setPageSize((width, height))
        out.drawImage(str(path), 0, 0, width=width, height=height)
        out.showPage()
    out.save()


def introduction(spec):
    text = (SUITE / "README.md").read_text(encoding="utf-8")
    lines = [text, "", "## 固定教材版本与选页", "",
             "| 组 | 教材 | 电子书页 | 书内印刷页 |", "|---|---|---|---|"]
    for source in spec["sources"]:
        lines.append(f"| {source['domain']} | [{source['title']}]({source['url']}) | "
                     f"{', '.join(map(str,source['reader_pages']))} | "
                     f"{', '.join(map(str,source['printed_pages']))} |")
    return "\n".join(lines)


def prepare(root, source_root):
    root = Path(root).resolve()
    if (root / "dataset.json").exists() or (root / "run.json").exists() or (root / "results.json").exists():
        raise ValueError("Corpus already frozen; use a new output directory")
    spec, rubric = base.read_json(SUITE / "spec.json"), base.read_json(SUITE / "rubric.json")
    # Check every source before authoring any PDF.
    checked = {s["id"]: checked_source_pages(s, source_root) for s in spec["sources"]}
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "references").mkdir(exist_ok=True)
    (root / "sources").mkdir(exist_ok=True)
    cases = []
    for source in spec["sources"]:
        (root / "sources" / (source["id"] + "-license.txt")).write_text(
            source["license"] + "\n" + source["url"] + "\n保留原图水印与署名；未获再分发授权，不属于项目MIT许可。\n", encoding="utf-8")
        for count in spec["page_counts"]:
            numbers = source["reader_pages"][:count]
            printed = source["printed_pages"][:count]
            name = f"{source['id']}-{count:02d}"
            path = root / "inputs" / (name + "-ocr.pdf")
            image_pdf([checked[source["id"]][n] for n in numbers], path, source["title"], spec["image_page_dpi"])
            pdf = PdfReader(path)
            if len(pdf.pages) != count or any(page.extract_text().strip() for page in pdf.pages):
                raise ValueError("Image input unexpectedly has a text layer or wrong page count")
            reference = root / "references" / (name + ".json")
            base.write_json(reference, {"original_pages": numbers, "printed_pages": printed,
                                       "texts": [], "reference_kind": "original_page_images_no_gold_transcription"})
            cases.append({"id": name + "-ocr", "source_id": source["id"], "domain": source["domain"],
                          "title": source["title"], "pages": count, "format": "ocr", "language": source["language"],
                          "level": source["level"], "original_pages": numbers, "printed_pages": printed,
                          "input": path.relative_to(root).as_posix(), "sha256": base.digest(path),
                          "source_sha256": source["sha256"], "reference": reference.relative_to(root).as_posix(),
                          "anchors": [a for a in rubric["anchors"][source["id"]] if a["page"] <= count]})
    cases.sort(key=lambda c: (c["pages"], c["source_id"]))
    dataset = {"version": spec["version"], "spec_sha256": base.digest(SUITE / "spec.json"),
               "rubric_sha256": base.digest(SUITE / "rubric.json"),
               "preparation_script_sha256": base.digest(Path(__file__)),
               "created_at": datetime.now(timezone.utc).isoformat(), "cases": cases,
               "text_cases_available": 0, "redistribution_authorized": False,
               "pending_sources": spec["pending_sources"], "coverage_gaps": spec["coverage_gaps"]}
    base.write_json(root / "dataset.json", dataset)
    base.write_json(root / "input-preflight.json", {"cases": len(cases), "pages": sum(c["pages"] for c in cases),
                                                   "all_hashes_checked": True, "all_image_only": True})
    for name in ("spec.json", "rubric.json", "README.md"):
        shutil.copyfile(SUITE / name, root / name)
    (root / "INTRODUCTION.md").write_text(introduction(spec), encoding="utf-8")
    return dataset


_original_grade = base.grade


def grade_without_false_ocr_score(*args, **kwargs):
    metrics = _original_grade(*args, **kwargs)
    metrics["source_word_f1"] = None
    metrics["ocr_accuracy_available"] = False
    metrics["ocr_reference_note"] = "原图无原生文字层及独立人工全文转录；不报告OCR准确率"
    return metrics


def configure_runner():
    base.SPEC, base.RUBRIC = SUITE / "spec.json", SUITE / "rubric.json"
    base.introduction = introduction
    base.grade = grade_without_false_ocr_score


def package(root):
    """Explicit whitelist for the same user's local personal-study archive."""
    root = Path(root).resolve()
    dataset = base.read_json(root / "dataset.json")
    if not dataset:
        raise ValueError("Prepare inputs first")
    archive = root / "Book2Course-benchmark-v3-Chinese-personal-study.zip"
    manifest = []
    with ZipFile(archive, "w", ZIP_DEFLATED) as out:
        for case in dataset["cases"]:
            expected_input = f"inputs/{case['id']}.pdf"
            expected_reference = f"references/{case['source_id']}-{case['pages']:02d}.json"
            if case["input"] != expected_input or case["reference"] != expected_reference:
                raise ValueError("Unexpected archive input or reference path")
            path = (root / case["input"]).resolve()
            if not path.is_relative_to(root) or base.digest(path) != case["sha256"]:
                raise ValueError("Frozen input changed")
            out.write(path, case["input"])
            manifest.append({"file": case["input"], "sha256": case["sha256"]})
            out.write(root / case["reference"], case["reference"])
        for name in ("README.md", "INTRODUCTION.md", "spec.json", "rubric.json", "dataset.json", "input-preflight.json"):
            out.write(root / name, name)
        for path in sorted((root / "sources").glob("*-license.txt")):
            out.write(path, path.relative_to(root).as_posix())
        out.writestr("SHA256.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with ZipFile(archive) as verify:
        if verify.testzip() is not None:
            raise ValueError("Archive CRC failed")
    return archive


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "report", "audit", "package"))
    parser.add_argument("--root", type=Path, default=REPO / "data/textbook-benchmark-v3-run")
    parser.add_argument("--source-root", type=Path, default=REPO / "data/textbook-benchmark-v3")
    parser.add_argument("--model", default="qwen3-vl:8b-instruct")
    parser.add_argument("--cases", help="Comma-separated frozen case IDs")
    args = parser.parse_args()
    configure_runner()
    if args.command == "prepare":
        print("PREPARED", len(prepare(args.root, args.source_root)["cases"]))
    elif args.command == "run":
        dataset = base.read_json(args.root / "dataset.json", {})
        if dataset.get("preparation_script_sha256") != base.digest(Path(__file__)):
            raise ValueError("Chinese harness changed; prepare a new frozen directory")
        if base.Settings.model_is_remote("ollama", base.Settings.from_env().llm_base_url, args.model):
            raise ValueError("This Chinese benchmark uses local models only")
        base.run(args.root, args.model, args.cases.split(",") if args.cases else None)
    elif args.command == "report":
        print(json.dumps(base.report(args.root), ensure_ascii=False))
    elif args.command == "audit":
        base.audit(args.root)
    else:
        print("PACKAGE", package(args.root))


if __name__ == "__main__":
    main()
