"""Repeatable local-model, multi-subject and long-video production checks.

Inputs are original teaching notes. Reports and generated files stay in data/.
The duration probe uses a synthetic audio signal, not a generated lecture.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import wave
import math
from array import array
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PIL import Image
import imageio_ffmpeg
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from zhijiang.config import Settings
from zhijiang.models import GenerationOptions,Mode,VoiceMode
from zhijiang.pipeline import JobProcessor
from zhijiang.storage import JobStore
from zhijiang.page_media import narrated_pages,clip_duration


CASES={
 'physics': ('传热方式',[
    '热传导是接触物体内部或物体之间的能量传递。它不要求物体整体移动。金属勺的一端接触热水，另一端也会升温。热从高温处传向低温处。',
    '热对流伴随流体的宏观运动。锅中的水受热后发生流动，运动的流体携带能量。热辐射通过电磁波传递能量，能够穿过真空。太阳向地球传递能量就是辐射。',
    '三种方式的区别是是否需要物质接触、流体运动以及能否通过真空。在真实环境中，多种传热方式可以同时存在，不能把它们都画成同一个机械流程。']),
 'finance': ('现金流与利润',[
    '现金流是一定期间内实际流入和流出的现金。收入确认与收款可能发生在不同时间，所以利润与现金流不是同一概念。赊销已经确认收入时，现金可能尚未收到。',
    '经营活动现金流来自日常经营，例如收到客户货款和支付供应商货款。投资活动现金流与长期资产和投资有关，例如购买设备。筹资活动现金流与借款和权益融资有关。',
    '现金流量的类别取决于交易的经济性质，不能只根据流入或流出判断类别。利润反映会计期间的经营成果，现金流反映现金变化，两者需要结合阅读。']),
 'biology': ('种子萌发的条件',[
    '种子萌发需要适宜的水分、氧气和温度。种子吸水后，内部的代谢活动逐渐恢复。氧气参与细胞呼吸，为生命活动提供能量。不同植物适宜的温度范围可能不同。',
    '萌发过程中，胚根通常先突破种皮，随后胚芽继续生长。胚根与胚芽不是同一个器官，不能把它们标在同一张不分结构的图片上。种皮在萌发前起保护作用。',
    '仅具备外界条件并不能保证所有种子都会萌发。种子还需要具有活力，部分种子存在休眠。观察萌发时，需要同时记录外部条件与种子的状态。']),
}


def original_pdf(path,title,paragraphs):
    font=Path('C:/Windows/Fonts/simhei.ttf')
    if not font.is_file():raise RuntimeError('Original Chinese fixtures require the Windows SimHei font.')
    pdfmetrics.registerFont(TTFont('MatrixChinese',str(font)))
    doc=canvas.Canvas(str(path));doc.setTitle(title);doc.setAuthor('Book2Course original test fixture')
    doc.setFont('MatrixChinese',20);doc.drawString(42,795,title)
    y=745;doc.setFont('MatrixChinese',13)
    for paragraph in paragraphs:
        for start in range(0,len(paragraph),36):doc.drawString(42,y,paragraph[start:start+36]);y-=22
        y-=22
    doc.save()


def decode(path):
    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(path),
                           '-f','null','-'],capture_output=True)
    return result.returncode==0


def run(root,model,long_seconds,real_model):
    root.mkdir(parents=True,exist_ok=True);report={'model_tests':[],'duration_probe':{},
        'limits':'The measured duration is a test load, not an application maximum.'}
    if real_model:
        local=Settings.from_env();store=JobStore(root/'tasks')
        processor=JobProcessor(Settings(data_dir=store.data_dir,system_voice=local.system_voice,
                                        ollama_num_gpu=local.ollama_num_gpu),store)
        for name,(title,paragraphs) in CASES.items():
            source=root/f'{name}.pdf';original_pdf(source,title,paragraphs)
            job=store.create(source.name,Mode.AI,VoiceMode.SYSTEM,True,False,source.read_bytes(),
                GenerationOptions(provider='ollama',base_url='http://127.0.0.1:11434',model=model,
                    semantic_thinking=False,ppt_template={'physics':'academic','finance':'editorial','biology':'paper'}[name]))
            print('generating',name,job['id'],flush=True);processor.process(job['id'])
            state=store.get(job['id']);item={'subject':name,'job_id':job['id'],'status':state['status'],
                                            'model':model,'thinking':False,'error':state['error']}
            if state['status']=='completed':
                folder=store.jobs_dir/job['id'];manifest=json.loads((folder/'presentation-preview/manifest.json').read_text())
                item.update(duration=clip_duration(folder/'lesson.mp4'),decodable=decode(folder/'lesson.mp4'),
                    slides=len(manifest['pages']),representations=sorted({p.get('representation','') for p in manifest['pages'] if p['kind']=='content'}))
            report['model_tests'].append(item)
            (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print('result',name,state['status'],flush=True)
    if long_seconds>0:
        folder=root/'duration';folder.mkdir(exist_ok=True)
        states=[]
        for i,color in enumerate(['#29547b','#427541','#a05b35']):
            path=folder/f'frame-{i}.png';Image.new('RGB',(1280,720),color).save(path);states.append(path)
        audio=folder/'synthetic.wav'
        with wave.open(str(audio),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000)
            tone=array('h',(int(5000*math.sin(2*math.pi*440*i/24000)) for i in range(24000))).tobytes()
            for _ in range(long_seconds):wav.writeframes(tone)
        output=folder/'long.mp4';print('encoding duration probe',long_seconds,flush=True)
        narrated_pages(states,audio,output)
        report['duration_probe']={'input_seconds':long_seconds,'output_seconds':clip_duration(output),
            'decodable':decode(output),'resolution':[1280,720],'audio':'synthetic test signal, not AI narration',
            'bytes':output.stat().st_size}
    (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('data/generation-matrix'))
    parser.add_argument('--real-local-model',action='store_true')
    parser.add_argument('--model',default='qwen3.5:9b')
    parser.add_argument('--long-seconds',type=int,default=1800)
    args=parser.parse_args()
    result=run(args.output,args.model,args.long_seconds,args.real_local_model)
    print('report',str((args.output/'report.json').resolve()))
    if any(r['status']!='completed' or not r.get('decodable') for r in result['model_tests']):sys.exit(1)
    probe=result['duration_probe']
    if probe and (not probe['decodable'] or abs(probe['output_seconds']-probe['input_seconds'])>.2):sys.exit(1)
