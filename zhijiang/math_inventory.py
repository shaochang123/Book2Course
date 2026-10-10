"""Read-only tool results for planners, never a lesson or correctness verdict."""
import itertools
import math

import sympy as sp

from zhijiang.visual_planning import VisualSceneError
from typing import Literal
from pydantic import Field, create_model
from zhijiang.math_construction import StrictMathModel


def computed_inventory(compiler):
    """Report exact formulas and initial values from the actual dependency graph.

    Undefined or oversized values are explicit nulls, never guessed answers.
    Operations still require independent source and moving-geometry checks.
    """
    values={compiler.symbols[name]:sp.Rational(str(value))
        for name,value in compiler.program.parameters.items()
        if getattr(compiler.symbols[name],'is_Symbol',False)}
    def measurement(expr):
        formula=str(expr)
        result={'formula':formula if len(formula)<=360 else None}
        try:
            value=float(expr.subs(values))
            result['initial']=value if math.isfinite(value) else None
        except (TypeError,ValueError,OverflowError):
            result['initial']=None
        return result
    records={};angles=[]
    for name,item in compiler.items.items():
        record={'type':item['type']}
        if item['type']=='point':
            record['coordinates']=[measurement(q) for q in item['p']]
        elif item['type']=='line':
            a,b=map(sp.Matrix,(item['a'],item['b']))
            record['extent']=item.get('extent','segment')
            record['endpoints']=[[measurement(q) for q in p] for p in (a,b)]
            if record['extent']=='segment':
                record['length']=measurement(sp.sqrt(sp.simplify((b-a).dot(b-a))))
        elif item['type']=='polygon':
            record['area']=measurement(compiler._area(item['vertices']))
        elif item['type']=='group':
            record['area']=measurement(sum(compiler._area(compiler.items[part]['vertices'])
                for part in item['members']))
        elif item['type']=='circle':
            record['center']=[measurement(q) for q in item['center']]
            record['radius']=measurement(item['radius'])
        elif item['type'] in {'function','parametric'}:
            shape=next(o for o in compiler.shapes if o.id==name)
            record['domain']=shape.domain
            if item['type']=='function':
                record['expression']=str(item['expr'])
            else:
                record['sample_positions']=[[measurement(q.subs(compiler.x,t)) for q in item['expr']]
                    for t in [shape.domain[0],sum(shape.domain)/2,shape.domain[1]]]
        records[name]=record
    edges=[name for name,item in compiler.items.items()
        if item['type']=='line' and item.get('extent','segment')!='line']
    for vertex,item in compiler.items.items():
        if item['type']!='point':continue
        incident=[]
        for line in edges:
            try:
                compiler.vertex_vectors(compiler.point(vertex),line,line)
                incident.append(line)
            except VisualSceneError:
                continue
        for first,second in itertools.combinations(incident,2):
            expression=f'angle_at({vertex},{first},{second})'
            angles.append({'expression':expression,'radians':measurement(compiler.parse(expression))})
            if len(angles)>=36:break
        if len(angles)>=36:break
    return {'scope':'Computed at initial controls; not approval. Moving states and source meaning still require verification.',
        'objects':records,'vertex_angles':angles}


def validate_initial_geometry(ledger):
    """Reject undefined construction data before asking a model to approve it.

    This checks the same actual initial geometry later consumed by the scene.
    A hidden auxiliary point is still a dependency and cannot start at infinity.
    It is not a source verdict or a substitute for checking moving states.
    """
    def walk(value,path):
        if isinstance(value,dict):
            if 'initial' in value and value['initial'] is None:
                raise VisualSceneError('初态数学构造不能得到有限实数：'+path+' / '+str(value.get('formula')))
            for key,child in value.items():walk(child,path+'.'+key)
        elif isinstance(value,list):
            for i,child in enumerate(value):walk(child,path+f'[{i}]')
    for name,record in ledger['objects'].items():walk(record,name)


