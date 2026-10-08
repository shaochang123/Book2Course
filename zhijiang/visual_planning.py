"""Subject-independent scene graph planning and restricted expression checks.

The model supplies data, never Python/SVG/TeX code. A subject name is descriptive,
not a routing whitelist. New domain checks can be registered by project code.
"""
from __future__ import annotations

import ast
import math
import re
import json
import hashlib
import os
import unicodedata
import importlib.util
import shutil
from typing import Literal
from functools import lru_cache
from pydantic import BaseModel, Field, model_validator, create_model, ConfigDict

from zhijiang.agents import GenerationError, validate_evidence
from zhijiang.models import Lesson, LessonSegment, VisualScenePlan, VisualBeat, Mode, ReviewResult, Evidence, SceneObject, SceneCheck


class VisualSceneError(GenerationError):
    pass


def visual_capabilities() -> dict:
    """Diagram animation uses native text; only computed geometry needs TeX."""
    missing = [name for name in ('manim','jieba','pymupdf')
               if importlib.util.find_spec(name) is None]
    tex_missing = [name for name in ('latex','dvisvgm') if not shutil.which(name)]
    return {'ready':not missing,'missing':missing,'geometry_ready':not (missing or tex_missing),
            'geometry_reason':'缺少：'+'、'.join(missing+tex_missing) if missing or tex_missing else '',
            'renderer':'Manim Cairo','reason':'缺少：'+'、'.join(missing) if missing else ''}


class VisualCoursePlan(BaseModel):
    title: str = Field(min_length=2,max_length=80)
    objective: str = Field(min_length=8,max_length=240)
    point_ids: list[int] = Field(min_length=1)


class SceneObjectDraft(SceneObject):
    @classmethod
    def __get_pydantic_json_schema__(cls,core_schema,handler):
        schema=handler.resolve_ref_schema(handler(core_schema))
        schema.get('properties',{}).pop('points',None)
        return schema


class SceneCheckDraft(SceneCheck):
    @model_validator(mode='before')
    @classmethod
    def program_tolerance(cls,value):
        # A model cannot weaken the acceptance threshold to approve wrong math.
        if isinstance(value,dict): value={**value,'tolerance':1e-6}
        return value

    @classmethod
    def __get_pydantic_json_schema__(cls,core_schema,handler):
        schema=handler.resolve_ref_schema(handler(core_schema))
        schema.get('properties',{}).pop('tolerance',None)
        return schema


class VisualSceneDraft(VisualScenePlan):
    # These fields are supplied/verified by the program, not drafted by the model.
    evidence: Evidence = Field(default_factory=lambda:Evidence(page=1,quote='由程序填入已核验的来源。'))
    objects: list[SceneObjectDraft] = Field(min_length=2,max_length=24)
    beats: list[VisualBeat] = Field(min_length=3,max_length=12)
    checks: list[SceneCheckDraft] = Field(default_factory=list,max_length=16)
    diagram: None = None

    @classmethod
    def __get_pydantic_json_schema__(cls,core_schema,handler):
        schema=handler.resolve_ref_schema(handler(core_schema))
        for key in ['evidence','verification','narration_binding','diagram','geometry_constraints']:
            schema.get('properties',{}).pop(key,None)
        schema['required']=[key for key in schema.get('required',[]) if key not in {'evidence','verification'}]
        return schema


LAYOUT_FIELDS={'domain','question','parameters','objects','x_range','y_range','axes'}
SEQUENCE_FIELDS={'beats','checks','domain_data','domain_validators','teaching_example','simplifications'}


def _partial_scene_model(name,fields):
    from copy import copy
    return create_model(name,__config__=ConfigDict(extra='forbid'),**{
        key:(field.annotation,copy(field)) for key,field in VisualSceneDraft.model_fields.items() if key in fields})


VisualLayoutDraft=create_model('VisualLayoutDraft',
    __base__=_partial_scene_model('VisualLayoutFields',LAYOUT_FIELDS),
    step_count=(int,Field(default=3,ge=3,le=5)))
VisualSequenceDraft=_partial_scene_model('VisualSequenceDraft',SEQUENCE_FIELDS)


def sequence_schema(layout):
    """Constrain numeric prose during decoding, rather than relying on reminders.

    Declared scientific names can contain digits; arbitrary numeric assertions
    cannot. The same schema is also checked by Pydantic for external APIs.
    """
    names=[]
    for obj in layout.objects:
        for value in (obj.id,obj.text):
            if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',value) and any(c.isdigit() for c in value):
                names.append(re.escape(value))
    alternatives=r'[^0-9０-９⁰¹²³⁴⁵⁶⁷⁸⁹\\=＝^＾{}<>*]'
    if names: alternatives+='|'+'|'.join(sorted(set(names)))
    # Bound the regex too: local JSON grammars do not necessarily enforce
    # maxLength, and an unbounded prose branch can exhaust num_predict.
    change_model=create_model('ParameterChange',
        name=(Literal[tuple(layout.parameters)],Field(description='Declared parameter name')),
        value=(float,Field(ge=-1e4,le=1e4))) if layout.parameters else None
    class OperationBeat(VisualBeat):
        @classmethod
        def __get_pydantic_json_schema__(cls,core_schema,handler):
            schema=handler.resolve_ref_schema(handler(core_schema))
            schema.get('properties',{}).pop('parameters',None)
            return schema

        @model_validator(mode='after')
        def bind_parameter_changes(self):
            if getattr(self,'parameter_changes',None):
                names=[v.name for v in self.parameter_changes]
                if len(set(names))!=len(names):raise ValueError('同一步不能重复修改一个参数。')
                self.parameters={v.name:v.value for v in self.parameter_changes}
            return self
    beat_model=create_model('VisualBeatDraft',__base__=OperationBeat,
        **({'parameter_changes':(list[change_model],Field(default_factory=list,max_length=40))} if change_model else {}),
        narration=(str,Field(min_length=12,max_length=100,pattern='^('+alternatives+'){12,100}$')))
    return create_model('VisualSequenceDraft',__base__=VisualSequenceDraft,
        beats=(list[beat_model],Field(min_length=getattr(layout,'step_count',3),
                                    max_length=getattr(layout,'step_count',3))))


def validate_motion_layout(layout):
    """Reject unbound coordinates before spending a call on a motion script."""
    names=set(layout.parameters)
    for name,value in layout.parameters.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}',name) or name in {'x','pi','e'}:
            raise VisualSceneError('参数名称无效或与保留变量冲突：'+name+'。x仅用于曲线自由变量，不在parameters声明。')
        if not math.isfinite(value) or abs(value)>1e4:
            raise VisualSceneError('场景参数必须是有限且有界的数值。')
    used=set()
    for obj in layout.objects:
        object_geometry(obj,layout.parameters)
        expressions=[v for p in coordinate_expressions(obj) for v in p]
        expressions.extend([obj.expression,*obj.parametric_expression])
        if obj.kind=='circle':expressions.append(obj.radius)
        for expression in filter(None,expressions):
            used.update(node.id for node in ast.walk(expression_tree(expression)) if isinstance(node,ast.Name))
    if not names & used:
        raise VisualSceneError('所有对象坐标与尺寸都是常数，没有对象依赖已声明参数。'
            '重新设计对象：将确实要变化的数学量作为参数，并在相应position/start/end/vertices/expression/radius中引用参数名，'
            '不要把参数预先计算成固定坐标；随后步骤才能改变它。不能用改show/hide冒充数学变化。')


