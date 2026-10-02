"""Original cross-subject regression fixtures, rendered by one generic engine.

These are authored test models, not a claim that a model or verifier proves every
subject. Use the web/PDF workflow to test actual model planning separately.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

from zhijiang.config import Settings
from zhijiang.models import (VisualScenePlan, SceneObject, VisualBeat, Evidence,
    SceneCalculation, SceneCheck, Lesson, LessonSegment, Mode, VoiceMode)
from zhijiang.visual_media import render_visual_assets
from zhijiang.speech import AISpeech
from zhijiang.video import render_video
from zhijiang.presentation import render_presentation


REFERENCES = [
    'Original calculus fixture: for f(x)=x squared, P=(1,1) is fixed and Q=(1+h,(1+h) squared) approaches P as positive h decreases. The secant slope is 2+h. A finite secant is not the limiting tangent.',
    'Original probability fixture: an event with probability p and its complement partition a unit total. Their probabilities are p and 1-p. The areas of two equal-height rectangles represent this partition as p changes within the unit interval.',
    'Original physics fixture: in a simplified constant-gravity model with unit mass, horizontal velocity 1, vertical initial velocity 2, and gravity 1, x=t and y=2t-t squared/2. The sum of kinetic and gravitational potential energy is 2.5. Air resistance is omitted.',
    'Original chemistry fixture: the balanced equation 2 H2 + O2 -> 2 H2O conserves four hydrogen and two oxygen atoms. Repositioning six persistent colored atoms and changing displayed bonds illustrates stoichiometry; interpolated motion is not reaction dynamics.',
    'Original biology fixture: a substrate can bind an enzyme active site, undergo a catalyzed conversion, and leave as products. The enzyme is available again afterwards. Circles and dots are a schematic teaching model, not molecular geometry or a kinetic simulation.',
]


def fixtures():
    def obj(id,kind='dot',points=None,**kw): return SceneObject(id=id,kind=kind,points=points or [],**kw)
    def beat(words,changes=None,**kw): return VisualBeat(narration=words,parameters=changes or {},**kw)
    def make(i,domain,question,params,objects,beats,**kw):
        return VisualScenePlan(domain=domain,question=question,parameters=params,objects=objects,beats=beats,
                               evidence=Evidence(page=i+1,quote=REFERENCES[i][:280]),**kw)
    calculus=make(0,'微积分','割线为什么越来越接近切线？',{'a':1,'h':1},[
        obj('function','curve',expression='x**2',domain=[0,2],color='#6DE2C0'),
        obj('p',points=[['a','a**2']],color='#78BAFF'),
        obj('q',points=[['a+h','(a+h)**2']],color='#FFA458'),
        obj('secant','line',[['a','a**2'],['a+h','(a+h)**2']],color='#FFA458'),
        obj('tangent','curve',expression='2*a*(x-a)+a**2',domain=[0,2],color='#CB94FF')],[
        beat('固定蓝色点，橙色点位于同一条抛物线上。连接两点得到割线；紫色直线表示固定点处的切线。'),
        beat('减小横坐标间隔，橙色点沿曲线接近蓝色点。割线方向同时变化，计算结果与当前点的位置保持对应。',{'h':.4},calculations=[SceneCalculation(label='割线斜率',expression='((a+h)**2-a**2)/h',expected=2.4)]),
        beat('继续缩小间隔，割线斜率进一步接近切线斜率二。当前间隔仍然非零，所以两条直线尚未完全重合。',{'h':.1},calculations=[SceneCalculation(label='割线斜率',expression='((a+h)**2-a**2)/h',expected=2.1)])],axes=True,x_range=[0,2.5],y_range=[0,4.5],
        simplifications=['数值示例采用二次函数；有限步骤展示逼近，不宣称证明任意函数的极限。'])
    probability=make(1,'概率论','事件和补事件如何分配同一个总量？',{'p':.2},[
        obj('event','polygon',[['-3','0'],['-3+6*p','0'],['-3+6*p','1'],['-3','1']],color='#78BAFF'),
        obj('complement','polygon',[['-3+6*p','0'],['3','0'],['3','1'],['-3+6*p','1']],color='#FFA458'),
        obj('label_event','label',[['-3+3*p','-.5']],text='事件'),
        obj('label_complement','label',[['3*p','-.5']],text='补事件',color='#FFA458')],[
        beat('两块相同高度的矩形共同表示全部可能性。蓝色面积对应事件，橙色面积对应补事件，总宽度保持不变。'),
        beat('改变事件概率，分界线移动。蓝色增加的份额由橙色相应减少，因此两部分仍然覆盖同一个整体。',{'p':.5},calculations=[SceneCalculation(label='概率总和',expression='p+(1-p)',expected=1)]),
        beat('再提高事件概率，观察分界线和两块面积同步变化。任何时刻概率都在零与一之间，事件和补事件之和始终为一。',{'p':.8},calculations=[SceneCalculation(label='补事件概率',expression='1-p',expected=.2)])],
        checks=[SceneCheck(expression='p+(1-p)',expected=1),SceneCheck(checker='nonnegative',expression='p'),SceneCheck(checker='at_most',expression='p',expected=1)],
        simplifications=['矩形面积表示概率份额，不表示真实随机样本的频数。'])
    energy='(vx**2+(vy-g*t)**2)/2+g*(vy*t-g*t**2/2)'
    physics=make(2,'物理','同一小球的轨迹和能量如何对应？',{'t':0,'vx':1,'vy':2,'g':1},[
        obj('trajectory','curve',expression='vy*x/vx-g*(x/vx)**2/2',domain=[0,4],color='#6DE2C0'),
        obj('ball',points=[['vx*t','vy*t-g*t**2/2']],radius='.12',color='#FFA458')],[
        beat('采用忽略空气阻力的恒定重力教学模型，绿色曲线显示运动轨迹，橙色小球从地面开始运动。'),
        beat('时间增加，小球一边水平前进，一边上升。竖直速度逐渐减小；画面位置和能量计算来自同一时刻。',{'t':2},calculations=[SceneCalculation(label='机械能',expression=energy,expected=2.5)]),
        beat('经过最高点后小球下降并回到原高度。动能和势能互相转换，在这个理想模型中机械能保持不变。',{'t':4},calculations=[SceneCalculation(label='机械能',expression=energy,expected=2.5)])],
        checks=[SceneCheck(expression=energy,expected=2.5)],axes=True,x_range=[0,4.5],y_range=[0,3],
        simplifications=['单位质量，统一示例单位；恒定重力，无空气阻力，非真实测量数据。'])
    starts=[[-3,-.3],[-2.5,-.3],[-1.8,.4],[-1.3,.4],[1.5,-.3],[2,-.3]]
    ends=[[-1.5,.4],[-.5,.4],[.5,.4],[1.5,.4],[-1,0],[1,0]]
    atoms=[]
    for i,(a,b) in enumerate(zip(starts,ends)):
        atoms.append(obj(f'atom_{i}',points=[[f'{a[0]}+r*({b[0]}-({a[0]}))',f'{a[1]}+r*({b[1]}-({a[1]}))']],radius='.13',color='#78BAFF' if i<4 else '#FFA458'))
    def bond(id,a,b,visible): return obj(id,'line',[atoms[a].points[0],atoms[b].points[0]],color='#AEC4D0',visible=visible)
    chemistry=make(3,'化学','反应前后有哪些数量保持不变？',{'r':0,'hydrogen':4,'oxygen':2},atoms+[
        bond('hh_one',0,1,True),bond('hh_two',2,3,True),bond('oo',4,5,True),
        bond('oh_one',4,0,False),bond('oh_two',4,1,False),bond('oh_three',5,2,False),bond('oh_four',5,3,False)],[
        beat('先辨认两种颜色的原子：蓝色为氢，橙色为氧。初态表示两份氢分子与一份氧分子的配比。'),
        beat('保持六个原子的身份和颜色，重新安排位置。这里只用移动说明反应物到产物的对应，不模拟真实反应路径。',{'r':1},hide=['hh_one','hh_two','oo']),
        beat('现在连接产物中的原子，形成两份水分子的示意。反应前后四个氢原子和两个氧原子的数量相同。',show=['oh_one','oh_two','oh_three','oh_four'],calculations=[SceneCalculation(label='氢原子数',expression='hydrogen',expected=4),SceneCalculation(label='氧原子数',expression='oxygen',expected=2)])],
        checks=[SceneCheck(expression='hydrogen',expected=4),SceneCheck(expression='oxygen',expected=2)],
        simplifications=['二维原子与键示意，不代表真实键角、键长、电子机制或反应动力学。'])
    biology=make(4,'生物','底物如何结合、转化并离开酶？',{'sx':3,'px':1.25,'py':0,'enzyme_count':1},[
        obj('enzyme','circle',[['0','0']],radius='1',color='#6DE2C0'),
        obj('active_site','circle',[['1','0']],radius='.25',color='#AEC4D0'),
        obj('substrate',points=[['sx','0']],radius='.2',color='#FFA458'),
        obj('product_one',points=[['px','py']],radius='.14',color='#78BAFF',visible=False),
        obj('product_two',points=[['px','-py']],radius='.14',color='#CB94FF',visible=False),
        obj('enzyme_label','label',[['0','-1.5']],text='酶与活性部位',color='#6DE2C0')],[
        beat('绿色轮廓表示酶，右侧小圈标记活性部位，橙色粒子表示底物。这些图形用于讲解，并不是分子的真实结构。'),
        beat('底物接近活性部位并形成结合状态。真实结合依赖分子相互作用，图中的直线移动只是过程示意。',{'sx':1.25}),
        beat('用两个不同颜色的产物标记催化转化后的状态。该例只说明过程顺序，并不指定某种真实酶的化学反应。',{'py':.2},hide=['substrate'],show=['product_one','product_two']),
        beat('产物离开活性部位，酶再次可用于后续过程。观察酶的对象身份始终保持，同一份酶没有被当作产物消耗。',{'px':3,'py':.8})],
        checks=[SceneCheck(expression='enzyme_count',expected=1)],
        simplifications=['泛化的催化过程示意；无真实分子几何、诱导契合形变或速率模型。'])
    return [calculus,probability,physics,chemistry,biology]


def build(output: Path, *, reuse_audio=False):
    output=output.resolve(); output.mkdir(parents=True,exist_ok=True)
    source=canvas.Canvas(str(output/'source.pdf'))
    for i,text in enumerate(REFERENCES):
        source.setFont('Helvetica',11); source.drawString(45,790,f'Book2Course original regression reference {i+1}')
        for j,line in enumerate(simpleSplit(text,'Helvetica',11,490)): source.drawString(45,750-j*18,line)
        source.showPage()
    source.save()
    scenes=fixtures()
    lesson=Lesson(title='跨学科通用场景执行器：五组原创验证示例',objective='验证同一通用图形执行器能够承接不同学科的连续过程与明确的数值关系。',
        mode=Mode.AI,voice_mode=VoiceMode.AI,notice='分镜由开发者编写用于回归验证；配音使用本机模型。本课不是模型自动规划能力的验收。',
        segments=[LessonSegment(title=s.domain+'：'+s.question,kind='process',narration=' '.join(b.narration for b in s.beats),bullets=[s.question],evidence=s.evidence,visual_scene=s) for s in scenes],
        animation_report={'renderer':'Manim scene graph','scene_type':'general','scene_count':len(scenes),'planning':'authored regression fixtures'})
    settings=Settings.from_env()
    if not settings.ai_tts_ready: raise RuntimeError('Configure the local speech API before rendering examples')
    speech=AISpeech(settings.tts_base_url,settings.tts_api_key,settings.tts_model,settings.tts_voice)
    try:
        render_visual_assets(lesson,speech,output,lambda stage,_:print(stage,flush=True),reuse_audio=reuse_audio)
    finally: speech.close()
    render_video(lesson,[output/'visual'/f'scene-{i+1:02d}'/'narration.wav' for i in range(len(scenes))],output/'lesson.mp4')
    render_presentation(lesson,output/'lesson.pptx')
    print(output,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--output',type=Path,default=Path('data/exports/general-examples'))
    parser.add_argument('--reuse-audio',action='store_true',help='Reuse exact matching fixture speech for visual QA revisions')
    args=parser.parse_args(); build(args.output,reuse_audio=args.reuse_audio)
