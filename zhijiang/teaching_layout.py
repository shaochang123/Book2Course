"""Shared deterministic diagram geometry for movies and SVG summaries."""
from __future__ import annotations
import math

COLORS=('#78BAFF','#6DE2C0','#FFA458','#D5A3FF','#FF829E','#B2D77B')


def layout_diagram(diagram):
    ids=[n.id for n in diagram.nodes]; count=len(ids)
    has_source=bool(diagram.source_asset and diagram.representation=='source_figure')
    if has_source:
        positions=[(x,y) for y in (1.7,0,-1.7) for x in (0.1,4.0)]
        width,height=3.1,1.05
    elif count<=3:
        xs=(0,) if count==1 else ((-2.6,2.6) if count==2 else (-4.2,0,4.2))
        positions=[(x,.45) for x in xs];width,height=3.15,1.15
        if count==3 and any({r.source,r.target}=={ids[0],ids[2]} for r in diagram.relations):
            # A long horizontal edge would pierce the middle concept card.
            degree={key:sum(key in (r.source,r.target) for r in diagram.relations) for key in ids}
            hub=max(ids,key=lambda key:degree[key]);leaves=[key for key in ids if key!=hub]
            branch={hub:(-3,.45),leaves[0]:(3,1.55),leaves[1]:(3,-.65)}
            positions=[branch[key] for key in ids]
    elif count==4:
        positions=[(-3,1.55),(3,1.55),(3,-.65),(-3,-.65)];width,height=3.3,1.1
    else:
        positions=[(-4.25,1.55),(0,1.55),(4.25,1.55),(4.25,-.65),(0,-.65),(-4.25,-.65)]
        width,height=3.1,1.1
    nodes={key:{'position':positions[i],'width':width,'height':height,'color':COLORS[i]} for i,key in enumerate(ids)}
    edges={}
    for relation in diagram.relations:
        a=nodes[relation.source]['position'];b=nodes[relation.target]['position']
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        scale=min(width/2/abs(dx) if dx else math.inf,height/2/abs(dy) if dy else math.inf)
        scale+=.1/length
        start=(a[0]+dx*scale,a[1]+dy*scale);end=(b[0]-dx*scale,b[1]-dy*scale)
        # Horizontal labels sit above the boxes, because the short gap between
        # boxes cannot hold a complete explanatory phrase. Shared SVG/movie
        # coordinates avoid labels being hidden behind SVG node rectangles.
        offset=height/2+.32 if abs(dx)>=3*abs(dy) else .28
        label=((start[0]+end[0])/2-dy/length*offset,(start[1]+end[1])/2+dx/length*offset)
        edges[relation.id]={'start':start,'end':end,'label':label,'color':nodes[relation.source]['color']}
    return nodes,edges


def wrap_label(value,width=10):
    return '\n'.join(value[i:i+width] for i in range(0,len(value),width))