def _check_construction_readiness_batch(client,requirements,program,ledger,source,operator_reference):
    """Ask whether the actual graph can express the independently defined scope.

    This happens before behavior generation, not as a substitute for source,
    coordinate, SVG, motion or final coverage acceptance.
    """
    import json
    item=create_model('MathConstructionRequirement',__base__=StrictMathModel,
        requirement_id=(Literal[tuple(r['id'] for r in requirements)],...),
        observation=(str,Field(min_length=8,max_length=300)),
        feasible=(bool,...),
        objects=(list[Literal[tuple(ledger['objects'])]],Field(max_length=12)))
    schema=create_model('MathConstructionReadiness',__base__=StrictMathModel,
        checks=(list[item],Field(min_length=len(requirements),max_length=len(requirements))))
    result=client.generate(schema,
        '在编写讲稿和操作之前，独立检查实际数学构造图能否表达教材必讲要求。'
        '候选只有对象和控制量，后续仍可选择合法参数值、显示或隐藏对象、编写口播和测量；不要因还没编写这些内容拒绝。'
        '已核对的每条中文statement将逐字放入来源说明卡并配音，定义与必要条件在首次数学运动之前说明。'
        '纯代数通式、术语定义及限制条件可由该说明讲出，不要求每个定义都变成任意阶数或任意函数的可变图形。'
        '有限实际示例不能声称一般性证明；来源已给出的核心图解/计算示例和演示关系仍必须由现有数学对象表达，说明卡不能代替它们。'
        '本批逐项核对真实依赖公式、对象类型和自由度，先记录观察再判feasible。'
        '仅输出本批编号，一两句写具体依据或缺漏，不重述整个教案；其他要求由其他批次检查。'
        '如果图形始终满足某个条件，不能声称移动其现有参数可以演示该条件失效。'
        '所有来源已解算例的数值和必要符号须可由现有对象、控制量表达；只画新的方便例子不算覆盖。'
        '如果缺少必要的对象、独立自由度、绑定关系或实际拼接构造，feasible=false并指出具体缺失。'
        '初态值与某个算例不同不一定是失败，后续参数确实可到达该值才算可表达。'
        '不能只因有同类型占位对象就批准；核对来源主语与真实依赖图，有限闭合边环也可以表达多边形。'
        '概念照片和装饰图可使用正确等价示意；不要求重绘照片，不添加原页没有的证明目标。'
        '不设计替代场景，不给手写坐标，不批准成片。每个编号恰好一次，objects只选择真实清单ID。'
        '\n可用执行器（不是教材事实）：'+operator_reference,
        source+'\n独立来源要求：'+json.dumps(requirements,ensure_ascii=False)+
        '\n实际对象依赖图与计算工具结果：'+json.dumps({'construction':program.model_dump(),
            'computed_inventory':ledger},ensure_ascii=False))
    ids=[c.requirement_id for c in result.checks]
    if len(set(ids))!=len(ids) or set(ids)!={r['id'] for r in requirements}:
        raise VisualSceneError('构造可表达性复核必须逐项覆盖且不重复。')
    return result


def check_construction_readiness(client,requirements,program,ledger,source,operator_reference):
    """Review bounded groups without dropping any source requirement."""
    checks=[]
    for start in range(0,len(requirements),2):
        result=_check_construction_readiness_batch(client,requirements[start:start+2],
            program,ledger,source,operator_reference)
        checks.extend(c.model_dump() for c in result.checks)
    if not checks:raise VisualSceneError('构造可表达性来源要求不能为空。')
    item=create_model('MathConstructionRequirementResult',__base__=StrictMathModel,
        requirement_id=(Literal[tuple(r['id'] for r in requirements)],...),
        observation=(str,Field(min_length=8,max_length=300)),feasible=(bool,...),
        objects=(list[Literal[tuple(ledger['objects'])]],Field(max_length=12)))
    schema=create_model('MathConstructionReadinessResult',__base__=StrictMathModel,
        checks=(list[item],Field(min_length=len(requirements),max_length=len(requirements))))
    return schema.model_validate({'checks':checks})
