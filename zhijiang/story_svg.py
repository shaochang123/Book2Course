"""Program-controlled, editable SVG diagrams for reviewed compact slide stories."""
from __future__ import annotations
import html
from PIL import Image, ImageDraw
from zhijiang.presentation import _font, PresentationError


def visual_pages(visual, template, width, height, *, art_slots=()):
    """Paginate a dense diagram, preserving every object, relation and condition.

    Graph continuations repeat their endpoint identities rather than silently
    dropping cross-page edges. Narration is still used once by the media layer.
    """
    try:
        visual_svg(visual, template, width, height, art_slots=art_slots)
        return [visual]
    except PresentationError:
        pass
    items = visual['items']; links = visual.get('links', [])
    groups = []
    if links:
        groups = [list(dict.fromkeys([e['source']-1, e['target']-1])) for e in links]
        used = {i for group in groups for i in group}
        groups += [[i] for i in range(len(items)) if i not in used]
    else:
        groups = [list(range(i, min(i+2, len(items)))) for i in range(0, len(items), 2)]
    pages = []
    def part(indices):
        mapping = {i+1: n+1 for n,i in enumerate(indices)}
        edges = [{**e, 'source': mapping[e['source']], 'target': mapping[e['target']]}
                 for e in links if e['source'] in mapping and e['target'] in mapping]
        view = visual['representation']
        if not edges and view in {'process', 'relationship'}:
            view = 'annotated'
        if len(indices) == 1 and view != 'table': view = 'key_idea'
        return {**visual, 'representation': view, 'items': [items[i] for i in indices], 'links': edges}
    for indices in groups:
        page = part(indices)
        try:
            visual_svg(page, template, width, height,
                       art_slots=[n for n,i in enumerate(indices) if i in art_slots])
            pages.append(page)
        except PresentationError:
            if page['links']:
                # Keep the complete edge on a diagram page and retain the
                # endpoint explanations on adjacent full-width pages.
                edge_page={**page,'items':[{**item,'caption':''} for item in page['items']]}
                visual_svg(edge_page,template,width,height)
                pages.append(edge_page)
                for i in indices:
                    single=part([i]);visual_svg(single,template,width,height)
                    pages.append(single)
                continue
            # A pair of long independent descriptions can each use a full page.
            if len(indices) == 1:
                raise
            for i in indices:
                single = part([i])
                visual_svg(single, template, width, height, art_slots=[0] if i in art_slots else ())
                pages.append(single)
    return pages


def node_shape(item, view):
    selected = item.get('shape', 'auto')
    if selected != 'auto': return selected
    return 'process' if view == 'process' else 'concept'


