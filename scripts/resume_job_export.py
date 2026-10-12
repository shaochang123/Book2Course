"""Export a retained course after a late production failure, without LLM calls."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from zhijiang.config import Settings
from zhijiang.models import VoiceMode
from zhijiang.presentation import render_presentation
from zhijiang.speech import AISpeech,SystemSpeech
from zhijiang.speech_cache import synthesize_cached
from zhijiang.storage import JobStore
from zhijiang.video import render_video


def resume(job_id,settings):
    store=JobStore(settings.data_dir);job=store.get(job_id);lesson=store.lesson(job_id)
    if not job or job['status']!='failed' or not lesson or job['progress']<88:
        raise ValueError('仅支持已完成讲稿和配音、在导出阶段失败的任务。')
    if any(s.math_scene or s.visual_scene for s in lesson.segments):
        raise ValueError('连续数学场景请通过网页原任务重试，以恢复场景文件。')
    options=store.get_speech_options(job_id)
    if lesson.voice_mode==VoiceMode.AI and not Settings._is_loopback(options.base_url):
        raise ValueError('此恢复命令仅使用本地语音；外部语音请通过网页重试。')
    speech=(AISpeech(options.base_url,'',options.model,options.voice,
                     timeout_seconds=settings.tts_timeout_seconds)
            if lesson.voice_mode==VoiceMode.AI else SystemSpeech(settings.system_voice))
    folder=store.jobs_dir/job_id
    if not store.retry(job_id):raise ValueError('任务状态已改变。')
    store.save_lesson(job_id,lesson);audio=[]
    try:
        for i,segment in enumerate(lesson.segments):
            store.set_progress(job_id,f'恢复配音（{i+1}/{len(lesson.segments)}）',73+i*14//len(lesson.segments))
            path=folder/f'audio-{i}.wav';synthesize_cached(speech,segment.narration,path);audio.append(path)
            print('audio',i+1,len(lesson.segments),flush=True)
        store.set_progress(job_id,'恢复共享画面与 PPT',88);render_presentation(lesson,folder/'lesson.pptx')
        store.set_progress(job_id,'恢复完整视频',94);render_video(lesson,audio,folder/'lesson.mp4')
        store.complete(job_id)
        print('completed',job_id,flush=True)
    except Exception as exc:
        store.fail(job_id,str(exc));raise
    finally:
        if isinstance(speech,AISpeech):speech.close()
    return folder


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job_id');args=p.parse_args()
    resume(args.job_id,Settings.from_env())
