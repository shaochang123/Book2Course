"""Original PDF through the real local pipeline; no retained lesson."""
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zhijiang.config import Settings
from zhijiang.models import Mode, VoiceMode, GenerationOptions
from zhijiang.storage import JobStore
from zhijiang.pipeline import JobProcessor
from verify_visual_assets import sample_pdf, source_audio, inspect

def main():
    settings=Settings.from_env()
    if not settings.llm_is_local:raise SystemExit('This verification uses the local model only.')
    root=Path('data/visual-variety-repair/fresh-finance');root.mkdir(parents=True,exist_ok=True)
    material=json.loads(Path('examples/finance_exhibits_original.json').read_text(encoding='utf-8'))
    pdf=root/'original-finance.pdf'
    sample_pdf(material['title'],material['paragraphs'],pdf,include_header=False)
    store=JobStore(root/'jobs')
    options=GenerationOptions(provider='ollama',base_url=settings.llm_base_url,model=settings.llm_model,
        animation_mode='basic',ppt_template='academic',use_illustrations=True,semantic_thinking=False)
    job=store.create(pdf.name,Mode.AI,VoiceMode.SYSTEM,True,False,pdf.read_bytes(),options)
    (root/'job-id.txt').write_text(job['id'])
    from zhijiang.deck_renderer import render_template_presentation
    import shutil
    def retained_render(lesson,path):
        folder=Path(path).parent;audio=source_audio(folder,lesson)
        for i,a in enumerate(audio,1):
            target=folder/'acceptance-audio'/f'source-{i:03d}.wav';target.parent.mkdir(exist_ok=True)
            shutil.copyfile(a,target)
            target.with_suffix('.json').write_text(json.dumps({'origin':'original PCM WAV'}),encoding='utf-8')
        render_template_presentation(lesson,path,audio_files=audio)
    print('fresh original finance PDF: '+job['id'],flush=True)
    JobProcessor(settings,store,presentation_renderer=retained_render).process(job['id'])
    final=store.get(job['id']);print(json.dumps(final,ensure_ascii=False),flush=True)
    if final['status']!='completed':raise SystemExit('Actual generation failed: '+str(final['error']))
    folder=store.jobs_dir/job['id'];lesson=store.lesson(job['id'])
    (folder/'lesson.json').write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
    result=inspect(folder,lesson)
    result.update(baseline='original PDF; actual local extraction, script, director, exhibit and system speech pipeline; development regression after omission repair')
    (root/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
