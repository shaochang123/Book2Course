"""Separate narrated video, using the same layout as the static PPT."""
from __future__ import annotations
import hashlib
import json
import subprocess
import wave
import re
from pathlib import Path
import imageio_ffmpeg


def media_fingerprint(lesson, audio_files):
    from zhijiang.visual_assets import AssetCatalog
    from zhijiang.presentation_templates import get_template,template_backdrop_svg
    digest = hashlib.sha256(('shared-pages-v26-source-figure-aspect-static-deck'+lesson.model_dump_json()).encode())
    # Program-selected source crops affect PPT and video, not just course JSON.
    for figure in (lesson.deck_plan or {}).get('source_figures',{}).values():
        if audio_files:
            root=Path(audio_files[0]).parent
            if root.name.startswith('scene-'):root=root.parent.parent
            path=root/figure['file']
            if path.is_file():digest.update(path.read_bytes())
    digest.update(AssetCatalog().fingerprint.encode())
    template=get_template(lesson.ppt_template)
    digest.update(repr(template).encode())
    digest.update(template_backdrop_svg(template).encode())
    for audio in audio_files:
        if Path(audio).is_file():
            digest.update(Path(audio).read_bytes())
    for i, segment in enumerate(lesson.segments, 1):
        if segment.math_scene or segment.visual_scene or i in lesson.animation_report.get('prepared_scenes',[]):
            root = Path(audio_files[i-1]).parent
            clip = (root/'visual'/f'scene-{i:02d}'/'clip.mp4' if i in lesson.animation_report.get('prepared_scenes',[])
                    else root/'clip.mp4')
            if clip.is_file():
                digest.update(clip.read_bytes())
    return digest.hexdigest()


def _run(args, output):
    from zhijiang.presentation import PresentationError
    process = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
        '-y', *args], capture_output=True, timeout=900)
    if process.returncode or not Path(output).is_file():
        Path(output).with_suffix('.ffmpeg.log').write_bytes(process.stderr)
        raise PresentationError('共享画面的视频合成失败：'+process.stderr.decode('utf-8', errors='replace')[-400:])


def _encoding():
    return ['-r','30','-fps_mode','cfr','-c:v','libx264','-preset','veryfast','-crf','20',
            '-threads','2','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-ac','2','-movflags','+faststart']


def narrated_pages(states, audio, output, *, fractions=None):
    """Each recorded utterance is used once, across all visual reveal states."""
    output = Path(output)
    with wave.open(str(audio)) as wav:
        duration = wav.getnframes()/wav.getframerate()
    if duration <= 0:
        from zhijiang.presentation import PresentationError
        raise PresentationError('配音为空。')
    manifest = output.with_suffix('.txt')
    # Paths are internally generated; escape apostrophes in user workspace paths.
    def quoted(path):
        return str(Path(path).resolve().as_posix()).replace("'", "'\\''")
    if not states:raise ValueError('讲解画面不能为空。')
    if fractions is None:fractions=[i/len(states) for i in range(len(states))]
    if len(fractions)!=len(states) or fractions[0]!=0 or any(not 0<=v<1 for v in fractions) or any(
            a>=b for a,b in zip(fractions,fractions[1:])):
        raise ValueError('画面时点必须从零开始、严格递增并位于音频内。')
    lines = []
    for i,state in enumerate(states):
        state_duration=duration*((fractions[i+1] if i+1<len(states) else 1)-fractions[i])
        lines += [f"file '{quoted(state)}'", f'duration {state_duration:.8f}']
    lines.append(f"file '{quoted(states[-1])}'")
    manifest.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    _run(['-f','concat','-safe','0','-i',str(manifest),'-i',str(audio),
          '-map','0:v:0','-map','1:a:0',
          '-vf',f'fps=30,tpad=stop_mode=clone:stop_duration={duration}',
          *_encoding(), '-t',str(duration), str(output)], output)
    return duration


def scene_on_page(background, source, viewport, output):
    """Aspect-preserving window: the original continuous scene is not cropped."""
    x,y,w,h = [round(v*96) for v in viewport]
    # Even viewport dimensions improve codec compatibility, without distorting.
    w -= w%2; h -= h%2
    duration=clip_duration(source)
    filters = (f'[1:v]scale={w}:{h}:force_original_aspect_ratio=decrease,setsar=1,setpts=PTS-STARTPTS[scene];'
               f'[0:v][scene]overlay=x={x}+({w}-overlay_w)/2:y={y}+({h}-overlay_h)/2:eof_action=repeat[out]')
    # Bound by the original clip, not by the still-image/AAC muxer's shortest
    # buffer: -shortest can prematurely cut a looped-image overlay on Windows.
    _run(['-loop','1','-framerate','30','-i',str(background),'-i',str(source),'-filter_complex',filters,
          '-map','[out]','-map','1:a:0', *_encoding(), '-t',str(duration),str(output)], output)


def clip_duration(path):
    probe=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(path)],
                         capture_output=True,timeout=30)
    match=re.search(rb'Duration: (\d+):(\d+):([\d.]+)',probe.stderr)
    if not match:
        from zhijiang.presentation import PresentationError
        raise PresentationError('无法读取场景视频时长。')
    hours,minutes,seconds=map(float,match.groups())
    return hours*3600+minutes*60+seconds


def concatenate_pages(clips, output):
    output = Path(output)
    manifest = output.parent/'shared-clips.txt'
    manifest.write_text('\n'.join("file '"+str(Path(p).resolve().as_posix()).replace("'", "'\\''")+"'"
                                  for p in clips)+'\n', encoding='utf-8')
    _run(['-f','concat','-safe','0','-i',str(manifest), *_encoding(),str(output)], output)


def render_shared_video(lesson, audio_files, output):
    from zhijiang.presentation import PresentationError
    output = Path(output)
    manifest = output.parent/'presentation-preview/manifest.json'
    key = media_fingerprint(lesson, audio_files)
    data = json.loads(manifest.read_text(encoding='utf-8')) if manifest.is_file() else {}
    if data.get('media_fingerprint') != key or not data.get('segments'):
        from zhijiang.deck_renderer import render_template_presentation
        render_template_presentation(lesson, output.with_suffix('.pptx'), audio_files=audio_files)
        data = json.loads(manifest.read_text(encoding='utf-8'))
    if len(data['segments']) != len(lesson.segments):
        raise PresentationError('共享视频片段未覆盖课程。')
    bookends=data.get('bookends',[])
    clips = [output.parent/item['clip'] for item in bookends if item['kind']=='cover']
    clips += [output.parent/item['clip'] for item in data['segments']]
    clips += [output.parent/item['clip'] for item in bookends if item['kind']=='ending']
    concatenate_pages(clips, output)
    (output.parent/'video-timeline.json').write_text(json.dumps({'template_id': lesson.ppt_template,
        'segments': data['segments'], 'bookends':bookends,'narration_uses_per_segment': 1,
        'visual_source': 'shared-native-slide-layout'}, ensure_ascii=False, indent=2), encoding='utf-8')
