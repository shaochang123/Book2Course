"""Source-bound relations measured from the actual mathematical objects.

No textbook names, subject templates, model code, or authored coordinates.
These are partial geometric invariants, not a universal mathematical prover.
"""
from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import Field,create_model

from zhijiang.models import GeometryConstraint


class GeometryRelationError(ValueError):
    pass


def check_geometry_visibility(scene, geometry, visible):
    """Keep displayed point/label anchors inside the mathematical viewport.

    Curves and lines may legitimately be clipped at the plotting boundary.
    This checks anchors, not label extents or general composition quality.
    """
    for obj in scene.objects:
        if obj.id not in visible or obj.kind not in {'dot', 'label'}:
            continue
        x, y = geometry[obj.id]['points'][0]
        if not (scene.x_range[0] <= x <= scene.x_range[1]
                and scene.y_range[0] <= y <= scene.y_range[1]):
            raise GeometryRelationError('可见数学点或标签超出坐标窗口：' + obj.id
                                        + '。调整坐标范围或显式隐藏对象，不能让关键对象被遮罩吞掉。')


def check_geometry_constraints(scene,geometry,parameters):
    from zhijiang.visual_planning import evaluate
    objects={o.id:o for o in scene.objects};report=[]
    for constraint in scene.geometry_constraints:
        ids=constraint.objects;kind=constraint.kind
        if len(set(ids))!=len(ids) or any(i not in objects for i in ids):
            raise GeometryRelationError('几何关系必须引用不同且存在的对象：'+kind)
        if len(ids)!=(3 if kind=='equal_distance' else 2):
            raise GeometryRelationError('几何关系对象数量错误：'+kind)
        def point(i):
            if objects[i].kind!='dot':raise GeometryRelationError('几何关系需要点对象：'+i)
            return geometry[i]['points'][0]
        def line(i,nondegenerate=True):
            if objects[i].kind not in {'line','arrow'}:raise GeometryRelationError('几何关系需要线对象：'+i)
            a,b=geometry[i]['points'];v=[b[j]-a[j] for j in range(2)];length=math.hypot(*v)
            if nondegenerate and length<1e-8:raise GeometryRelationError('几何关系中的线不能退化：'+i)
            return a,b,v,length
        def distance(p,i):
            if objects[i].kind=='dot':return math.dist(p,point(i))
            a,_b,v,length=line(i)
            return abs(v[0]*(p[1]-a[1])-v[1]*(p[0]-a[0]))/length
        a,b=ids[:2]
        if kind=='on_function':
            p=point(a);curve=objects[b]
            if curve.kind!='curve' or not curve.domain[0]<=p[0]<=curve.domain[1]:
                raise GeometryRelationError('函数归属需要定义域内的点和函数曲线。')
            left,right=p[1],evaluate(curve.expression,{**parameters,'x':p[0]})
        elif kind=='on_circle':
            p=point(a)
            if objects[b].kind!='circle':raise GeometryRelationError('圆周归属需要圆对象。')
            left,right=math.dist(p,geometry[b]['points'][0]),geometry[b]['radius']
        elif kind=='equal_distance':
            p=point(a);left,right=distance(p,b),distance(p,ids[2])
        elif kind=='equal_length':
            left,right=line(a,False)[3],line(b,False)[3]
        elif kind=='equal_area':
            def area(i):
                if objects[i].kind!='polygon':raise GeometryRelationError('面积关系需要多边形对象。')
                ps=geometry[i]['points']
                return abs(sum(p[0]*q[1]-p[1]*q[0] for p,q in zip(ps,ps[1:]+ps[:1])))/2
            left,right=area(a),area(b)
        elif kind=='same_start':
            left,right=math.dist(line(a,False)[0],line(b,False)[0]),0
        else:
            va,la=line(a)[2:];vb,lb=line(b)[2:]
            left=(sum(x*y for x,y in zip(va,vb)) if kind=='perpendicular' else va[0]*vb[1]-va[1]*vb[0])/(la*lb)
            right=0
        tolerance=1e-6*max(1,abs(left),abs(right))
        if not math.isfinite(left+right) or abs(left-right)>tolerance:
            raise GeometryRelationError(f'实际几何关系失败：{kind} {ids}，测量 {left:.8g} 与 {right:.8g} 不一致。')
        report.append({'kind':kind,'objects':ids,'measured':[left,right],'passed':True})
    return report


def plan_geometry_constraints(client,scene,source_page,prompt):
    from zhijiang.agents import _page_quotes
    sources={i:q for i,q in enumerate(_page_quotes(source_page,300,8),1)}
    if not sources:raise GeometryRelationError('当前原页没有可绑定的几何关系依据。')
    draft=create_model('GeometryConstraintDraft',
        kind=(GeometryConstraint.model_fields['kind'].annotation,Field()),
        objects=(list[Literal[tuple(o.id for o in scene.objects)]],Field(min_length=2,max_length=3)),
        source_id=(Literal[tuple(sources)],Field()))
    schema=create_model('GeometryConstraintsDraft',
        constraints=(list[draft],Field(min_length=1,max_length=12)))
    result=client.generate(schema,
        '独立绑定原文数学关系到当前图形对象，用程序测量实际对象，不能用参数名或任意表达式假装验证。'
        '选全部可核验的核心几何关系：on_function=[点,函数曲线]；on_circle=[点,圆]；'
        'equal_distance=[动点,参照点,参照线或另一点]；equal_length=[线,线]；'
        'equal_area=[多边形,多边形]；perpendicular/parallel/same_start=[线,线]。'
        '每项source_id选实际说明该关系的原文编号。关系在所有步骤及连续中间状态检查，不能凭名称判断正确。'
        '优先核验“点在所画曲线上”和讲解声称相等的实际距离/长度/面积，不用无关的辅助关系代替核心条件。'
        'equal_distance的后两项是两个距离目标，例如一个参照点和一条参照线，不是画出来的距离连接线。'
        '若比较已画出的两条距离线段，使用equal_length。不要比较点到它所在连接线的零距离。'
        '不输出代码、公式、坐标或自定容差。程序绑定原文并独立计算，不允许输出恒等式0=0。'
        '\n用户偏好：'+prompt,
        json.dumps({'source_excerpts':[{'id':i,'text':q} for i,q in sources.items()],
                    'scene':scene.model_dump(exclude={'verification'})},ensure_ascii=False))
    scene.geometry_constraints=[GeometryConstraint(kind=c.kind,objects=c.objects,source_quote=sources[c.source_id])
        for c in result.constraints]
    return result.model_dump()
