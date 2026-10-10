"""Program-controlled, editable SVG diagrams for reviewed compact slide stories."""
from __future__ import annotations
import html
from PIL import Image, ImageDraw
from zhijiang.presentation import _font, PresentationError


def lines(text, width, size=32):
    draw=ImageDraw.Draw(Image.new('RGB',(1,1)));font=_font(size)
    result=[];line=''
    for c in text:
        if c=='\n' or line and draw.textlength(line+c,font=font)>width:
            result.append(line);line=''
        if c!='\n':line+=c
    if line:result.append(line)
    return result


def visual_svg(visual, template, width, height, *, reveal=None, art_slots=()):
    """Return SVG and node boxes. No arbitrary SVG from a model is executed."""
    items=visual['items'];count=len(items);view=visual['representation']
    visible=count if reveal is None else min(reveal,count)
    context=visual.get('context','')
    context_lines=lines(context,width-40) if context else []
    context_h=len(context_lines)*42+22 if context else 0
    h=height-context_h
    if h<180:raise PresentationError('图示条件过长，需要拆分教学画面。')
    if view=='table':
        boxes=[(18,18+i*(h-30)/count,width-36,(h-30)/count-8) for i in range(count)]
    elif view=='key_idea' and count==1:
        boxes=[(width*.10,40,width*.80,h-65)]
    elif view=='annotated' and count>1:
        boxes=[(18,18,width*.48,h-36),*[(width*.51,18+i*(h-36)/(count-1),
                width*.49-18,(h-36)/(count-1)-12) for i in range(count-1)]]
    elif view in {'process','relationship'}:
        from types import SimpleNamespace
        from zhijiang.teaching_graph import graph_layers
        graph=SimpleNamespace(representation=view,nodes=[SimpleNamespace(id=i+1) for i in range(count)],
            relations=[SimpleNamespace(source=e['source'],target=e['target'],
                directed=e['kind']!='undirected') for e in visual.get('links',[])])
        layers=graph_layers(graph)
        if layers:
            gap=74;bw=(width-36-gap*(len(layers)-1))/len(layers)
            boxes=[None]*count
            for col,layer in enumerate(layers):
                bh=(h-46-24*(len(layer)-1))/len(layer)
                for row,ni in enumerate(layer):boxes[ni-1]=(18+col*(bw+gap),25+row*(bh+24),bw,bh)
        else:
            # Cycles/undirected links do not pretend to be a topological chain.
            cols=2 if count==4 else min(3,count);rows=(count+cols-1)//cols;gap=74
            bw=(width-36-gap*(cols-1))/cols;bh=(h-46-(rows-1)*40)/rows
            boxes=[(18+(i%cols)*(bw+gap),25+(i//cols)*(bh+40),bw,bh) for i in range(count)]
    elif count<=3:
        gap=26;bw=(width-36-gap*(count-1))/count
        boxes=[(18+i*(bw+gap),32,bw,h-60) for i in range(count)]
    else:
        boxes=[(18+(i%2)*width*.5,16+(i//2)*h*.5,width*.5-36,h*.5-28) for i in range(count)]
    if view=='annotated' and count>2:
        too_tall=any(74+len(lines(item['label'],box[2]-36-(72 if i in art_slots else 0)))*40.32+
            len(lines(item.get('caption',''),box[2]-36))*40.32>box[3]
            for i,(item,box) in enumerate(zip(items,boxes)))
        if too_tall:
            gap=26;bw=(width-36-gap*(count-1))/count
            boxes=[(18+i*(bw+gap),32,bw,h-60) for i in range(count)]
    p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
       '<title>教学概念与示例</title><desc>对象、实例及连线来自经过逐项复核的讲稿；不是物理模拟。</desc>',
       f'<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L9,4.5 L0,9" fill="#{template.accent}"/></marker></defs>']
    secondary={'classic':'9AC8EF','paper':'356585','academic':'9B4F36','editorial':'356585'}[template.id]
    label_accent='806019' if template.id=='paper' else template.accent
    def text(value,x,y,w,size=32,bold=False,color=None):
        wrapped=lines(value,w,size)
        for j,line in enumerate(wrapped):
            p.append(f'<text x="{x}" y="{y+j*size*1.26}" font-family="Microsoft YaHei" font-size="{size}" font-weight="{700 if bold else 400}" fill="#{color or template.ink}">{html.escape(line)}</text>')
        return len(wrapped)*size*1.26
    for i,(item,box) in enumerate(zip(items,boxes)):
        if i>=visible:continue
        x,y,w,bh=box
        if view=='table':
            p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{bh}" rx="10" fill="#{template.panel}"/>')
            split=w*.31
            p.append(f'<path d="M{x+split},{y+12} V{y+bh-12}" stroke="#{template.accent}" stroke-width="3"/>')
            lh=text(item['label'],x+16,y+42,split-30,bold=True,color=label_accent)
            ch=text(item.get('caption',''),x+split+18,y+42,w-split-34,color=secondary)
            if max(lh,ch)+24>bh:raise PresentationError('示例表格内容过多，需要拆页。')
        else:
            size=42 if view=='key_idea' and count==1 else 32
            p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{bh}" rx="18" fill="#{template.panel}"/>')
            p.append(f'<path d="M{x+18},{y+16} H{x+min(w-18,90)}" stroke="#{template.accent}" stroke-width="5"/>')
            # A number identifies comparison/example items, not a causal step.
            lh=text(item['label'],x+18,y+size+30,w-36-(72 if i in art_slots else 0),size,
                    bold=True,color=label_accent if i%2==0 else secondary)
            ch=text(item.get('caption',''),x+18,y+size+48+lh,w-36)
            if size+42+lh+ch>bh:raise PresentationError('概念框文字过多，需要减少画面说明或拆页。')
    for i,link in enumerate(visual.get('links',[])):
        if max(link['source'],link['target'])>visible:continue
        a=boxes[link['source']-1];b=boxes[link['target']-1]
        forward=b[0]>a[0];x1=a[0]+a[2] if forward else a[0];x2=b[0] if forward else b[0]+b[2]
        y1=a[1]+a[3]*.5;y2=b[1]+b[3]*.5
        horizontal=a[0]+a[2]<=b[0] or b[0]+b[2]<=a[0]
        if horizontal:
            # A tall source and short branch still connect through their sides.
            # Using bottom/top ports solely because their tops differ cuts
            # through the source card and can point outside the diagram.
            low=max(a[1],b[1])+16;high=min(a[1]+a[3],b[1]+b[3])-16
            if low<=high:y1=y2=(low+high)/2
        else:
            down=y2>y1
            x1=a[0]+a[2]*.5;x2=b[0]+b[2]*.5
            y1=a[1]+a[3] if down else a[1]
            y2=b[1] if down else b[1]+b[3]
        marker='' if link['kind']=='undirected' else ' marker-end="url(#arrow)"'
        p.append(f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="#{template.accent}" stroke-width="4"{marker}/>')
        # Labels have dedicated upper lanes, avoiding arrow/node intersections.
        label=link['label'];label_lines=lines(label, max(100,abs(x2-x1)),28)
        tx=(x1+x2)/2- max(100,abs(x2-x1))/2
        ty=max(28,min(y1,y2)-18-len(label_lines)*35)
        text(label,tx,ty,max(100,abs(x2-x1)),28)
        if link['kind']=='negative':
            cx=(x1+x2)/2;cy=(y1+y2)/2
            p.append(f'<path d="M{cx-8},{cy-10} L{cx+8},{cy+10}" stroke="#{template.accent}" stroke-width="4"/>')
    if context:
        p.append(f'<path d="M18,{h+7} H{width-18}" stroke="#{template.accent}" stroke-width="2"/>')
        text(context,20,h+48,width-40)
    p.append('</svg>')
    return ''.join(p).encode(),boxes