def bind_motion_parameters(client,layout,material,instruction):
    """Ask for symbolic bindings rather than repeating a constant layout."""
    if not layout.parameters:raise VisualSceneError('数学变化需要显式声明初始参数。')
    targets={}
    for obj in layout.objects:
        for name in ['position','start','end','vertices','parametric_expression']:
            value=getattr(obj,name)
            for i,item in enumerate(value):
                if isinstance(item,list):
                    for j,_ in enumerate(item):targets[f'{obj.id}.{name}.{i}.{j}']=(obj,name,i,j)
                else:targets[f'{obj.id}.{name}.{i}']=(obj,name,i,None)
        for name in ['expression','radius']:
            if name=='expression' and obj.kind!='curve':continue
            if name=='radius' and obj.kind!='circle':continue
            targets[f'{obj.id}.{name}']=(obj,name,None,None)
    if not targets:raise VisualSceneError('没有可绑定的数学坐标或表达式。')
    # A bounded token pattern helps native JSON decoders retain variables. The
    # AST validator and actual motion checks remain authoritative after decoding.
    names='|'.join(re.escape(v) for v in layout.parameters)
    expression_pattern=r'^[a-z0-9_+*/(). -]{0,120}('+names+r')[a-z0-9_+*/(). -]{0,120}$'
    binding=create_model('MotionParameterBinding',
        target=(Literal[tuple(targets)],Field()),
        expression=(str,Field(min_length=1,max_length=240,pattern=expression_pattern)))
    schema=create_model('MotionParameterBindings',bindings=(list[binding],Field(min_length=1,max_length=8)))
    repair=client.generate(schema,instruction+
        '\n当前候选错误地把变化量预先算成固定坐标。只修复确实需要变化的对象字段，用已声明参数写完整坐标表达式。'
        '多个坐标必须一起变化时逐项绑定。保持参照对象与原文数学条件；不为通过检查增加无关运动。'
        'target仅选可改字段；expression必须实际依赖参数，不能乘零或抵消参数。',
        material+'\n待绑定对象：'+layout.model_dump_json()+'\n可改字段：'+json.dumps(list(targets)))
    seen=set()
    for item in repair.bindings:
        if item.target in seen:raise VisualSceneError('重复的对象参数绑定。')
        seen.add(item.target)
        obj,name,i,j=targets[item.target]
        if i is None:setattr(obj,name,item.expression)
        elif j is None:getattr(obj,name)[i]=item.expression
        else:getattr(obj,name)[i][j]=item.expression
    validate_motion_layout(layout)
    return repair.model_dump()


def plan_general_lesson(client,bundle,document,prompt,voice_mode,progress,draft_output=None,
                        source_assets=None,pdf_path=None,*,geometry_only=False):
    """Use stable source IDs; mutable model-generated titles are not identifiers."""
    material='知识点：'+json.dumps([
        # Course ordering needs topic identities, not a second copy of every
        # scanned excerpt. Full evidence remains attached to each segment and
        # is read independently during scene design.
        {'id':i+1,'title':point.title,'kind':point.kind}
        for i,point in enumerate(bundle.points)],ensure_ascii=False)
    expected=set(range(1,len(bundle.points)+1))
    order_path=draft_output.with_name('course-order.json') if draft_output else None
    order_hash=hashlib.sha256(json.dumps({'version':'course-order-v1',
        'source':hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_path else document.model_dump_json(),
        'knowledge':bundle.model_dump(mode='json'),'prompt':prompt,
        'endpoint':getattr(client,'base_url',''),'model':getattr(client,'model','')},sort_keys=True).encode()).hexdigest()
    outline=None
    if order_path:
        try:
            saved=json.loads(order_path.read_text(encoding='utf-8'))
            if saved['fingerprint']==order_hash:
                candidate=VisualCoursePlan.model_validate(saved['outline'])
                if set(candidate.point_ids)==expected and len(candidate.point_ids)==len(expected):
                    outline=candidate
                    progress('复用完整课程顺序',52)
        except (OSError,ValueError,KeyError):pass
    if outline is None:
        for attempt in range(3):
            outline=client.generate(VisualCoursePlan,
                '规划完整教学课程，标题和目标用中文。point_ids 必须使用每个输入id恰好一次，以教学顺序排列。'+
                ('上次遗漏或重复编号，请检查完整编号集合。' if attempt else '')+
                '\n用户的教学偏好：'+prompt+
                '\n必须覆盖的知识点编号：'+str(sorted(expected))+'；教学偏好中的步骤数指每个片段，不得删掉来源知识点。',material)
            if set(outline.point_ids)==expected and len(outline.point_ids)==len(expected): break
        else:
            # Coverage is a structural property with authoritative source IDs.
            # Retain valid ordering and append omitted points, never invent IDs.
            outline.point_ids=list(dict.fromkeys(i for i in outline.point_ids if i in expected))
            outline.point_ids.extend(i for i in sorted(expected) if i not in outline.point_ids)
        if order_path:
            order_path.parent.mkdir(parents=True,exist_ok=True)
            temporary=order_path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'fingerprint':order_hash,'outline':outline.model_dump(),
                'status':'structurally_valid_course_order'},ensure_ascii=False,indent=2),encoding='utf-8')
            os.replace(temporary,order_path)
    lesson=Lesson(title=outline.title,objective=outline.objective,mode=Mode.AI,voice_mode=voice_mode,
        notice='AI 生成：教学场景按表达类型核查来源、关系或几何与声明的数值；教学含义、领域事实和示意简化仍需复核。',
        segments=[LessonSegment(title=bundle.points[i-1].title,kind=bundle.points[i-1].kind,
            narration=bundle.points[i-1].explanation+' 请结合来源观察逐步演示过程。',
            bullets=[bundle.points[i-1].title],evidence=bundle.points[i-1].evidence) for i in outline.point_ids])
    plan_visual_scenes(client,lesson,document,prompt,progress,draft_output=draft_output,
        pedagogical_design=True,source_assets=source_assets,pdf_path=pdf_path,geometry_only=geometry_only)
    lesson.animation_report['source_point_ids']=outline.point_ids
    return lesson


PRIMITIVES = ("dot", "circle", "line", "arrow", "polygon", "curve", "parametric_curve", "label")
FUNCTIONS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt,
             'asin':math.asin,'acos':math.acos,'atan':math.atan,'atan2':math.atan2,
             "exp": math.exp, "log": math.log, "abs": abs, "min": min, "max": max}
CHECKERS = {
    "equal": lambda value, expected, tolerance: abs(value-expected) <= tolerance,
    "nonnegative": lambda value, expected, tolerance: value >= -tolerance,
    "at_most": lambda value, expected, tolerance: value <= expected+tolerance,
}
DOMAIN_VALIDATORS = {}


