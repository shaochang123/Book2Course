"""Run the same source-driven repair workflow on the frozen eight-case corpus."""
import argparse
import hashlib
import json
from pathlib import Path

from zhijiang.agents import OllamaClient, validate_lesson
from zhijiang.config import Settings
from zhijiang.math_sources import read_math_pdf
from zhijiang.mathematical_planning import plan_constructed_lesson
from zhijiang.visual_media import render_visual_assets
from zhijiang.video import render_video
from zhijiang.presentation import render_presentation
from zhijiang.speech import SystemSpeech
from scripts.verify_math_artifacts import media_check, frame_at


def code_hashes():
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('zhijiang').rglob('*'))
        if p.is_file() and p.suffix in {'.py','.js','.html','.css','.ps1'} and '__pycache__' not in p.parts}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case')
    parser.add_argument('--model',default='qwen3.5:9b')
    parser.add_argument('--review-model',default='')
    parser.add_argument('--math-model',default='',help='Optional separate construction/behavior model, preserving the page reader and reviewer')
    parser.add_argument('--thinking-level',choices=['low','medium','high'],default=None,help='Use only exact levels advertised by the model; otherwise retain boolean thinking')
    parser.add_argument('--semantic-thinking',action=argparse.BooleanOptionalAction,default=True,
        help='Record and compare the actual supported thinking switch; does not change local configuration')
    parser.add_argument('--output',type=Path,default=Path('data/math-repair/acceptance'))
    parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--resume-draft',action='store_true',help='Debug only: repair the last saved model draft; final corpus must omit this flag')
    args=parser.parse_args();settings=Settings.from_env()
    manifest=json.loads(Path('examples/math-level-sources.json').read_text(encoding='utf-8'))
    cases=[c for c in manifest['cases'] if not args.case or c['id']==args.case]
    if not cases:parser.error('Unknown case; the validation selection must not be empty.')
    frozen=code_hashes()
    args.output.mkdir(exist_ok=True,parents=True)
    def model_progress(*v):
        print('LLM',*v,flush=True)
        (args.output/'live-model-errors.json').write_text(json.dumps(client.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
        (args.output/'live-model-calls.json').write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        (args.output/'live-model-requests.json').write_text(json.dumps(client.call_requests,ensure_ascii=False,indent=2),encoding='utf-8')
        (args.output/'live-activity.json').write_text(json.dumps(client.activity,ensure_ascii=False),encoding='utf-8')
    client=OllamaClient(settings.llm_base_url,args.model,semantic_thinking=args.semantic_thinking,prefer_json=True,
        progress=model_progress,num_gpu=settings.ollama_num_gpu,thinking_level=args.thinking_level or settings.ollama_thinking_level)
    reviewer=OllamaClient(settings.llm_base_url,args.review_model,semantic_thinking=args.semantic_thinking,prefer_json=True,
        num_gpu=settings.ollama_num_gpu,thinking_level=args.thinking_level or settings.ollama_thinking_level) if args.review_model else None
    planner=OllamaClient(settings.llm_base_url,args.math_model,semantic_thinking=args.semantic_thinking,prefer_json=True,
        progress=model_progress,num_gpu=settings.ollama_num_gpu,thinking_level=args.thinking_level or settings.ollama_thinking_level) if args.math_model else None
    results=[]
    try:
        for case in cases:
            if code_hashes()!=frozen:raise RuntimeError('Implementation changed during the run; start a new validation.')
            folder=args.output/case['id'];folder.mkdir(parents=True,exist_ok=True)
            record={'id':case['id'],'source':case,'code_sha256':frozen,
                'model':client.model,'math_model':args.math_model or client.model,'review_model':args.review_model,
                'requested_thinking_level':args.thinking_level or settings.ollama_thinking_level,'semantic_thinking':args.semantic_thinking,'authored_scene':False,'accepted':False,
                'resumed_model_draft':args.resume_draft}
            print('CASE',case['id'],flush=True)
            try:
                pdf=Path(case['local_pdf']);data=pdf.read_bytes()
                if hashlib.sha256(data).hexdigest()!=case['sha256']:raise ValueError('Source hash changed')
                before_source=len(client.call_metrics)
                document=read_math_pdf(client,data,pdf.name,pages=case['pdf_pages'],
                    cache_dir=Path('data/math-repair/sources')/case['id'],progress=lambda *v:print(*v,flush=True))
                (folder/'source.json').write_text(document.model_dump_json(indent=2),encoding='utf-8')
                record['source_cache_reused']=not any(c['stage']=='MathSourceReading' for c in client.call_metrics[before_source:])
                from zhijiang.models import Lesson
                saved=folder/'lesson.json'
                if args.resume and saved.exists():lesson=Lesson.model_validate_json(saved.read_text(encoding='utf-8'))
                else:
                    initial=None
                    if args.resume_draft:
                        from zhijiang.math_construction import MathProgramDraft
                        history=json.loads((folder/'planning.json').read_text(encoding='utf-8'))
                        previous=next(a['program'] for a in reversed(history['attempts']) if a.get('program'))
                        # Only the model's object graph is reused for debugging.
                        # Failed behavior is discarded, not relabeled as valid.
                        previous['operations']=[{'narration':'重新规划实际对象的连续运动与讲解操作。'}]*3
                        initial=MathProgramDraft.model_validate(previous)
                    lesson=plan_constructed_lesson(client,document,
                        '演示当前选页的核心数学问题，保留来源例子和必要条件。用连续数学对象变化解释原因。',
                        progress=lambda *v:print(*v,flush=True),draft_output=folder/'planning.json',initial_program=initial,
                        review_client=reviewer,
                        planning_client=planner,
                        source_image_loader=lambda page:__import__('zhijiang.math_sources',fromlist=['page_png']).page_png(data,page))
                validate_lesson(document,lesson)
                saved.write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
                record['planned']=True
                if not args.plan_only:
                    speech=SystemSpeech(settings.system_voice)
                    render_visual_assets(lesson,speech,folder,lambda *v:print(*v,flush=True))
                    saved.write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
                    audios=[folder/'visual'/f'scene-{i+1:02d}'/'narration.wav' for i in range(len(lesson.segments))]
                    render_video(lesson,audios,folder/'lesson.mp4')
                    render_presentation(lesson,folder/'lesson.pptx')
                    record['media']=media_check(folder/'lesson.mp4')
                    for i,segment in enumerate(lesson.segments,1):
                        timings=lesson.animation_report['assets'][i-1]['timing']
                        for j,timing in enumerate(timings,1):
                            for name,fraction in [('mid',.28),('end',.92)]:
                                frame_at(folder/'visual'/f'scene-{i:02d}'/'clip.mp4',timing['start']+timing.get('source_seconds',0)+(timing['duration']-timing.get('source_seconds',0))*fraction).save(folder/f'scene-{i}-beat-{j}-{name}.png')
                    record['rendered']=True
                if code_hashes()!=frozen:raise RuntimeError('Implementation changed during generation; this run cannot be accepted.')
                record['automatic_checks_passed']=True
                record['manual_review']='pending'
            except Exception as exc:
                record['error']=f'{type(exc).__name__}: {exc}';print('FAILED',record['error'],flush=True)
            results.append(record)
            (folder/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            args.output.mkdir(exist_ok=True,parents=True)
            (args.output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        args.output.mkdir(exist_ok=True,parents=True)
        (args.output/'model-calls.json').write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        (args.output/'model-errors.json').write_text(json.dumps(client.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
        client.close()
        if reviewer:
            (args.output/'independent-review-calls.json').write_text(json.dumps(reviewer.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
            (args.output/'independent-review-format-errors.json').write_text(json.dumps(reviewer.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
            reviewer.close()
        if planner:
            (args.output/'mathematical-planning-calls.json').write_text(json.dumps(planner.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
            (args.output/'mathematical-planning-format-errors.json').write_text(json.dumps(planner.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
            planner.close()
    if not all(r.get('automatic_checks_passed') for r in results):raise SystemExit(1)


if __name__=='__main__':main()
