"""Subject-independent scene graph planning and restricted expression checks.

The model supplies data, never Python/SVG/TeX code. A subject name is descriptive,
not a routing whitelist. New domain checks can be registered by project code.
"""
from __future__ import annotations

import ast
import math
import re
import json
import unicodedata
from functools import lru_cache
from pydantic import BaseModel, Field, model_validator, create_model, ConfigDict

from zhijiang.agents import GenerationError, validate_evidence
from zhijiang.models import Lesson, LessonSegment, VisualScenePlan, VisualBeat, Mode, ReviewResult, Evidence, SceneObject, SceneCheck


class VisualSceneError(GenerationError):
    pass


class VisualCoursePlan(BaseModel):
    title: str = Field(min_length=2,max_length=80)
    objective: str = Field(min_length=8,max_length=240)
    point_ids: list[int] = Field(min_length=3)


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
    checks: list[SceneCheckDraft] = Field(default_factory=list,max_length=16)

    @classmethod
    def __get_pydantic_json_schema__(cls,core_schema,handler):
        schema=handler.resolve_ref_schema(handler(core_schema))
        for key in ['evidence','verification','narration_binding']:
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
    beat_model=create_model('VisualBeatDraft',__base__=VisualBeat,
        narration=(str,Field(min_length=12,max_length=100,pattern='^('+alternatives+'){12,100}$')))
    return create_model('VisualSequenceDraft',__base__=VisualSequenceDraft,
        beats=(list[beat_model],Field(min_length=getattr(layout,'step_count',3),
                                    max_length=getattr(layout,'step_count',3))))


def plan_general_lesson(client,bundle,document,prompt,voice_mode,progress,draft_output=None):
    """Use stable source IDs; mutable model-generated titles are not identifiers."""
    material='知识点：'+json.dumps([
        {'id':i+1,**point.model_dump()} for i,point in enumerate(bundle.points)],ensure_ascii=False)
    expected=set(range(1,len(bundle.points)+1))
    for attempt in range(3):
        outline=client.generate(VisualCoursePlan,
            '规划完整教学课程，标题和目标用中文。point_ids 必须使用每个输入id恰好一次，以教学顺序排列。'+
            ('上次遗漏或重复编号，请检查完整编号集合。' if attempt else '')+
            '\n用户的教学偏好：'+prompt+
            '\n必须覆盖的知识点编号：'+str(sorted(expected))+'；教学偏好中的步骤数指每个片段，不得删掉来源知识点。',material)
        if set(outline.point_ids)==expected and len(outline.point_ids)==len(expected): break
    else:
        # Coverage is a structural property with authoritative source IDs. Keep
        # valid proposed order and append omitted source points, never invent IDs.
        outline.point_ids=list(dict.fromkeys(i for i in outline.point_ids if i in expected))
        outline.point_ids.extend(i for i in sorted(expected) if i not in outline.point_ids)
    lesson=Lesson(title=outline.title,objective=outline.objective,mode=Mode.AI,voice_mode=voice_mode,
        notice='AI 生成：教学场景已检查几何、表达式与声明的数值关系；来源含义、领域事实和示意简化仍需复核。',
        segments=[LessonSegment(title=bundle.points[i-1].title,kind=bundle.points[i-1].kind,
            narration=bundle.points[i-1].explanation+' 请结合来源观察逐步演示过程。',
            bullets=[bundle.points[i-1].title],evidence=bundle.points[i-1].evidence) for i in outline.point_ids])
    plan_visual_scenes(client,lesson,document,prompt,progress,draft_output=draft_output)
    lesson.animation_report['source_point_ids']=outline.point_ids
    return lesson


PRIMITIVES = ("dot", "circle", "line", "arrow", "polygon", "curve", "label")
FUNCTIONS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt,
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
    radius = evaluate(obj.radius, parameters) if obj.kind in {"circle", "dot"} else 0
    return {"points": points, "radius": radius}


