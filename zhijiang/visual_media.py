"""Narrated general scene assets reused by the PPT and complete teaching video."""
from __future__ import annotations

import html
import json
import math
import os
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

from zhijiang.math_media import _run, render_summary_png
from zhijiang.visual_planning import object_geometry, verify_visual_scene


def visual_summary_svg(scene) -> str:
    state = verify_visual_scene(scene)['states'][-1]
    def xy(p):
        return [60+1080*(p[0]-scene.x_range[0])/(scene.x_range[1]-scene.x_range[0]),
                405-310*(p[1]-scene.y_range[0])/(scene.y_range[1]-scene.y_range[0])]
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="500" viewBox="0 0 1200 500">',
           '<title>'+html.escape(scene.domain)+'</title><desc>'+html.escape(scene.question)+'</desc>',
           '<rect width="1200" height="500" fill="#10283A"/>',
           '<defs><clipPath id="plot"><rect x="50" y="85" width="1100" height="330"/></clipPath></defs>',
           '<g clip-path="url(#plot)">']
    if scene.axes:
        for p,q in [([scene.x_range[0],0],[scene.x_range[1],0]),([0,scene.y_range[0]],[0,scene.y_range[1]])]:
            a,b=xy(p),xy(q)
            parts.append(f'<path d="M {a[0]} {a[1]} L {b[0]} {b[1]}" stroke="#698CA5" stroke-width="2"/>')
    for obj in scene.objects:
        if obj.id not in state['visible']: continue
        geometry=object_geometry(obj,state['parameters']); pts=[xy(p) for p in geometry['points']]; color=obj.color
        if obj.kind in {'dot','circle'}:
            r=geometry['radius']*1080/(scene.x_range[1]-scene.x_range[0])
            if obj.kind=='dot': r=min(9,max(3,r))
            parts.append(f'<circle cx="{pts[0][0]}" cy="{pts[0][1]}" r="{r}" fill="{color}" fill-opacity="{1 if obj.kind=="dot" else 0.2}" stroke="{color}" stroke-width="3"/>')
        elif obj.kind=='label':
            parts.append(f'<text x="{pts[0][0]}" y="{pts[0][1]}" font-size="23" fill="{color}">{html.escape(obj.text)}</text>')
        elif obj.kind=='polygon':
            points=' '.join(f'{p[0]},{p[1]}' for p in pts)
            parts.append(f'<polygon points="{points}" fill="{color}" fill-opacity=".2" stroke="{color}" stroke-width="3"/>')
        else:
            path=' '.join(('M' if i==0 else 'L')+f' {p[0]} {p[1]}' for i,p in enumerate(pts))
            parts.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="3"/>')
            if obj.kind=='arrow':
                a,b=pts[0],pts[-1]; angle=math.atan2(b[1]-a[1],b[0]-a[0])
                tip=[b]+[[b[0]-12*math.cos(angle+d),b[1]-12*math.sin(angle+d)] for d in [-.42,.42]]
                points=' '.join(f'{p[0]},{p[1]}' for p in tip)
                parts.append(f'<polygon points="{points}" fill="{color}" stroke="{color}" stroke-width="1"/>')
    parameter_label=', '.join(f'{key}={value:.4g}' for key,value in list(state['parameters'].items())[:5])
    calculation_label=' · '.join(f"{c['label'][:12]}={c['value']:.5g}" for c in state['calculations'][:2])
    parts+=['</g>','<rect width="1200" height="78" fill="#10283A"/>','<rect y="420" width="1200" height="80" fill="#10283A"/>',f'<text x="50" y="50" font-size="28" fill="#F4F7F9">{html.escape(scene.question[:38])}</text>',
            f'<text x="50" y="440" font-size="19" fill="#6DE2C0">{html.escape(parameter_label)}</text>',
            f'<text x="680" y="440" font-size="19" fill="#FFA458">{html.escape(calculation_label)}</text>',
            f'<text x="50" y="467" font-size="19" fill="#AEC4D0">{html.escape(scene.domain)} · PDF 第 {scene.evidence.page} 页 · 示意与计算检查，领域解释需复核</text>','</svg>']
    return ''.join(parts)


