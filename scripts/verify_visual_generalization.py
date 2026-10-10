"""Frozen unseen teaching inputs; real local AI, no lesson-specific art picks."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_visual_assets import sample_pdf, inspect, source_audio
from zhijiang.config import Settings
from zhijiang.models import GenerationOptions, Mode, VoiceMode
from zhijiang.pipeline import JobProcessor
from zhijiang.presentation import render_presentation
from zhijiang.storage import JobStore
from zhijiang.visual_assets import AssetCatalog
from zhijiang.agents import OllamaClient, GenerationError
from zhijiang.deck_planning import plan_deck
from zhijiang.caption_grounding import ground_lesson_captions
from zhijiang.deck_renderer import render_template_presentation
from zhijiang.video import render_video


INPUTS = {
    'optics': ('放大镜中的像与观察条件', 'academic', [
        '放大镜通常使用凸透镜。在这里讨论的观察条件中，物体位于透镜焦点以内，观察者看到的是正立、放大的虚像。虚像不能直接呈现在屏幕上。把物体逐渐移到焦点之外后，成像条件会改变，不能继续用原来的结论解释所有位置。这个例子说明，观察结果必须与物体的位置条件一起说明。',
        '用放大镜观察书本上的字时，需要同时调整物体与透镜的距离，使眼睛能够清楚辨认。放大倍数并不表示字的实际尺寸发生变化。插图可以帮助识别透镜和书本，但仅画出一枚放大镜并不能说明光线如何传播。解释成像时仍需要单独画出光线与位置关系，且示意图不代表真实尺寸。']),
    'library': ('借阅中的分类与查找', 'editorial', [
        '图书分类帮助读者在书架上找到相关主题。一本书的封面可以提供书名和作者信息，但不能替代内容目录。目录列出书中各部分的名称和页码，读者可以先查目录，再打开对应章节。阅读时应区分书架上的位置、目录中的页码和阅读顺序，这些信息有不同用途。',
        '检索图书时，可以组合主题、作者和书名等信息。相同主题可能有多本书，同一本书也可能讨论多个主题，分类标签不是知识内容的全部。借阅记录用于管理书本是否已经借出，并不直接表示书的质量或难度。找到资料后还需要检查内容是否适合当前的学习目标。']),
    'metamorphosis': ('蝴蝶的完全变态', 'paper', [
        '蝴蝶的个体发育通常经历卵、幼虫、蛹和成虫四个阶段，这种发育方式称为完全变态。幼虫和成虫在形态和生活方式上差异明显。毛毛虫是蝴蝶的幼虫，不能把它当作另一种动物的固定成体。成虫有翅膀，但幼虫没有成虫那样的翅膀，不能用一幅成虫图代替四个阶段的比较。',
        '观察发育过程时，应把阶段名称与观察时间分别记录。不同种类和环境条件会影响发育所需的时间，不能把一个观察个体的天数说成所有蝴蝶都遵循的固定规律。蛹期并非内部完全没有变化；后续形成的成虫结构与内部发育过程有关。成虫插画只能帮助识别讨论对象。']),
    'logic': ('条件命题中的充分与必要', 'classic', [
        '如果条件甲成立就能推出结论乙成立，那么甲是乙的充分条件，乙是甲的必要条件。这一关系不表示甲与乙必然等价，也不说明两个事件在时间上的先后顺序。若想主张二者等价，还需要说明从乙也能推出甲，不能只凭一个方向的推导就认为两个条件可以互换。',
        '推理时应写明讨论对象和成立范围。发现反例可以否定一个全称主张，而观察到若干支持的例子并不能直接证明所有对象都满足该主张。这里的甲与乙只是命题名称，不代表人物、物体或数字。抽象关系需要用清楚的条件语句说明，装饰性图片不能替代推理本身。']),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('data/visual-generalization'))
    parser.add_argument('--refresh-catalog',action='store_true',
                        help='Archive the previous asset freeze; keep all input PDFs and prompts unchanged.')
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    settings = Settings.from_env()
    if not settings.llm_is_local:
        raise SystemExit('These acceptance inputs must use the local model.')
    prompt = ('每页一个讲解重点。保留原文的关键实例和成立条件。'
              '画面要点只讲知识，不用出处提示或技术说明代替结论。')
    files = {}
    for key, (title, _, paragraphs) in INPUTS.items():
        path = root / f'{key}.pdf'
        if not path.is_file():
            sample_pdf(title, paragraphs, path)
        files[key] = {'title': title, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'paragraphs': paragraphs, 'origin': 'original unseen acceptance text, MIT'}
    frozen = {'inputs': files, 'asset_catalog': AssetCatalog().fingerprint,
              'model': settings.llm_model, 'voice': 'Windows system speech, not AI speech',
              'prompt': prompt, 'no_manual_asset_ids': True}
    freeze_path = root / 'frozen-inputs.json'
    if freeze_path.is_file():
        old=json.loads(freeze_path.read_text(encoding='utf-8'))
        if old!=frozen:
            if not args.refresh_catalog or {**old,'asset_catalog':frozen['asset_catalog']}!=frozen:
                raise SystemExit('Frozen inputs or catalog changed. Use a new output directory.')
            i=len(list(root.glob('frozen-inputs-before-refresh-*.json')))+1
            shutil.copyfile(freeze_path,root/f'frozen-inputs-before-refresh-{i}.json')
    freeze_path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding='utf-8')
    code_hash = hashlib.sha256(b''.join(p.read_bytes() for p in sorted(Path('zhijiang').glob('*.py')))).hexdigest()
    execution={'source_code_sha256': code_hash,
        'git_head': subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()}
    history_path=root/'execution-history.json'
    history=json.loads(history_path.read_text()) if history_path.is_file() else []
    if not history and (root/'execution.json').is_file():
        history.append(json.loads((root/'execution.json').read_text()))
    history.append(execution)
    history_path.write_text(json.dumps(history,indent=2),encoding='utf-8')
    (root/'execution.json').write_text(json.dumps(execution,indent=2),encoding='utf-8')
    if (root/'results.json').is_file():
        shutil.copyfile(root/'results.json',root/f'results-before-retry-{len(history)-1}.json')
    store = JobStore(root / 'jobs')
    def retain_audio(lesson, ppt):
        folder = Path(ppt).parent
        for i, audio in enumerate(source_audio(folder, lesson), 1):
            target = folder / 'acceptance-audio' / f'source-{i:03d}.wav'
            target.parent.mkdir(exist_ok=True)
            if audio != target:
                shutil.copyfile(audio, target)
                target.with_suffix('.json').write_text(json.dumps({'origin':'original PCM WAV retained before cleanup'}))
        render_presentation(lesson, ppt)
    processor = JobProcessor(settings, store, presentation_renderer=retain_audio)
    results = []
    for key, (_, template, _) in INPUTS.items():
        with store._connect() as connection:
            row = connection.execute('SELECT id FROM jobs WHERE filename=? ORDER BY created_at DESC LIMIT 1',
                                     (f'{key}.pdf',)).fetchone()
        options = GenerationOptions(provider='ollama', base_url=settings.llm_base_url,
            model=settings.llm_model, animation_mode='basic', ppt_template=template,
            semantic_thinking=False, prompt=prompt)
        job = store.get(row['id']) if row else None
        if job is None:
            job = store.create(f'{key}.pdf', Mode.AI, VoiceMode.SYSTEM, True, False,
                               (root / f'{key}.pdf').read_bytes(), options)
        elif job['status'] != 'completed':
            folder=store.jobs_dir/job['id']
            for name in ('model-calls.json','presentation-plan-attempts.json'):
                previous=folder/name
                if previous.is_file():
                    shutil.copyfile(previous,folder/f'{previous.stem}-before-retry-{len(history)-1}.json')
            store.retry(job['id'], options=options)
        print(f'{key}: real local pipeline, template={template}, job={job["id"]}',flush=True)
        if job['status'] != 'completed':
            processor.process(job['id'])
        current = store.get(job['id'])
        if current['status'] != 'completed':
            results.append({'subject':key, 'job_id':job['id'], 'status':current['status'], 'error':current['error']})
        else:
            folder = store.jobs_dir / job['id']
            lesson=store.lesson(job['id'])
            if args.refresh_catalog:
                client=OllamaClient(settings.llm_base_url,settings.llm_model,semantic_thinking=False,
                                    prefer_json=True,num_gpu=settings.ollama_num_gpu)
                previous=folder/'presentation-plan-attempts.json'
                if previous.is_file():
                    shutil.copyfile(previous,folder/f'layout-attempts-before-refresh-{len(history)-1}.json')
                try:
                    ground_lesson_captions(lesson,client,output=folder/'caption-grounding.json')
                    lesson.deck_plan=plan_deck(lesson,template,client,output=folder/'presentation-plan.json')
                    store.save_lesson(job['id'],lesson)
                except GenerationError as exc:
                    results.append({'subject':key,'job_id':job['id'],'status':'refresh_failed','error':str(exc),
                                    'previous_files_retained':True})
                    (root/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps(results[-1],ensure_ascii=False),flush=True)
                    continue
                finally:
                    (folder/'layout-refresh-calls.json').write_text(
                        json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
                    client.close()
                audio=source_audio(folder,lesson)
                render_template_presentation(lesson,folder/'lesson.pptx',audio_files=audio)
                render_video(lesson,audio,folder/'lesson.mp4')
            result = inspect(folder, lesson)
            result.update(subject=key, job_id=job['id'], status='completed',
                          input_sha256=files[key]['sha256'])
            results.append(result)
        (root / 'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(results[-1],ensure_ascii=False),flush=True)
    if any(r['status'] != 'completed' for r in results):
        raise SystemExit('Some frozen inputs failed; failures retained in results.json.')


if __name__ == '__main__':
    main()