def register_checker(name: str, checker) -> None:
    """Register a trusted project-owned chemistry/physics/etc. numeric rule."""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name) or not callable(checker):
        raise ValueError("Invalid checker registration")
    CHECKERS[name] = checker


def register_domain_validator(name: str, validator) -> None:
    """Trusted rule gets full scene context for units, atoms, relationships, etc."""
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,31}',name) or not callable(validator):
        raise ValueError('Invalid domain validator')
    DOMAIN_VALIDATORS[name]=validator


def check_domain_state(scene,parameters):
    reports=[]
    for name in scene.domain_validators:
        if name not in DOMAIN_VALIDATORS:
            raise VisualSceneError('未安装的领域核验扩展：'+name)
        result=DOMAIN_VALIDATORS[name](scene,parameters)
        if not isinstance(result,dict) or result.get('passed') is not True:
            raise VisualSceneError('领域核验扩展拒绝当前状态：'+name)
        reports.append({'validator':name,**result})
    return reports


def load_registered_checkers():
    # Installed extensions load in both the server and the Manim child process.
    # This executes trusted installed project code, never scene/model code.
    from importlib.metadata import entry_points
    for entry in entry_points(group='book2course.visual_checks'):
        register_checker(entry.name,entry.load())
    for entry in entry_points(group='book2course.visual_validators'):
        register_domain_validator(entry.name,entry.load())


load_registered_checkers()


@lru_cache(maxsize=1024)
def expression_tree(expression: str):
    try:
        tree = ast.parse(expression, mode="eval").body
    except (SyntaxError, RecursionError) as exc:
        raise VisualSceneError("图形表达式有歧义；只支持明确的数学表达式。") from exc
    if len(list(ast.walk(tree))) > 100:
        raise VisualSceneError("图形表达式过于复杂，请拆分推理步骤。")
    return tree