@lru_cache(maxsize=512)
def expression_tex(expression: str) -> str:
    """Generate TeX from an already restricted expression, never model TeX."""
    import sympy as sp
    functions={'sin':sp.sin,'cos':sp.cos,'tan':sp.tan,'sqrt':sp.sqrt,'exp':sp.exp,
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


def verify_visual_scene(scene: VisualScenePlan) -> dict:
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
            if any(char.isdigit() for char in prose) or worded_number or any(
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
        required = {"dot": 1, "circle": 1, "label": 1, "line": 2, "arrow": 2, "polygon": 3}.get(obj.kind, 0)
        coordinates=coordinate_expressions(obj)
        if (len(coordinates) < required or any(len(p) != 2 for p in coordinates)
                or (obj.kind in {'dot','circle','label','line','arrow'} and len(coordinates)!=required)):
            raise VisualSceneError(f"对象{obj.id}的{obj.kind}类型需要恰好{required}个二维坐标（polygon至少3个）；不要把两个点放进一个dot。")
        if obj.kind == "curve" and (not obj.expression or not all(math.isfinite(v) for v in obj.domain)
                                    or obj.domain[1] <= obj.domain[0]):
            raise VisualSceneError("曲线需要明确表达式和递增定义域。")
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
        for alpha in (0, 0.25, 0.5, 0.75, 1):
            params = {key: before[key]+alpha*(after[key]-before[key]) for key in before}
            check_domain_state(scene,params)
            geometry = {}
            for obj in scene.objects:
                g = object_geometry(obj, params)
                if any(abs(v)>1e4 for p in g['points'] for v in p) or not 0 <= g['radius'] <= 100:
                    raise VisualSceneError("图形尺寸或坐标超出可渲染范围。")
                geometry[obj.id] = g
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
        meaningful_motion |= any(samples[0][key] != sample[key] for sample in samples[1:] for key in visible)
        calculations = []
        for calculation in beat.calculations:
            value = evaluate(calculation.expression, after)
            if calculation.expected is not None and abs(value-calculation.expected) > 1e-6:
                raise VisualSceneError(f"分镜计算结果不正确：{calculation.label}，声明{calculation.expected}，计算{value}")
            calculations.append({"label": calculation.label, "expression": calculation.expression, "value": value})
        verified_states.append({"step": index+1, "parameters": after, "visible": sorted(visible),
                                "calculations": calculations, "start_geometry": samples[0], "end_geometry": samples[-1]})
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


def plan_visual_scenes(client, lesson: Lesson, document, prompt: str, progress, draft_output=None) -> None:
    instruction = (
        "为当前教学片段生成可执行的跨学科 visual_scene 数据。学科名称不限。"
        "不是淡入静态图：至少3步，以参数变化驱动同一对象的位置、半径、曲线或关系过程，解释为什么变化。"
        "只用 dot,circle,line,arrow,polygon,curve,label。dot/circle/label 用position=[横坐标表达式,纵坐标表达式]；"
        "line/arrow用start和end两个二维坐标；polygon用vertices二维坐标数组。"
        "curve.expression 用 x 表示横坐标，domain 是绘图区间。参数只用小写英文，x/pi/e 保留。"
        "表达式仅用四则、**、sin/cos/sqrt/exp/log/abs/min/max。不生成代码、SVG、LaTeX。"
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
        'position/start/end绝不允许自由变量x。直线的函数图像也用curve，例如expression="2*a*(x-a)+a**2"，domain=[0,3]，不填start/end。'
        '语法示例：固定点 {"id":"p","kind":"dot","position":["a","a**2"]}；'
        '随h移动的点 {"id":"q","kind":"dot","position":["a+h","(a+h)**2"]}；'
        '曲线 {"id":"f","kind":"curve","expression":"x**2","domain":[0,2]}；'
        '直线 {"id":"l","kind":"line","start":["0","0"],"end":["a","a**2"]}。'
    )
    instruction += '\n可用checks名称：'+', '.join(sorted(CHECKERS))+\
        '；已安装domain_validators名称：'+(', '.join(sorted(DOMAIN_VALIDATORS)) or '无，保持空数组')+'。'
    sequence_instruction = (
        '为已经确定的教学对象规划中文操作步骤，输出当前JSON契约。不要重新定义对象。'
        'beats为3至5步，每步narration解释当前对象、操作及原因，parameters只改变已声明参数。'
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
    drafts=[]; reviews=[]
    for index, segment in enumerate(lesson.segments):
        progress(f"规划通用教学场景（{index+1}/{len(lesson.segments)}）：{segment.title}", 54+index*10//len(lesson.segments))
        feedback = ""; previous_draft=""; last_error="";layout=None
        for _ in range(5):
            # Human preferences and computed repair instructions are authoritative
            # task instructions. Source excerpts and old model drafts stay data.
            # Putting all three inside source_data made small models ignore repairs.
            task_instruction=instruction+'\n用户的教学偏好：'+prompt+feedback
            material="片段："+segment.model_dump_json(exclude={'math_scene','visual_scene'})+previous_draft
            if layout is None:
                progress(f'规划图形对象（{index+1}/{len(lesson.segments)}）：{segment.title}',54+index*10//len(lesson.segments))
                layout=client.generate(VisualLayoutDraft,task_instruction+
                    '\n本轮只规划对象与初始参数，不输出口播步骤或计算检查。把用户要求的曲线、点、参照线全部画出；'
                    '对象表达式保留可变参数，固定对象不得依赖未来会变化的参数。明确每个对象的颜色。'
                    'step_count按用户要求选择3至5步，后续分镜必须恰好使用这个步数。',material)
            layout_data=layout.model_dump(include=LAYOUT_FIELDS)
            progress(f'规划操作与计算（{index+1}/{len(lesson.segments)}）：{segment.title}',55+index*10//len(lesson.segments))
            sequence=client.generate(sequence_schema(layout),sequence_instruction+
                f'\n本场景恰好{getattr(layout,"step_count",3)}步，不得重复追加步骤。'
                '\n用户的教学偏好：'+prompt+feedback,
                material+'\n已确定的场景对象：'+json.dumps(layout_data,ensure_ascii=False))
            scene=VisualScenePlan.model_validate({**layout_data,**sequence.model_dump(include=SEQUENCE_FIELDS),
                'evidence':segment.evidence,'narration_binding':'computed'})
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
                review=client.generate(ReviewResult,
                    '检查通用教学分镜与给定来源的概念是否对应、口播和图形是否一致。'
                    '已由程序检查的计算及标明条件的原创数值是合法教学示例，不要求原文包含这些数字。'
                    '重点检查：声称移动的对象是否真的依赖被改变参数；不同对象是否混淆；'
                    '固定对象是否保持固定；有限步骤不能冒充严格极限或真实微观机制。'
                    '逐项核对口播中的数值与当前参数/表达式，不能批准错误斜率、遗漏要求的函数图像、或不匹配的对象颜色。'
                    '只审批当前片段，不要求该片段讲完其他知识点。若有问题，明确指出对象ID和操作。'
                    '\n用户的教学偏好：'+prompt,
                    json.dumps({'scene':scene.model_dump(exclude={'verification'}),
                        'computed_steps':[{'parameters':s['parameters'],'calculations':s['calculations']} for s in scene.verification['states']]},ensure_ascii=False))
                if not review.approved:
                    raise VisualSceneError('分镜教学检查未通过：'+'；'.join(review.issues[:3]))
                reviews.append({'segment_index':index,**review.model_dump()})
                break
            except VisualSceneError as exc:
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
                if not str(exc).startswith(('领域计算检查失败','分镜计算结果不正确','口播数字未绑定','口播格式无效')):
                    layout=None
                drafts[-1]['error']=str(exc)
                if draft_output:
                    draft_output.write_text(json.dumps(drafts,ensure_ascii=False,indent=2),encoding='utf-8')
                progress(f"修正通用分镜（{index+1}/{len(lesson.segments)}）：{exc}",54+index*10//len(lesson.segments))
        else:
            raise VisualSceneError("通用教学场景无法通过检查："+last_error+"。请调整教学要求或选择能力更强的模型。")
        segment.visual_scene = scene
        segment.narration = " ".join(beat.narration for beat in scene.beats)
    lesson.animation_report = {"renderer": "Manim scene graph", "scene_count": len(lesson.segments),
        "scene_type": "general", "domains": sorted({s.visual_scene.domain for s in lesson.segments}),
        "verification_scope": "几何、表达式、已声明的数值关系；领域事实和教学解释仍需复核",
        "coverage": "学科不限，使用通用图形与参数步骤；专门机制和复杂三维可扩展执行器与领域检查",
        "storyboard_reviews":reviews}
    lesson.animation_report['narration_binding']='computed numeric values; qualitative model prose still requires source review'
    attribution=general_source_attribution(document)
    if attribution:
        lesson.animation_report['source_attribution']=attribution


def general_source_attribution(document):
    title=unicodedata.normalize('NFKC',document.pages[0].text).lower()
    if 'geometric definition of the derivative' in title and any('ocw.mit.edu' in p.text.lower() for p in document.pages):
        return {
            'title':'Geometric definition of the derivative','author':'MIT OpenCourseWare, 18.01SC',
            'url':'https://ocw.mit.edu/courses/18-01sc-single-variable-calculus-fall-2010/resources/mit18_01scf10_ses1c/',
            'license':'CC BY-NC-SA 4.0','license_url':'https://ocw.mit.edu/pages/privacy-and-terms-of-use/'}
    return {}
