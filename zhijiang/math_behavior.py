"""Bind model measurements to the actual objects available in a construction.

The generated schema exposes typed mathematical tools, not free-form function
names or fabricated object IDs. Sums, factors and powers express general laws.
"""
from typing import Literal, Annotated, Union
import ast

from pydantic import BaseModel, Field, create_model
from zhijiang.math_construction import StrictMathModel, MathOperation, MathematicalClaim, MathConstructionDraft, Compiler, MEASURES, discrete_controls
from zhijiang.visual_planning import expression_tree, VisualSceneError


class Term(StrictMathModel):
    factor: str = '1'
    power: int = Field(default=1,ge=0,le=6)


def behavior_schema(program,source_ids):
    inventory=Compiler(MathConstructionDraft.model_validate(program.model_dump(exclude={'operations','claims','roles'}))).items
    controls=tuple(name for name in program.parameters if name not in discrete_controls(program))
    if not controls:raise VisualSceneError('当前对象没有连续控制参数；请规划动点、刚体操作或逐项权重。')
    def free_names(value):
        if isinstance(value,dict):return set().union(*(free_names(v) for v in value.values()))
        if isinstance(value,(list,tuple)):return set().union(*(free_names(v) for v in value))
        return {str(s) for s in getattr(value,'free_symbols',set())}
    if not set(controls)&free_names(inventory):
        raise VisualSceneError('连续控制参数未耦合任何实际数学对象，请将控制量用于坐标、函数或变换。')
    def ids(kind):return tuple(name for name,item in inventory.items() if item['type']==kind)
    variants=[create_model('ScalarTerm',__base__=Term,kind=(Literal['scalar'],...),expr=(str,...))]
    point,line,polygon,function=ids('point'),ids('line'),ids('polygon')+ids('group'),ids('function')
    if point:
        variants.extend([
            create_model('CoordinateTerm',__base__=Term,kind=(Literal['xcoord','ycoord'],...),point=(Literal[point],...)),
            create_model('DistanceTerm',__base__=Term,kind=(Literal['distance'],...),first=(Literal[point],...),second=(Literal[point],...))])
    if line:
        segments=tuple(name for name in line if inventory[name].get('extent','segment')=='segment')
        if segments:variants.append(create_model('LengthTerm',__base__=Term,kind=(Literal['length'],...),line=(Literal[segments],...)))
        variants.append(create_model('AngleTerm',__base__=Term,kind=(Literal['angle','signed_angle'],...),first=(Literal[line],...),second=(Literal[line],...)))
        finite=tuple(name for name in line if inventory[name].get('extent','segment')!='line')
        if point and finite:variants.append(create_model('VertexAngleTerm',__base__=Term,kind=(Literal['angle_at'],...),
            point=(Literal[point],...),first=(Literal[finite],...),second=(Literal[finite],...)))
        if point:variants.append(create_model('LineDistanceTerm',__base__=Term,kind=(Literal['line_distance'],...),point=(Literal[point],...),line=(Literal[line],...)))
    if polygon:variants.append(create_model('AreaTerm',__base__=Term,kind=(Literal['area'],...),polygon=(Literal[polygon],...)))
    if function:
        variants.extend([
            create_model('ValueTerm',__base__=Term,kind=(Literal['value'],...),function=(Literal[function],...),at=(str,...)),
            create_model('DerivativeTerm',__base__=Term,kind=(Literal['derivative'],...),function=(Literal[function],...),at=(str,...),order=(int,Field(ge=0,le=8)))])
    atom=Annotated[Union[tuple(variants)],Field(discriminator='kind')]
    value=create_model('MeasuredSum',__base__=StrictMathModel,
        terms=(list[atom],Field(min_length=1,max_length=6)),
        divisor=(list[atom],Field(default_factory=list,max_length=6)),absolute=(bool,False))
    step=create_model('MeasuredOperation',__base__=StrictMathModel,
        narration=(str,Field(min_length=8,max_length=180)),
        changes=(dict[Literal[controls],float],Field(min_length=1)),
        show=(list[str],[]),hide=(list[str],[]),
        measurements=(dict[Annotated[str,Field(pattern=r'^[\u4e00-\u9fff]+$',min_length=1,max_length=12)],value],Field(default_factory=dict,max_length=2)))
    claim=create_model('MeasuredClaim',__base__=StrictMathModel,
        source_id=(Literal[tuple(source_ids)],...),left=(value,...),right=(value,...),
        phase=(Literal['invariant','endpoint'],'invariant'),steps=(list[Annotated[int,Field(ge=1,le=10)]],Field(default_factory=list,max_length=10)),
        relation=(Literal['equal','positive','nonnegative','at_most'],'equal'))
    return create_model('MathBehaviorDraft',__base__=StrictMathModel,
        operations=(list[step],Field(min_length=3,max_length=10)),claims=(list[claim],Field(min_length=1,max_length=12)),
        roles=(dict[Literal[tuple(inventory)],Annotated[str,Field(pattern=r'^[^=＝{}$\\^*/<>\n]{1,24}$',max_length=24)]],Field(default_factory=dict,max_length=32)))


