"""Synthesize beat audio, render Manim, and produce shared PPT/video assets."""
from __future__ import annotations

import html
import json
import math
import os
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg

from zhijiang.math_planning import (MathAnimationError, numeric_facts, verify_scene,
                                    verified_narration_phrases)
from zhijiang.models import Lesson, MathScenePlan

LABELS = {
    "vectors": "先辨认输入向量 v 与 w", "add_then_transform": "左侧：先构造向量和，再施加 A",
    "transform_then_add": "右侧：先分别施加 A，再相加", "homogeneity": "改变倍数，两条路径仍一致",
    "translation_counterexample": "平移反例：原点被移走，因此不是线性变换",
    "basis_vectors": "两个基向量是所有坐标的参照", "basis_images": "先看两个基向量的去向",
    "matrix_columns": "基向量的像依次组成矩阵的两列", "decompose": "回到原空间，先把 v 拆成两个分量",
    "transform_combination": "分别变换两个分量，再合成为 Av",
    "plane_start": "观察同一网格、向量和单位正方形", "plane_transform": "每个点都按同一矩阵移动",
    "area": "用顶点坐标计算面积，核对伸缩比",
    "projection_start": "确定投影直线与输入向量", "project": "沿垂线移动到投影位置",
    "eigen_parallel": "平行方向保持：特征值为 1", "eigen_perpendicular": "垂直方向归零：特征值为 0",
    "change_basis": "沿投影方向选基，矩阵变成对角形式",
    "composition_start": "同一个输入，比较两种操作顺序", "rotate_then_stretch": "左侧：先旋转，再伸缩",
    "stretch_then_rotate": "右侧：先伸缩，再旋转", "compare_order": "最终位置不同，对应矩阵乘法的顺序",
}


def _run(command: list[str], *, env=None, timeout=1800, log: Path | None = None) -> None:
    if log is None:
        result = subprocess.run(command, capture_output=True, timeout=timeout, env=env)
        detail = result.stderr.decode("utf-8", errors="replace")[-600:]
    else:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=stream, timeout=timeout, env=env)
        detail = log.read_text(encoding="utf-8", errors="replace")[-800:]
    if result.returncode:
        raise MathAnimationError("教学动画渲染失败：" + detail)