def outline_port(box, other, shape):
    """Intersect the center-to-center connector with the actual node outline."""
    import math
    x,y,w,h=box; ox,oy,ow,oh=other
    cx,cy=x+w/2,y+h/2;dx,dy=ox+ow/2-cx,oy+oh/2-cy
    if not dx and not dy:return cx,cy
    if shape in {'concept','result'}:
        scale=1/math.sqrt((dx/(w/2))**2+(dy/(h/2))**2)
    elif shape=='decision':
        scale=1/(abs(dx)/(w/2)+abs(dy)/(h/2))
    elif shape=='data':
        # Parallelogram side intersections, not its rectangular bounding box.
        vertices=[(x+w*.12,y),(x+w,y),(x+w*.88,y+h),(x,y+h)]
        hits=[]
        for (ax,ay),(bx,by) in zip(vertices,vertices[1:]+vertices[:1]):
            ex,ey=bx-ax,by-ay;den=dx*ey-dy*ex
            if abs(den)<1e-9:continue
            t=((ax-cx)*ey-(ay-cy)*ex)/den
            u=((ax-cx)*dy-(ay-cy)*dx)/den
            if t>=0 and 0<=u<=1:hits.append(t)
        scale=min(hits)
    else:
        scale=min((w/2)/abs(dx) if dx else float('inf'),
                  (h/2)/abs(dy) if dy else float('inf'))
    return cx+dx*scale,cy+dy*scale


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
            gap=max(74,min(240,max((ImageDraw.Draw(Image.new('RGB',(1,1))).textlength(
                e['label'],font=_font(28))+24 for e in visual.get('links',[])),default=74)))
            bw=(width-36-gap*(len(layers)-1))/len(layers)
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
    def required(item, box, i):
        size=42 if view=='key_idea' and count==1 else 32
        w=box[2]-36-(72 if i in art_slots else 0)
        if view in {'process','relationship'}:
            shape=node_shape(item,view)
            if shape=='decision':w=box[2]*.6
            elif shape=='data':w=box[2]*.7
            elif shape in {'concept','result'}:w=box[2]*.68-(72 if i in art_slots else 0)
        return 28+len(lines(item['label'],w,size))*size*1.26 + (
            12+len(lines(item.get('caption',''),w))*40.32 if item.get('caption') else 0)
    if view not in {'process','relationship','table'} and count>2:
        if any(required(item,box,i)>box[3] or (view=='annotated' and
               len(lines(item.get('caption',''),box[2]-36))>1)
               for i,(item,box) in enumerate(zip(items,boxes))):
            gap=26;bw=(width-36-gap*(count-1))/count
            boxes=[(18+i*(bw+gap),32,bw,h-60) for i in range(count)]
    if view in {'process','relationship'}:
        # Keep nodes close to the actual text instead of filling entire columns.
        compact=[]
        for i,(item,(x,y,w,bh)) in enumerate(zip(items,boxes)):
            needed=required(item,(x,y,w,bh),i)
            shape=node_shape(item,view)
            if shape in {'concept','result','decision'}:needed*=1.5
            inner_w=w*(.6 if shape=='decision' else .68 if shape in {'concept','result'} else .7 if shape=='data' else 1)-36
            if len(lines(item['label'],inner_w))>2 or len(lines(item.get('caption',''),inner_w))>3:
                raise PresentationError('节点过窄，需要自动拆页。')
            if needed>bh:raise PresentationError('图示内容需要自动拆页。')
            nh=min(bh,max(120,needed+12))
            compact.append((x,y+(bh-nh)/2,w,nh))
        boxes=compact
    p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
       '<title>教学概念与示例</title><desc>根据讲稿规划的对象、实例及连线；不是物理模拟，审核状态见课程报告。</desc>',
       f'<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L9,4.5 L0,9" fill="#{template.accent}"/></marker></defs>']
    secondary={'classic':'9AC8EF','academic':'9B4F36'}.get(template.id,template.secondary)
    label_accent='806019' if template.id=='paper' else template.accent
    def text(value,x,y,w,size=32,bold=False,color=None,center=False):
        wrapped=lines(value,w,size)
        for j,line in enumerate(wrapped):
            p.append(f'<text x="{x+w/2 if center else x}" y="{y+j*size*1.26}" text-anchor="{"middle" if center else "start"}" font-family="Microsoft YaHei" font-size="{size}" font-weight="{700 if bold else 400}" fill="#{color or template.ink}">{html.escape(line)}</text>')
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
            tx=x+18;tw=w-36-(72 if i in art_slots else 0);top=y+18
            if view in {'process','relationship'}:
                shape=node_shape(item,view)
                attrs=f'fill="#{template.panel}" stroke="#{template.accent if i%2==0 else secondary}" stroke-width="3"'
                if shape=='decision':
                    p.append(f'<polygon points="{x+w/2},{y} {x+w},{y+bh/2} {x+w/2},{y+bh} {x},{y+bh/2}" {attrs}/>')
                    tx=x+w*.2;tw=w*.6;top=y+bh*.22
                elif shape=='data':
                    p.append(f'<polygon points="{x+w*.12},{y} {x+w},{y} {x+w*.88},{y+bh} {x},{y+bh}" {attrs}/>')
                    tx=x+w*.15;tw=w*.7
                elif shape=='document':
                    p.append(f'<path d="M{x},{y} H{x+w-24} L{x+w},{y+24} V{y+bh} H{x} Z M{x+w-24},{y} V{y+24} H{x+w}" {attrs}/>')
                elif shape in {'result','concept'}:
                    p.append(f'<ellipse cx="{x+w/2}" cy="{y+bh/2}" rx="{w/2}" ry="{bh/2}" {attrs}/>')
                    tx=x+w*.16;tw=w*.68-(72 if i in art_slots else 0)
                else:
                    p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{bh}" rx="12" {attrs}/>')
            else:
                # Open comparisons and annotations emphasize knowledge, not cards.
                p.append(f'<path d="M{x+18},{y+8} H{x+min(w-18,90)}" stroke="#{template.accent}" stroke-width="4"/>')
            graph=view in {'process','relationship'}
            if graph:
                text_h=len(lines(item['label'],tw,size))*size*1.26
                if item.get('caption'):text_h+=12+len(lines(item['caption'],tw))*40.32
                top=y+(bh-text_h)/2
            lh=text(item['label'],tx,top+size,tw,size,
                    bold=True,color=label_accent if i%2==0 else secondary,center=graph)
            ch=text(item.get('caption',''),tx,top+lh+12+32,tw,center=graph)
            if top-y+lh+(12+ch if ch else 0)>bh:raise PresentationError('图示内容需要自动拆页。')
    for i,link in enumerate(visual.get('links',[])):
        if max(link['source'],link['target'])>visible:continue
        a=boxes[link['source']-1];b=boxes[link['target']-1]
        x1,y1=outline_port(a,b,node_shape(items[link['source']-1],view))
        x2,y2=outline_port(b,a,node_shape(items[link['target']-1],view))
        marker='' if link['kind']=='undirected' else ' marker-end="url(#arrow)"'
        p.append(f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="#{template.accent}" stroke-width="4"{marker}/>')
        # Labels have dedicated upper lanes, avoiding arrow/node intersections.
        label=link['label'];label_lines=lines(label, max(100,abs(x2-x1)),28)
        tx=(x1+x2)/2- max(100,abs(x2-x1))/2
        ty=max(28,min(a[1],b[1])-18-len(label_lines)*35)
        text(label,tx,ty,max(100,abs(x2-x1)),28)
        if link['kind']=='negative':
            cx=(x1+x2)/2;cy=(y1+y2)/2
            p.append(f'<path d="M{cx-8},{cy-10} L{cx+8},{cy+10}" stroke="#{template.accent}" stroke-width="4"/>')
    if context:
        p.append(f'<path d="M18,{h+7} H{width-18}" stroke="#{template.accent}" stroke-width="2"/>')
        text(context,20,h+48,width-40)
    p.append('</svg>')
    return ''.join(p).encode(),boxes