def plain_scalar(expression):
    if not isinstance(expression,str):raise VisualSceneError('标量表达式必须是字符串。')
    if any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in MEASURES
           for n in ast.walk(expression_tree(expression))):
        raise VisualSceneError('实际测量必须使用类型化测量项，不能绕过对象类型契约。')
    return expression


def sum_expression(value):
    expressions=[]
    def expression_for(term):
        kind=term.kind
        if kind=='scalar':base=plain_scalar(term.expr)
        elif kind in {'xcoord','ycoord'}:base=f'{kind}({term.point})'
        elif kind=='distance':base=f'distance({term.first},{term.second})'
        elif kind=='line_distance':base=f'line_distance({term.point},{term.line})'
        elif kind=='length':base=f'length({term.line})'
        elif kind in {'angle','signed_angle'}:base=f'{kind}({term.first},{term.second})'
        elif kind=='angle_at':base=f'angle_at({term.point},{term.first},{term.second})'
        elif kind=='area':base=f'area({term.polygon})'
        elif kind=='value':base=f'value({term.function},{plain_scalar(term.at)})'
        elif kind=='derivative':base=f'derivative({term.function},{plain_scalar(term.at)},{term.order})'
        else:raise VisualSceneError('未知的类型化数学工具。')
        result=base if term.power==1 else f'({base})**{term.power}'
        factor=plain_scalar(term.factor)
        return result if factor=='1' else f'({factor})*({result})'
    expressions=[expression_for(term) for term in value.terms]
    expression='+'.join(expressions)
    if value.divisor:expression=f'({expression})/('+ '+'.join(expression_for(term) for term in value.divisor)+')'
    return f'abs({expression})' if value.absolute else expression


def decode_behavior(draft):
    operations=[MathOperation(narration=op.narration,changes=op.changes,show=op.show,hide=op.hide,
        measurements={label:sum_expression(value) for label,value in op.measurements.items()}) for op in draft.operations]
    claims=[MathematicalClaim(source_id=c.source_id,lhs=sum_expression(c.left),rhs=sum_expression(c.right),relation=c.relation,phase=c.phase,steps=c.steps)
        for c in draft.claims]
    return operations,claims


