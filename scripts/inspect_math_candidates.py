"""Preview rejected, numerically executable candidates for human assessment.

This diagnostic never changes the production result or counts a rejected scene
as a successful lesson. It picks the last executable candidate in topic order.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from zhijiang.config import Settings
from zhijiang.models import VisualScenePlan
from zhijiang.speech import SystemSpeech
from zhijiang.visual_planning import verify_visual_scene,VisualSceneError
from zhijiang.visual_media import visual_summary_svg, render_visual_scene
from zhijiang.math_media import render_summary_png
from scripts.verify_math_artifacts import frame_at,media_check


def inspect(case: Path, render: bool):
    results=json.loads((case/'results.json').read_text(encoding='utf-8'))
    for topic in results['topics']:
        if topic['generated']:continue
        path=case/f"topic-{topic['index']:02d}"/'visual-planning.json'
        if not path.is_file():continue
        for draft in reversed(json.loads(path.read_text(encoding='utf-8'))):
            if 'scene' not in draft:continue
            try:
                scene=VisualScenePlan.model_validate(draft['scene']);verify_visual_scene(scene)
            except (ValueError,VisualSceneError):continue
            folder=case/'rejected-preview';folder.mkdir(exist_ok=True)
            # Only a diagnostic banner is added; mathematical data is untouched.
            scene.question=('未批准草稿 · '+scene.question)[:120]
            (folder/'scene.json').write_text(scene.model_dump_json(indent=2),encoding='utf-8')
            (folder/'summary.svg').write_text(visual_summary_svg(scene),encoding='utf-8')
            render_summary_png(folder/'summary.svg',folder/'summary.png')
            record={'approved':False,'counts_as_generated':False,'human_review':'pending',
                'topic':topic['title'],'selection':'first failed topic with last numerically executable candidate',
                'production_error':topic['error'],'candidate_error':draft.get('error','')}
            if render:
                asset=render_visual_scene(scene,SystemSpeech(Settings.from_env().system_voice),folder/'render')
                record['media']=media_check(folder/'render/clip.mp4')
                for i,timing in enumerate(asset['timing'],1):
                    for label,f in [('mid',.28),('end',.92)]:
                        frame_at(folder/'render/clip.mp4',timing['start']+timing['duration']*f).save(folder/f'beat-{i:02d}-{label}.png')
            (folder/'assessment.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            return record
    return {'approved':False,'preview_available':False,'reason':'No rejected candidate passed numeric execution'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir',type=Path,required=True)
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    print(json.dumps(inspect(args.case_dir.resolve(),args.render),ensure_ascii=False,indent=2))
