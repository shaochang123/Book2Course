import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from pypdf import PdfReader
import pytest

from scripts import benchmark_chinese_textbooks as chinese


@pytest.fixture
def local_corpus(tmp_path, monkeypatch):
    suite, source_root, root = tmp_path / "suite", tmp_path / "originals", tmp_path / "run"
    suite.mkdir()
    folder = source_root / "sources" / "subject"
    folder.mkdir(parents=True)
    assets = []
    for number in range(1, 13):
        path = folder / f"{number}.jpg"
        Image.new("RGB", (100, 150), (number * 10, 230, 230)).save(path)
        assets.append({"kind": "pages", "reader_page": number,
                       "file": path.relative_to(source_root).as_posix(),
                       "url": f"https://book.pep.com.cn/test/files/mobile/{number}.jpg",
                       "sha256": chinese.base.digest(path)})
    numbers = list(range(1, 13))
    source = {"id": "subject", "book_id": "test", "reader_pages": numbers, "printed_pages": numbers,
              "sha256": chinese.selection_fingerprint(assets, numbers), "title": "测试教材",
              "domain": "测试", "level": "初中", "language": "zh-Hans", "license": "个人学习",
              "url": "https://book.pep.com.cn/test/"}
    record = {"source_id": "subject", "selected_reader_pages": numbers, "assets": assets}
    (folder / "acquisition.json").write_text(json.dumps(record), encoding="utf-8")
    spec = {"version": "fixture", "sources": [source], "page_counts": [2, 6, 12], "image_page_dpi": 150,
            "pending_sources": [], "coverage_gaps": ["native text unavailable"]}
    (suite / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (suite / "rubric.json").write_text(json.dumps({"anchors": {"subject": []}}), encoding="utf-8")
    (suite / "README.md").write_text("# 本机个人学习\n", encoding="utf-8")
    monkeypatch.setattr(chinese, "SUITE", suite)
    return source, record, source_root, root


def test_preparation_keeps_image_only_and_original_proportions(local_corpus):
    _, _, sources, root = local_corpus
    dataset = chinese.prepare(root, sources)
    assert len(dataset["cases"]) == 3
    assert dataset["text_cases_available"] == 0
    assert not dataset["redistribution_authorized"]
    for case in dataset["cases"]:
        pdf = PdfReader(root / case["input"])
        assert len(pdf.pages) == case["pages"]
        for page in pdf.pages:
            assert not page.extract_text()
            assert float(page.mediabox.width) / float(page.mediabox.height) == pytest.approx(2 / 3)
        assert chinese.base.digest(root / case["input"]) == case["sha256"]


def test_changed_source_is_rejected_before_pdfs_are_written(local_corpus):
    _, _, sources, root = local_corpus
    (sources / "sources/subject/1.jpg").write_bytes(b"changed")
    with pytest.raises(ValueError, match="image changed"):
        chinese.prepare(root, sources)
    assert not (root / "inputs").exists()


@pytest.mark.parametrize("change", ["missing", "duplicate", "order"])
def test_source_selection_is_frozen(local_corpus, change):
    source, record, sources, _ = local_corpus
    if change == "missing":
        record["assets"].pop()
    elif change == "duplicate":
        record["assets"].append(record["assets"][0])
    else:
        record["selected_reader_pages"].reverse()
    (sources / "sources/subject/acquisition.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError):
        chinese.checked_source_pages(source, sources)


def test_acquisition_cannot_read_outside_its_directory(local_corpus):
    source, record, sources, _ = local_corpus
    record["assets"][0]["file"] = "../private.jpg"
    (sources / "sources/subject/acquisition.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        chinese.checked_source_pages(source, sources)


def test_frozen_inputs_are_not_overwritten(local_corpus):
    _, _, sources, root = local_corpus
    chinese.prepare(root, sources)
    with pytest.raises(ValueError, match="already frozen"):
        chinese.prepare(root, sources)


def test_package_excludes_keys_caches_and_generated_results(local_corpus):
    _, _, sources, root = local_corpus
    dataset = chinese.prepare(root, sources)
    for name in (".env", "cache.json", "lesson.mp4", "private.pdf", "model.gguf"):
        (root / name).write_text("private", encoding="utf-8")
    archive = chinese.package(root)
    with ZipFile(archive) as z:
        assert z.testzip() is None
        assert len([name for name in z.namelist() if name.endswith(".pdf")]) == 3
        assert not {".env", "cache.json", "lesson.mp4", "private.pdf", "model.gguf"}.intersection(z.namelist())
        manifest = json.loads(z.read("SHA256.json"))
        for record in manifest:
            assert hashlib.sha256(z.read(record["file"])).hexdigest() == record["sha256"]
    assert len(dataset["cases"]) == len(manifest)


def test_package_rejects_reference_path_manipulation(local_corpus):
    _, _, sources, root = local_corpus
    dataset = chinese.prepare(root, sources)
    dataset["cases"][0]["reference"] = "../secret.json"
    chinese.base.write_json(root / "dataset.json", dataset)
    with pytest.raises(ValueError, match="Unexpected archive"):
        chinese.package(root)


def test_ocr_accuracy_is_unknown_without_independent_transcription(monkeypatch):
    monkeypatch.setattr(chinese, "_original_grade", lambda *a, **k: {"source_word_f1": 0, "ocr_pages": 2})
    result = chinese.grade_without_false_ocr_score(None)
    assert result["source_word_f1"] is None
    assert result["ocr_accuracy_available"] is False
    assert result["ocr_pages"] == 2


def test_published_definition_does_not_count_unavailable_books_or_text_layers():
    suite = Path(__file__).resolve().parents[1] / "benchmarks/textbooks_v3"
    spec = json.loads((suite / "spec.json").read_text(encoding="utf-8"))
    assert spec["formats"] == ["ocr"]
    assert len(spec["sources"]) == 7
    assert {s["id"] for s in spec["sources"]} == {"math-junior", "math-senior", "chinese-poetry", "english", "physics", "chemistry", "biology"}
    assert all(s["language"].startswith("zh-Hans") for s in spec["sources"])
    assert all(len(s["reader_pages"]) == len(s["printed_pages"]) == 12 for s in spec["sources"])
    assert spec["pending_sources"][0]["id"] == "math-university"
    assert not spec["rights"]["redistribution_authorized"]
