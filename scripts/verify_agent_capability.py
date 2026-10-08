"""Replan generated failure cases with unchanged local model and input pages.

This is a diagnostic regression, not a blind generalization benchmark. Titles
and original citations are copied from a previous generated lesson, never
authored as a storyboard. Source input and generated content remain local.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from urllib.request import urlopen
from pathlib import Path

from zhijiang.agents import OllamaClient
from zhijiang.config import Settings
from zhijiang.models import Lesson, SourceDocument
from zhijiang.teaching_design import (plan_teaching_representation, compile_teaching_scene,
                                     prepare_source_assets)
from zhijiang.visual_media import render_visual_scene
from zhijiang.speech import SystemSpeech


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--segments', required=True, help='One-based segment indices, for example 1,3')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--thinking', action='store_true', help='Compare optional reasoning on the same model; baseline configuration is used otherwise.')
    args = parser.parse_args()
    settings = Settings.from_env()
    if not settings.llm_is_local or settings.llm_provider != 'ollama':
        parser.error('This comparison requires a local Ollama endpoint.')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    baseline = args.baseline.resolve()
    lesson = Lesson.model_validate_json((baseline/'lesson.json').read_text(encoding='utf-8'))
    document = SourceDocument.model_validate_json((baseline/'parsed-source.json').read_text(encoding='utf-8'))
    previous = json.loads((baseline/'input.json').read_text(encoding='utf-8'))
    pdf = Path(previous['source_pdf'])
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != previous['sha256']:
        parser.error('The PDF no longer matches the baseline source hash.')
    model = previous['model']
    thinking = args.thinking or previous['semantic_thinking']
    client = OllamaClient(settings.llm_base_url, model,
                          semantic_thinking=thinking)
    generate = client.generate; calls = []
    def recorded(schema, instruction, material):
        start = time.monotonic(); record = {'schema': schema.__name__}
        try:
            value = generate(schema, instruction, material)
            record['result'] = value.model_dump()
            return value
        except Exception as exc:
            record['error'] = str(exc)
            raise
        finally:
            if client.call_metrics:
                record['metrics'] = client.call_metrics[-1]
            if client.invalid_outputs:
                (out/'model-format-errors.json').write_text(json.dumps(client.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
            record['seconds'] = round(time.monotonic()-start, 3); calls.append(record)
            (out/'model-calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding='utf-8')
            print(record['schema'], record['seconds'], record.get('error', 'decoded'), flush=True)
    client.generate = recorded
    protocol = {'baseline': str(baseline), 'model': model, 'endpoint': settings.llm_base_url,
        'semantic_thinking': thinking, 'pages': previous['pages'],
        'source_sha256': previous['sha256'], 'prompt': '', 'blind': False,
        'note': 'Same installed model and PDF pages; historical baseline server version may differ.'}
    try:
        with urlopen(settings.llm_base_url.rstrip('/')+'/api/version',timeout=5) as response:
            protocol['ollama_version'] = json.load(response)['version']
    except (OSError,ValueError,KeyError):
        protocol['ollama_version'] = 'unavailable'
    (out/'input.json').write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding='utf-8')
    assets = prepare_source_assets(pdf, out/'source-pages', document) if args.render else None
    results = []
    for index in [int(value) for value in args.segments.split(',')]:
        segment = lesson.segments[index-1].model_copy(deep=True)
        segment.visual_scene = None
        result = {'segment': index, 'title': segment.title, 'before': lesson.segments[index-1].model_dump()}
        try:
            draft, report, errors = plan_teaching_representation(client, segment, document, '',
                pdf_path=pdf, force_diagram=True, diagnostic_output=out/f'teaching-design-{index:02d}.json',
                on_phase=lambda name: print(index, name, flush=True))
            page = next(p for p in document.pages if p.page == report['topic_scope']['page'])
            scene = compile_teaching_scene(draft, segment, report, source_assets=assets,
                                          pdf_path=pdf, source_text=page.text)
            result.update(status='generated', after=scene.model_dump(), rejected_designs=errors)
            if args.render:
                result['asset'] = render_visual_scene(scene, SystemSpeech(settings.system_voice), out/f'scene-{index:02d}')
        except Exception as exc:
            result.update(status='rejected', error=str(exc))
            print('REJECTED', str(exc), flush=True)
        results.append(result)
        (out/'comparison.json').write_text(json.dumps({'protocol': protocol, 'results': results},
            ensure_ascii=False, indent=2), encoding='utf-8')
    print('Results:', [(r['title'], r['status']) for r in results], flush=True)


if __name__ == '__main__':
    main()