def evaluate(expression: str, parameters: dict[str, float]) -> float:
    def walk(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id in parameters:
                return parameters[node.id]
            if node.id in {"pi", "e"}:
                return getattr(math, node.id)
            raise VisualSceneError("未定义的图形参数："+node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = walk(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            a, b = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Add): return a+b
            if isinstance(node.op, ast.Sub): return a-b
            if isinstance(node.op, ast.Mult): return a*b
            if isinstance(node.op, ast.Div): return a/b
            if isinstance(node.op, ast.Pow) and abs(b) <= 12: return a**b
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            if not node.keywords and 1 <= len(node.args) <= 4:
                return FUNCTIONS[node.func.id](*(walk(arg) for arg in node.args))
        raise VisualSceneError("不支持的表达式操作；禁止代码、属性访问和工具调用。")
    try:
        result = walk(expression_tree(expression))
        if isinstance(result, complex) or not math.isfinite(result) or abs(result) > 1e12:
            raise ValueError("not a bounded real value")
        return float(result)
    except (ArithmeticError, ValueError, TypeError, OverflowError) as exc:
        raise VisualSceneError("图形表达式不能得到有限实数："+expression) from exc


def coordinate_expressions(obj):
    explicit=[]
    if obj.kind in {'dot','circle','label'} and obj.position:
        explicit=[obj.position]
    elif obj.kind in {'line','arrow'} and (obj.start or obj.end):
        explicit=[obj.start,obj.end]
    elif obj.kind=='polygon' and obj.vertices:
        explicit=obj.vertices
    if explicit and obj.points and explicit!=obj.points:
        raise VisualSceneError('对象包含互相矛盾的坐标定义：'+obj.id)
    return explicit or obj.points


def object_geometry(obj, parameters: dict) -> dict:
    for coordinate in coordinate_expressions(obj):
        for expression in coordinate:
            if any(isinstance(node, ast.Name) and node.id == 'x'
                   for node in ast.walk(expression_tree(expression))):
                raise VisualSceneError(
                    f"对象{obj.id}的{obj.kind}坐标包含自由变量x：{expression}。"
                    "position/start/end必须是参数决定的数值坐标；"
                    "如果要画y=f(x)的函数图像，改用curve，把函数写入expression，"
                    "提供domain并清空坐标字段。不要添加名为x的参数。")
    points = [[evaluate(p[0], parameters), evaluate(p[1], parameters)] for p in coordinate_expressions(obj)]
    if obj.kind == "curve":
        lo, hi = obj.domain
        points = [[lo+(hi-lo)*i/100, evaluate(obj.expression, dict(parameters, x=lo+(hi-lo)*i/100))]
                  for i in range(101)]
    elif obj.kind == 'parametric_curve':
        if len(obj.parametric_expression)!=2:
            raise VisualSceneError('参数曲线需要横纵两个表达式：'+obj.id)
        lo,hi=obj.domain
        points=[[evaluate(expression,dict(parameters,x=lo+(hi-lo)*i/100))
                 for expression in obj.parametric_expression] for i in range(101)]
    radius = evaluate(obj.radius, parameters) if obj.kind in {"circle", "dot"} else 0
    return {"points": points, "radius": radius}


@lru_cache(maxsize=512)
def expression_tex(expression: str) -> str:
    """Generate TeX from an already restricted expression, never model TeX."""
    import sympy as sp
    functions={'sin':sp.sin,'cos':sp.cos,'tan':sp.tan,'sqrt':sp.sqrt,'exp':sp.exp,
               'asin':sp.asin,'acos':sp.acos,'atan':sp.atan,'atan2':sp.atan2,
               'log':sp.log,'abs':sp.Abs,'min':sp.Min,'max':sp.Max}
    def symbolic(node):
        if isinstance(node,ast.Constant) and type(node.value) in (int,float): return sp.Rational(str(node.value))
        if isinstance(node,ast.Name):
            if node.id=='pi': return sp.pi
            if node.id=='e': return sp.E
            if re.fullmatch(r'[a-z][a-z0-9_]{0,31}',node.id): return sp.Symbol(node.id)
        if isinstance(node,ast.UnaryOp):
            v=symbolic(node.operand)
            if isinstance(node.op,ast.USub): return -v
            if isinstance(node.op,ast.UAdd): return v
        if isinstance(node,ast.BinOp):
            a,b=symbolic(node.left),symbolic(node.right)
            if isinstance(node.op,ast.Add): return a+b
            if isinstance(node.op,ast.Sub): return a-b
            if isinstance(node.op,ast.Mult): return a*b
            if isinstance(node.op,ast.Div): return a/b
            if isinstance(node.op,ast.Pow): return a**b
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in functions and not node.keywords:
            return functions[node.func.id](*(symbolic(arg) for arg in node.args))
        raise VisualSceneError('公式包含不支持的表达式。')
    return sp.latex(symbolic(expression_tree(expression)))


def states(scene: VisualScenePlan):
    params = dict(scene.parameters)
    visible = {obj.id for obj in scene.objects if obj.visible}
    for beat in scene.beats:
        before = dict(params)
        params.update(beat.parameters)
        visible.update(beat.show)
        visible.difference_update(beat.hide)
        yield before, dict(params), set(visible)


def motion_features(scene,samples,visible):
    """Measure actual geometry independently of the model's narration."""
    features={}
    for obj in scene.objects:
        if obj.id not in visible:continue
        geometries=[sample[obj.id] for sample in samples];points=[g['points'] for g in geometries]
        displacement=max(math.dist(a,b) for sample in points[1:] for a,b in zip(points[0],sample))
        turning=False;sweep=False
        if obj.kind in {'line','arrow','polygon','curve','parametric_curve'}:
            for j in range(len(points[0])-1):
                directions=[]
                for sample in points:
                    a,b=sample[j],sample[j+1];dx,dy=b[0]-a[0],b[1]-a[1]
                    if math.hypot(dx,dy)>1e-6:directions.append(math.atan2(dy,dx))
                if directions and any(abs(math.atan2(math.sin(a-directions[0]),math.cos(a-directions[0])))>1e-4 for a in directions[1:]):
                    turning=True
                # A collinear collapse and reversal changes direction but is
                # not a continuous angular sweep. True half-turns have a
                # non-collinear intermediate direction.
                if directions and any(abs(math.sin(a-directions[0]))>1e-4 for a in directions[1:]):
                    sweep=True;break
        elif obj.kind=='dot' and displacement>1e-6:
            for reference in scene.objects:
                if reference.id==obj.id or reference.kind not in {'dot','circle'}:continue
                centers=[sample[reference.id]['points'][0] for sample in samples]
                if any(math.dist(centers[0],c)>1e-6 for c in centers[1:]):continue
                distances=[math.dist(p[0],c) for p,c in zip(points,centers)]
                if min(distances)>1e-6 and max(distances)-min(distances)<1e-5:
                    turning=True;sweep=True;break
        def preview(value):
            return value if len(value)<=12 else [value[0],value[len(value)//2],value[-1]]
        features[obj.id]={'maximum_displacement':displacement,'direction_changed':turning,'angular_sweep':sweep,
            'radius_changed':max(g['radius'] for g in geometries)-min(g['radius'] for g in geometries),
            'stationary':all(g==geometries[0] for g in geometries[1:]),
            'start_points':preview(points[0]),'end_points':preview(points[-1])}
    return features


def verify_visual_scene(scene: VisualScenePlan) -> dict:
    if scene.diagram:
        from zhijiang.teaching_design import validate_diagram
        report=validate_diagram(scene.diagram,scene.domain_data.get('source_page_text'))
        if len(scene.beats)!=len(scene.diagram.steps) or any(
                b.narration!=s.narration for b,s in zip(scene.beats,scene.diagram.steps)):
            raise VisualSceneError('教学步骤与实际口播不一致。')
        report['states']=[{'step':i+1,'parameters':{},'calculations':[],
                           'focus':s.focus,'relations':s.relations} for i,s in enumerate(scene.diagram.steps)]
        return report
    if scene.narration_binding == 'computed':
        # Model prose describes operations. The trusted speech layer supplies
        # actual parameter/calculation values, so stale numbers can't survive
        # merely because another model approved the free-form narration.
        identifiers = [obj.id for obj in scene.objects]
        identifiers += [obj.text for obj in scene.objects
                        if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', obj.text)]
        def without_identifiers(text):
            for name in sorted(identifiers, key=len, reverse=True):
                text = re.sub(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])', '', text)
            return text
        for index, beat in enumerate(scene.beats):
            prose = without_identifiers(beat.narration)
            if re.search(r'[\\=＝^＾{}<>]|\*\*', prose):
                raise VisualSceneError(f'口播格式无效：第{index+1}步。口播必须是可直接朗读的自然语言，'
                    '不能包含方程符号、LaTeX或转义串；公式放在对象表达式与calculations。')
            worded_number = re.search(
                r'(?:为|是|等于|趋近|接近|达到|变为|增加到|减小到|保持在)\s*'
                r'[负零〇一二两三四五六七八九十百千万亿点]+'
                r'(?=$|[，。,；;！!？?\s]|(?:米|秒|度|份|倍|焦耳))', prose)
            quantity_unit=re.search(r'[负零〇一二两三四五六七八九十百千万亿点]+(?:度|倍|米|秒|份)(?![a-zA-Z])',prose)
            if any(char.isdigit() for char in prose) or worded_number or quantity_unit or any(
                    any(char.isdigit() for char in without_identifiers(c.label)) for c in beat.calculations):
                raise VisualSceneError(f'口播数字未绑定：第{index+1}步。口播只用中文描述对象、操作与原因，'
                    '不要写数值、坐标或方程；把这些放在parameters与calculations，程序负责计算与播报。')
    if len(scene.parameters) > 40:
        raise VisualSceneError("单场景参数过多，请拆成多个片段。")
    for axis in (scene.x_range, scene.y_range):
        if not all(math.isfinite(v) and abs(v) <= 1e4 for v in axis) or axis[1]-axis[0] < 0.01:
            raise VisualSceneError("图形坐标范围无效。")
    ids = [obj.id for obj in scene.objects]
    if len(ids) != len(set(ids)):
        raise VisualSceneError("场景对象 ID 必须唯一，跨步骤维持身份。")
    for obj in scene.objects:
        if obj.kind not in PRIMITIVES:
            raise VisualSceneError("尚未注册的图形原语："+obj.kind)
        if obj.kind=='label' and re.search(r'\$\{[^}]+\}',obj.text):
            raise VisualSceneError('文字标签不支持动态模板：'+obj.id+'。使用普通名称；动态数值放在calculations，由程序计算显示。')
        required = {"dot": 1, "circle": 1, "label": 1, "line": 2, "arrow": 2, "polygon": 3}.get(obj.kind, 0)
        coordinates=coordinate_expressions(obj)
        if (len(coordinates) < required or any(len(p) != 2 for p in coordinates)
                or (obj.kind in {'dot','circle','label','line','arrow'} and len(coordinates)!=required)):
            raise VisualSceneError(f"对象{obj.id}的{obj.kind}类型需要恰好{required}个二维坐标（polygon至少3个）；不要把两个点放进一个dot。")
        if obj.kind == "curve" and (not obj.expression or not all(math.isfinite(v) for v in obj.domain)
                                    or obj.domain[1] <= obj.domain[0]):
            raise VisualSceneError("曲线需要明确表达式和递增定义域。")
        if obj.kind == 'parametric_curve' and (len(obj.parametric_expression)!=2 or
                not all(math.isfinite(v) for v in obj.domain) or obj.domain[1]<=obj.domain[0]):
            raise VisualSceneError('参数曲线需要横纵两个表达式和递增定义域。')
    def check_params(params):
        for key, value in params.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", key) or key in {"x", "pi", "e"}:
                raise VisualSceneError("参数名称无效或与保留变量冲突："+key)
            if not math.isfinite(value) or abs(value) > 1e4:
                raise VisualSceneError("场景参数必须是有限且有界的数值。")
    check_params(scene.parameters)
    verified_states = []
    meaningful_motion = False
    for index, (before, after, visible) in enumerate(states(scene)):
        beat = scene.beats[index]
        if set(beat.parameters)-set(scene.parameters):
            raise VisualSceneError("步骤只能修改已声明的参数。")
        if (set(beat.show)|set(beat.hide))-set(ids) or set(beat.show)&set(beat.hide):
            raise VisualSceneError("显示与隐藏操作引用了无效对象。")
        check_params(after)
        samples = []
        relation_samples=[]
        for alpha in (0, 0.25, 0.5, 0.75, 1):
            params = {key: before[key]+alpha*(after[key]-before[key]) for key in before}
            check_domain_state(scene,params)
            geometry = {}
            for obj in scene.objects:
                g = object_geometry(obj, params)
                if any(abs(v)>1e4 for p in g['points'] for v in p) or not 0 <= g['radius'] <= 100:
                    raise VisualSceneError("图形尺寸或坐标超出可渲染范围。")
                geometry[obj.id] = g
            if scene.geometry_constraints:
                from zhijiang.visual_geometry_checks import check_geometry_constraints,check_geometry_visibility,GeometryRelationError
                try:
                    check_geometry_visibility(scene,geometry,visible)
                    relation_samples.append(check_geometry_constraints(scene,geometry,params))
                except GeometryRelationError as exc:raise VisualSceneError(str(exc)) from exc
            for check in scene.checks:
                if check.checker not in CHECKERS:
                    raise VisualSceneError("尚未注册的领域检查："+check.checker)
                value = evaluate(check.expression, params)
                if not CHECKERS[check.checker](value, check.expected, check.tolerance):
                    raise VisualSceneError(
                        f"领域计算检查失败：{check.expression}，参数{params}时计算值{value:.8g}，"
                        f"检查{check.checker}的预期为{check.expected:.8g}。checks是所有步骤及中间帧的恒成立条件，"
                        "不能把最终参数或某一步的结果当作全程恒等式；逐步结果应放在对应beat.calculations。")
            samples.append(geometry)
        meaningful_motion |= any(
            samples[0][key]['points']!=sample[key]['points'] or
            (next(obj.kind for obj in scene.objects if obj.id==key)=='circle' and samples[0][key]['radius']!=sample[key]['radius'])
            for sample in samples[1:] for key in visible)
        motion=motion_features(scene,samples,visible)
        if re.search(r'旋转|转动|转向|夹角[^。；]*(?:增大|减小|变大|变小)',beat.narration) and not any(v['angular_sweep'] for v in motion.values()):
            raise VisualSceneError(f'口播运动不一致：第{index+1}步声称旋转或改变夹角，但实际可见对象没有方向变化。'
                '长度增减不是旋转；修改真实坐标表达式或如实讲解当前操作，不得只改变参数名称。')
        calculations = []
        for calculation in beat.calculations:
            value = evaluate(calculation.expression, after)
            if calculation.expected is not None and abs(value-calculation.expected) > 1e-6:
                raise VisualSceneError(f"分镜计算结果不正确：{calculation.label}，声明{calculation.expected}，计算{value}")
            calculations.append({"label": calculation.label, "expression": calculation.expression, "value": value})
        verified_states.append({"step": index+1, "parameters": after, "visible": sorted(visible),
                                "calculations": calculations,"motion":motion,'geometry_relations':relation_samples,
                                "start_geometry": samples[0], "end_geometry": samples[-1]})
    if not meaningful_motion:
        raise VisualSceneError("分镜需要与讲解对应的对象位置、尺寸或曲线变化，不能只逐项显现要点。")
    for obj in scene.objects:
        visible_states=[s for s in verified_states if obj.id in s['visible']]
        if obj.kind in {'line','arrow'} and visible_states and all(
            s['end_geometry'][obj.id]['points'][0]==s['end_geometry'][obj.id]['points'][-1] for s in visible_states):
            raise VisualSceneError('线或箭头在所有可见步骤都退化为一点：'+obj.id)
    for i,obj in enumerate(scene.objects):
        if obj.kind!='dot': continue
        for other in scene.objects[i+1:]:
            common=[s for s in verified_states if obj.id in s['visible'] and other.id in s['visible']]
            if other.kind=='dot' and len(common)>=2 and all(
                s['end_geometry'][obj.id]['points']==s['end_geometry'][other.id]['points'] for s in common):
                raise VisualSceneError('两个点始终完全重合，无法区分教学对象：'+obj.id+' / '+other.id)
    return {"passed": True, "states": verified_states, "interpolation_samples_per_step": 5,
            "declared_domain_checks": len(scene.checks), "scope": "表达式、声明的数值关系与几何状态；领域事实及示意简化仍需来源和人工核对"}


def plan_visual_scenes(client, lesson: Lesson, document, prompt: str, progress, draft_output=None,
                       pedagogical_design=False,source_assets=None,pdf_path=None,*,geometry_only=False) -> None:
    from zhijiang.teaching_design import plan_teaching_representation,compile_teaching_scene
    instruction = (
        "为当前教学片段生成可执行的跨学科 visual_scene 数据。学科名称不限。"
        "不是淡入静态图：至少3步，以参数变化驱动同一对象的位置、半径、曲线或关系过程，解释为什么变化。"
        "只用 dot,circle,line,arrow,polygon,curve,parametric_curve,label。dot/circle/label 用position=[横坐标表达式,纵坐标表达式]；"
        "line/arrow用start和end两个二维坐标；polygon用vertices二维坐标数组。"
        "curve.expression 用 x 表示横坐标，domain 是绘图区间。参数只用小写英文，x/pi/e 保留。"
        "parametric_curve.parametric_expression=[横向表达式,纵向表达式]，x在此代表沿路径的自由参数，domain为它的范围；"
        "可表达圆弧、闭合轨迹及不属于单值函数的曲线。弧的角度和路径形状也可依赖已声明参数；不输出坐标字段。"
        "表达式仅用四则、**、sin/cos/tan/asin/acos/atan/atan2/sqrt/exp/log/abs/min/max。不生成代码、SVG、LaTeX。"
        "sin/cos/tan 的输入是弧度；度数必须先乘pi/180再进入三角函数。log是一元自然对数，其他底用log(变量)/log(底数)。"
        "label.text只用普通静态名称，不支持${...}模板；动态角度、长度和数值放入calculations，且表达式须测量当前实际图形。"
        "对象不超过8个，步骤3至5步，每步口播30至70字。参数在初始 parameters 全部声明，步骤只修改其数值。"
        "domain写中文学科/概念名称，question与narration用中文。坐标图设axes=true。"
        "坐标合理放入 x_range/y_range；默认 [-5,5]/[-3,3]。同一对象ID及颜色全程不变。"
        "数学/物理可用曲线、点和连线，概率用概率参数，化学/生物用粒子、组分和关系。"
        "末步有结论。计算写 calculations(expression,label,expected)，必须是确定的数值标量，不能含自由变量x；函数写在curve.expression。能检验的守恒/归一化写checks(equal/nonnegative/at_most)。"
        "checks在每个步骤及连续中间帧都检查，只写恒成立条件；最终数值不属于checks。"
        "涉及斜率、面积、概率等数值的步骤必须在calculations写明确表达式；口播解释过程，计算值由程序播报。"
        "不捏造领域结论，示意简化写 simplifications，原创数值 teaching_example=true。"
        "口播对应当前图形操作，不能把参数插值说成未经证明的真实物理路径。"
        "只输出必要字段，不输出evidence、verification或tolerance；来源、核验及严格数值容差由程序控制。一个点只能有一个position，不能同时装两个位置。"
        '函数必须使用curve，且expression与domain非空；line/arrow必须有start和end，不能只给expression。'
        'position/start/end绝不允许自由变量x。直线的函数图像也用curve，expression根据当前资料中的公式定义，domain按来源变量范围选择，不填start/end。'
        '语法示例仅说明字段：点 {"id":"marker","kind":"dot","position":["horizontal","vertical"]}，'
        '其中horizontal与vertical必须在parameters声明。具体参数、函数和路径须来自当前来源或明确标注的计算示例，不能套用其他教材的分镜。'
    )
    instruction += '\n可用checks名称：'+', '.join(sorted(CHECKERS))+\
        '；已安装domain_validators名称：'+(', '.join(sorted(DOMAIN_VALIDATORS)) or '无，保持空数组')+'。'
    sequence_instruction = (
        '为已经确定的教学对象规划中文操作步骤，输出当前JSON契约。不要重新定义对象。'
        'beats为3至5步，每步narration解释当前对象、操作及原因，parameter_changes写变更列表，每项name选择已声明参数，value为该步目标值。'
        '至少有一步真正改变参数数值；保持当前状态时parameter_changes=[]。不能输出parameters字典。'
        'narration中禁止字面数字、具体坐标和方程，不得将数字改写为中文数词规避；程序从当前参数和计算生成数值口播。'
        'narration只写可以直接朗读的自然语言，不用等号、幂号、LaTeX或转义串。'
        '口播风格示例：观察固定对象和移动对象，沿图中路径调整位置，比较它与参照对象的关系。'
        '同一对象身份与颜色不变，至少一次连续几何变化；末步讲清结论和条件。'
        '每步的数值计算放在该步calculations：只给label与expression，expected可省略，数值由程序计算和配音。'
        '表达式只含已声明参数，不含自由变量x。不要口算或在口播断言未核验数值。'
        'checks是所有初态、中间帧和终态均成立的关系，绝不是单步结果。不能证明恒成立时保持checks=[]。'
        '用户要求checks为空时必须保持空数组。旧稿被指出错误的check必须删除，不能复制。'
        'show/hide只引用已确定对象ID。domain_data记录领域条件，simplifications记录示意假设。'
        '原创数值teaching_example=true；不能把有限逼近说成严格极限，不能把插值说成真实微观机制。'
        '\n可用checks名称：'+', '.join(sorted(CHECKERS))+
        '；已安装domain_validators名称：'+(', '.join(sorted(DOMAIN_VALIDATORS)) or '无，保持空数组')+'。')
    if geometry_only and not visual_capabilities()['geometry_ready']:
        raise VisualSceneError('数学对象推演需要 TeX 和动画依赖：'+visual_capabilities()['geometry_reason'])
    drafts=[]; reviews=[]
    source_digest=hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_path else document.model_dump_json()
    for index, segment in enumerate(lesson.segments):
        cache_path=draft_output.with_name(f'planned-scene-{index+1:02d}.json') if pedagogical_design and draft_output else None
        fingerprint=hashlib.sha256(json.dumps({'version':'teaching-design-v32','source':source_digest,
            'geometry_only':geometry_only,
            'semantic_thinking':getattr(client,'semantic_thinking',True),
            'endpoint':getattr(client,'base_url',''),'model':getattr(client,'model',''),
            'prompt':prompt,'topic':segment.title,'evidence':segment.evidence.model_dump(),
            'geometry_ready':visual_capabilities()['geometry_ready']},sort_keys=True).encode()).hexdigest()
        if cache_path:
            cached=load_planned_scene(cache_path,fingerprint,document,segment)
            if geometry_only and cached and not cached[0].geometry_constraints:
                cached=None
            if cached and cached[0].diagram:
                from zhijiang.teaching_design import cached_source_examples_covered,cached_source_sequence_covered,cached_topic_focus_covered,normalized
                try:
                    reading=json.loads(cache_path.with_name(f'source-reading-{index+1:02d}.json').read_text(encoding='utf-8'))
                    source_page=next(page.text for page in document.pages if page.page==cached[0].evidence.page)
                    facts=reading['facts']
                    if (not all(normalized(fact['source_quote']) in normalized(source_page) for fact in facts)
                            or not cached_source_examples_covered(cached[0],facts,prompt)
                            or not cached_source_sequence_covered(cached[0],facts)
                            or (not cached[1].get('topic_scope') and not cached_topic_focus_covered(cached[0],facts,segment.title))):
                        cached=None
                except (OSError,ValueError,KeyError):cached=None
            if cached:
                scene,review=cached
                segment.visual_scene=scene;segment.narration=' '.join(b.narration for b in scene.beats)
                segment.evidence=scene.evidence
                drafts.append({'segment_index':index,'cached':True,'scene':scene.model_dump()})
                reviews.append({**review,'segment_index':index,'cached':True})
                progress(f'复用已核验分镜（{index+1}/{len(lesson.segments)}）：{segment.title}',54+index*10//len(lesson.segments))
                continue
        geometry_context={}
        if geometry_only and pedagogical_design:
            # An explicit mathematical animation request is a representation
            # contract. Retrieve the source before planning mathematical objects;
            # a failed construction must not silently become a flowchart.
            validate_evidence(document,segment.evidence)
            page=next(p for p in document.pages if p.page==segment.evidence.page)
            # Read the complete cited page. The qualitative graph reader's
            # fact/relationship contract cannot carry mathematical expressions.
            # The separate geometry review below checks the full page, title,
            # objects, operations, conditions and computed states together.
            geometry_context={'geometry_source':{'page':page.page,'text':page.text,
                'topic':segment.title,'evidence':segment.evidence.model_dump()}}
        if pedagogical_design and not geometry_only:
            progress(f'分析教学表达（{index+1}/{len(lesson.segments)}）：{segment.title}',54+index*10//len(lesson.segments))
            diagnostic=draft_output.with_name(f'teaching-design-{index+1:02d}.json') if draft_output else None
            design,report,design_errors=plan_teaching_representation(client,segment,document,prompt,diagnostic_output=diagnostic,
                pdf_path=pdf_path,
                force_diagram=not visual_capabilities()['geometry_ready'],
                on_phase=lambda name:progress(f'{name}（{index+1}/{len(lesson.segments)}）：{segment.title}',54+index*10//len(lesson.segments)))
            drafts.append({'segment_index':index,'teaching_design':design.model_dump(),'rejected_designs':design_errors})
            if draft_output:
                draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
            if design.representation!='geometry':
                page=next(p for p in document.pages if p.page==report.get('topic_scope',{}).get('page',segment.evidence.page))
                scene=compile_teaching_scene(design,segment,report,source_assets=source_assets,pdf_path=pdf_path,source_text=page.text)
                scene.verification=verify_visual_scene(scene)
                segment.visual_scene=scene
                segment.narration=' '.join(b.narration for b in scene.beats)
                reviews.append({'segment_index':index,'representation':design.representation,**report})
                save_planned_scene(cache_path,fingerprint,scene,reviews[-1])
                continue
        progress(f"规划通用教学场景（{index+1}/{len(lesson.segments)}）：{segment.title}", 54+index*10//len(lesson.segments))
        feedback = ""; previous_draft=""; last_error="";layout=None;approved=False;rejected_counts={}
        for _ in range(5):
            # Human preferences and computed repair instructions are authoritative
            # task instructions. Source excerpts and old model drafts stay data.
            # Putting all three inside source_data made small models ignore repairs.
            task_instruction=instruction+'\n用户的教学偏好：'+prompt+feedback
            material="片段："+segment.model_dump_json(exclude={'math_scene','visual_scene'})+previous_draft
            if geometry_context:
                material+='\n独立检索的原文依据（不得把新算例冒充原文）：'+json.dumps(geometry_context,ensure_ascii=False)
            if layout is None:
                progress(f'规划图形对象（{index+1}/{len(lesson.segments)}）：{segment.title}',54+index*10//len(lesson.segments))
                try:
                    layout=client.generate(VisualLayoutDraft,task_instruction+
                        '\n本轮只规划对象与初始参数，不输出口播步骤或计算检查。把用户要求的曲线、点、参照线全部画出；'
                        '对象表达式保留可变参数，固定对象不得依赖未来会变化的参数。明确每个对象的颜色。'
                        '至少一个图形的坐标或尺寸表达式必须引用parameters的参数名，不能所有表达式都是常数。'
                        'step_count按用户要求选择3至5步，后续分镜必须恰好使用这个步数。',material)
                    try:validate_motion_layout(layout)
                    except VisualSceneError as exc:
                        if not str(exc).startswith('所有对象坐标与尺寸都是常数'):raise
                        binding=bind_motion_parameters(client,layout,material,task_instruction)
                        drafts.append({'segment_index':index,'phase':'symbolic_binding','binding':binding})
                except (GenerationError,ValueError) as exc:
                    rejected_layout=layout.model_dump() if layout is not None else None
                    layout=None
                    last_error=str(exc); feedback='\n必须修正对象契约：'+last_error
                    drafts.append({'segment_index':index,'phase':'layout','error':last_error,'layout':rejected_layout})
                    if draft_output:draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
                    progress(f'修正图形对象：{last_error}',54+index*10//len(lesson.segments))
                    continue
            layout_data=layout.model_dump(include=LAYOUT_FIELDS)
            progress(f'规划操作与计算（{index+1}/{len(lesson.segments)}）：{segment.title}',55+index*10//len(lesson.segments))
            try:
                sequence=client.generate(sequence_schema(layout),sequence_instruction+
                    f'\n本场景恰好{getattr(layout,"step_count",3)}步，不得重复追加步骤。'
                    '\n用户的教学偏好：'+prompt+feedback,
                    material+'\n已确定的场景对象：'+json.dumps(layout_data,ensure_ascii=False))
                scene=VisualScenePlan.model_validate({**layout_data,**sequence.model_dump(include=SEQUENCE_FIELDS),
                    'evidence':segment.evidence,'narration_binding':'computed'})
            except (GenerationError,ValueError) as exc:
                last_error=str(exc); feedback='\n必须修正步骤契约：'+last_error
                drafts.append({'segment_index':index,'phase':'sequence','error':last_error})
                if draft_output:draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
                progress(f'修正操作步骤：{last_error}',54+index*10//len(lesson.segments))
                continue
            # The lesson's already checked citation is authoritative.
            scene.evidence = segment.evidence
            if not scene.parameters and scene.beats[0].parameters:
                # The first narrated state can explicitly declare initialization.
                # Promote those exact values, never invent missing later inputs.
                scene.parameters=dict(scene.beats[0].parameters)
            for obj in scene.objects:
                # A supplied function expression is a curve even when a small
                # model calls its straight-line graph a line. Preserve its math.
                if obj.kind=='line' and not coordinate_expressions(obj) and obj.expression:
                    obj.kind='curve'
            drafts.append({'segment_index':index,'scene':scene.model_dump()})
            if draft_output:
                draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
            try:
                validate_evidence(document, scene.evidence)
                scene.verification = verify_visual_scene(scene)
                if geometry_only and pedagogical_design:
                    from zhijiang.visual_geometry_checks import plan_geometry_constraints
                    progress(f'绑定实际几何关系（{index+1}/{len(lesson.segments)}）：{segment.title}',56)
                    bindings=plan_geometry_constraints(client,scene,
                        next(p.text for p in document.pages if p.page==scene.evidence.page),prompt)
                    drafts[-1]['geometry_bindings']=bindings
                    drafts[-1]['scene']=scene.model_dump(exclude={'verification'})
                    if draft_output:draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
                    scene.verification=verify_visual_scene(scene)
                review=client.generate(ReviewResult,
                    '检查通用教学分镜与给定来源的概念是否对应、口播和图形是否一致。'
                    '已由程序检查的计算及标明条件的原创数值是合法教学示例，不要求原文包含这些数字。'
                    '重点检查：声称移动的对象是否真的依赖被改变参数；不同对象是否混淆；'
                    '固定对象是否保持固定；有限步骤不能冒充严格极限或真实微观机制。'
                    '逐项核对口播中的数值与当前参数/表达式，不能批准错误斜率、遗漏要求的函数图像、或不匹配的对象颜色。'
                    '只审批当前片段，不要求该片段讲完其他知识点。若有问题，明确指出对象ID和操作。'
                    '\n用户的教学偏好：'+prompt,
                    json.dumps({'source_page':next(p.text for p in document.pages if p.page==segment.evidence.page),
                        'topic':segment.title,'citation':segment.evidence.model_dump(),
                        'scene':scene.model_dump(exclude={'verification'}),
                        'computed_steps':[{'parameters':s['parameters'],'calculations':s['calculations'],
                            'motion':s['motion']} for s in scene.verification['states']]},ensure_ascii=False))
                if not review.approved:
                    raise VisualSceneError('分镜教学检查未通过：'+'；'.join(review.issues[:3]))
                reviews.append({'segment_index':index,**review.model_dump(),**geometry_context})
                approved=True
                break
            except (VisualSceneError,GenerationError,ValueError) as exc:
                last_error=str(exc)
                feedback = "\n必须修正上一稿，不能照抄错误："+str(exc)
                excluded={'verification'}
                if str(exc).startswith('领域计算检查失败'):
                    # Don't feed the rejected invariant back as a JSON example.
                    # The error still states its exact computed contradiction;
                    # a newly generated check must pass the same strict verifier.
                    excluded.add('checks')
                previous_data=scene.model_dump(exclude=excluded)
                if str(exc).startswith(('口播数字未绑定','口播格式无效')):
                    for beat_data in previous_data['beats']:
                        beat_data.pop('narration',None)
                previous_draft='\n旧草稿数据：'+json.dumps(previous_data,ensure_ascii=False)
                # Numeric/scope corrections don't need to redraw good objects.
                missing_parameter_changes=(str(exc).startswith('分镜需要与讲解对应') and
                    all(before==after for before,after,_visible in states(scene)))
                if missing_parameter_changes:
                    feedback+='\n对象已有可变表达式，但所有步骤都保持初始参数。保留对象，在parameter_changes中真正修改已声明参数数值，不能只改show/hide。'
                elif not str(exc).startswith(('领域计算检查失败','分镜计算结果不正确','口播数字未绑定','口播格式无效')):
                    layout=None
                drafts[-1]['error']=str(exc)
                digest=hashlib.sha256(json.dumps(scene.model_dump(exclude={'verification'}),sort_keys=True).encode()).hexdigest()
                rejected_counts[digest]=rejected_counts.get(digest,0)+1
                if draft_output:
                    draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
                progress(f"修正通用分镜（{index+1}/{len(lesson.segments)}）：{exc}",54+index*10//len(lesson.segments))
                if rejected_counts[digest]>=3:
                    last_error='同一无效分镜累计返回三次，修正无进展：'+last_error
                    break
        if not approved:
            if not pedagogical_design or geometry_only:
                raise VisualSceneError("通用教学场景无法通过检查："+last_error+"。请调整教学要求或选择能力更强的模型。")
            # Failed geometry is a representation failure, not permission to
            # animate invented coordinates or abort every other course segment.
            progress(f'重新设计教学表达：{segment.title}',54+index*10//len(lesson.segments))
            design,report,errors=plan_teaching_representation(client,segment,document,prompt,force_diagram=True,
                pdf_path=pdf_path,
                diagnostic_output=draft_output.with_name(f'teaching-redesign-{index+1:02d}.json') if draft_output else None)
            page=next(p for p in document.pages if p.page==report.get('topic_scope',{}).get('page',segment.evidence.page))
            scene=compile_teaching_scene(design,segment,report,source_assets=source_assets,pdf_path=pdf_path,source_text=page.text)
            scene.verification=verify_visual_scene(scene)
            drafts.append({'segment_index':index,'teaching_design':design.model_dump(),'geometry_failure':last_error,'rejected_designs':errors})
            reviews.append({'segment_index':index,'representation':design.representation,**report})
            if draft_output:
                draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
        segment.visual_scene = scene
        segment.narration = " ".join(beat.narration for beat in scene.beats)
        save_planned_scene(cache_path,fingerprint,scene,reviews[-1])
    lesson.animation_report = {"renderer": "Manim scene graph", "scene_count": len(lesson.segments),
        "scene_type": "general", "domains": sorted({s.visual_scene.domain for s in lesson.segments}),
        "verification_scope": "按表达类型核对来源摘录、关系引用或几何与数值关系；领域事实和教学解释仍需复核",
        "coverage": "学科不限，使用通用图形与参数步骤；专门机制和复杂三维可扩展执行器与领域检查",
        "storyboard_reviews":reviews}
    lesson.animation_report['representations']=[s.visual_scene.diagram.representation if s.visual_scene.diagram else 'geometry' for s in lesson.segments]
    lesson.animation_report['geometry_required']=geometry_only
    lesson.animation_report['coverage']='按内容选择过程、关系、比较、原文图示或可计算几何；学科名称不限，复杂机制仍需专门执行器'
    lesson.animation_report['narration_binding']='computed numeric values; qualitative model prose still requires source review'
    attribution=general_source_attribution(document)
    if attribution:
        lesson.animation_report['source_attribution']=attribution


def save_planned_scene(path, fingerprint, scene, review):
    if path:
        path.write_text(json.dumps({'fingerprint':fingerprint,'scene':scene.model_dump(),
            'review':review,'scene_digest':scene_digest(scene)},ensure_ascii=False),encoding='utf-8')


def scene_digest(scene):
    # Pydantic defaults may initially contain ints in float fields. Normalize
    # exactly as a saved scene is read, so benign 2 -> 2.0 roundtrips don't
    # invalidate the review while edited objects/constraints still do.
    normalized=VisualScenePlan.model_validate(scene.model_dump())
    return hashlib.sha256(json.dumps(normalized.model_dump(exclude={'verification'}),sort_keys=True).encode()).hexdigest()


def load_planned_scene(path, fingerprint, document, segment):
    """Reuse completed planning, rechecking against the actual source and rules."""
    from zhijiang.teaching_design import validate_diagram,TeachingDesignError,TeachingSourceReview,validate_meaning_review
    try:
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved.get('fingerprint')!=fingerprint:return None
        review=saved['review']
        if review.get('semantic_review',review).get('approved') is not True:return None
        scene=VisualScenePlan.model_validate(saved['scene'])
        if not scene.diagram and saved.get('scene_digest')!=scene_digest(scene):return None
        if scene.evidence!=segment.evidence and not review.get('topic_scope'):return None
        validate_evidence(document,scene.evidence)
        for constraint in scene.geometry_constraints:
            validate_evidence(document,Evidence(page=scene.evidence.page,quote=constraint.source_quote,ocr=scene.evidence.ocr))
        if scene.diagram:
            if review.get('topic_scope'):
                from zhijiang.teaching_scope import validate_cached_scope
                if not validate_cached_scope(scene,review['topic_scope'],document,segment,review.get('protected_literals')):
                    return None
            from zhijiang.teaching_graph import design_digest,validate_source_propositions
            if review.get('reviewed_design_digest')!=design_digest(scene.diagram):
                return None
            if any(edge.binding=='semantic' for edge in scene.diagram.relations):
                validate_source_propositions(scene.diagram,review.get('source_propositions',[]))
            validate_meaning_review(TeachingSourceReview.model_validate(review['semantic_review']),scene.diagram)
            page=next(p for p in document.pages if p.page==scene.evidence.page)
            validate_diagram(scene.diagram,page.text)
            scene.domain_data['source_page_text']=page.text
        scene.verification=verify_visual_scene(scene)
        return scene,review
    except (OSError,ValueError,KeyError,GenerationError,TeachingDesignError):
        return None


def general_source_attribution(document):
    title=unicodedata.normalize('NFKC',document.pages[0].text).lower()
    if 'geometric definition of the derivative' in title and any('ocw.mit.edu' in p.text.lower() for p in document.pages):
        return {
            'title':'Geometric definition of the derivative','author':'MIT OpenCourseWare, 18.01SC',
            'url':'https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/resources/mit18_01scf10_ses1c/',
            'license':'CC BY-NC-SA 4.0','license_url':'https://ocw.mit.edu/pages/privacy-and-terms-of-use/'}
    return {}
