"""Exercise PDF upload -> live AI planning -> SVG/audio/video/PPT through HTTP.

Selected PDFs are lawful test excerpts, not prewritten scenes. Failure records
and every produced artifact remain available for independent human acceptance.
"""
import argparse
import hashlib
import json
import time
import zipfile
import shutil
from io import BytesIO
from pathlib import Path

import httpx
from pypdf import PdfReader, PdfWriter
from scripts.verify_math_artifacts import media_check, frame_at


def code_hashes():
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path('zhijiang').rglob('*'))
        if p.is_file() and p.suffix in {'.py','.js','.html','.css','.ps1'} and '__pycache__' not in p.parts}


def snapshot_diagnostics(job_id,folder):
    """Retain this run's evidence before the server overwrites retry outputs."""
    root=Path('data/jobs').resolve();job=(root/job_id).resolve()
    if job==root or not job.is_relative_to(root):raise ValueError('Invalid diagnostic job path')
    sources=sorted(source for source in job.iterdir()
        if source.is_file() and source.suffix in {'.json','.svg','.png'})
    hashes={source.name:hashlib.sha256(source.read_bytes()).hexdigest() for source in sources}
    digest=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    destination=folder/'job-diagnostics'
    if destination.exists():
        # Retry evidence is immutable. A later diagnostic must not overwrite
        # the earlier run's files merely because both runs share a job ID.
        destination=folder/'job-diagnostics-history'/digest
    destination.mkdir(parents=True,exist_ok=True)
    for source in sources:
        target=destination/source.name
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=hashes[source.name]:
                raise RuntimeError('Diagnostic snapshot changed while being copied')
        else:shutil.copy2(source,target)
    (destination/'snapshot.sha256.json').write_text(json.dumps(hashes,sort_keys=True,indent=2),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8765')
    parser.add_argument('--case')
    parser.add_argument('--model',default='qwen3.5:9b')
    parser.add_argument('--review-model',default='')
    parser.add_argument('--math-model',default='')
    parser.add_argument('--inputs-from',type=Path,help='Retry failed HTTP jobs with hash-verified identical public inputs; no authored scene is reused.')
    parser.add_argument('--output',type=Path,default=Path('data/math-repair/web-acceptance'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    source_manifest=json.loads(Path('examples/math-level-sources.json').read_text(encoding='utf-8'))
    cases=[c for c in source_manifest['cases'] if not args.case or c['id']==args.case]
    if not cases:parser.error('Unknown case; the validation selection must not be empty.')
    frozen=code_hashes();records=[]
    with httpx.Client(base_url=args.url,timeout=180,trust_env=False) as client:
        config=client.get('/api/config');config.raise_for_status()
        assert config.json()['ollama_semantic_thinking'] is True
        for case in cases:
            if code_hashes()!=frozen:raise RuntimeError('Implementation changed during the acceptance run; rerun the complete corpus.')
            folder=args.output/case['id'];folder.mkdir(parents=True,exist_ok=True)
            record={'case':case,'code_sha256':frozen,'authored_scene':False,'manual_review':'pending','accepted':False,
                'requested_thinking_level':config.json().get('ollama_thinking_level','')}
            try:
                data=Path(case['local_pdf']).read_bytes()
                assert hashlib.sha256(data).hexdigest()==case['sha256']
                reader=PdfReader(BytesIO(data));writer=PdfWriter()
                for page in case['pdf_pages']:writer.add_page(reader.pages[page-1])
                buffer=BytesIO();writer.write(buffer);excerpt=buffer.getvalue()
                (folder/'input.pdf').write_bytes(excerpt)
                record['uploaded_sha256']=hashlib.sha256(excerpt).hexdigest()
                record['original_page_mapping']={i+1:n for i,n in enumerate(case['pdf_pages'])}
                print('UPLOAD',case['id'],flush=True)
                options={'rights_confirmed':'true','remote_consent':'true','mode':'ai','voice_mode':'system','animation_mode':'geometry',
                        'llm_provider':'ollama','llm_base_url':'http://127.0.0.1:11434','llm_model':args.model,
                        'llm_review_model':args.review_model,
                        'llm_math_model':args.math_model,
                        'custom_prompt':'解释本选页核心数学问题及必要条件，保留来源例子，绘制真实数学对象并通过连续变化说明原因。'}
                reused=False
                old_record=args.inputs_from/case['id']/'job.json' if args.inputs_from else None
                if old_record and old_record.is_file():
                    old=json.loads(old_record.read_text(encoding='utf-8'));old_id=old['job_id']
                    old_job=client.get(f'/api/jobs/{old_id}');old_job.raise_for_status()
                    if old_job.json()['status']=='failed':
                        original=Path('data/jobs')/old_id/'source.pdf'
                        assert original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest()==record['uploaded_sha256']
                        assert old['original_page_mapping']=={str(k):v for k,v in record['original_page_mapping'].items()}
                        snapshot_diagnostics(old_id,old_record.parent)
                        record['input_reused_from']=str(old_record)
                        record['prior_job_code_sha256']=old['code_sha256']
                        response=client.post(f'/api/jobs/{old_id}/retry',data=options);reused=True
                if not reused:
                    response=client.post('/api/jobs',files={'file':(case['id']+'.pdf',excerpt,'application/pdf')},data=options)
                response.raise_for_status();job_id=response.json()['id'];record['job_id']=job_id
                (folder/'job.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                previous='';start=time.monotonic()
                while True:
                    response=client.get(f'/api/jobs/{job_id}');response.raise_for_status();job=response.json()
                    stage=job['stage']
                    if stage!=previous:print(case['id'],job['status'],stage,flush=True);previous=stage
                    if job['status'] in {'failed','completed'}:break
                    if time.monotonic()-start>7200:raise TimeoutError('Live task exceeded two hours; retained for inspection.')
                    time.sleep(5)
                record['status']=job
                if job['status']!='completed':raise RuntimeError(job.get('error','Generation failed'))
                lesson=client.get(f'/api/jobs/{job_id}/lesson');lesson.raise_for_status()
                course=lesson.json();(folder/'lesson.json').write_text(json.dumps(course,ensure_ascii=False,indent=2),encoding='utf-8')
                for endpoint,filename in [('video','lesson.mp4'),('presentation','lesson.pptx'),('scenes','scene-data.json')]:
                    response=client.get(f'/api/jobs/{job_id}/{endpoint}');response.raise_for_status()
                    (folder/filename).write_bytes(response.content)
                record['media']=media_check(folder/'lesson.mp4')
                with zipfile.ZipFile(folder/'lesson.pptx') as ppt:
                    record['pptx']={'svg_count':len([n for n in ppt.namelist() if n.endswith('.svg')]),
                        'video_count':len([n for n in ppt.namelist() if n.endswith('.mp4')]),
                        'slide_count':len([n for n in ppt.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')])}
                    assert record['pptx']['svg_count']>=1 and record['pptx']['video_count']>=1
                scenes=json.loads((folder/'scene-data.json').read_text(encoding='utf-8'))
                for i,asset in enumerate(scenes['assets'],1):
                    clip=Path('data/jobs')/job_id/'visual'/f'scene-{i:02d}'/'clip.mp4'
                    for j,timing in enumerate(asset['timing'],1):
                        for label,fraction in [('mid',.28),('end',.92)]:
                            frame_at(clip,timing['start']+timing.get('source_seconds',0)+fraction*(timing['duration']-timing.get('source_seconds',0))).save(folder/f'scene-{i}-beat-{j}-{label}.png')
                        for k,panel in enumerate(timing.get('fact_panels',[]),1):
                            frame_at(clip,timing['start']+panel['start']+.5*panel['duration']).save(folder/f'scene-{i}-beat-{j}-source-{k}.png')
                if code_hashes()!=frozen:raise RuntimeError('Implementation changed during generation; this run cannot be accepted.')
                record['automatic_checks_passed']=True
            except Exception as exc:
                record['error']=f'{type(exc).__name__}: {exc}';print('FAIL',case['id'],record['error'],flush=True)
            if record.get('job_id'):snapshot_diagnostics(record['job_id'],folder)
            records.append(record)
            (folder/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            (args.output/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    if not all(r.get('automatic_checks_passed') for r in records):raise SystemExit(1)


if __name__=='__main__':main()
