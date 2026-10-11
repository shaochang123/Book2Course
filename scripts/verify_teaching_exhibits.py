"""Actual local-model diagram regression, reusing disclosed scripts and audio."""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zhijiang.agents import OllamaClient
from zhijiang.config import Settings
from zhijiang.models import Lesson
from zhijiang.teaching_exhibits import enrich_teaching_exhibits
from zhijiang.deck_renderer import render_template_presentation
from zhijiang.video import render_video
from verify_visual_assets import inspect

CASES=['ml','physics','biology','logic','library']

def run(name,root,settings,render_only=False,plan_only=False,segments=()):
    origin=Path('data/story-repair')/name;folder=root/name;folder.mkdir(parents=True,exist_ok=True)
    if not render_only:
        lesson=Lesson.model_validate_json(((folder if segments and (folder/'lesson.json').is_file() else origin)/'lesson.json').read_text(encoding='utf-8'))
        for i,s in enumerate(lesson.segments,1):
            shutil.copyfile(origin/f'audio-{i-1}.wav',folder/f'audio-{i-1}.wav')
            if s.math_scene or s.visual_scene or i in lesson.animation_report.get('prepared_scenes',[]):
                sub=Path('math' if s.math_scene else 'visual')/f'scene-{i:02d}'
                (folder/sub).mkdir(parents=True,exist_ok=True)
                for filename in ['clip.mp4','summary.png','summary.svg']:
                    shutil.copyfile(origin/sub/filename,folder/sub/filename)
        client=OllamaClient(settings.llm_base_url,settings.llm_model,semantic_thinking=False,
            prefer_json=True,num_gpu=settings.ollama_num_gpu,context_tokens=settings.ollama_context_tokens)
        original_script=[s.narration for s in lesson.segments]
        original_plan=lesson.deck_plan
        if segments:lesson.deck_plan={**original_plan,'pages':[p for p in original_plan['pages'] if p['segment_id'] in segments]}
        try:
            print(name+': planning specific examples with actual local model',flush=True)
            enrich_teaching_exhibits(lesson,client,folder=folder/'teaching-exhibits')
            if segments:
                previous=original_plan.get('teaching_exhibits',{}).get('pages',{})
                pages={**previous,**lesson.deck_plan['teaching_exhibits']['pages']}
                lesson.deck_plan={**original_plan,'teaching_exhibits':{**lesson.deck_plan['teaching_exhibits'],'pages':pages,
                    'accepted':sum(p['accepted'] for p in pages.values()),'rejected':sum(not p['accepted'] for p in pages.values())}}
        finally:
            (folder/('model-calls-repair.json' if segments else 'model-calls.json')).write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
            client.close()
        assert original_script==[s.narration for s in lesson.segments]
        (folder/'lesson.json').write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
        print(name+': '+json.dumps({k:v for k,v in lesson.deck_plan['teaching_exhibits'].items() if k!='pages'},ensure_ascii=False),flush=True)
    else:lesson=Lesson.model_validate_json((folder/'lesson.json').read_text(encoding='utf-8'))
    if plan_only:return
    audio=[folder/f'audio-{i}.wav' for i in range(len(lesson.segments))]
    print(name+': rendering shared PPT and full video',flush=True)
    render_template_presentation(lesson,folder/'lesson.pptx',audio_files=audio)
    render_video(lesson,audio,folder/'lesson.mp4')
    result=inspect(folder,lesson)
    manifest=json.loads((folder/'presentation-preview/manifest.json').read_text(encoding='utf-8'))
    content=[p for p in manifest['pages'] if p['kind']=='content']
    result.update(case=name,exhibit_accepted=lesson.deck_plan['teaching_exhibits']['accepted'],
        exhibit_rejected=lesson.deck_plan['teaching_exhibits']['rejected'],
        forms=sorted({p.get('representation','existing_scene') for p in content}),
        compositions=sorted({p['composition'] for p in content}),
        arrow_pages=sum(p.get('relation_count',0)>0 for p in content),
        pictures=sum(len(p.get('illustration_regions',[])) for p in content),
        baseline='retained script/audio and continuous scenes; new local-model exhibit planning')
    (folder/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=[*CASES,'all'],default='all')
    parser.add_argument('--output',type=Path,default=Path('data/visual-variety-repair'))
    parser.add_argument('--render-only',action='store_true');parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--segments',nargs='+',type=int,default=[],help='Replan only selected segment IDs of a saved course, without hand-editing exhibits.')
    args=parser.parse_args()
    settings=Settings.from_env()
    if not args.render_only and not settings.llm_is_local:raise SystemExit('Private retained scripts must use the local model.')
    for name in CASES if args.case=='all' else [args.case]:run(name,args.output,settings,args.render_only,args.plan_only,args.segments)

if __name__=='__main__':main()
