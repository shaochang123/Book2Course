"""Open educational compositions and their progressive explanation states.

No model coordinates/SVG/code are executed. Blank space belongs to content,
not four full-height panels. Colors are supplied by the selected PPT template.
"""
from __future__ import annotations
import html
import re
from types import SimpleNamespace

from zhijiang.presentation import PresentationError
from zhijiang.story_svg import lines
from zhijiang.teaching_graph import graph_layers


def literal_transport_rows(exhibit):
    """Re-express complete, explicit from/to claims without adding a relation.

    The mover, origin, verb and destination are all copied from an already
    reviewed caption. Negated, qualified or partial clauses stay as prose.
    This grammar works for gases, parcels, money and information alike.
    """
    from zhijiang.slide_story import visual_object_name
    if exhibit['form']!='contrast' or len(exhibit['items'])!=2:return []
    result=[]
    for item in exhibit['items']:
        label=item['label'];detail=item.get('detail','').rstrip('。')
        if len(label)>12:return []
        match=re.fullmatch(r'(?:而)?'+re.escape(label)+r'(?:则)?(?:从|由)'
            r'([^，,；;。]{1,12}?)(扩散进入|传递到|运输到|转移到|发送到|传输到|移动到|流入|流向|进入|到达)'
            r'([^，,；;。]{1,12})',detail)
        if not match:return []
        origin,action,target=match.groups()
        if not all(visual_object_name(name,detail) for name in (origin,target)):return []
        result.append({'mover':label,'origin':origin,'action':action,'target':target})
    return result


def literal_named_parts(exhibit):
    """Split an explicit coordinated name into peers, never a causal chain."""
    from zhijiang.slide_story import visual_object_name
    if exhibit['form']!='statement' or len(exhibit['items'])!=1:return []
    item=exhibit['items'][0];label=item['label']
    if '、' not in label or not re.search('[和与]',label):return []
    names=re.split('[、和与]',label)
    source=label+item.get('detail','')
    if not 2<=len(names)<=4 or any(not 2<=len(n)<=12 or not visual_object_name(n,source) for n in names):return []
    return names


