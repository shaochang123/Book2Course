"""Exercise production mathematical planning on every automatically found topic.

Only published PDF pages and a shared representation preference are supplied.
Failed topics are retained, not replaced by an authored scene or silently dropped.
This isolates scenes for assessment; it does not claim whole-book coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from zhijiang.agents import AIAgents, OllamaClient, validate_knowledge
from zhijiang.config import Settings
from zhijiang.models import KnowledgeBundle, Lesson, LessonSegment, Mode, PageText, SourceDocument, VoiceMode
from zhijiang.pdf import extract_page_text
from zhijiang.speech import SystemSpeech
from zhijiang.visual_media import render_visual_scene, visual_summary_svg
from zhijiang.math_media import render_summary_png
from zhijiang.visual_planning import plan_visual_scenes

PREFERENCE='只选择需要数学对象推演的核心数学知识与必要条件，不选人物历史背景、重复子主题或泛泛回顾。短选页可仅选一个知识点。画出真实数学对象，用连续几何变化解释当前知识；不能用流程图、文字卡片或原页高亮替代。由当前原文自行设计对象、参数和步骤；原创数值示例须标注，保留条件并计算核验。'


def run_case(pdf: Path, pages: list[int], output: Path, render: bool, model: str | None = None):
    output.mkdir(parents=True,exist_ok=True)
    settings=Settings.from_env()
    reader=PdfReader(pdf)
    document=SourceDocument(filename=pdf.name,pages=[PageText(page=n,text=extract_page_text(reader.pages[n-1])) for n in pages])
    manifest={'source_pdf':str(pdf.resolve()),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
              'pages':pages,'model':model or settings.llm_model,'prompt':PREFERENCE,
              'geometry_required':True,'authored_scene':False,'authored_topics':False,
              'semantic_thinking':False,'complete_sources':True,'decoding':'json with program schema validation',
              'protocol':'automatic-topic-isolated-math-v2'}
    code_files=['agents.py','models.py','visual_planning.py','visual_geometry_checks.py','visual_media.py','visual_renderer.py','visual_coordinates.py','pdf.py','speech.py','math_media.py']
    manifest['code_sha256']={name:hashlib.sha256((Path('zhijiang')/name).read_bytes()).hexdigest() for name in code_files}
    (output/'input.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'parsed-source.json').write_text(document.model_dump_json(indent=2),encoding='utf-8')
    client=OllamaClient(settings.llm_base_url,manifest['model'],semantic_thinking=False,
        prefer_json=True,
        progress=lambda stage,seconds,chars:print(f'LLM {stage}: {seconds}s / {chars} chars',flush=True))
    agents=AIAgents(client);results=[]
    try:
        fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
        path=output/'knowledge.json';bundle=None
        if path.exists():
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved['fingerprint']==fingerprint:
                bundle=KnowledgeBundle.model_validate(saved['bundle']);validate_knowledge(document,bundle)
        if bundle is None:
            bundle=agents.extract_knowledge(document,cache_dir=output/'knowledge-batches',cache_fingerprint=fingerprint,
                teaching_preference=PREFERENCE,
                complete_sources=True,
                progress=lambda *v:print(*v,flush=True))
            validate_knowledge(document,bundle)
            path.write_text(json.dumps({'fingerprint':fingerprint,'bundle':bundle.model_dump()},ensure_ascii=False,indent=2),encoding='utf-8')
        for index,point in enumerate(bundle.points,1):
            folder=output/f'topic-{index:02d}';folder.mkdir(exist_ok=True)
            result={'index':index,'title':point.title,'evidence':point.evidence.model_dump(),
                    'generated':False,'human_review':'pending'}
            print(index,point.title,flush=True)
            lesson=Lesson(title=point.title,objective='通过连续数学对象演示解释当前原文知识点。',mode=Mode.AI,
                voice_mode=VoiceMode.SYSTEM,notice='自动规划的数学教学示例，来源和内容需复核。',
                segments=[LessonSegment(title=point.title,kind=point.kind,narration=point.explanation+' 请观察当前数学演示。',
                    bullets=[point.title],evidence=point.evidence)])
            try:
                plan_visual_scenes(client,lesson,document,PREFERENCE,lambda *v:print(*v,flush=True),
                    draft_output=folder/'visual-planning.json',pedagogical_design=True,pdf_path=pdf,geometry_only=True)
                scene=lesson.segments[0].visual_scene
                (folder/'lesson.json').write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
                (folder/'summary.svg').write_text(visual_summary_svg(scene),encoding='utf-8')
                render_summary_png(folder/'summary.svg',folder/'summary.png')
                if render:
                    result['render_code_sha256']=hashlib.sha256(Path('zhijiang/visual_renderer.py').read_bytes()).hexdigest()
                    result['asset']=render_visual_scene(scene,SystemSpeech(settings.system_voice),folder/'render',reuse_audio=True)
                    from scripts.verify_math_artifacts import media_check,frame_at
                    result['media']=media_check(folder/'render'/'clip.mp4')
                    for beat,timing in enumerate(result['asset']['timing'],1):
                        for label,fraction in [('mid',.28),('end',.92)]:
                            frame_at(folder/'render'/'clip.mp4',timing['start']+timing['duration']*fraction).save(folder/f'beat-{beat:02d}-{label}.png')
                result['generated']=True
                result['representation']='geometry'
                result['numeric_verification']=scene.verification
            except Exception as exc:
                result['error']=str(exc);print('FAILED',str(exc),flush=True)
            results.append(result)
            (output/'results.json').write_text(json.dumps({'input':manifest,'topics':results,
                'all_generated':all(r['generated'] for r in results),'assessment_complete':False},ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as exc:
        (output/'results.json').write_text(json.dumps({'input':manifest,'topics':results,'all_generated':False,
            'extraction_error':str(exc),'assessment_complete':False},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    finally:
        (output/'model-calls.json').write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        (output/'model-errors.json').write_text(json.dumps(client.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
        (output/'knowledge-planning.json').write_text(json.dumps(agents.knowledge_drafts,ensure_ascii=False,indent=2),encoding='utf-8')
        client.close()
    return results


def main():
    import sys
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf',type=Path)
    parser.add_argument('--pages')
    parser.add_argument('--manifest',type=Path,help='Source manifest; all cases unless --case is supplied')
    parser.add_argument('--case',help='Case ID from the manifest')
    parser.add_argument('--download',action='store_true',help='Download missing publisher PDFs and verify their recorded hashes')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model')
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    if args.manifest:
        import httpx
        manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
        cases=[c for c in manifest['cases'] if not args.case or c['id']==args.case]
        if not cases:parser.error('Unknown case ID')
        all_generated=True
        for case in cases:
            pdf=Path(case['local_pdf'])
            if not pdf.exists() and args.download:
                response=httpx.get(case['pdf_url'],follow_redirects=True,timeout=180)
                response.raise_for_status()
                if not response.content.startswith(b'%PDF-'):raise ValueError('Publisher did not return a PDF')
                if hashlib.sha256(response.content).hexdigest()!=case['sha256']:
                    raise ValueError('Publisher PDF changed; update source selection and review it before testing')
                pdf.parent.mkdir(parents=True,exist_ok=True);pdf.write_bytes(response.content)
            if not pdf.exists():parser.error('Missing PDF; use --download or supply the matching local file')
            if hashlib.sha256(pdf.read_bytes()).hexdigest()!=case['sha256']:raise ValueError('Local source PDF hash mismatch')
            print('CASE',case['id'],flush=True)
            try:
                results=run_case(pdf,case['pdf_pages'],args.output.resolve()/case['id'],args.render,args.model)
                all_generated &= bool(results) and all(r['generated'] for r in results)
            except Exception as exc:
                all_generated=False;print('CASE FAILED',case['id'],str(exc),flush=True)
        if not all_generated:sys.exit(1)
    else:
        if args.pdf is None or not args.pages:parser.error('--pdf and --pages are required without --manifest')
        results=run_case(args.pdf,[int(v) for v in args.pages.split(',')],args.output.resolve(),args.render,args.model)
        if not results or not all(r['generated'] for r in results):sys.exit(1)


if __name__=='__main__':main()
