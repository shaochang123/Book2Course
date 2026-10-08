"""Render an authored contract fixture, never a textbook generalization result."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from zhijiang.config import Settings
from zhijiang.models import Evidence, GeometryConstraint, SceneObject, VisualBeat, VisualScenePlan
from zhijiang.speech import SystemSpeech
from zhijiang.visual_media import render_visual_scene, visual_summary_svg
from zhijiang.math_media import render_summary_png
from scripts.verify_math_artifacts import frame_at, media_check


def verify(folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    scene=VisualScenePlan(domain='原创执行器测试',question='圆周点与圆弧是否保持真实位置和颜色？',
        parameters={'t':0},x_range=[-2,2],y_range=[-1.5,1.5],
        evidence=Evidence(page=1,quote='原创执行器契约，不是教材来源或模型自动生成验收。'),
        objects=[SceneObject(id='circle',kind='circle',position=['0','0'],radius='1'),
            SceneObject(id='point',position=['cos(t)','sin(t)']),
            SceneObject(id='arc',kind='parametric_curve',domain=[0,1],
                parametric_expression=['cos(t*x)','sin(t*x)'],color='#FFA458')],
        geometry_constraints=[GeometryConstraint(kind='on_circle',objects=['point','circle'],
            source_quote='原创执行器契约，不是教材来源或模型自动生成验收。')],
        beats=[VisualBeat(narration='先观察固定的圆和圆周上的点，圆弧尚未展开。'),
            VisualBeat(narration='移动圆周上的点，同时展开同一圆周上的橙色圆弧。',parameters={'t':1}),
            VisualBeat(narration='保留最后的位置，圆弧终点和移动的点应当保持重合。')])
    (folder/'fixture.json').write_text(scene.model_dump_json(indent=2),encoding='utf-8')
    svg=visual_summary_svg(scene)
    (folder/'summary.svg').write_text(svg,encoding='utf-8')
    root=ET.fromstring(svg);ns={'s':'http://www.w3.org/2000/svg'}
    circle,point=root.findall('.//s:circle',ns)
    distance=math.dist([float(circle.get(k)) for k in ('cx','cy')],
                       [float(point.get(k)) for k in ('cx','cy')])
    assert abs(distance-float(circle.get('r')))<1e-6,'SVG unequal units'
    render_summary_png(folder/'summary.svg',folder/'summary.png')
    asset=render_visual_scene(scene,SystemSpeech(Settings.from_env().system_voice),folder/'render')
    counts=[]
    for label,fraction in [('mid',.3),('end',.95)]:
        timing=asset['timing'][1]
        frame=frame_at(folder/'render/clip.mp4',timing['start']+timing['duration']*fraction)
        frame.save(folder/f'motion-{label}.png')
        # Restrict to the plot so orange parameter text cannot hide a missing arc.
        crop=frame.convert('RGB').crop((490,180,800,500))
        pixels=crop.get_flattened_data() if hasattr(crop,'get_flattened_data') else crop.getdata()
        count=sum(1 for r,g,b in pixels if r>180 and 65<g<210 and b<130 and r>g)
        counts.append(count)
        assert count>30,'Rendered orange arc is missing or hidden behind the circle'
    result={'passed':True,'authored_scene':True,'textbook_generalization':False,
        'svg_equal_units':True,'orange_arc_pixels_mid_end':counts,'media':media_check(folder/'render/clip.mp4')}
    (folder/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(verify(args.output.resolve()),ensure_ascii=False,indent=2))
