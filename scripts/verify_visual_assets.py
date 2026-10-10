"""Actual local-model acceptance; outputs and private source content stay in data/."""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import imageio_ffmpeg
from pptx import Presentation
from zhijiang.agents import OllamaClient
from zhijiang.config import Settings
from zhijiang.deck_planning import plan_deck
from zhijiang.caption_grounding import ground_lesson_captions
from zhijiang.models import Lesson, GenerationOptions, SpeechOptions, Mode, VoiceMode
from zhijiang.pipeline import JobProcessor
from zhijiang.presentation import render_presentation
from zhijiang.storage import JobStore
from zhijiang.video import render_video
from zhijiang.visual_assets import AssetCatalog

SUBJECTS = {
    'physics': ('电路中的电流与电压', [
        '电池为闭合电路提供电压，电流沿导体形成通路。开关断开时，电路不闭合，灯泡不会持续发光。电压是电势差，电流是电荷通过导体截面的速率，两者是不同的物理量，不能把电压理解为流动的电荷。',
        '在理想直流电路中，串联元件流过的电流相同，各元件电压之和等于电源电压。并联支路两端的电压相同，各支路电流之和等于总电流。这些关系以稳定状态为前提，不表示每条支路电流必然相等。',
        '电阻影响电流大小。对于温度等条件保持不变的欧姆导体，电压、电流和电阻满足欧姆定律。实验中应同时记录电压和电流并控制温度。普通灯泡的灯丝温度会随电流改变，因此不能把其电阻视为始终不变。']),
    'finance': ('储蓄中的本金与复利', [
        '本金是最初投入的金额，利息是按约定利率获得的金额。这里讨论一个教学例子：利率固定为年利率百分之五，每年结息一次，没有新增投入，也不考虑税费。利率是比率，不等于实际赚到的货币金额。',
        '单利只对初始本金计息。复利把已结算的利息加入下一期计息本金。对于本金一百元、固定年利率百分之五的教学例子，复利第一年末金额是一百零五元，第二年末金额是一百一十点二五元。',
        '比较收益时需要区分计息方式、期限和费用。教学例子中的固定利率并不是市场回报保证，现实投资的收益可能变化，本金也可能损失。增长图可以帮助说明累积的方向，但不能把示意曲线当作真实产品的历史收益数据。']),
    'biology': ('从呼吸到细胞利用氧', [
        '呼吸系统使外界空气进入肺部，并在肺泡处进行气体交换。吸气时膈肌收缩，胸腔容积增大，空气进入肺部。呼气时的情况相反。通气是空气的移动，气体交换则涉及氧和二氧化碳跨膜扩散，两者不能混同。',
        '肺泡周围有毛细血管，氧从肺泡扩散进入血液，二氧化碳从血液扩散进入肺泡。气体扩散与分压差有关。肺泡表面积大、壁薄等结构有利于交换，但结构示意图不代表真实尺寸，也不意味着每个肺泡都具有相同形状。',
        '血液把氧运输到组织，细胞在代谢中利用氧。外界呼吸、血液运输和细胞代谢是相互联系的不同环节。细胞图可以帮助识别讨论对象，肺部插画可以帮助定位器官，但两者不能代替对实际生化过程的解释。']),
}

def sample_pdf(title, paragraphs, output):
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    pdf=canvas.Canvas(str(output),pagesize=(595,842))
    for i,paragraph in enumerate(paragraphs,1):
        pdf.setFont('STSong-Light',20); pdf.drawString(46,790,f'{title} · {i}')
        pdf.setFont('STSong-Light',14)
        for row,start in enumerate(range(0,len(paragraph),35)):
            pdf.drawString(46,730-row*27,paragraph[start:start+35])
        pdf.showPage()
    pdf.save()


