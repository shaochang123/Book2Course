"""Evaluate a previously unseen textbook with the production AI planner.

Only the PDF and page selection are supplied. No topic-specific prompt, authored
scene, example values, SVG, coordinates, or storyboard is passed to the model.
Original PDF page numbers are retained. Local model logs and artifacts stay in
the ignored data directory; the publisher's attribution belongs in the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader

from zhijiang.agents import AIAgents,OllamaClient,validate_knowledge,validate_lesson
from zhijiang.config import Settings
from zhijiang.models import SourceDocument,PageText,KnowledgeBundle,VoiceMode
from zhijiang.teaching_design import prepare_source_assets
from zhijiang.visual_planning import plan_general_lesson
from zhijiang.visual_media import render_visual_assets,visual_summary_svg
from zhijiang.math_media import render_summary_png
from zhijiang.presentation import render_presentation
from zhijiang.speech import SystemSpeech
from zhijiang.video import render_video
from zhijiang.pdf import extract_page_text


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf',type=Path,required=True)
    parser.add_argument('--pages',required=True,help='Original PDF page numbers, for example 18,19,20')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model')
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--no-thinking',action='store_true',help='Disable optional Ollama thinking, using server-advertised controls only')
    args=parser.parse_args();settings=Settings.from_env();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    reader=PdfReader(args.pdf);numbers=[int(value) for value in args.pages.split(',')]
    document=SourceDocument(filename=args.pdf.name,pages=[PageText(page=number,
        text=extract_page_text(reader.pages[number-1]))
        for number in numbers])
    # Inputs are saved before model planning to make selection/re-runs auditable.
    source_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    manifest={'source_pdf':str(args.pdf.resolve()),'sha256':source_hash,'pages':numbers,
              'model':args.model or settings.llm_model,'prompt':'','authored_scene':False,
              'semantic_thinking':not args.no_thinking,'parser':'pdf-pages-v2'}
    (out/'input.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'parsed-source.json').write_text(document.model_dump_json(indent=2),encoding='utf-8')
    assets=prepare_source_assets(args.pdf,out/'source-pages',document)
    client=OllamaClient(settings.llm_base_url,manifest['model'],semantic_thinking=manifest['semantic_thinking'])
    agents=AIAgents(client)
    try:
        path=out/'knowledge.json';fingerprint=hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
        bundle=None
        if path.exists():
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved.get('fingerprint')==fingerprint:
                bundle=KnowledgeBundle.model_validate(saved['bundle']);validate_knowledge(document,bundle)
        if bundle is None:
            bundle=agents.extract_knowledge(document,cache_dir=out/'knowledge-batches',cache_fingerprint=fingerprint,
                progress=lambda done,total,phase:print(phase,done,total,flush=True))
            validate_knowledge(document,bundle)
            path.write_text(json.dumps({'fingerprint':fingerprint,'bundle':bundle.model_dump()},ensure_ascii=False,indent=2),encoding='utf-8')
        print('Knowledge points:',[point.title for point in bundle.points],flush=True)
        lesson=plan_general_lesson(client,bundle,document,'',VoiceMode.SYSTEM,
            lambda phase,*_:print(phase,flush=True),draft_output=out/'visual-planning.json',source_assets=assets,pdf_path=args.pdf)
        validate_lesson(document,lesson)
        for index,segment in enumerate(lesson.segments,1):
            folder=out/'visual'/f'scene-{index:02d}';folder.mkdir(parents=True,exist_ok=True)
            (folder/'summary.svg').write_text(visual_summary_svg(segment.visual_scene),encoding='utf-8')
            render_summary_png(folder/'summary.svg',folder/'summary.png')
        (out/'lesson.json').write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
        if args.render:
            render_visual_assets(lesson,SystemSpeech(settings.system_voice),out,lambda phase,*_:print(phase,flush=True),reuse_audio=True)
            (out/'lesson.json').write_text(lesson.model_dump_json(indent=2),encoding='utf-8')
            render_video(lesson,[out/'visual'/f'scene-{i:02d}'/'narration.wav' for i in range(1,len(lesson.segments)+1)],out/'lesson.mp4')
            render_presentation(lesson,out/'lesson.pptx')
            from scripts.verify_teaching_artifacts import verify
            verify(out,document=document)
        (out/'result.json').write_text(json.dumps({'passed':True,'input':manifest,
            'segment_count':len(lesson.segments),'representations':lesson.animation_report['representations'],
            'rendered':args.render},ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as exc:
        (out/'result.json').write_text(json.dumps({'passed':False,'input':manifest,'error':str(exc)},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    finally:
        (out/'model-calls.json').write_text(json.dumps(client.call_metrics,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'model-errors.json').write_text(json.dumps(client.invalid_outputs,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'knowledge-planning.json').write_text(json.dumps(agents.knowledge_drafts,ensure_ascii=False,indent=2),encoding='utf-8')
        client.close()


if __name__=='__main__':main()
