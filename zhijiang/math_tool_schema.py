"""Expose each mathematical operator's real arity to structured planners."""
from typing import Annotated,Literal,Union
from pydantic import Field,create_model
from zhijiang.math_construction import MathConstructionObject


def typed_construction(*,object_ids=None):
    # Types describe general operators, not subjects or textbook templates.
    groups=[
        (('point',),(0,0),(2,2)),
        (('parametric','locus'),(0,0),(2,2)),
        (('rectangle',),(0,0),(4,4)),
        (('function',),(0,0),(1,1)),
        (('segment','ray','line','midpoint','projection'),(2,2),(0,0)),
        (('circle','point_on_function','point_on_curve','square'),(1,1),(1,1)),
        (('inverse',),(1,1),(0,0)),
        (('polygon',),(3,12),(0,0)),
        (('polar_point',),(0,1),(2,2)),
        (('intersection',),(2,2),(0,1)),
        (('angle_arc',),(2,2),(1,2)),
        (('partition',),(1,1),(2,2)),
        (('transform',),(1,2),(3,3)),
        (('align',),(5,5),(1,1)),
        (('series',),(1,1),(2,8))]
    variants=[]
    def arguments(bounds, *, reference=False):
        low,high=bounds
        element=Annotated[str,Field(pattern=r'^[a-z][a-z0-9_]*$')] if reference else str
        return (list[element],Field(min_length=low,max_length=high,
            **({'default_factory':list} if low==0 else {})))
    for names,refs,expr in groups:
        fields={'op':(Literal[names],...), 'refs':arguments(refs,reference=True), 'expr':arguments(expr)}
        if object_ids:fields['id']=(Literal[tuple(object_ids)],...)
        rule=('expr表示函数或轨迹，可使用函数自变量x。' if names[0] in {'parametric','function','locus'} else
              'expr表示实际对象位置或参数，禁止函数自由变量x/y；使用已声明控制参数、具体常数或此前点的坐标。')
        variants.append(create_model('Tool_'+names[0],__base__=MathConstructionObject,__doc__=rule,**fields))
    return Annotated[Union[tuple(variants)],Field(discriminator='op')]