def inspect(folder, lesson):
    import zipfile
    from xml.etree import ElementTree as ET
    ppt=folder/'lesson.pptx'; video=folder/'lesson.mp4'
    with zipfile.ZipFile(ppt) as archive:
        assert archive.testzip() is None
        svgs=[p for p in archive.namelist() if p.endswith('.svg')]
        for name in svgs: ET.fromstring(archive.read(name))
    process=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(video),'-f','null','-'],
                           capture_output=True,timeout=900)
    if process.returncode: raise RuntimeError('完整视频解码失败。')
    manifest=json.loads((folder/'presentation-preview/manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['segments'])==len(lesson.segments)
    import numpy as np
    from PIL import Image, ImageDraw
    from zhijiang.page_media import clip_duration
    audio_files=source_audio(folder,lesson)
    audio_seconds=0.; rms=[]
    for audio_path in audio_files:
        with wave.open(str(audio_path)) as audio:
            assert audio.getsampwidth()==2 and audio.getnframes()>0
            raw=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(float)
            audio_seconds+=audio.getnframes()/audio.getframerate()
        level=float(np.sqrt(np.mean(raw**2)));assert level>10, '源配音为空或近乎静音。'
        rms.append(round(level,2))
    decoded_audio=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(video),
        '-vn','-f','s16le','-ar','24000','-ac','1','-'],capture_output=True,check=True,timeout=900)
    decoded_seconds=len(decoded_audio.stdout)/(24000*2)
    video_seconds=clip_duration(video)
    bookend_seconds=sum(b['duration'] for b in manifest.get('bookends',[]))
    assert abs(decoded_seconds-audio_seconds-bookend_seconds)<max(.5,len(lesson.segments)*.08), '成片配音时长与完整源讲稿及封面结尾停留不符。'
    # Compare actual decoded frames to the final shared page of ordinary segments.
    # Continuous scenes have independent motion checks in the media regressions.
    comparisons=[]; frames=[]; cursor=sum(b['duration'] for b in manifest.get('bookends',[]) if b['kind']=='cover')
    for item in manifest['segments']:
        index=item['segment_id']; segment=lesson.segments[index-1]
        duration=clip_duration(folder/item['clip'])
        timestamp=cursor+max(.05,duration-.25)
        image_bytes=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss',str(timestamp),
            '-i',str(video),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
        frame=Image.frombytes('RGB',(1280,720),image_bytes)
        frames.append((item,frame))
        if not (segment.math_scene or segment.visual_scene or index in lesson.animation_report.get('prepared_scenes',[])):
            with Image.open(folder/'presentation-preview'/f'page-{item["pages"][-1]:03d}.png') as expected:
                error=float(abs(np.asarray(frame).astype(float)-np.asarray(expected).astype(float)).mean())
                assert error<5, f'第{index}段 PPT 与视频画面不一致：{error:.2f}'
                comparisons.append({'segment_id':index,'mean_pixel_error':round(error,3)})
        cursor+=duration
    for sheet,start in enumerate(range(0,len(frames),8),1):
        group=frames[start:start+8]; contact=Image.new('RGB',(1280,390*((len(group)+1)//2)),'#F5F3ED')
        draw=ImageDraw.Draw(contact)
        for i,(item,frame) in enumerate(group):
            x=(i%2)*640;y=(i//2)*390
            contact.paste(frame.resize((640,360)),(x,y))
            draw.text((x+10,y+365),f'Segment {item["segment_id"]} / actual video frame',fill='black')
        contact.save(folder/f'video-review-{sheet}.png')
        contact.save(folder/f'review-{sheet}.png')
    bookend_comparisons=[]
    for item in manifest.get('bookends',[]):
        timestamp=item['duration']/2 if item['kind']=='cover' else video_seconds-item['duration']/2
        raw=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-ss',str(timestamp),
            '-i',str(video),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],
            capture_output=True,check=True).stdout
        frame=Image.frombytes('RGB',(1280,720),raw)
        with Image.open(folder/'presentation-preview'/f'page-{item["page"]:03d}.png') as expected:
            error=float(abs(np.asarray(frame).astype(float)-np.asarray(expected).astype(float)).mean())
            assert error<5, f'{item["kind"]} PPT 与视频画面不一致：{error:.2f}'
        frame.save(folder/f'video-{item["kind"]}.png')
        bookend_comparisons.append({'kind':item['kind'],'mean_pixel_error':round(error,3)})
    selected=[r['asset_id'] for p in lesson.deck_plan['pages'] for r in p.get('asset_refs',[])]
    result={'template':lesson.ppt_template,'model':lesson.deck_plan['model'], 'planner':lesson.deck_plan['planner'],
            'segments':len(lesson.segments),'slides':len(Presentation(ppt).slides), 'svg_parts':len(svgs),
            'selected_assets':selected,'unique_selected_assets':sorted(set(selected)),
            'full_video_decoded':True,'pptx_zip_valid':True,'powerpoint_application_playback':'not_performed',
            'video_seconds':round(video_seconds,2),'source_audio_seconds':round(audio_seconds,3),
            'decoded_audio_seconds':round(decoded_seconds,3),'source_audio_rms':rms,
            'bookend_seconds':bookend_seconds,
            'bookend_frame_comparisons':bookend_comparisons,
            'ordinary_frame_comparisons':comparisons,'narration_uses_per_segment':1,
            'pptx_sha256':hashlib.sha256(ppt.read_bytes()).hexdigest(),
            'mp4_sha256':hashlib.sha256(video.read_bytes()).hexdigest()}
    (folder/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def source_audio(folder,lesson):
    paths=[folder/('math' if s.math_scene else 'visual')/f'scene-{i:02d}'/'narration.wav'
            if s.math_scene or s.visual_scene else folder/f'audio-{i-1}.wav'
            for i,s in enumerate(lesson.segments,1)]
    records=[]; result=[]
    for index,path in enumerate(paths,1):
        retained=folder/'acceptance-audio'/f'source-{index:03d}.wav'
        marker=retained.with_suffix('.json')
        if path.is_file():
            origin='original PCM WAV'
            result.append(path)
        elif retained.is_file():
            origin=json.loads(marker.read_text(encoding='utf-8'))['origin']
            result.append(retained)
        else:
            # Production removes temporary ordinary WAVs after generation. For
            # past acceptance jobs, recover the existing utterance, never ask
            # the model to speak it again or claim this is the original PCM.
            retained.parent.mkdir(exist_ok=True)
            clip=folder/'presentation-media'/f'segment-{index:03d}.mp4'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(clip),
                            '-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(retained)],check=True)
            origin='PCM recovered from existing segment AAC; no new synthesis'
            marker.write_text(json.dumps({'origin':origin}),encoding='utf-8')
            result.append(retained)
        records.append({'segment_id':index,'origin':origin,'path':result[-1].relative_to(folder).as_posix()})
    (folder/'audio-evidence.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def ml(settings, output, render_only=False):
    origin=Path('data/ml-editorial'); output.mkdir(parents=True,exist_ok=True)
    lesson=Lesson.model_validate_json((origin/'lesson.json').read_text(encoding='utf-8'))
    lesson.ppt_template='editorial'
    # The previously checked narration is the fixed content baseline. Only the
    # local model makes the new illustration/layout decisions; no manual picks.
    for i in range(len(lesson.segments)):
        shutil.copyfile(origin/'audio'/f'page-{i+1:02d}.wav',output/f'audio-{i}.wav')
    # Preserve existing checked geometry/states, increasing their text sizes.
    # These are explicit imported media for this acceptance input, not subject
    # rules in the agent. No coordinates, values or relations are rewritten.
    lesson.animation_report['prepared_scenes']=[10,13]
    for index in lesson.animation_report['prepared_scenes']:
        target=output/'visual'/f'scene-{index:02d}';target.mkdir(parents=True,exist_ok=True)
        import resvg_py
        from xml.etree import ElementTree as ET
        from zhijiang.page_media import narrated_pages
        def enlarged_svg(path):
            root=ET.fromstring(path.read_bytes())
            for node in root.iter():
                if node.tag.endswith('text') and float(node.get('font-size','32'))<32:
                    node.set('font-size','32')
            return ET.tostring(root,encoding='utf-8')
        svg=enlarged_svg(origin/'figures'/f'figure-{index:02d}.svg')
        (target/'summary.svg').write_bytes(svg)
        (target/'summary.png').write_bytes(resvg_py.svg_to_bytes(svg_string=svg.decode()))
        stamp=hashlib.sha256(svg+b'import-large-type-v1').hexdigest()
        marker=target/'import-fingerprint.txt'
        if not marker.is_file() or marker.read_text()!=stamp or not (target/'clip.mp4').is_file():
            frames=[]
            stems=([f'filter-{i:02d}' for i in range(4)] if index==10 else [f'curve-{i:03d}' for i in range(61)])
            for i,stem in enumerate(stems):
                frame=target/f'frame-{i:03d}.png'
                frame.write_bytes(resvg_py.svg_to_bytes(svg_string=enlarged_svg(origin/'figures'/f'{stem}.svg').decode()))
                frames.append(frame)
            narrated_pages(frames,output/f'audio-{index-1}.wav',target/'clip.mp4')
            marker.write_text(stamp)
    if render_only:
        lesson.deck_plan=json.loads((output/'presentation-plan.json').read_text(encoding='utf-8'))
    else:
        client=OllamaClient(settings.llm_base_url,settings.llm_model,semantic_thinking=False,
                            prefer_json=True,num_gpu=settings.ollama_num_gpu)
        try:
            print('ML: local model selecting assets and layouts for 25 passages',flush=True)
            ground_lesson_captions(lesson,client,output=output/'caption-grounding.json')
            lesson.deck_plan=plan_deck(lesson,'editorial',client,output=output/'presentation-plan.json')
        finally:
            (output/'model-calls.json').write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
            client.close()
    (output/'lesson.json').write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
    print('ML: rendering shared pages, PPT and complete narrated video',flush=True)
    render_presentation(lesson,output/'lesson.pptx')
    render_video(lesson,[output/f'audio-{i}.wav' for i in range(len(lesson.segments))],output/'lesson.mp4')
    result=inspect(output,lesson)
    assert any('watermelon' in key for key in result['selected_assets']), '真实模型未给西瓜讲解选择插画。'
    result['content_baseline']='existing checked lesson; new local-model visual planning'
    (output/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def subjects(settings, output):
    output.mkdir(parents=True,exist_ok=True)
    store=JobStore(output/'jobs')
    def retain_audio_and_render(lesson,ppt):
        folder=Path(ppt).parent
        for index,path in enumerate(source_audio(folder,lesson),1):
            target=folder/'acceptance-audio'/f'source-{index:03d}.wav'
            target.parent.mkdir(exist_ok=True)
            if target!=path:
                shutil.copyfile(path,target)
                target.with_suffix('.json').write_text(json.dumps({'origin':'original PCM WAV retained before cleanup'}),encoding='utf-8')
        render_presentation(lesson,ppt)
    processor=JobProcessor(settings,store,presentation_renderer=retain_audio_and_render)
    results=[]
    for key,(title,paragraphs) in SUBJECTS.items():
        pdf=output/f'{key}.pdf'
        if not pdf.is_file(): sample_pdf(title,paragraphs,pdf)
        options=GenerationOptions(provider='ollama',base_url=settings.llm_base_url,model=settings.llm_model,
            animation_mode='basic',ppt_template={'physics':'academic','finance':'editorial','biology':'paper'}[key],
            semantic_thinking=False)
        speech_options=SpeechOptions(base_url=settings.tts_base_url,model=settings.tts_model,
                                     voice=settings.tts_voice,api_key=settings.tts_api_key)
        with store._connect() as connection:
            row=connection.execute('SELECT id FROM jobs WHERE filename=? ORDER BY created_at DESC LIMIT 1',(pdf.name,)).fetchone()
        job=store.get(row['id']) if row else None
        if job and job['status']=='completed':
            folder=store.jobs_dir/job['id']; lesson=store.lesson(job['id'])
            if lesson:
                client=OllamaClient(settings.llm_base_url,settings.llm_model,semantic_thinking=False,
                                   prefer_json=True,num_gpu=settings.ollama_num_gpu)
                try:
                    ground_lesson_captions(lesson,client,output=folder/'caption-grounding.json')
                    lesson.deck_plan=plan_deck(lesson,lesson.ppt_template,client,output=folder/'presentation-plan.json')
                    store.save_lesson(job['id'],lesson)
                finally:
                    (folder/'visual-refresh-calls.json').write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
                    client.close()
            from zhijiang.page_media import media_fingerprint
            manifest=json.loads((folder/'presentation-preview/manifest.json').read_text(encoding='utf-8'))
            if manifest.get('media_fingerprint')!=media_fingerprint(lesson,source_audio(folder,lesson)):
                from zhijiang.deck_renderer import render_template_presentation
                render_template_presentation(lesson,folder/'lesson.pptx',audio_files=source_audio(folder,lesson))
                render_video(lesson,source_audio(folder,lesson),folder/'lesson.mp4')
            result=inspect(folder,lesson)
            result.update(subject=key,job_id=job['id'],source='original acceptance PDF')
            results.append(result)
            continue
        if job:
            store.retry(job['id'],options=options,speech_options=speech_options)
        else:
            job=store.create(pdf.name,Mode.AI,VoiceMode.AI,True,False,pdf.read_bytes(),options,speech_options)
        print(f'{key}: original PDF -> actual local AI pipeline; job={job["id"]}',flush=True)
        processor.process(job['id'])
        current=store.get(job['id'])
        if current['status']!='completed':
            raise RuntimeError(f'{key}: {current["error"]}')
        folder=store.jobs_dir/job['id']; result=inspect(folder,store.lesson(job['id']))
        result.update(subject=key,job_id=job['id'],source='original acceptance PDF')
        results.append(result)
        (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False),flush=True)
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=['ml','subjects','all'],default='all')
    parser.add_argument('--render-only',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('data/illustration-acceptance'))
    args=parser.parse_args(); settings=Settings.from_env()
    if not settings.llm_is_local or not settings.tts_is_local:
        raise SystemExit('验收仅使用本机模型和配音服务。')
    if args.case in {'ml','all'}:
        result=ml(settings,args.output/'ml',args.render_only)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    if args.case in {'subjects','all'}:
        subjects(settings,args.output/'subjects')

if __name__=='__main__': main()
