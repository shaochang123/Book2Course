"""Frozen, paired textbook benchmarks through the unmodified production Agent.

Public corpus definitions are versioned; all inputs, logs and results use data/.
Gold anchors are used only after production and are never sent to the model.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import html
from io import BytesIO
import json
import platform
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
import httpx
import imageio_ffmpeg
from pypdf import PdfReader, PdfWriter
from pptx import Presentation
from zhijiang.config import Settings
from zhijiang.models import GenerationOptions, Mode, VoiceMode
from zhijiang.pdf import extract_page_text
from zhijiang.pipeline import JobProcessor
from zhijiang.storage import JobStore
from zhijiang.page_media import clip_duration

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / 'benchmarks/textbooks_v1/spec.json'
RUBRIC = REPO / 'benchmarks/textbooks_v1/rubric.json'


def read_json(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return default


def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(path)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def download(source, root):
    target = root / 'sources' / (source['id'] + '.pdf')
    if target.is_file():
        if digest(target) != source['sha256']: raise ValueError('Source fingerprint differs: ' + source['id'])
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = target.with_suffix('.pending')
    with httpx.stream('GET', source['pdf_url'], timeout=180, follow_redirects=True) as response:
        response.raise_for_status()
        with pending.open('wb') as output:
            for chunk in response.iter_bytes(): output.write(chunk)
    if digest(pending) != source['sha256']: raise ValueError('Downloaded book version differs: ' + source['id'])
    pending.replace(target)
    return target


def image_only_pdf(source, destination, dpi, quality):
    import pypdfium2
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    pdf = pypdfium2.PdfDocument(str(source))
    output = canvas.Canvas(str(destination), invariant=1, pageCompression=1)
    try:
        for page in pdf:
            width, height = page.get_size()
            bitmap = page.render(scale=dpi / 72)
            image = bitmap.to_pil().convert('RGB')
            buffer = BytesIO(); image.save(buffer, format='JPEG', quality=quality)
            output.setPageSize((width, height))
            output.drawImage(ImageReader(BytesIO(buffer.getvalue())), 0, 0, width=width, height=height)
            output.showPage()
            bitmap.close(); page.close()
        output.setTitle('Book2Course paired image-only benchmark input')
        output.save()
    finally: pdf.close()


def prepare(root):
    spec = read_json(SPEC); rubric = read_json(RUBRIC)
    if read_json(root / 'results.json'):
        raise ValueError('This corpus has measured results; prepare a new directory instead of overwriting inputs')
    root.mkdir(parents=True, exist_ok=True)
    cases = []; input_dir = root / 'inputs'; input_dir.mkdir(exist_ok=True)
    for source in spec['sources']:
        original = download(source, root); reader = PdfReader(original)
        license_text = source.get('license_notice') or reader.pages[source['license_page'] - 1].extract_text() or ''
        (root / 'sources' / (source['id'] + '-license.txt')).write_text(license_text, encoding='utf-8')
        for count in spec['page_counts']:
            numbers = list(range(source['start_page'], source['start_page'] + count))
            if numbers[-1] > len(reader.pages): raise ValueError('Invalid source page selection')
            base_id = f"{source['id']}-{count:02d}"
            text_pdf = input_dir / (base_id + '-text.pdf')
            writer = PdfWriter()
            for number in numbers: writer.add_page(reader.pages[number - 1])
            writer.add_metadata({'/Title': source['title'] + ': ' + source['section'],
                                 '/Author': source['author'], '/Subject': source['url'] + ' | ' + source['license']})
            writer.write(text_pdf)
            reference = [extract_page_text(page) for page in PdfReader(text_pdf).pages]
            if any(not text.strip() for text in reference): raise ValueError('Text baseline contains an empty text layer')
            references = root / 'references'; references.mkdir(exist_ok=True)
            write_json(references / (base_id + '.json'), {'original_pages': numbers, 'texts': reference})
            scan = input_dir / (base_id + '-ocr.pdf')
            image_only_pdf(text_pdf, scan, spec['scan_dpi'], spec['scan_jpeg_quality'])
            if any(extract_page_text(page).strip() for page in PdfReader(scan).pages):
                raise ValueError('OCR input unexpectedly has a hidden text layer')
            for form, path in [('text', text_pdf), ('ocr', scan)]:
                cases.append({'id': base_id + '-' + form, 'source_id': source['id'],
                    'domain': source['domain'], 'title': source['title'], 'pages': count, 'format': form,
                    'language': source.get('language', 'en'), 'level': source.get('level'),
                    'original_pages': numbers, 'input': path.relative_to(root).as_posix(),
                    'sha256': digest(path), 'source_sha256': source['sha256'],
                    'reference': (references / (base_id + '.json')).relative_to(root).as_posix(),
                    'anchors': [a for a in rubric['anchors'][source['id']] if a['page'] <= count]})
        print('prepared', source['id'], flush=True)
    cases.sort(key=lambda item: (item['pages'], item['source_id'], item['format'] != 'text'))
    dataset = {'version': spec['version'], 'spec_sha256': digest(SPEC), 'rubric_sha256': digest(RUBRIC),
               'created_at': datetime.now(timezone.utc).isoformat(), 'cases': cases}
    write_json(root / 'dataset.json', dataset)
    (root / 'INTRODUCTION.md').write_text(introduction(spec), encoding='utf-8')
    return dataset


def introduction(spec):
    counts = ' / '.join(map(str, spec['page_counts']))
    total = len(spec['sources']) * len(spec['page_counts']) * len(spec['formats'])
    text = ['# Book2Course Textbook Benchmark ' + spec['version'], '',
        f"{len(spec['sources'])} 个学科/学段组，{counts} 页，原生文字 PDF 与同内容纯图像 PDF 配对，共 {total} 个案例。",
        f"选页保留原版布局、表格、图片及原书页码映射；纯图像版以 {spec['scan_dpi']} DPI、JPEG {spec['scan_jpeg_quality']} 生成，没有隐藏文字层。",
        '图像版为可控模拟扫描，未加入手机拍照、污渍或旋转干扰；输入语言和学段逐教材记录，Agent 输出中文。', '',
        '## 来源与许可', '']
    for source in spec['sources']:
        text.append(f"- **{source['domain']}**：{source['title']}，{source['author']}，{source['year']}；原 PDF 从第 {source['start_page']} 页开始。来源：{source['url']}；许可：{source['license']}（{source['license_url']}）。")
    text += ['', '本轮用途为非商业评估。原始教材与衍生选页遵循各书许可，保留原图的单独署名；它们不改为项目 MIT 许可。', '',
        '## 固定生成条件', '', json.dumps(spec['preset'], ensure_ascii=False), '',
        '只传 PDF 和固定通用教学偏好；评价锚点、答案、图形坐标与人为分镜不传给 Agent。每个案例创建新任务，使用真实模型、正常解析、课程规划、图示、配音、PPT 与视频合成。',
        '通过 Ollama 接入模型并使用 Windows 系统语音。默认本地模型；仅明确启用的公开输入对照可使用非 DeepSeek 云模型。实际模型、远程标记和推理设置见 run.json；不同配置分开记录，不代表其他模型或模板的最好效果。', '',
        '## 指标与范围', '',
        '- 首次任务成功率：是否完成全部正常生成步骤；内部模型结构修复调用包含在耗时和 token 中。',
        '- 解析：页数、OCR 页数、文字量、相对文字版提取的词项 F1；参考提取可能拼接单词，F1 不是 OCR 准确率，也不衡量语序、语义或公式正确性。',
        '- 工程输出：PPT ZIP/SVG、讲者备注、外框边界、完整 MP4 解码、音频轨时长及可见画面变化。',
        '- 教学输出：关键词锚点出现率只反映提及；原文事实、条件、关系方向与图示含义另做人工抽查。',
        '- 实际视频帧与 PPT 共享页面做像素比较，人工查看代表帧和关键讲稿。', '',
        f'每个案例只做一次外层生成；不能由一次运行估计 pass@3 或稳定性。{counts} 页是测试规模，不是应用上限，也不代表整本书验收。',
        '新任务不复用课程检查点，模型驻留、OCR 权重和文件缓存可以复用；这不是全冷启动或受控硬件基准。人工检查需记录讲稿段号与视频帧页码，属于单评估者抽查。',
        '扫描对由同一教材生成，结果存在配对相关性；领域、语言与清晰度覆盖有限，不能外推成所有教材的成功率。', '']
    return '\n'.join(text)


class ObservedStore(JobStore):
    def __init__(self, root):
        super().__init__(root); self.started = {}; self.last_print = {}; self.labels = {}

    def set_progress(self, job_id, stage, progress):
        super().set_progress(job_id, stage, progress)
        now = time.perf_counter(); start = self.started.setdefault(job_id, now)
        event = {'elapsed_seconds': round(now - start, 3), 'stage': stage, 'progress': progress}
        with (self.jobs_dir / job_id / 'benchmark-events.jsonl').open('a', encoding='utf-8') as output:
            output.write(json.dumps(event, ensure_ascii=False) + '\n')
        phase = re.split('[（(]| · ', stage)[0]
        previous, previous_time = self.last_print.get(job_id, ('', 0))
        if phase != previous or now - previous_time >= 30:
            print(self.labels.get(job_id, job_id), round(now - start, 1), progress, stage, flush=True)
            self.last_print[job_id] = (phase, now)


def _words(text): return re.findall(r'[a-z0-9]+|[\u4e00-\u9fff]', text.casefold())


def word_f1(reference, hypothesis):
    a, b = Counter(_words(reference)), Counter(_words(hypothesis))
    overlap = sum((a & b).values())
    return 2 * overlap / (sum(a.values()) + sum(b.values())) if a or b else 1.0


def anchor_mentions(anchors, narration):
    return [{**a, 'mentioned': all(re.search(pattern, narration, re.I | re.S) for pattern in a['groups']) is True}
            for a in anchors]


def _ffmpeg(*args):
    return subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', *map(str, args)], capture_output=True)


def artifact_checks(folder, lesson, review_dir, *, review_all=False):
    from xml.etree import ElementTree as ET
    review_dir.mkdir(parents=True, exist_ok=True)
    ppt = folder / 'lesson.pptx'; video = folder / 'lesson.mp4'
    manifest = read_json(folder / 'presentation-preview/manifest.json', {})
    with ZipFile(ppt) as archive:
        archive_ok = archive.testzip() is None
        svgs = [name for name in archive.namelist() if name.endswith('.svg')]
        embedded_media=[name for name in archive.namelist() if name.startswith('ppt/media/') and
            Path(name).suffix.lower() in {'.mp4','.wav','.mp3','.m4a','.avi','.wmv'}]
        for name in svgs: ET.fromstring(archive.read(name))
    deck = Presentation(ppt)
    notes = '\n'.join(slide.notes_slide.notes_text_frame.text for slide in deck.slides)
    compact = lambda text: re.sub(r'\s+', '', text)
    notes_complete = all(compact(segment.narration) in compact(notes) for segment in lesson.segments)
    outside = []
    for n, slide in enumerate(deck.slides, 1):
        for shape in slide.shapes:
            if (shape.left < -10000 or shape.top < -10000 or
                shape.left + shape.width > deck.slide_width + 10000 or shape.top + shape.height > deck.slide_height + 10000):
                outside.append(n)
    duration = clip_duration(video)
    segment_entries = manifest.get('segments', [])
    expected_duration = sum(clip_duration(folder / entry['clip']) for entry in segment_entries)
    expected_duration += sum(entry['duration'] for entry in manifest.get('bookends', []))
    decoded = _ffmpeg('-i', video, '-f', 'null', '-')
    audio = _ffmpeg('-i', video, '-vn', '-ac', 1, '-ar', 8000, '-f', 's16le', '-')
    import numpy as np
    samples = np.frombuffer(audio.stdout, dtype='<i2').astype(float)
    audio_seconds = len(samples) / 8000
    audio_rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0
    frame_checks = []; cursor = sum(b['duration'] for b in manifest.get('bookends', []) if b['kind'] == 'cover')
    selected = {0, len(manifest.get('segments', [])) // 2, max(0, len(manifest.get('segments', [])) - 1)}
    if review_all:selected=set(range(len(manifest.get('segments',[]))))
    contact = Image.new('RGB', (1280, 390 * max(1, (len(selected) + 1) // 2)), '#eef1f4')
    draw = ImageDraw.Draw(contact); slot = 0
    for n, entry in enumerate(manifest.get('segments', [])):
        seconds = clip_duration(folder / entry['clip'])
        if n in selected:
            stamp = cursor + max(.05, seconds - .25)
            raw = _ffmpeg('-ss', stamp, '-i', video, '-frames:v', 1, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-')
            if raw.returncode != 0 or len(raw.stdout) != 1280 * 720 * 3:
                raise RuntimeError('Could not decode an actual review frame')
            frame = Image.frombytes('RGB', (1280, 720), raw.stdout)
            image_path = review_dir / f"segment-{entry['segment_id']:03d}.png"; frame.save(image_path)
            expected = folder / 'presentation-preview' / f"page-{entry['pages'][-1]:03d}.png"
            with Image.open(expected) as page:
                difference = float(abs(np.asarray(frame).astype(float) - np.asarray(page).astype(float)).mean())
            early_raw = _ffmpeg('-ss', cursor + max(.05, min(seconds - .05, seconds * .1)), '-i', video,
                                '-frames:v', 1, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-')
            motion = None
            if len(early_raw.stdout) == 1280 * 720 * 3:
                early = np.frombuffer(early_raw.stdout, dtype=np.uint8).reshape((720, 1280, 3))
                change = abs(np.asarray(frame).astype(float) - early.astype(float))
                motion = round(float(np.mean(np.max(change, axis=2) > 12)), 5)
            frame_checks.append({'segment_id': entry['segment_id'], 'page': entry['pages'][-1], 'time': stamp,
                                 'ppt_video_mean_pixel_error': round(difference, 3), 'changed_pixel_fraction': motion})
            scene=lesson.segments[entry['segment_id']-1].visual_scene
            if scene:
                for part,fraction in [('early',.1),('middle',.5)]:
                    raw_scene=_ffmpeg('-ss',cursor+seconds*fraction,'-i',video,'-frames:v',1,
                        '-f','rawvideo','-pix_fmt','rgb24','-')
                    if raw_scene.returncode or len(raw_scene.stdout)!=1280*720*3:
                        raise RuntimeError('Could not decode computed scene review frame')
                    Image.frombytes('RGB',(1280,720),raw_scene.stdout).save(
                        review_dir/f"segment-{entry['segment_id']:03d}-{part}.png")
            x, y = slot % 2 * 640, slot // 2 * 390
            contact.paste(frame.resize((640, 360)), (x, y))
            draw.text((x + 12, y + 363), f"Segment {entry['segment_id']} / actual MP4 frame", fill='black')
            slot += 1
        cursor += seconds
    contact.save(review_dir / 'frames.png')
    pages = [page for page in manifest.get('pages', []) if page['kind'] == 'content']
    changed = []
    for entry in manifest.get('segments', []):
        frames = [path for page in entry['pages'] for path in (folder / 'presentation-preview').glob(f'page-{page:03d}-*.png')]
        if not frames: continue
        changed.append({'segment_id': entry['segment_id'], 'unique_frames': len({digest(p) for p in frames})})
    return {'pptx_valid': archive_ok, 'slides': len(deck.slides), 'svg_count': len(svgs), 'notes_complete': notes_complete,
        'embedded_audio_video_count':len(embedded_media),'static_deck':not embedded_media,
        'computed_scene_segments':sum(bool(s.math_scene or (s.visual_scene and s.visual_scene.mathematical_model))
                                     for s in lesson.segments),
        'source_figure_pages':sum(bool(p.get('source_figure')) for p in pages),
        'segment_count_matches': len(segment_entries) == len(lesson.segments),
        'cover_and_closing_present': {entry['kind'] for entry in manifest.get('bookends', [])} >= {'cover','ending'},
        'full_video_duration_matches_segments': abs(expected_duration - duration) < .5,
        'outer_bounds_violations': sorted(set(outside)), 'video_decodable': decoded.returncode == 0,
        'video_seconds': round(duration, 3), 'audio_decodable': audio.returncode == 0, 'audio_seconds': round(audio_seconds, 3),
        'audio_rms': round(audio_rms, 2), 'audio_duration_matches': abs(audio_seconds - duration) < .5,
        'representations': dict(Counter(page.get('representation', 'unspecified') for page in pages)),
        'layouts': dict(Counter(page.get('layout', page.get('composition', 'unspecified')) for page in pages)),
        'relation_count': sum(page.get('relation_count', 0) for page in pages),
        'selected_asset_pages': sum(bool(page.get('asset_ids')) for page in pages),
        'illustrated_pages': sum(bool(page.get('illustration_regions')) for page in pages),
        'placed_illustrations': sum(len(page.get('illustration_regions', [])) for page in pages),
        'displayed_characters': [page.get('displayed_characters') for page in pages],
        'actual_frame_checks': frame_checks, 'progressive_frame_records': changed}


def grade(root, case, store, job_id, generation_seconds=None):
    folder = store.jobs_dir / job_id; document = read_json(folder / 'parsed-source.json', {}).get('data', {})
    reference = read_json(root / case['reference'])['texts']
    pages = document.get('pages', [])
    result = {'parsed_pages': len(pages), 'ocr_pages': sum(page.get('ocr', False) for page in pages),
        'parsed_characters': sum(len(page.get('text', '')) for page in pages),
        'knowledge_points': len(read_json(folder / 'knowledge.json', {}).get('data', {}).get('points', [])),
        'source_word_f1': round(word_f1('\n'.join(reference), '\n'.join(page.get('text', '') for page in pages)), 4)}
    calls = read_json(folder / 'model-calls.json', [])
    result.update(model_calls=len(calls), model_stages=dict(Counter(call['stage'] for call in calls)),
        generated_tokens=sum(call.get('eval_count') or 0 for call in calls) if calls else None,
        input_tokens=sum(call.get('prompt_eval_count') or 0 for call in calls) if calls else None,
        model_seconds=round(sum(call.get('total_duration') or 0 for call in calls) / 1e9, 3) if calls else None,
        internal_repair_calls=sum(call.get('attempt', 1) > 1 for call in calls))
    event_file = folder / 'benchmark-events.jsonl'
    events = [json.loads(line) for line in event_file.read_text(encoding='utf-8').splitlines()] if event_file.is_file() else []
    phase_seconds = Counter()
    for n, event in enumerate(events):
        phase = re.split('[（(]| · ', event['stage'])[0]
        end = events[n + 1]['elapsed_seconds'] if n + 1 < len(events) else (generation_seconds or event['elapsed_seconds'])
        phase_seconds[phase] += max(0, end - event['elapsed_seconds'])
    result['phase_seconds'] = {key: round(value, 3) for key, value in phase_seconds.items()}
    retrieval = read_json(folder / 'presentation-plan.json', {}).get('asset_retrieval', [])
    result.update(asset_candidate_segments=sum(bool(entry.get('candidates')) for entry in retrieval),
                  asset_selected_segments=sum(bool(entry.get('selected')) for entry in retrieval))
    write_json(root / 'reviews' / case['id'] / 'assets.json', [
        {'segment_id': entry['segment_id'], 'query': entry.get('query'),
         'candidates': [{key: asset.get(key) for key in ('id','title','score','kind','entity_aliases')}
                        for asset in entry.get('candidates', [])],
         'selected': entry.get('selected', []), 'gap': entry.get('gap')}
        for entry in retrieval])
    lesson = store.lesson(job_id)
    if lesson:
        narration = '\n'.join(segment.narration for segment in lesson.segments)
        anchors = anchor_mentions(case['anchors'], narration)
        result.update(segments=len(lesson.segments), anchors=anchors,
            anchor_mention_ratio=round(sum(a['mentioned'] for a in anchors) / len(anchors), 4) if anchors else None,
            cited_pages=sorted({segment.evidence.page for segment in lesson.segments}),
            narration_characters=len(narration), warnings=lesson.animation_report.get('warnings', []))
        from zhijiang.models import SourceDocument
        from zhijiang.agents import validate_evidence, GenerationError
        if document:
            parsed = SourceDocument.model_validate(document); invalid = []
            for n, segment in enumerate(lesson.segments, 1):
                try: validate_evidence(parsed, segment.evidence)
                except GenerationError: invalid.append(n)
            result['citation_identity_invalid_segments'] = invalid
        write_json(root / 'reviews' / case['id'] / 'script.json', {'case': case['id'], 'anchors': anchors,
            'segments': [{'title': s.title, 'page': s.evidence.page, 'narration': s.narration} for s in lesson.segments]})
    if store.get(job_id)['status'] == 'completed' and lesson:
        result['artifacts'] = artifact_checks(folder, lesson, root / 'reviews' / case['id'],
                                            review_all=read_json(SPEC).get('version')=='textbooks-v2')
    return result


def run(root, model=None, selected=None, *, allow_ollama_cloud=False):
    dataset = read_json(root / 'dataset.json')
    if not dataset or dataset['spec_sha256'] != digest(SPEC) or dataset['rubric_sha256'] != digest(RUBRIC):
        raise ValueError('Prepare the frozen corpus before running; spec/rubric must match')
    local = Settings.from_env(); spec = read_json(SPEC)
    if local.llm_provider != 'ollama' or not local.llm_is_local:
        raise ValueError('This benchmark uses a local Ollama model; remote keys and private inputs are excluded')
    chosen = model or local.llm_model
    if 'deepseek' in chosen.casefold(): raise ValueError('DeepSeek is excluded from this benchmark')
    cloud=Settings.model_is_remote('ollama',local.llm_base_url,chosen)
    if cloud and not allow_ollama_cloud: raise ValueError('Use a local model tag, or explicitly enable the public-input Ollama cloud comparison')
    if selected and set(selected) - {case['id'] for case in dataset['cases']}:
        raise ValueError('Unknown benchmark case ID')
    root_settings = replace(local, data_dir=root / 'tasks')
    options = GenerationOptions(provider='ollama', base_url=local.llm_base_url, model=chosen,
        prompt=spec['prompt'], **{k: v for k, v in spec['preset'].items() if k != 'voice_mode'})
    config = {'model': chosen, 'provider': 'ollama', 'semantic_thinking': options.semantic_thinking,
        'context_tokens': None if cloud else local.ollama_context_tokens, 'gpu_layers': None if cloud else local.ollama_num_gpu,
        'voice': 'Windows system speech', 'preset': spec['preset'], 'prompt': spec['prompt'],
        'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'python': platform.python_version(), 'platform': platform.system(),
        'benchmark_script_sha256': digest(Path(__file__)),
        'remote_model':cloud,'public_input_transmission_consent':bool(cloud and allow_ollama_cloud),
        'production_sha256': {p.relative_to(REPO).as_posix(): digest(p)
            for p in sorted((REPO / 'zhijiang').glob('*.py'))},
        'started_at': datetime.now(timezone.utc).isoformat()}
    existing = read_json(root / 'run.json')
    if existing and any(existing[k] != config[k] for k in ('model', 'preset', 'prompt', 'context_tokens', 'gpu_layers')):
        raise ValueError('Run configuration changed; use a new output directory')
    if existing and existing.get('production_sha256', config['production_sha256']) != config['production_sha256']:
        raise ValueError('Production code changed; use a separate run directory to preserve comparisons')
    if existing and existing.get('git_commit') != config['git_commit']:
        # A documentation commit does not alter the frozen production bytes.
        # Retain the original revision and record each identical-code resumption.
        revisions=existing.setdefault('resume_revisions',[])
        if not revisions or revisions[-1]['git_commit'] != config['git_commit']:
            revisions.append({'git_commit':config['git_commit'],'at':config['started_at'],
                              'production_sha256_unchanged':True})
            write_json(root/'run.json',existing)
    if not existing: write_json(root / 'run.json', config)
    store = ObservedStore(root / 'tasks'); processor = JobProcessor(root_settings, store)
    results = read_json(root / 'results.json', {})
    previous = read_json(root / 'current.json', {})
    if previous.get('case_id') and previous['case_id'] not in results:
        raise ValueError('An earlier attempt was interrupted without a measured result; preserve this directory and start a new run')
    for case in dataset['cases']:
        if selected and case['id'] not in selected: continue
        if case['id'] in results: continue
        input_pdf = root / case['input']
        if digest(input_pdf) != case['sha256']: raise ValueError('Benchmark input changed: ' + case['id'])
        job = store.create(input_pdf.name, Mode.AI, VoiceMode.SYSTEM, True, bool(cloud and allow_ollama_cloud), input_pdf.read_bytes(), options)
        job_id = job['id']; store.labels[job_id] = case['id']
        write_json(root / 'current.json', {'case_id': case['id'], 'job_id': job_id, 'started_at': datetime.now(timezone.utc).isoformat()})
        started = time.perf_counter(); print('START', case['id'], job_id, flush=True)
        processor.process(job_id); state = store.get(job_id)
        row = {**case, 'job_id': job_id, 'status': state['status'], 'error': state['error'],
               'stage': state['stage'], 'generation_seconds': round(time.perf_counter() - started, 3),
               'first_attempt': True, 'ended_at': datetime.now(timezone.utc).isoformat()}
        audit = time.perf_counter()
        try: row['metrics'] = grade(root, case, store, job_id, row['generation_seconds'])
        except Exception as exc: row['audit_error'] = type(exc).__name__ + ': ' + str(exc)
        row['audit_seconds'] = round(time.perf_counter() - audit, 3)
        results[case['id']] = row; write_json(root / 'results.json', results)
        print('RESULT', case['id'], state['status'], row['generation_seconds'], state['error'], flush=True)
        report(root)
    report(root)


def audit(root):
    """Recompute evidence metrics without rerunning or relabelling generation."""
    results = read_json(root / 'results.json', {})
    store = JobStore(root / 'tasks')
    for row in results.values():
        started = time.perf_counter()
        try:
            row['metrics'] = grade(root, row, store, row['job_id'], row['generation_seconds'])
            row.pop('audit_error', None)
        except Exception as exc:
            row['audit_error'] = type(exc).__name__ + ': ' + str(exc)
        row['last_audit_seconds'] = round(time.perf_counter() - started, 3)
        print('AUDIT', row['id'], row.get('audit_error', 'ok'), flush=True)
    write_json(root / 'results.json', results)
    report(root)


def recover_exports(root):
    """Export retained failed lessons into new folders, without any model/TTS call."""
    from zhijiang.presentation import render_presentation
    from zhijiang.video import render_video
    store = JobStore(root / 'tasks')
    results = read_json(root / 'results.json', {})
    recovered = read_json(root / 'recovery-results.json', {})
    code_hash = digest(REPO / 'zhijiang/rich_deck.py')
    for case, baseline in results.items():
        if baseline['status'] != 'failed' or recovered.get(case, {}).get('status') == 'completed': continue
        lesson = store.lesson(baseline['job_id'])
        folder = store.jobs_dir / baseline['job_id']
        paths = [folder / ('math' if segment.math_scene else 'visual') / f'scene-{n:02d}/narration.wav'
                 if segment.math_scene or segment.visual_scene else folder / f'audio-{n-1}.wav'
                 for n, segment in enumerate(lesson.segments, 1)] if lesson else []
        if not lesson or not paths or not all(path.is_file() for path in paths):
            recovered[case] = {'status': 'not_recoverable', 'notes': '缺少保留课程或完整原始配音，未重新请求模型。'}
            write_json(root / 'recovery-results.json', recovered)
            continue
        output = root / 'recoveries' / case
        output.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        row = {'case': case, 'job_id': baseline['job_id'], 'fixed_code_sha256': code_hash,
               'generation_rerun': False, 'tts_rerun': False,
               'notes': '沿用首轮课程与配音，知识与图示评价不重置。'}
        try:
            for directory in ('math','visual','source-pages','source-figures'):
                if (folder / directory).is_dir(): shutil.copytree(folder / directory, output / directory, dirs_exist_ok=True)
            audio = []
            for n, path in enumerate(paths):
                target = output / f'audio-{n}.wav'
                shutil.copy2(path, target); audio.append(target)
            (output / 'lesson.json').write_text(lesson.model_dump_json(indent=2), encoding='utf-8')
            render_presentation(lesson, output / 'lesson.pptx')
            render_video(lesson, audio, output / 'lesson.mp4')
            row.update(status='completed', export_seconds=round(time.perf_counter() - started, 3))
            row['metrics'] = {'artifacts': artifact_checks(output, lesson, root / 'recovery-reviews' / case)}
            row['engineering_passed'] = engineering_ok(row)
        except Exception as exc:
            row.update(status='failed', export_seconds=round(time.perf_counter() - started, 3),
                       notes=type(exc).__name__ + ': ' + str(exc))
        recovered[case] = row
        write_json(root / 'recovery-results.json', recovered)
        print('RECOVERY', case, row['status'], row.get('engineering_passed'), flush=True)
    report(root)


def engineering_ok(row):
    art = row.get('metrics', {}).get('artifacts', {})
    return all([row.get('status') == 'completed', art.get('pptx_valid'), art.get('notes_complete'),
        art.get('video_decodable'), art.get('audio_decodable'), art.get('audio_duration_matches'),
        not art.get('outer_bounds_violations'), not row.get('audit_error')])


def grouped_metrics(rows, key):
    groups = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    result = {}
    for name, cases in groups.items():
        completed = [row for row in cases if row['status'] == 'completed']
        token_values = lambda field: [row['metrics'][field] for row in cases
            if row.get('metrics', {}).get(field) is not None]
        generated = token_values('generated_tokens'); inputs = token_values('input_tokens')
        result[name] = {'attempts': len(cases), 'completed': len(completed),
            'engineering_passed': sum(engineering_ok(row) for row in cases),
            'median_attempt_seconds': round(statistics.median(row['generation_seconds'] for row in cases), 3),
            'median_completed_seconds': round(statistics.median(row['generation_seconds'] for row in completed), 3) if completed else None,
            'median_generated_tokens': statistics.median(generated) if generated else None,
            'median_input_tokens': statistics.median(inputs) if inputs else None}
    return result


def pairs(dataset, results):
    comparison = []
    for case in dataset['cases']:
        if case['format'] != 'text': continue
        scan_id = case['id'].removesuffix('-text') + '-ocr'
        text = results.get(case['id']); scan = results.get(scan_id)
        if not text or not scan: continue
        comparison.append({'pair': case['id'].removesuffix('-text'), 'pages': case['pages'], 'domain': case['domain'],
            'text_status': text['status'], 'ocr_status': scan['status'],
            'ocr_minus_text_seconds': round(scan['generation_seconds'] - text['generation_seconds'], 3),
            'ocr_word_f1': scan.get('metrics', {}).get('source_word_f1')})
    return comparison


def report(root):
    dataset = read_json(root / 'dataset.json', {'cases': []}); results = read_json(root / 'results.json', {})
    config = read_json(root / 'run.json', {}); manual = read_json(root / 'manual-review.json', {})
    done = list(results.values()); success = sum(row['status'] == 'completed' for row in done)
    lines = ['# Book2Course 教材 Benchmark 实测结果', '',
        f"已运行 {len(done)} / {len(dataset['cases'])}；首次生成完成 {success} / {len(done)}。", '',
        f"模型：{config.get('model', '未运行')}；深度推理：{config.get('semantic_thinking')}；系统语音；直接生成；学术课堂模板。", '',
        '工程完成与教学质量分列。关键词出现率不等于知识正确率；未人工检查的结果不标为教学合格。', '',
        '| 案例 | 领域 | 页数 | PDF 类型 | 生成 | 秒 | 解析/OCR页 | 输入/输出token | 片段/PPT页 | 视频秒 | 锚点提及 | 人工抽查 |',
        '|---|---|---:|---|---|---:|---|---|---|---:|---:|---|']
    csv_rows = []
    for case in dataset['cases']:
        row = results.get(case['id'], {}); metrics = row.get('metrics', {}); art = metrics.get('artifacts', {})
        review = manual.get(case['id'], {}).get('overall', '未复核')
        lines.append(f"| {case['id']} | {case['domain']} | {case['pages']} | {'文字' if case['format']=='text' else '纯图像'} | {row.get('status','待运行')} | {row.get('generation_seconds','-')} | {metrics.get('parsed_pages','-')}/{metrics.get('ocr_pages','-')} | {metrics.get('input_tokens','-')}/{metrics.get('generated_tokens','-')} | {metrics.get('segments','-')}/{art.get('slides','-')} | {art.get('video_seconds','-')} | {metrics.get('anchor_mention_ratio','-')} | {review} |")
        csv_rows.append({'case': case['id'], 'domain': case['domain'], 'pages': case['pages'], 'format': case['format'],
            'status': row.get('status','pending'), 'seconds': row.get('generation_seconds'), 'ocr_pages': metrics.get('ocr_pages'),
            'source_word_f1': metrics.get('source_word_f1'), 'input_tokens': metrics.get('input_tokens'),
            'parsed_characters': metrics.get('parsed_characters'), 'model_calls': metrics.get('model_calls'),
            'knowledge_points': metrics.get('knowledge_points'),
            'internal_repair_calls': metrics.get('internal_repair_calls'),
            'output_tokens': metrics.get('generated_tokens'), 'segments': metrics.get('segments'), 'slides': art.get('slides'),
            'video_seconds': art.get('video_seconds'), 'placed_illustrations': art.get('placed_illustrations'),
            'asset_candidate_segments': metrics.get('asset_candidate_segments'),
            'asset_selected_segments': metrics.get('asset_selected_segments'),
            'relations': art.get('relation_count'), 'anchor_mentions': metrics.get('anchor_mention_ratio'), 'manual': review})
    breakdown = {key: grouped_metrics(done, key) for key in ('pages', 'format', 'domain')}
    paired = pairs(dataset, results)
    reviews = Counter(manual.get(row['id'], {}).get('overall', 'not_reviewed') for row in done)
    lines += ['', '## 分组统计', '', '| 分组 | 首次完成/尝试 | 工程检查通过 | 尝试耗时中位数（秒） | 完成项耗时中位数（秒） |', '|---|---|---|---:|---:|']
    for key, groups in breakdown.items():
        for label, stats in groups.items():
            lines.append(f"| {key}={label} | {stats['completed']}/{stats['attempts']} | {stats['engineering_passed']} | {stats['median_attempt_seconds']} | {stats['median_completed_seconds']} |")
    lines += ['', '耗时包含内部修复与正常媒体生成，不包含随后输出审计；失败项的耗时也保留。新任务没有课程检查点，模型驻留、OCR 权重与系统文件缓存可复用，不能称为全冷启动。', '',
        '## 文字/OCR 配对', '', '| 教材/页数 | 文字生成 | OCR 生成 | OCR 比文字耗时差（秒） | OCR 词项 F1 |', '|---|---|---|---:|---:|']
    for pair in paired:
        lines.append(f"| {pair['pair']} | {pair['text_status']} | {pair['ocr_status']} | {pair['ocr_minus_text_seconds']} | {pair['ocr_word_f1']} |")
    lines += ['', '正负耗时差包含随机模型输出长度和修复差异，不能全部解释成 OCR 开销。', '', '## 失败与抽查', '']
    for row in done:
        review = manual.get(row['id'])
        if row['status'] != 'completed' or row.get('audit_error'):
            lines.append(f"- **{row['id']}**：{row.get('error') or row.get('audit_error')}")
        if review: lines.append(f"- **{row['id']}**：{review.get('overall')}；{review.get('notes', '')}")
    environment = read_json(root / 'environment.json', {})
    if environment:
        lines += ['', '## 机器与版本', '', f"CPU：{environment.get('cpu')}；内存：{round(environment.get('ram_bytes',0)/1024**3,1)} GiB；GPU：{environment.get('gpu')}。", '',
            f"Ollama {environment.get('ollama_version')}；Python {config.get('python')}；应用基线 {config.get('git_commit')}。", '',
            f"模型指纹：{environment.get('model',{}).get('digest')}；量化：{environment.get('model',{}).get('details',{}).get('quantization_level')}；请求上下文：{config.get('context_tokens')}。", '',
            environment.get('measurement_notes','')]
    recovery = read_json(root / 'recovery-results.json', {})
    if recovery:
        lines += ['', '## 导出故障修复后的恢复（独立记录）', '', '使用原任务已生成的课程和音频重新导出，没有重新调用模型，也没有把首次失败改为成功。', '',
            '| 案例 | 恢复状态 | 导出秒 | 工程检查 | 说明 |', '|---|---|---:|---|---|']
        for name, result in recovery.items():
            lines.append(f"| {name} | {result['status']} | {result.get('export_seconds')} | {result.get('engineering_passed')} | {result.get('notes','')} |")
    lines += ['', '## 文件与复查', '',
        '每项原始 PPT/视频位于 `tasks/jobs/<job_id>/`；HTML 报告提供链接。`reviews/` 保存实际视频代表帧及完整讲稿。打包文件包含输入、来源许可、统计与抽查，不包含大体积完整教材、模型记录及所有生成媒体。', '',
        '关键词提及不等于知识正确。人工结论只覆盖注明的讲稿与抽查帧，不是独立盲评或整段视频逐帧验收；目前由同一评估者查阅原文和输出。']
    findings = root / 'FINDINGS.md'
    if findings.is_file():
        lines += ['', findings.read_text(encoding='utf-8')]
    (root / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    import csv
    with (root / 'results.csv').open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=list(csv_rows[0]) if csv_rows else []); writer.writeheader(); writer.writerows(csv_rows)
    overview = {'expected': len(dataset['cases']), 'executed': len(done), 'completed': success,
        'failed': len(done) - success, 'complete_run': len(done) == len(dataset['cases']),
        'median_generation_seconds': statistics.median([row['generation_seconds'] for row in done]) if done else None,
        'engineering_passed': sum(engineering_ok(row) for row in done), 'manual_review_counts': dict(reviews),
        'breakdown': breakdown, 'paired_comparisons': paired,
        'input_tokens': sum(row.get('metrics', {}).get('input_tokens') or 0 for row in done),
        'generated_tokens': sum(row.get('metrics', {}).get('generated_tokens') or 0 for row in done),
        'generation_seconds': round(sum(row['generation_seconds'] for row in done), 3),
        'recovery_completed': sum(row['status'] == 'completed' for row in recovery.values())}
    write_json(root / 'summary.json', overview)
    intro = introduction(read_json(SPEC))
    # The spec defines presets; the run records the actual local model override.
    if config.get('model'):
        intro = intro.replace('qwen3.5:9b', config['model'])
    (root / 'INTRODUCTION.md').write_text(intro, encoding='utf-8')
    gallery = ''.join(f'<section><h3>{html.escape(case["id"])}</h3><img src="reviews/{case["id"]}/frames.png" loading="lazy" alt="实际视频代表帧"></section>'
        for case in dataset['cases'] if (root / 'reviews' / case['id'] / 'frames.png').is_file())
    document = report_html(root, dataset, results, manual, overview, gallery)
    (root / 'REPORT.html').write_text(document, encoding='utf-8')
    return overview


def report_html(root, dataset, results, manual, overview, gallery):
    escape = lambda value: html.escape(str(value))
    def display(value): return '-' if value is None else escape(value)
    rows = []
    for case in dataset['cases']:
        row = results.get(case['id'], {}); metric = row.get('metrics', {}); art = metric.get('artifacts', {})
        review = manual.get(case['id'], {}); status = row.get('status','pending')
        engineering = engineering_ok(row)
        first = f'<a href="inputs/{escape(case["id"])}.pdf">{escape(case["id"])}</a>'
        if status == 'completed':
            folder = 'tasks/jobs/' + escape(row['job_id'])
            first += f'<br><a href="{folder}/lesson.pptx">PPT</a> · <a href="{folder}/lesson.mp4">视频</a>'
        anchor = metric.get('anchor_mention_ratio'); f1 = metric.get('source_word_f1')
        cells = [first, escape(case['domain']), str(case['pages']), '文字' if case['format']=='text' else 'OCR',
            {'completed':'完成','failed':'失败','pending':'待运行'}.get(status,status), '通过' if engineering else ('未完成' if status=='pending' else '未通过'),
            display(row.get('generation_seconds')), f"{display(metric.get('input_tokens'))} / {display(metric.get('generated_tokens'))}",
            f"{display(metric.get('ocr_pages'))} / {case['pages']}", display(round(f1*100,1) if f1 is not None else None),
            f"{display(art.get('slides'))} / {display(art.get('svg_count'))}", display(art.get('video_seconds')),
            display(round(anchor*100,1) if anchor is not None else None), escape(review.get('overall','未复核'))]
        detail = '；'.join(filter(None, [row.get('error'), row.get('audit_error'), review.get('notes','')]))
        rows.append('<tr data-domain="'+escape(case['domain'])+'" data-pages="'+str(case['pages'])+'" data-format="'+case['format']+'"><td>'+ '</td><td>'.join(cells) + '</td></tr>')
        if detail: rows.append('<tr class="detail" data-domain="'+escape(case['domain'])+'" data-pages="'+str(case['pages'])+'" data-format="'+case['format']+'"><td colspan="14">'+escape(detail)+'</td></tr>')
    sources = read_json(SPEC)['sources']
    domains = ''.join('<option>'+escape(source['domain'])+'</option>' for source in sources)
    citations = ''.join(f'<li><a href="{escape(source["url"])}">{escape(source["title"])}</a>：{escape(source["license"])}；原 PDF 第 {source["start_page"]} 页起。</li>' for source in sources)
    config = read_json(root / 'run.json', {})
    findings_link = ' · <a href="FINDINGS.md">实测结论与问题</a>' if (root / 'FINDINGS.md').is_file() else ''
    reviewed = overview['manual_review_counts']
    quality = f"教学抽查：{reviewed.get('pass',0)} 项通过，{reviewed.get('partial',0)} 项部分满足，{reviewed.get('fail',0)} 项未通过，{reviewed.get('not_reviewed',0)} 项未复核。整体标签包含首轮能否完成；不能当作知识点准确率。"
    group_rows = []
    for key, groups in overview['breakdown'].items():
        for name, stats in groups.items():
            group_rows.append(f'<tr><td>{escape(key)}={escape(name)}</td><td>{stats["completed"]} / {stats["attempts"]}</td><td>{stats["engineering_passed"]}</td><td>{stats["median_attempt_seconds"]}</td><td>{display(stats["median_completed_seconds"])}</td></tr>')
    group_table = '<section><h2>分组结果</h2><div class="table"><table><tr><th>分组</th><th>首次完成 / 尝试</th><th>工程检查通过</th><th>尝试中位秒</th><th>完成项中位秒</th></tr>'+''.join(group_rows)+'</table></div><p>配对与不同页数并非独立随机样本；失败项也计入尝试耗时。</p></section>'
    environment = read_json(root / 'environment.json', {})
    machine = '<section><h2>环境与计量</h2><p>' + escape(environment.get('cpu','未记录')) + '；内存 ' + display(round(environment.get('ram_bytes',0)/1024**3,1)) + ' GiB；' + escape(environment.get('gpu','未记录')) + '</p><p>Ollama ' + escape(environment.get('ollama_version','未记录')) + '；应用基线 ' + escape(config.get('git_commit','未运行')) + '</p><p>' + escape(environment.get('measurement_notes','')) + '</p><p>总输入 token：' + str(overview['input_tokens']) + '；总输出 token：' + str(overview['generated_tokens']) + '。使用本机 Ollama，未调用 DeepSeek API；本轮没有 API 费用。</p></section>'
    recovery = read_json(root / 'recovery-results.json', {})
    recovery_html = ''
    if recovery:
        links = []
        for name, row in recovery.items():
            note = escape(row.get('notes',''))
            if row['status'] == 'completed':
                links.append(f'<li>{escape(name)}：恢复导出 {display(row.get("export_seconds"))} 秒；<a href="recoveries/{escape(name)}/lesson.pptx">PPT</a> · <a href="recoveries/{escape(name)}/lesson.mp4">视频</a>。{note}<br><img src="recovery-reviews/{escape(name)}/frames.png" loading="lazy" alt="恢复后的实际视频帧"></li>')
            else: links.append(f'<li>{escape(name)}：{escape(row["status"])}；{note}</li>')
        recovery_html = '<section><h2>修复后的独立恢复记录</h2><p>沿用首次任务的课程与音频重新导出，不再请求模型。首次失败状态与计量保留；工程恢复不修正原讲稿中的知识错误。</p><ul>'+''.join(links)+'</ul></section>'
    spec = read_json(SPEC)
    description = f"{len(spec['sources'])} 个学科／学段 × {' / '.join(map(str, spec['page_counts']))} 页 × 文字版 / 纯图像版，共 {len(dataset['cases'])} 项。"
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Book2Course 教材 Benchmark</title>
<style>body{font:17px/1.7 system-ui;margin:0;background:#f4f7fb;color:#17283a}main{max-width:1440px;margin:36px auto;padding:0 28px}h1{font-size:38px;margin-bottom:8px}h2{font-size:27px}.cards{display:flex;gap:16px;flex-wrap:wrap}.card,section,.table{background:white;border:1px solid #d8e1ed;border-radius:14px;padding:22px;margin:18px 0}.card strong{display:block;font-size:30px;color:#1762a8}.filters{display:flex;gap:16px;flex-wrap:wrap;margin:22px 0}select{font:inherit;padding:8px 14px;border:1px solid #aebccc;border-radius:8px}.table{overflow:auto;padding:0}table{border-collapse:collapse;font-size:16px;width:100%}th,td{padding:12px;border-bottom:1px solid #d8e1ed;text-align:left;white-space:nowrap}th{background:#edf3fb}.detail td{white-space:normal;color:#526377;padding-top:0}a{color:#1762a8}img{max-width:100%;border-radius:8px}.method{color:#4d6077}summary{cursor:pointer;font-weight:650}section{break-inside:avoid}@media print{select,.filters{display:none}body{background:white}.table{overflow:visible}table{font-size:11px}main{padding:0}}</style><main>
<p>Book2Course · 真实生产流程评估</p><h1>多领域教材与 OCR Benchmark</h1><p>''' + escape(description) + '''</p>
<div class="cards"><div class="card">已执行<strong>''' + str(overview['executed']) + ' / ' + str(overview['expected']) + '''</strong></div><div class="card">首次生成完成<strong>''' + str(overview['completed']) + '''</strong></div><div class="card">首次生成失败<strong>''' + str(overview['failed']) + '''</strong></div><div class="card">尝试耗时中位数<strong>''' + display(round(overview['median_generation_seconds'],1) if overview['median_generation_seconds'] is not None else None) + ''' 秒</strong></div></div>
<p class="method">模型：''' + escape(config.get('model','未运行')) + '''；可选深度推理：''' + ('开启' if config.get('semantic_thinking') else '关闭') + '''；系统语音；学术课堂；直接生成。一次外层尝试，内部修复计入耗时与 token。工程完成不等于教学正确；人工评价只覆盖已注明的抽查。</p>
<p><strong>''' + quality + '''</strong></p>
<p><a href="INTRODUCTION.md">完整 Benchmark 介绍</a> · <a href="results.csv">CSV 数据</a> · <a href="results.json">原始统计</a> · <a href="REPORT.md">文字报告</a>''' + findings_link + '''</p>
<div class="filters"><label>领域 <select id="domain"><option value="">全部</option>''' + domains + '''</select></label><label>页数 <select id="pages"><option value="">全部</option><option>2</option><option>6</option><option>12</option></select></label><label>输入 <select id="format"><option value="">全部</option><option value="text">文字</option><option value="ocr">OCR</option></select></label></div>
<div class="table"><table><thead><tr><th>案例 / 输入PDF</th><th>领域</th><th>页数</th><th>输入</th><th>生成</th><th>工程检查</th><th>生成秒</th><th>输入 / 输出token</th><th>OCR页</th><th>词项F1%</th><th>PPT页 / SVG数</th><th>视频秒</th><th>锚点提及%</th><th>人工抽查</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table></div>
''' + group_table + machine + '''<section><h2>如何解释结果</h2><ul><li>图像版是 180 DPI 清晰模拟扫描，不含隐藏文字层。未覆盖拍照、手写、污渍或严重倾斜。</li><li>F1 是相对文字版提取的词项相似度，忽略语序；原生提取也可能拼接单词，因此不是 OCR 准确率。</li><li>锚点关键词出现不证明单位、条件、角色或箭头正确。SVG 数量包含模板及素材；实际视频帧与口播另做人工抽查。</li><li>共享画面预览不是 Microsoft PowerPoint 应用截图；ZIP/SVG、备注、边界和视频解码有自动验证。</li><li>2 / 6 / 12 页是测试规模，没有设置应用生成长度上限。本轮没有验收整本书，也没有估计重复运行成功概率。</li><li>人工结论由同一评估者查阅原文与输出，仅覆盖注明的讲稿和代表帧；不是独立盲评或整段逐帧验收。</li><li>初始失败与修复后的恢复分别保留，不合并成首次成功率。</li><li>完整 PPT/视频链接需要本机结果目录或包含媒体的完整 ZIP；轻量输入与结果 ZIP 不含这些媒体。</li></ul><h3>教材来源与许可</h3><ul>''' + citations + '''</ul><p>输入与衍生选页为非商业评估，遵循各书原始许可，不改为项目 MIT 许可。</p></section><h2>实际视频代表帧</h2>''' + gallery + recovery_html + '''</main><script>for(const element of document.querySelectorAll('select'))element.addEventListener('change',()=>{for(const row of document.querySelectorAll('tbody tr[data-domain]'))row.hidden=['domain','pages','format'].some(key=>document.getElementById(key).value&&row.dataset[key]!==document.getElementById(key).value)});</script></html>'''


def package(root, include_media=False):
    report(root)
    path = root / ('benchmark-full-review.zip' if include_media else 'benchmark-inputs-and-results.zip')
    with ZipFile(path, 'w', ZIP_DEFLATED) as out:
        for name in ('dataset.json','run.json','environment.json','results.json','baseline-first-results.json','results.csv','summary.json','REPORT.md','REPORT.html','INTRODUCTION.md','FINDINGS.md','DATASET_CAVEATS.md','manual-review.json','recovery-results.json','validation.json','input-contact.png'):
            file = root / name
            if file.is_file(): out.write(file, name)
        out.write(SPEC, 'definition/spec.json'); out.write(RUBRIC, 'definition/rubric.json')
        if (SPEC.parent / 'README.md').is_file(): out.write(SPEC.parent / 'README.md', 'definition/README.md')
        for folder in ('inputs','reviews','references','recovery-reviews'):
            for file in (root / folder).rglob('*'):
                if file.is_file(): out.write(file, file.relative_to(root).as_posix())
        for file in (root / 'sources').glob('*-license.txt'): out.write(file, 'licenses/' + file.name)
        if include_media:
            for row in read_json(root / 'results.json', {}).values():
                for name in ('lesson.pptx','lesson.mp4'):
                    file = root / 'tasks/jobs' / row['job_id'] / name
                    if file.is_file(): out.write(file, file.relative_to(root).as_posix())
            for folder in (root / 'recoveries').glob('*'):
                for name in ('lesson.pptx','lesson.mp4'):
                    file = folder / name
                    if file.is_file(): out.write(file, file.relative_to(root).as_posix())
    print('PACKAGE', str(path.resolve()))


def main():
    global SPEC, RUBRIC
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare','run','audit','recover','report','package'])
    parser.add_argument('--root', type=Path, default=Path('data/textbook-benchmark'))
    parser.add_argument('--suite', type=Path, help='Versioned directory containing spec.json and rubric.json; defaults to textbooks_v1')
    parser.add_argument('--model')
    parser.add_argument('--allow-ollama-cloud',action='store_true',
        help='Explicitly consent to a separate Ollama cloud comparison on hash-pinned public inputs; DeepSeek remains excluded')
    parser.add_argument('--cases', help='Optional comma-separated case IDs; omit for the complete suite')
    parser.add_argument('--include-media', action='store_true', help='Include final PPT/videos in the review ZIP, never model caches or credentials')
    args = parser.parse_args(); root = args.root.resolve()
    if args.suite:
        SPEC = args.suite.resolve() / 'spec.json'; RUBRIC = args.suite.resolve() / 'rubric.json'
    if args.command == 'prepare': prepare(root)
    elif args.command == 'run': run(root, args.model, args.cases.split(',') if args.cases else None,
                                  allow_ollama_cloud=args.allow_ollama_cloud)
    elif args.command == 'audit': audit(root)
    elif args.command == 'recover': recover_exports(root)
    elif args.command == 'report': print(json.dumps(report(root), ensure_ascii=False))
    else: package(root, args.include_media)


if __name__ == '__main__': main()