def exhibit_svg(exhibit, template, width, height, *, layout='wide', reveal=None, active=None, progress=1.):
    form=exhibit['form'];items=exhibit['items'];count=len(items)
    total=len(exhibit['rows']) if form=='matrix' else count
    visible=total if reveal is None else min(reveal,total)
    context=exhibit.get('context','')
    compact=lambda s:re.sub(r'[\s，,；;。！？!?：:]','',s)
    if context and any(compact(context) in {compact(i.get('detail','')),compact(i['label']+i.get('detail',''))} for i in items):
        context=''
    context_lines=lines(context,width-40,32)
    h=height-(len(context_lines)*41+24 if context else 0)
    if h<250:raise PresentationError('示例条件过长，需要拆分。')
    accent=template.accent if template.id!='paper' else '806019'
    second={'classic':'9AC8EF','paper':'356585','academic':'9B4F36','editorial':'356585'}[template.id]
    p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
       '<title>具体教学示例与图解</title><desc>文字、字段值和关系绑定完整讲稿句子。形状位置不表示数值比例。</desc>',
       f'<defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="11" refY="6" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L12,6 L0,12" fill="#{accent}"/></marker></defs>']
    boxes=[];arts={}
    whole_pic=next((pic for pic in exhibit.get('pictures',[]) if pic['item_id']==0),None)
    pic_ids={pic['item_id']-1 for pic in exhibit.get('pictures',[]) if pic['item_id']}
    # The object accent is constrained to 1.15 in; text/diagrams own the canvas.
    reserve=140 if whole_pic else 0
    content_width=width-reserve
    if whole_pic:arts[0]=(width-120, max(30,h*.38),110,110)
    def text(value,x,y,w,size=32,color=None,bold=False,anchor=None):
        wrapped=lines(value,w,size)
        for j,line in enumerate(wrapped):
            p.append(f'<text x="{x}" y="{y+j*size*1.26}" font-family="Microsoft YaHei" font-size="{size}" font-weight="{700 if bold else 400}" fill="#{color or template.ink}"'
                +(f' text-anchor="{anchor}"' if anchor else '')+f'>{html.escape(line)}</text>')
        return len(wrapped)*size*1.26
    def line(x1,y1,x2,y2,color=None,stroke=3,dash=''):
        p.append(f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="#{color or accent}" stroke-width="{stroke}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
    def rect(x,y,w,bh,fill='none',stroke=None,rx=0):
        p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{bh}" rx="{rx}" fill="{fill if fill=="none" else "#"+fill}" stroke="{("#"+stroke) if stroke else "none"}" stroke-width="2"/>')
    def entry(item,i,box,*,heading=36,indicator=True):
        x,y,w,bh=box;boxes.append(box)
        if i>=visible:return
        color=accent if i%2==0 else second
        if active==i+1:rect(x-8,y-8,w+16,bh+16,template.panel,rx=8)
        art=78 if i in pic_ids else 0
        if art:arts[i+1]=(x+w-art,y,art,art)
        lh=text(item['label'],x,y+heading,w-art-12,heading,color,True)
        if indicator:line(x,y+lh+14,x+min(96,w*.45),y+lh+14,color,4)
        ch=text(item.get('detail',''),x,y+lh+60,w,32) if item.get('detail') else 0
        if lh+ch+(60 if ch else 24)>bh:raise PresentationError('图解文字越界；需减少重复释义或换画面。')
    if form=='matrix':
        cols=exhibit['columns'];rows=exhibit['rows'];gap=18;cw=(content_width-36-gap*(len(cols)-1))/len(cols)
        head_h=max(len(lines(c,cw-18,32)) for c in cols)*41+22
        row_heights=[max(len(lines(c,cw-18,32)) for c in row['cells'])*41+20 for row in rows]
        required=head_h+sum(row_heights)+22
        if required>h:raise PresentationError('实例表格文字越界，需要拆分。')
        y=max(12,(h-required)/2)
        for j,c in enumerate(cols):
            x=18+j*(cw+gap);rect(x,y,cw,head_h,template.panel)
            text(c,x+9,y+38,cw-18,32,accent,True)
        line(18,y+head_h+3,content_width-18,y+head_h+3,accent,3)
        y+=head_h+12
        for i,row in enumerate(rows):
            boxes.append((18,y,content_width-36,row_heights[i]))
            if i<visible:
                if active==i+1:rect(18,y,content_width-36,row_heights[i],template.panel,rx=6)
                for j,c in enumerate(row['cells']):
                    text(c,27+j*(cw+gap),y+36,cw-18,32,accent if active==i+1 else None)
                line(18,y+row_heights[i],content_width-18,y+row_heights[i],template.muted,1)
            y+=row_heights[i]
    elif form=='record':
        split=content_width*.36
        row_h=max(85,(h-44)/max(count,1));required=count*row_h
        if required>h:raise PresentationError('属性记录过密，需要拆分。')
        top=max(16,(h-required)/2)
        # A record connects names to actual values; no invented causal arrows.
        for i,item in enumerate(items):
            y=top+i*row_h;box=(18,y,content_width-36,row_h-10);boxes.append(box)
            if i>=visible:continue
            if active==i+1:rect(18,y,content_width-36,row_h-10,template.panel,rx=8)
            lh=text(item['label'],36,y+40,split-48,32,accent,True)
            art=78 if i in pic_ids else 0
            ch=text(item['detail'],split+44,y+42,content_width-split-80-art,36,second,True)
            line(split+10,y+18,split+10,y+row_h-24,template.muted,2)
            if max(lh,ch)+20>row_h:raise PresentationError('记录字段或属性值越界。')
            if art:arts[i+1]=(content_width-100,y+5,78,78)
    elif form=='relations':
        graph=SimpleNamespace(representation='relationship',nodes=[SimpleNamespace(id=i+1) for i in range(count)],
            relations=[SimpleNamespace(source=e['source'],target=e['target'],directed=e['kind']!='undirected') for e in exhibit['links']])
        layers=graph_layers(graph)
        layers=layers or [[i+1 for i in range(count)]]
        gap=150 if len(layers)>1 else 24
        bw=(content_width-40-gap*(len(layers)-1))/len(layers)
        if bw<130:raise PresentationError('关系节点太多，需聚焦子关系。')
        geometry=[None]*count
        for col,layer in enumerate(layers):
            bh=min(190,(h-50-30*(len(layer)-1))/len(layer));top=(h-(bh+30)*len(layer)+30)/2
            for row,ni in enumerate(layer):
                item=items[ni-1]
                # The arrow must meet the visible node, not the edge of an
                # invisible full-column layout slot.
                nw=min(bw,max(150,len(item['label'])*36+24,240 if item.get('detail') else 0))
                while True:
                    art=78 if ni-1 in pic_ids else 0
                    lh=len(lines(item['label'],nw-art-12,36))*36*1.26
                    ch=len(lines(item['detail'],nw,32))*32*1.26 if item.get('detail') else 0
                    nh=lh+ch+(60 if ch else 24)+12
                    if nh<=bh or nw>=bw:break
                    nw=min(bw,nw+36)
                if nh>bh:raise PresentationError('关系图节点文字越界，需要拆分。')
                x=20+col*(bw+gap)+(bw-nw)/2
                y=top+row*(bh+30)+(bh-nh)/2
                geometry[ni-1]=(x,y,nw,nh)
        for i,(item,box) in enumerate(zip(items,geometry)):
            entry(item,i,box,heading=36)
        for e in exhibit['links']:
            if max(e['source'],e['target'])>visible:continue
            a=geometry[e['source']-1];b=geometry[e['target']-1]
            right=b[0]>a[0]
            if b[0]!=a[0]:
                x1=a[0]+a[2]+8 if right else a[0]-8;x2=b[0]-14 if right else b[0]+b[2]+14
                y1=a[1]+a[3]/2;y2=b[1]+b[3]/2
            else:
                down=b[1]>a[1];x1=a[0]+a[2]/2;x2=b[0]+b[2]/2
                y1=a[1]+a[3]+8 if down else a[1]-8;y2=b[1]-14 if down else b[1]+b[3]+14
            marker='' if e['kind']=='undirected' else ' marker-end="url(#arrow)"'
            path=f'M{x1},{y1} C{(x1+x2)/2},{y1} {(x1+x2)/2},{y2} {x2},{y2}'
            draw_progress=progress if active==e['target'] else 1.
            # Program-controlled drawing reveals this stated relation, not
            # a particle simulation or a claim about physical speed.
            if draw_progress<1:
                points=[]
                for k in range(25):
                    t=draw_progress*k/24;u=1-t;middle=(x1+x2)/2
                    x=u**3*x1+3*u*u*t*middle+3*u*t*t*middle+t**3*x2
                    y=u**3*y1+3*u*u*t*y1+3*u*t*t*y2+t**3*y2
                    points.append((x,y))
                path='M'+str(points[0][0])+','+str(points[0][1])+''.join(f' L{x},{y}' for x,y in points[1:])
            p.append(f'<path d="{path}" fill="none" stroke="#{accent}" stroke-width="4"{marker if draw_progress>=.95 else ""}/>')
            lane=min(300,max(190,len(e['label'])*29+12));wrapped=lines(e['label'],lane,28)
            # A cubic with these control points has its midpoint at the mean
            # of its endpoints. Centre the label there, close to its own edge,
            # instead of left-aligning it above a different branch.
            text(e['label'],(x1+x2)/2 if b[0]!=a[0] else x1+24,
                max(32,(y1+y2)/2-24-35*(len(wrapped)-1)),lane,28,accent,
                anchor='middle' if b[0]!=a[0] else None)
            if e['kind']=='negative':line((x1+x2)/2-9,(y1+y2)/2-10,(x1+x2)/2+9,(y1+y2)/2+10,accent,4)
    elif form=='timeline':
        gap=24;bw=(content_width-36-gap*(count-1))/count;y=h*.55
        # A schematic chronological line, not a quantitative time scale.
        line(36,y,content_width-36,y,accent,4)
        for i,item in enumerate(items):
            x=18+i*(bw+gap);boxes.append((x,20,bw,h-40))
            if i>=visible:continue
            p.append(f'<circle cx="{x+bw/2}" cy="{y}" r="9" fill="#{accent}"/>')
            text(item['label'],x,65,bw,32,accent,True)
            dh=text(item['detail'],x,y+62,bw,32)
            if y+62+dh>h:raise PresentationError('时间轴标签越界。')
    elif form=='equation':
        expression=exhibit['expression'].replace('*','×').replace('/','÷')
        if reveal==0 and '=' in expression:
            expression=expression.split('=',1)[0]+' = ?'
        eh=len(lines(expression,content_width-64,56))*71
        if eh>h*.5:raise PresentationError('算式过长，需要拆分。')
        text(expression,32,76,content_width-64,56,accent,True)
        line(32,eh+45,content_width-32,eh+45,accent,3)
        if count:
            gap=30;bw=(content_width-64-gap*(count-1))/count
            for i,item in enumerate(items):entry(item,i,(32+i*(bw+gap),eh+64,bw,h-eh-80),heading=32)
    elif form=='contrast' and (transport:=literal_transport_rows(exhibit)):
        # Separate arrow lanes preserve both the named material and direction;
        # a location never becomes the agent of the action.
        bh=(h-32)/2;node_w=content_width*.19
        source_x=content_width*.27;target_x=content_width-node_w-24
        for i,row in enumerate(transport):
            y=16+i*bh;color=accent if i==0 else second
            boxes.append((24,y,content_width-48,bh-12))
            if i>=visible:continue
            lh=len(lines(row['mover'],source_x-48,36))*36*1.26
            if lh>bh*.6:raise PresentationError('移动对象名称越界。')
            if active==i+1:rect(20,y,content_width-40,bh-8,template.panel,rx=8)
            text(row['mover'],24,y+bh*.55,source_x-48,36,color,True)
            node_y=y+bh*.37
            for name,x in ((row['origin'],source_x),(row['target'],target_x)):
                nh=len(lines(name,node_w-24,32))*41+20
                if nh>bh*.65:raise PresentationError('来源或目的地名称越界。')
                rect(x,node_y-30,node_w,nh,stroke=color,rx=12)
                text(name,x+12,node_y+8,node_w-24,32,color,True)
            x1=source_x+node_w+10;x2=target_x-12;ay=node_y+8
            if x2-x1<155:raise PresentationError('移动关系的连线区域过窄。')
            draw=progress if active==i+1 else 1.
            p.append(f'<defs><marker id="transport-arrow-{i}" markerWidth="12" markerHeight="12" '
                f'refX="11" refY="6" orient="auto" markerUnits="userSpaceOnUse">'
                f'<path d="M0,0 L12,6 L0,12" fill="#{color}"/></marker></defs>')
            p.append(f'<path d="M{x1},{ay} L{x1+(x2-x1)*draw},{ay}" fill="none" '
                f'stroke="#{color}" stroke-width="4"'+(f' marker-end="url(#transport-arrow-{i})"' if draw>=.95 else '')+'/>' )
            ah=text(row['action'],x1,y+30,x2-x1,28,color)
            if ah>bh*.3:raise PresentationError('移动关系文字越界。')
    elif form=='contrast':
        # The director's arrangement survives: paired rows for a captioned
        # page, facing columns for a wide page. Both preserve comparison.
        rows=layout in {'captioned','evidence'} and count==2
        if rows:
            bh=(h-50)/count
            for i,item in enumerate(items):
                box=(24,25+i*(bh+14),content_width-48,bh);boxes.append(box)
                if i>=visible:continue
                x,y,w,bh=box;color=accent if i==0 else second
                label_width=w*.3;art=80 if i in pic_ids else 0
                lh=text(item['label'],x,y+40,label_width-20,36,color,True)
                ch=text(item.get('detail',''),x+label_width+35,y+40,w-label_width-55-art,32)
                line(x+label_width,y+12,x+label_width,y+bh-18,color,3)
                if max(lh,ch)+20>bh:raise PresentationError('对照行文字越界。')
                if art:arts[i+1]=(x+w-78,y+12,78,78)
        else:
            gap=54;bw=(content_width-48-gap*(count-1))/count
            for i,item in enumerate(items):entry(item,i,(24+i*(bw+gap),max(24,h*.18),bw,h*.75),heading=40)
            for i in range(1,count):line(24+i*(bw+gap)-gap/2,26,24+i*(bw+gap)-gap/2,h-24,template.muted,1,'5 8')
    elif form=='annotated' and count>1:
        if layout in {'split','illustrated'} and count<=3:
            bw=content_width*.40;gap=56
            entry(items[0],0,(24,max(24,h*.18),bw,h*.75),heading=44)
            right=content_width-bw-gap-48;bh=(h-40)/(count-1)
            for i,item in enumerate(items[1:],1):entry(item,i,(24+bw+gap,20+(i-1)*bh,right,bh-18),heading=32)
        else:
            # Open field notes: one central heading, short distinct examples
            # along a second baseline, no enclosing full-page panel.
            gap=40;bw=(content_width-48-gap*(count-1))/count
            for i,item in enumerate(items):entry(item,i,(24+i*(bw+gap),max(24,h*.16),bw,h*.78),heading=36)
    elif form=='statement' and (names:=literal_named_parts(exhibit)):
        gap=36;bw=(content_width-48-gap*(len(names)-1))/len(names)
        y=max(24,h*.22);bh=h*.4
        for i,name in enumerate(names):
            x=24+i*(bw+gap);boxes.append((x,y,bw,bh))
            if not visible:continue
            color=accent if i%2==0 else second
            lh=text(name,x,y+44,bw,44,color,True)
            if lh+26>bh:raise PresentationError('并列环节名称越界。')
            line(x,y+lh+18,x+min(96,bw*.6),y+lh+18,color,4)
        if visible:
            dh=text(items[0].get('detail',''),24,y+bh+32,content_width-48,32)
            if y+bh+32+dh>h:raise PresentationError('并列环节说明越界。')
    else:
        if count==1:
            item=items[0];box=(32,max(20,h*.16),content_width-64,h*.78);boxes.append(box)
            if visible:
                art=100 if 0 in pic_ids else 0
                lh=text(item['label'],box[0],box[1]+56,box[2]-art-16,56,accent,True)
                line(32,box[1]+lh+28,min(content_width-32,240),box[1]+lh+28,accent,5)
                ch=text(item.get('detail',''),32,box[1]+lh+82,box[2],36)
                if lh+ch+80>box[3]:raise PresentationError('结论文字越界。')
                if art:arts[1]=(content_width-132,box[1],100,100)
        else:
            bh=(h-40)/count
            for i,item in enumerate(items):
                box=(24,20+i*bh,content_width-48,bh-16);boxes.append(box)
                if i>=visible:continue
                lh=text(item['label'],24,box[1]+36,content_width*.3-36,32,accent,True)
                art=78 if i in pic_ids else 0
                ch=text(item.get('detail',''),content_width*.3+30,box[1]+36,content_width*.7-70-art,32)
                if max(lh,ch)+20>box[3]:raise PresentationError('要点文字越界。')
                if art:arts[i+1]=(content_width-104,box[1],78,78)
    if context:
        line(20,h+6,width-20,h+6,template.muted,1)
        text(context,20,h+46,width-40,32)
    p.append('</svg>')
    return ''.join(p).encode(),boxes,arts


def exhibit_pages(exhibit, template, width, height, *, layout='wide'):
    """Keep all source content, paginate open text/records instead of shrinking."""
    try:
        exhibit_svg(exhibit,template,width,height,layout=layout)
        count=(1 if exhibit['form']=='equation' else len(exhibit['rows']) if exhibit['form']=='matrix' else len(exhibit['items']))
        return [(exhibit,list(range(1,count+1)))]
    except PresentationError:
        if exhibit['form'] in {'relations','timeline','equation'}:raise
    key='rows' if exhibit['form']=='matrix' else 'items';values=exhibit[key];parts=[]
    for start in range(0,len(values),2):
        indices=list(range(start+1,min(start+3,len(values)+1)));mapping={old:new for new,old in enumerate(indices,1)}
        part={**exhibit,key:values[start:start+2],'pictures':[
            {**p,'item_id':mapping.get(p['item_id'],0)} for p in exhibit['pictures']
            if not p['item_id'] or p['item_id'] in mapping]}
        if len(part[key])==1 and part['form']=='contrast':part['form']='annotated'
        exhibit_svg(part,template,width,height,layout=layout)
        parts.append((part,indices))
    return parts


def legacy_exhibit(visual, refs=(), narration=''):
    """Equivalent geometry for a previously reviewed story, not a new AI pass."""
    from zhijiang.caption_grounding import speech_sentences
    sentences=speech_sentences(narration)
    question=re.match(r'^([^？?]{6,23}[？?])',narration.strip())
    if question:
        pictures=[]
        for ref in refs:
            if ref.anchor_text in question.group(1):
                pictures=[{'asset_id':ref.asset_id,'item_id':0,'object_name':ref.anchor_text,'sentence_id':1}]
                break
        return {'form':'statement','items':[{'label':question.group(1),'detail':'','sentence_id':1}],
            'columns':[],'rows':[],'links':[],'expression':'','expression_sentence_id':None,
            'context':'','context_sentence_id':None,'pictures':pictures}
    numbered=[]
    for si,s in enumerate(sentences,1):
        match=re.match(r'^第[一二三四五六][，,：:]\s*(.{4,48})$',s)
        if match:numbered.append({'label':f'{len(numbered)+1:02d}','detail':match.group(1),'sentence_id':si})
    if 2<=len(numbered)<=4:
        return {'form':'statement','items':numbered,'columns':[],'rows':[],'links':[],
            'expression':'','expression_sentence_id':None,'context':'','context_sentence_id':None,'pictures':[]}
    form={'key_idea':'statement','annotated':'annotated','comparison':'contrast',
          'table':'record','process':'relations','relationship':'relations'}[visual['representation']]
    pictures=[]
    for ref in refs if not (form=='annotated' and len(visual['items'])>=3) else []:
        direct=next((i for i,item in enumerate(visual['items'],1)
            if ref.anchor_text in item['label']+' '+item['caption']),None)
        sources=[i for i,s in enumerate(speech_sentences(narration),1) if ref.anchor_text in s]
        if not sources:continue
        if not direct and form=='relations':continue
        item_id=direct or 0
        if any(p['item_id']==item_id for p in pictures):continue
        pictures.append({'asset_id':ref.asset_id,'item_id':item_id,'object_name':ref.anchor_text,'sentence_id':sources[0]})
    return {'form':form,'items':[{'label':i['label'],'detail':i['caption'],'sentence_id':i['sentence_id']} for i in visual['items']],
        'columns':[],'rows':[],'links':visual.get('links',[]),'expression':'','expression_sentence_id':None,
        'context':visual.get('context',''),'context_sentence_id':visual.get('context_sentence_id'),'pictures':pictures}


def exhibit_cues(exhibit, narration):
    """Reveal/focus at its support sentence, never rotate layouts randomly."""
    from zhijiang.caption_grounding import speech_sentences
    sentences=speech_sentences(narration)
    if exhibit['form']=='equation':
        weights=[max(4,len(s)) for s in sentences]
        si=max(1,min(exhibit.get('expression_sentence_id') or 1,len(weights)))
        at=(sum(weights[:si-1])+.65*weights[si-1])/sum(weights)
        at=min(.82,max(.18,at))
        return [{'fraction':0.,'reveal':0,'active':None,'source_sentence_id':None},
            {'fraction':at,'reveal':1,'active':1,'source_sentence_id':si},
            {'fraction':max(.88,at+.04),'reveal':1,'active':None,'source_sentence_id':None}]
    values=exhibit['rows'] if exhibit['form']=='matrix' else exhibit['items']
    # Keep arbitrary record order readable and align by the latest item source.
    order=[];last=0
    for i,value in enumerate(values,1):
        last=max(last,max(value.get('source_ids') or [value['sentence_id']])-1);order.append((last,i))
    weights=[max(4,len(s)) for s in sentences];total=sum(weights);cues=[]
    for n,(si,reveal) in enumerate(order):
        fraction=sum(weights[:si])/total
        if n and fraction<=cues[-1]['fraction']:
            # One sentence may name several fields. Distribute their reveals
            # within that sentence, not over unrelated later explanations.
            peers=[pair for pair in order if pair[0]==si];position=peers.index((si,reveal))
            fraction=(sum(weights[:si])+weights[si]*(position/len(peers)))/total
        cues.append({'fraction':fraction,'reveal':reveal,'active':reveal,'source_sentence_id':si+1})
    if not cues or cues[0]['fraction']>0:cues.insert(0,{'fraction':0.,'reveal':0,'active':None,'source_sentence_id':None})
    # A clean final state agrees with the exported PPT, and holds long enough.
    finish=min(.94,max(.75,cues[-1]['fraction']+.04)) if cues else .75
    if cues and finish<=cues[-1]['fraction']:finish=(1+cues[-1]['fraction'])/2
    cues.append({'fraction':finish,'reveal':len(values),'active':None,'source_sentence_id':None})
    return cues