def synthesize_beats(scene: MathScenePlan, speech, folder: Path) -> tuple[Path, list[dict]]:
    folder.mkdir(parents=True, exist_ok=True)
    combined = folder / "narration.wav"
    timing = []
    format_parameters = None
    cursor = 0.0
    phrases = verified_narration_phrases(scene) if scene.narration_binding == "verified" else {}
    with wave.open(str(combined), "wb") as target:
        for index, beat in enumerate(scene.beats):
            cues = []
            seconds = 0.0
            for cue_index, phrase in enumerate(phrases.get(beat.action, [beat.narration])):
                path = folder / f"beat-{index+1:02d}-cue-{cue_index+1:02d}.wav"
                speech.synthesize(phrase, path)
                with wave.open(str(path), "rb") as audio:
                    parameters = (audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
                    if format_parameters is None:
                        format_parameters = parameters
                        target.setnchannels(parameters[0])
                        target.setsampwidth(parameters[1])
                        target.setframerate(parameters[2])
                    if format_parameters != parameters or parameters[1] != 2:
                        raise MathAnimationError("逐步配音须返回同采样率的 16-bit PCM WAV。")
                    duration = audio.getnframes() / parameters[2]
                    cues.append({"start": cursor+seconds, "speech_seconds": duration, "text": phrase})
                    target.writeframes(audio.readframes(audio.getnframes()))
                    seconds += duration
            # Leave a visible conclusion before starting the next spoken step.
            pause = 0.8
            target.writeframes(b"\0" * round(pause*format_parameters[2])*format_parameters[0]*format_parameters[1])
            duration = seconds + pause
            timing.append({"action": beat.action, "start": cursor, "duration": duration,
                           "speech_seconds": seconds, "label": LABELS[beat.action], "cues": cues})
            cursor += duration
    return combined, timing


def render_math_scene(scene: MathScenePlan, speech, folder: Path,
                      *, resolution=(1280, 720), fps=30) -> dict:
    verification = verify_scene(scene)
    if scene.narration_binding != "verified":
        raise MathAnimationError("数学动画的口播尚未绑定核验数据，拒绝合成。")
    folder = folder.resolve()
    audio, timing = synthesize_beats(scene, speech, folder)
    config_file = folder / "scene.json"
    config_file.write_text(json.dumps({"plan": scene.model_dump(), "timing": timing,
                                      "audio": str(audio), "geometry_output": str(folder/"geometry.json")},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    source_file = folder / "scene.py"
    source_file.write_text("from zhijiang.math_renderer import TeachingScene\n\n"
                           "class Book2CourseScene(TeachingScene):\n    pass\n", encoding="utf-8")
    environment = dict(os.environ, BOOK2COURSE_SCENE=str(config_file), PYTHONUTF8="1")
    _run([sys.executable, "-m", "manim", str(source_file), "Book2CourseScene", "--renderer", "cairo",
          "--resolution", f"{resolution[0]},{resolution[1]}", "--fps", str(fps), "--disable_caching",
          "--media_dir", str(folder / "media"), "-o", "raw.mp4", "--verbosity", "WARNING"],
         env=environment, log=folder/"render.log")
    videos = list((folder / "media").rglob("raw.mp4"))
    if len(videos) != 1:
        raise MathAnimationError("Manim 未输出唯一的数学动画文件。")
    video = folder / "clip.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # Use the WAV directly instead of any Manim-added audio codec conversion.
    _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(videos[0]), "-i", str(audio),
          "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-ar", "48000", "-ac", "2", "-af", "apad=pad_dur=0.6",
          "-movflags", "+faststart", "-shortest", str(video)])
    poster = folder / "poster.png"
    duration = sum(item["duration"] for item in timing)
    _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(max(0, duration-0.3)),
          "-i", str(video), "-frames:v", "1", str(poster)])
    svg = folder / "summary.svg"
    svg.write_text(math_summary_svg(scene), encoding="utf-8")
    render_summary_png(svg, folder/"summary.png")
    return {"kind": scene.kind, "video": "clip.mp4", "svg": "summary.svg", "poster": "poster.png",
            "seconds": duration + 0.6, "timing": timing, "verification": verification,
            "rendered_geometry": json.loads((folder/"geometry.json").read_text(encoding="utf-8")),
            "resolution": list(resolution), "fps": fps, "has_audio": True}