def attach_measurement_glyphs(program,draft):
    """Encode a difference of two plotted values as actual vertical geometry.

    This is a general visual encoding of a typed measurement, not a lesson
    template. Function formulas, inputs and comparisons all come from the model.
    """
    from zhijiang.math_construction import Construction
    objects={item.id:item for item in program.constructions}
    constructions=list(program.constructions);created={};per_step=[];generated_ids=set()
    for operation in draft.operations:
        active=[]
        for measurement in operation.measurements.values():
            terms=measurement.terms
            if not measurement.absolute or measurement.divisor or len(terms)!=2:continue
            first,second=terms
            if first.kind!='value' or second.kind!='value' or first.at!=second.at:continue
            if first.factor!='1' or second.factor!='-1' or first.power!=1 or second.power!=1:continue
            key=(first.function,second.function,first.at)
            if key not in created:
                prefix=f'measure_{len(created)}';ids=[prefix+'_a',prefix+'_b',prefix+'_line']
                if any(id in objects for id in ids):raise VisualSceneError('自动测量图元ID与输入对象冲突。')
                a,b=objects[first.function],objects[second.function];additions=[]
                for index,(curve,at) in enumerate([(a,first.at),(b,second.at)]):
                    existing=next((obj.id for obj in constructions if obj.op=='point_on_function'
                        and obj.refs==[curve.id] and obj.expr==[at]),None)
                    if existing:ids[index]=existing
                    else:
                        additions.append(Construction(id=ids[index],op='point_on_function',refs=[curve.id],expr=[at],color=curve.color,visible=False))
                existing_line=next((obj.id for obj in constructions if obj.op=='segment' and
                    (obj.refs==ids[:2] or obj.refs==list(reversed(ids[:2])))),None)
                if existing_line:ids[2]=existing_line
                else:additions.append(Construction(id=ids[2],op='segment',refs=ids[:2],color='#6DE2C0',visible=False))
                generated_ids.update(item.id for item in additions)
                constructions.extend(additions);created[key]=ids
            active.extend(created[key])
        per_step.append(active)
    if len(constructions)>32:raise VisualSceneError('测量图元超过单场景对象上限，请减少同时比较项。')
    all_ids=generated_ids
    operations=[]
    for operation,active in zip(program.operations,per_step):
        operations.append(operation.model_copy(update={
            'show':list(dict.fromkeys(operation.show+active)),
            'hide':list(dict.fromkeys(operation.hide+sorted(all_ids-set(active))))}))
    return program.model_copy(update={'constructions':constructions,'operations':operations})


"""Repair invalid fields of a complete response; never accept partial JSON."""
import json
from copy import copy

from pydantic import ValidationError,create_model
from zhijiang.math_construction import StrictMathModel
from zhijiang.agents import _validation_repair_hints


def repair_behavior_contract(client,schema,error,instruction,material,record):
    try:
        raw=json.loads(error.content)
    except (AttributeError,TypeError,ValueError):
        raise error
    if not isinstance(raw,dict) or set(raw)-set(schema.model_fields):raise error
    if not {'operations','claims'}<=set(raw):raise error
    repaired={}
    history=record.setdefault('behavior_format_repairs',[])
    names={'operations':'MathOperationsRepair','claims':'MathClaimsRepair','roles':'MathRolesRepair'}
    for field in ('operations','claims','roles'):
        definition=schema.model_fields[field]
        partial=create_model(names[field],__base__=StrictMathModel,
            **{field:(definition.annotation,copy(definition))})
        data={field:raw[field]} if field in raw else {}
        try:
            value=partial.model_validate(data)
        except ValidationError as exc:
            before=data
            value=client.generate(partial,
                instruction+'\n只修复完整响应中无效的'+field+'字段，其他已验证字段由程序保留。'
                '返回本阶段完整JSON，不返回完整MathBehaviorDraft。operations必须为三至十步，'
                '每步最多两个测量项，至少两步真实运动；没有更多实际内容时不能虚构事实凑数。'
                'claims仅核查来源核心关系，角色名只绑定现有ID，不修改任何对象。'
                '步骤从一开始，不放宽数量、对象类型、出处或数值校验。'+_validation_repair_hints(partial,exc),
                material+'\n完整响应的待修复字段：'+json.dumps(data,ensure_ascii=False))
            history.append({'field':field,'before':before,'after':value.model_dump(),
                'validation_error_types':[e['type'] for e in exc.errors(include_input=False)]})
        repaired.update(value.model_dump())
    # No response or field is accepted as a lesson; the complete original
    # contract, actual geometry, source, SVG, motion and coverage still apply.
    return schema.model_validate(repaired)
