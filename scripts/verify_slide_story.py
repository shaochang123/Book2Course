"""Rebuild shared visual stories from retained scripts, without new private uploads."""
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
from zhijiang.slide_story import enrich_visual_story
from zhijiang.deck_renderer import render_template_presentation
from zhijiang.video import render_video
from verify_visual_assets import source_audio, inspect

CASES={
    'ml':Path('data/illustration-acceptance/ml'),
    'physics':Path('data/illustration-acceptance/subjects/jobs/jobs/b3051e72ec47420c854e629776c0d5cb'),
    'biology':Path('data/illustration-acceptance/subjects/jobs/jobs/9e24603497ed4e9ebcc1bd45b7d67e29'),
    'logic':Path('data/visual-generalization-v2/jobs/jobs/e3730175013b4a2db08e14f81b6fd7a4'),
    'library':Path('data/visual-generalization-v2/jobs/jobs/255d120dd0db4be68fe84f93df99e769'),
}

def run(name,root,settings,plan_only=False,render_only=False):
    origin=CASES[name];folder=root/name;folder.mkdir(parents=True,exist_ok=True)
    if render_only:
        lesson=Lesson.model_validate_json((folder/'lesson.json').read_text(encoding='utf-8'))
        audio=[folder/f'audio-{i}.wav' for i in range(len(lesson.segments))]
    else:
        lesson,audio=plan(name,origin,folder,settings)
    if plan_only:return {'case':name,'planned':True}
    print(name+': rendering PPT and full video',flush=True)
    render_template_presentation(lesson,folder/'lesson.pptx',audio_files=audio)
    render_video(lesson,audio,folder/'lesson.mp4')
    result=inspect(folder,lesson)
    manifest=json.loads((folder/'presentation-preview/manifest.json').read_text(encoding='utf-8'))
    content=[p for p in manifest['pages'] if p['kind']=='content']
    result.update(case=name,representations=sorted({p.get('representation','existing_scene') for p in content}),
        arrow_pages=sum(p.get('relation_count',0)>0 for p in content),
        rendered_asset_ids=[r['asset_id'] for p in content for r in p.get('illustration_regions',[])],
        max_displayed_characters=max(p.get('displayed_characters',0) for p in content),
        roadmap_pages=sum(p['kind']=='roadmap' for p in manifest['pages']),
        bookends=manifest['bookends'],baseline='retained script/audio; new actual local-model graphic planning')
    assert result['roadmap_pages']==1
    assert {p['kind'] for p in manifest['bookends']}=={'cover','ending'}
    (folder/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return result


def plan(name,origin,folder,settings):
    if (origin/'lesson.json').is_file():
        lesson=Lesson.model_validate_json((origin/'lesson.json').read_text(encoding='utf-8'))
    else:
        import sqlite3
        database=(origin.parents[1]/'jobs.sqlite3').resolve()
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as connection:
            row=connection.execute('SELECT lesson_json FROM jobs WHERE id=?',(origin.name,)).fetchone()
        if not row or not row[0]:raise ValueError('Retained lesson is missing: '+str(origin))
        lesson=Lesson.model_validate_json(row[0])
    audio=[]
    for i,path in enumerate(source_audio(origin,lesson)):
        target=folder/f'audio-{i}.wav';shutil.copyfile(path,target);audio.append(target)
    for i,s in enumerate(lesson.segments,1):
        if s.math_scene or s.visual_scene or i in lesson.animation_report.get('prepared_scenes',[]):
            sub=Path('math' if s.math_scene else 'visual')/f'scene-{i:02d}'
            (folder/sub).mkdir(parents=True,exist_ok=True)
            for filename in ['clip.mp4','summary.png','summary.svg']:
                shutil.copyfile(origin/sub/filename,folder/sub/filename)
    client=OllamaClient(settings.llm_base_url,settings.llm_model,semantic_thinking=settings.ollama_semantic_thinking,
                        prefer_json=True,num_gpu=settings.ollama_num_gpu)
    try:
        print(name+': planning compact diagrams and navigation with local model',flush=True)
        enrich_visual_story(lesson,client,folder=folder/'slide-story')
    finally:
        (folder/'model-calls.json').write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        client.close()
    (folder/'lesson.json').write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
    (folder/'presentation-plan.json').write_text(json.dumps(lesson.deck_plan,ensure_ascii=False,indent=2),encoding='utf-8')
    return lesson,audio

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=[*CASES,'all'],default='all')
    parser.add_argument('--output',type=Path,default=Path('data/story-repair'))
    actions=parser.add_mutually_exclusive_group()
    actions.add_argument('--plan-only',action='store_true')
    actions.add_argument('--render-only',action='store_true');args=parser.parse_args()
    settings=Settings.from_env()
    if not args.render_only and not settings.llm_is_local:raise SystemExit('This regression uses the local model only.')
    results=[]
    for name in CASES if args.case=='all' else [args.case]:
        results.append(run(name,args.output,settings,args.plan_only,args.render_only))
        (args.output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