def math_summary_svg(scene: MathScenePlan) -> str:
    """A vector summary of actual verified states, not a screenshot of the movie."""
    f = numeric_facts(scene.parameters)
    escape = lambda value: html.escape(str(value), quote=True)
    def text(x, y, value, size=25, color="#F4F7F9"):
        return f'<text x="{x}" y="{y}" fill="{color}" font-family="Microsoft YaHei,sans-serif" font-size="{size}">{escape(value)}</text>'
    def vector(value, color, origin=(430, 290), scale=42):
        end = (origin[0]+value[0]*scale, origin[1]-value[1]*scale)
        angle = math.atan2(end[1]-origin[1],end[0]-origin[0])
        tip = [end]+[(end[0]-12*math.cos(angle+delta),end[1]-12*math.sin(angle+delta)) for delta in (-0.42,0.42)]
        points = " ".join(f"{x},{y}" for x,y in tip)
        # Office renders SVG context-stroke marker fills as black. Use explicit
        # colored geometry for both Office and the raster compatibility fallback.
        return (f'<path d="M {origin[0]} {origin[1]} L {end[0]} {end[1]}" stroke="{color}" stroke-width="5"/>'
                f'<polygon points="{points}" fill="{color}" stroke="{color}" stroke-width="1"/>')
    title = {"linearity": "两条路径得到相同向量", "basis": "矩阵的列与基向量的像对应",
             "plane": "每个顶点按同一矩阵移动", "projection": "投影保留一个方向，压缩另一个方向",
             "composition": "相同输入，不同顺序"}[scene.kind]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="500" viewBox="0 0 1200 500">',
        '<title>'+escape(title)+'</title><desc>'+escape(scene.question)+'</desc>',
        '<rect width="1200" height="500" rx="24" fill="#10283A"/>', text(50, 58, title, 30)]
    if scene.kind == "composition":
        values = [f["v"], f["SRv"], f["RSv"]]
        labels = ["v", "S(Rv)", "R(Sv)"]
    elif scene.kind == "projection":
        values = [f["v"], f["Pv"], f["perpendicular"]]
        labels = ["v", "Pv", "垂直方向 → 0"]
    elif scene.kind == "linearity":
        values = [f["Av"], f["Aw"], f["A_sum"]]
        labels = ["Av", "Aw", "A(v+w) = Av+Aw"]
    else:
        values = [f["e1_image"], f["e2_image"], f["Av"]]
        labels = ["A 的第 1 列", "A 的第 2 列", "Av"]
    scale = min(58, 170/max(1, max(abs(value) for vector_values in values for value in vector_values)))
    parts += ['<path d="M 160 290 L 695 290 M 430 112 L 430 438" stroke="#698CA5" stroke-width="2"/>']
    colors = ["#6DE2C0", "#FFA458", "#78BAFF"]
    if scene.kind == "projection":
        colors = ["#78BAFF", "#78BAFF", "#FF862F"]
    elif scene.kind == "composition":
        colors = ["#78BAFF", "#83C167", "#FF862F"]
    for index, (value, label, color) in enumerate(zip(values, labels, colors)):
        parts.append(vector(value, color, scale=scale))
        coordinates = "("+", ".join(f"{number:.3g}" for number in value)+")"
        parts.append(text(750, 155+index*64, label+"  "+coordinates, 23, color))
    if scene.kind == "plane":
        matrix = scene.parameters.matrix
        vertices = [(0, 0), (matrix[0][0], matrix[1][0]),
                    (matrix[0][0]+matrix[0][1], matrix[1][0]+matrix[1][1]), (matrix[0][1], matrix[1][1])]
        points = " ".join(f"{430+x*scale},{290-y*scale}" for x, y in vertices)
        parts.append(f'<polygon points="{points}" fill="#78BAFF" fill-opacity=".22" stroke="#78BAFF" stroke-width="2"/>')
        parts.append(text(750, 375, f"单位正方形面积：1 → {f['area'][0]:.3g}", 23))
    if scene.kind == "projection":
        u = f["parallel"]
        parts.append(f'<path d="M {430-150*u[0]} {290+150*u[1]} L {430+150*u[0]} {290-150*u[1]}" stroke="#6DE2C0" stroke-width="3"/>')
        parts.append(text(750, 375, "沿投影方向选基：diag(1, 0)", 23))
    parts.append(text(50, 469, f"教学示例 · 原理来源：PDF 第 {scene.evidence.page} 页 · 计算已核验", 18, "#AEC4D0"))
    parts.append("</svg>")
    return "".join(parts)