def render_visual_scene(scene, speech, folder: Path, *, reuse_audio=False) -> dict:
    scene.verification=verify_visual_scene(scene)
    folder=folder.resolve(); folder.mkdir(parents=True,exist_ok=True)
    previous={}
    if reuse_audio and (folder/'scene.json').is_file():
        previous=json.loads((folder/'scene.json').read_text(encoding='utf-8'))
    audio=folder/'narration.wav'; timing=[]; cursor=0; format_parameters=None
    with wave.open(str(audio),'wb') as target:
        for i,beat in enumerate(scene.beats):
            words=beat.narration
            if scene.narration_binding == 'computed':
                parameters = beat.parameters or (scene.parameters if i == 0 else {})
                if parameters:
                    words += ' 当前参数：'+ '，'.join(f'{key}为{value:.5g}' for key,value in parameters.items())+'。'
            calculations=scene.verification['states'][i]['calculations']
            for c in calculations: words+=f" 计算得到，{c['label']}为{c['value']:.5g}。"
            clip=folder/f'beat-{i+1:02d}.wav'
            previous_timing=previous.get('timing',[])
            if not (reuse_audio and clip.is_file() and i<len(previous_timing) and previous_timing[i]['text']==words):
                speech.synthesize(words,clip)
            with wave.open(str(clip),'rb') as source:
                fmt=(source.getnchannels(),source.getsampwidth(),source.getframerate())
                if format_parameters is None:
                    format_parameters=fmt; target.setnchannels(fmt[0]); target.setsampwidth(fmt[1]); target.setframerate(fmt[2])
                if fmt!=format_parameters or fmt[1]!=2:
                    raise ValueError('Scene narration requires matching PCM16 WAV formats')
                seconds=source.getnframes()/fmt[2]; target.writeframes(source.readframes(source.getnframes()))
                target.writeframes(b'\0'*round(.8*fmt[2])*fmt[0]*fmt[1])
            timing.append({'step':i+1,'start':cursor,'duration':seconds+.8,'speech_seconds':seconds,'text':words})
            cursor+=seconds+.8
    config=folder/'scene.json'; config.write_text(json.dumps({'plan':scene.model_dump(),'timing':timing,'geometry_output':str(folder/'geometry.json')},ensure_ascii=False,indent=2),encoding='utf-8')
    source=folder/'scene.py'; source.write_text('from zhijiang.visual_renderer import GeneralTeachingScene\n\nclass Book2CourseScene(GeneralTeachingScene):\n    pass\n',encoding='utf-8')
    _run([sys.executable,'-m','manim',str(source),'Book2CourseScene','--renderer','cairo','--resolution','1280,720','--fps','30','--disable_caching','--media_dir',str(folder/'media'),'-o','raw.mp4','--verbosity','WARNING'],
         env=dict(os.environ,BOOK2COURSE_SCENE=str(config),PYTHONUTF8='1'),log=folder/'render.log')
    videos=list((folder/'media').rglob('raw.mp4'))
    if len(videos)!=1: raise ValueError('No unique general scene movie')
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    _run([ffmpeg,'-hide_banner','-loglevel','error','-y','-i',str(videos[0]),'-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2','-af','apad=pad_dur=0.6','-shortest','-movflags','+faststart',str(folder/'clip.mp4')])
    _run([ffmpeg,'-hide_banner','-loglevel','error','-y','-ss',str(max(0,cursor-.3)),'-i',str(folder/'clip.mp4'),'-frames:v','1',str(folder/'poster.png')])
    (folder/'summary.svg').write_text(visual_summary_svg(scene),encoding='utf-8'); render_summary_png(folder/'summary.svg',folder/'summary.png')
    return {'kind':'general','domain':scene.domain,'seconds':cursor+.6,'timing':timing,'verification':scene.verification,
            'rendered_geometry':json.loads((folder/'geometry.json').read_text(encoding='utf-8')),'resolution':[1280,720],'fps':30,'has_audio':True}


def render_visual_assets(lesson,speech,folder,progress, *, reuse_audio=False):
    assets=[]
    for i,segment in enumerate(lesson.segments):
        if not segment.visual_scene: continue
        progress(f'配音与渲染通用场景（{i+1}/{len(lesson.segments)}）：{segment.title}',74+i*15//len(lesson.segments))
        asset=render_visual_scene(segment.visual_scene,speech,folder/'visual'/f'scene-{i+1:02d}',reuse_audio=reuse_audio); asset['segment_index']=i; assets.append(asset)
    lesson.animation_report['assets']=assets
    (folder/'scene-data.json').write_text(json.dumps({'lesson':lesson.model_dump(),'assets':assets},ensure_ascii=False,indent=2),encoding='utf-8')
