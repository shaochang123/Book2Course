"""Apply bounded model edits to a validated mathematical dependency graph."""
import ast
import re
from pydantic import Field,model_validator

from zhijiang.math_construction import StrictMathModel,MathConstructionDraft,MathConstructionObject
from zhijiang.visual_planning import VisualSceneError,expression_tree


class MathConstructionPatch(StrictMathModel):
    parameters: dict[str,float] = Field(default_factory=dict,max_length=16)
    upserts: list[MathConstructionObject] = Field(default_factory=list,max_length=16)
    remove: list[str] = Field(default_factory=list,max_length=12)
    objective: str | None = Field(default=None,min_length=12,max_length=120)

    @model_validator(mode='after')
    def unique_updates(self):
        ids=[o.id for o in self.upserts]
        if len(ids)!=len(set(ids)) or len(self.remove)!=len(set(self.remove)) or set(ids)&set(self.remove):
            raise ValueError('每个对象ID只允许一次upsert或remove；替换只写完整upsert，不同时remove。')
        return self


def apply_construction_patch(program,patch):
    """Preserve untouched definitions and restore a stable dependency order.

    This composes data, never model code. Callers must compile the entire graph
    and run all source, relationship, SVG and motion checks before acceptance.
    """
    base=MathConstructionDraft.model_validate(program.model_dump(exclude={'operations','claims','roles'}))
    objects={item.id:item for item in base.constructions}
    if len(patch.remove)!=len(set(patch.remove)) or set(patch.remove)-set(objects):
        raise VisualSceneError('构造补丁删除编号重复或不存在。')
    upsert_ids=[item.id for item in patch.upserts]
    if len(upsert_ids)!=len(set(upsert_ids)) or set(upsert_ids)&set(patch.remove):
        raise VisualSceneError('构造补丁不能重复更新或同时删除同一对象。')
    for name in patch.remove:del objects[name]
    for item in patch.upserts:objects[item.id]=item
    parameters={**base.parameters,**patch.parameters}
    if set(parameters)&set(objects):
        raise VisualSceneError('控制参数与数学对象ID不能同名。')
    dependencies={}
    def owner(name):
        if name in objects:return name
        for parent,item in objects.items():
            if item.op=='partition' and re.fullmatch(re.escape(parent)+r'_\d+_\d+',name):return parent
        return None
    for name,item in objects.items():
        deps=set()
        for reference in item.refs:
            parent=owner(reference)
            if parent is None:raise VisualSceneError('构造补丁留下不存在的依赖：'+reference)
            deps.add(parent)
        for expression in item.expr:
            symbols={n.id for n in ast.walk(expression_tree(expression)) if isinstance(n,ast.Name)}
            deps.update(symbols&set(objects))
            deps.update(parent for symbol in symbols if (parent:=owner(symbol)) is not None)
            # Declared controls take precedence over possible coordinate aliases.
            # Only point constructors actually define *_x/*_y; a line named
            # span must not create a false dependency for a span_y control.
            # Real point/control alias collisions remain rejected by Compiler.
            deps.update(obj for obj in objects if (symbols-set(parameters))&{obj+'_x',obj+'_y'})
        if deps-set(objects):raise VisualSceneError('构造补丁留下不存在的依赖：'+str(sorted(deps-set(objects))))
        dependencies[name]=deps
    ordered=[];done=set()
    while len(done)<len(objects):
        ready=[name for name in objects if name not in done and dependencies[name]<=done]
        if not ready:raise VisualSceneError('构造补丁产生循环依赖。')
        for name in ready:ordered.append(objects[name]);done.add(name)
    return MathConstructionDraft.model_validate({**base.model_dump(),
        'parameters':parameters,'constructions':ordered,
        'objective':patch.objective or base.objective})