def render_summary_png(svg: Path, output: Path) -> None:
    """Render our own restricted SVG elements for the Office PNG fallback."""
    import math
    import re
    from xml.etree import ElementTree as ET
    from PIL import Image, ImageDraw
    from zhijiang.presentation import _font
    root = ET.parse(svg).getroot()
    size=(round(float(root.attrib.get('width','1200'))),round(float(root.attrib.get('height','500'))))
    image = Image.new("RGB", size, "#10283A")
    draw = ImageDraw.Draw(image, "RGBA")
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        attributes = node.attrib
        if tag == "rect" and "fill" in attributes:
            x,y=float(attributes.get("x",0)),float(attributes.get("y",0))
            draw.rounded_rectangle((x,y,x+float(attributes['width']),y+float(attributes['height'])),
                radius=float(attributes.get('rx',0)),fill=attributes['fill'],outline=attributes.get('stroke'),
                width=int(attributes.get('stroke-width','1')))
        elif tag == 'image':
            import base64,io
            href=attributes.get('{http://www.w3.org/1999/xlink}href',attributes.get('href',''))
            if not href.startswith('data:image/png;base64,'):
                raise ValueError('Summary images must embed locally extracted PNG data')
            with Image.open(io.BytesIO(base64.b64decode(href.split(',',1)[1],validate=True))) as asset:
                size=(round(float(attributes['width'])),round(float(attributes['height'])))
                image.paste(asset.convert('RGB').resize(size),
                    (round(float(attributes['x'])),round(float(attributes['y']))))
        elif tag == "circle":
            x,y,r=float(attributes['cx']),float(attributes['cy']),float(attributes['r'])
            color=attributes['fill'].lstrip('#')
            rgba=tuple(int(color[i:i+2],16) for i in (0,2,4))+(round(float(attributes.get('fill-opacity','1'))*255),)
            draw.ellipse((x-r,y-r,x+r,y+r),fill=rgba,outline=attributes.get('stroke',attributes['fill']),width=int(attributes.get('stroke-width','1')))
        elif tag == "text":
            draw.text((float(attributes["x"]), float(attributes["y"])), node.text or "",
                font=_font(max(1,round(float(attributes["font-size"])))), fill=attributes["fill"],
                      anchor={'middle':'ms','end':'rs'}.get(attributes.get('text-anchor'),'ls'))
        elif tag == "path":
            tokens = re.findall(r"[ML]|[-+]?\d+(?:\.\d+)?(?:e[-+]?\d+)?", attributes["d"], re.I)
            cursor = 0
            previous = None
            while cursor < len(tokens):
                command, x, y = tokens[cursor:cursor+3]
                point = (float(x), float(y))
                if command == "L" and previous:
                    draw.line((previous, point), fill=attributes["stroke"], width=int(attributes["stroke-width"]))
                    if "marker-end" in attributes and cursor+3 == len(tokens):
                        angle = math.atan2(point[1]-previous[1], point[0]-previous[0])
                        points = [point]+[(point[0]-12*math.cos(angle+delta), point[1]-12*math.sin(angle+delta))
                                         for delta in (-0.42, 0.42)]
                        draw.polygon(points, fill=attributes["stroke"])
                previous = point
                cursor += 3
        elif tag == "polygon":
            points = [tuple(map(float, pair.split(","))) for pair in attributes["points"].split()]
            color = attributes["fill"].lstrip("#")
            rgba = tuple(int(color[index:index+2], 16) for index in (0, 2, 4))+(round(float(attributes.get("fill-opacity","1"))*255),)
            draw.polygon(points, fill=rgba)
            draw.line(points+[points[0]], fill=attributes["stroke"], width=int(attributes.get("stroke-width","2")))
    image.save(output)


def render_math_assets(lesson: Lesson, speech, folder: Path, progress) -> None:
    assets = []
    scenes = [segment for segment in lesson.segments if segment.math_scene]
    for index, segment in enumerate(lesson.segments):
        if segment.math_scene is None:
            continue
        progress(f"配音与渲染数学推演（{len(assets)+1}/{len(scenes)}）：{segment.title}", 74+len(assets)*15//len(scenes))
        path = folder / "math" / f"scene-{index+1:02d}"
        asset = render_math_scene(segment.math_scene, speech, path)
        asset["segment_index"] = index
        assets.append(asset)
    lesson.animation_report["assets"] = assets
    (folder/"math-scenes.json").write_text(json.dumps({"lesson": lesson.model_dump(), "assets": assets},
        ensure_ascii=False, indent=2), encoding="utf-8")
