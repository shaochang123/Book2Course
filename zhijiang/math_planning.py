"""Plan and verify mathematical scenes; models never supply executable code."""
from __future__ import annotations

import importlib.util
import math
import re
import shutil

from pydantic import BaseModel, Field

from zhijiang.models import (Evidence, Lesson, LessonSegment, MathBeat, MathClaim,
                             MathParameters, MathSceneKind, MathScenePlan, Mode,
                             SourceDocument, VoiceMode)


class MathAnimationError(RuntimeError):
    pass


ACTIONS = {
    "linearity": ["vectors", "add_then_transform", "transform_then_add", "homogeneity", "translation_counterexample"],
    "basis": ["basis_vectors", "basis_images", "matrix_columns", "decompose", "transform_combination"],
    "plane": ["plane_start", "plane_transform", "area"],
    "projection": ["projection_start", "project", "eigen_parallel", "eigen_perpendicular", "change_basis"],
    "composition": ["composition_start", "rotate_then_stretch", "stretch_then_rotate", "compare_order"],
}
TITLES = {"linearity": "线性：两条计算路径为什么相同？", "basis": "矩阵的列：基向量的去向",
          "plane": "整个平面：坐标与面积一起变化", "projection": "投影：保留与消失的方向",
          "composition": "变换复合：顺序决定结果"}


def math_capabilities() -> dict:
    missing = [name for name in ("manim", "sympy") if importlib.util.find_spec(name) is None]
    missing += [name for name in ("latex", "dvisvgm") if not shutil.which(name)]
    return {"ready": not missing, "missing": missing, "topics": ["二维线性变换"],
            "renderer": "Manim Cairo", "reason": "缺少：" + "、".join(missing) if missing else ""}


def validate_parameters(p: MathParameters) -> None:
    if len(p.matrix) != 2 or any(len(row) != 2 for row in p.matrix):
        raise MathAnimationError("数学动画首轮仅支持 2×2 矩阵。")
    for vector in (p.vector, p.second_vector, p.shift, p.stretch):
        if len(vector) != 2:
            raise MathAnimationError("向量必须有两个坐标。")
    values = [*sum(p.matrix, []), *p.vector, *p.second_vector, *p.shift, *p.stretch,
              p.scalar, p.rotation_degrees, p.projection_degrees]
    if any(not math.isfinite(value) or abs(value) > 1000 for value in values):
        raise MathAnimationError("动画参数必须是有限的教学尺度数值（绝对值不超过 1000）。")
    if p.scalar == 0 or all(value == 0 for value in p.vector):
        raise MathAnimationError("演示向量和用于齐次性比较的倍数不能为零。")
    if all(value == 0 for value in p.shift):
        raise MathAnimationError("平移反例需要非零位移。")


def symbolic_facts(p: MathParameters) -> dict:
    import sympy as s
    validate_parameters(p)
    q = lambda value: s.Rational(str(value))
    A = s.Matrix([[q(value) for value in row] for row in p.matrix])
    v, w, shift = (s.Matrix([q(value) for value in vector])
                   for vector in (p.vector, p.second_vector, p.shift))
    theta = q(p.rotation_degrees) * s.pi / 180
    R = s.Matrix([[s.cos(theta), -s.sin(theta)], [s.sin(theta), s.cos(theta)]])
    S = s.diag(*[q(value) for value in p.stretch])
    angle = q(p.projection_degrees) * s.pi / 180
    u = s.Matrix([s.cos(angle), s.sin(angle)])
    perpendicular = s.Matrix([-s.sin(angle), s.cos(angle)])
    P = u * u.T
    Q = s.Matrix.hstack(u, perpendicular)
    return {"A": A, "v": v, "w": w, "shift": shift, "Av": A*v, "Aw": A*w,
            "sum": v+w, "A_sum": A*(v+w), "sum_images": A*v+A*w,
            "scaled_image": q(p.scalar)*(A*v), "image_scaled": A*(q(p.scalar)*v),
            "determinant": A.det(), "area": abs(A.det()), "e1_image": A[:, 0],
            "e2_image": A[:, 1], "P": s.simplify(P), "Pv": s.simplify(P*v),
            "P_squared": s.simplify(P*P), "parallel": u, "perpendicular": perpendicular,
            "parallel_image": s.simplify(P*u), "perpendicular_image": s.simplify(P*perpendicular),
            "diagonal_projection": s.simplify(Q.T*P*Q), "R": s.simplify(R), "S": S,
            "Rv": s.simplify(R*v), "Sv": S*v,
            "SR": s.simplify(S*R), "RS": s.simplify(R*S),
            "SRv": s.simplify(S*R*v), "RSv": s.simplify(R*S*v)}


def numeric_facts(p: MathParameters) -> dict[str, list[float]]:
    facts = symbolic_facts(p)
    return {key: [float(value) for value in (list(obj) if hasattr(obj, "rows") else [obj])]
            for key, obj in facts.items()}


def verify_scene(scene: MathScenePlan) -> dict:
    import sympy as s
    if [beat.action for beat in scene.beats] != ACTIONS[scene.kind]:
        raise MathAnimationError(f"{scene.kind} 的推理步骤缺失或顺序不正确。")
    facts = symbolic_facts(scene.parameters)
    numeric = numeric_facts(scene.parameters)
    checks = {"additivity": facts["A_sum"] == facts["sum_images"],
              "homogeneity": facts["image_scaled"] == facts["scaled_image"],
              "matrix_columns": facts["A"] == s.Matrix.hstack(facts["e1_image"], facts["e2_image"]),
              "projection_idempotence": facts["P_squared"] == facts["P"],
              "parallel_eigenvalue_1": s.simplify(facts["parallel_image"]-facts["parallel"]) == s.zeros(2, 1),
              "perpendicular_eigenvalue_0": facts["perpendicular_image"] == s.zeros(2, 1),
              "projection_in_own_basis": facts["diagonal_projection"] == s.diag(1, 0),
              "rotation_preserves_length": s.simplify(facts["R"].T*facts["R"]) == s.eye(2)}
    # Polygon area is computed independently by the shoelace formula.
    points = [facts["A"]*s.Matrix(point) for point in ((0, 0), (1, 0), (1, 1), (0, 1))]
    polygon_area = abs(sum(points[i][0]*points[(i+1)%4][1]-points[(i+1)%4][0]*points[i][1]
                           for i in range(4)))/2
    checks["area_shoelace_equals_abs_det"] = polygon_area == facts["area"]
    if scene.kind == "composition" and facts["SRv"] == facts["RSv"]:
        raise MathAnimationError("复合顺序示例的两个结果相同，请换用能显示顺序差异的参数。")
    if scene.kind == "plane" and facts["area"] == 0:
        raise MathAnimationError("面积伸缩主场景需要非奇异矩阵；降维在投影场景说明。")
    for claim in scene.claims:
        expected = numeric.get(claim.key)
        if expected is None or len(expected) != len(claim.values) or any(
                not math.isfinite(value) or not math.isclose(value, actual, abs_tol=1e-8, rel_tol=1e-8)
                for value, actual in zip(claim.values, expected)):
            raise MathAnimationError(f"数学计算声明错误：{claim.key}。")
    if not all(checks.values()):
        raise MathAnimationError("数学关系核验未通过。")
    if scene.narration_binding == "verified":
        phrases = verified_narration_phrases(scene)
        if any(beat.narration != "".join(phrases[beat.action]) for beat in scene.beats):
            raise MathAnimationError("数学口播与核验数据不一致，请重新生成分镜。")
        checks["narration_bound_to_computed_states"] = True
    return {"passed": True, "checks": checks, "computed": numeric,
            "scope": "代数、几何与绑定口播；教学表达和来源含义仍需人工核对"}


def verified_narration_phrases(scene: MathScenePlan) -> dict[str, list[str]]:
    """Finite teaching semantics: all spoken coordinates come from computed states.

    A correct claim array alone cannot certify free-form model prose. The model
    chooses parameters/questions and drafts beats; fact-bearing speech is bound
    to these parameterized explanations before synthesis. Phrases also provide
    audio cues for multi-operation beats.
    """
    f, p = numeric_facts(scene.parameters), scene.parameters
    def number(value):
        rounded = round(float(value), 4)
        if abs(rounded) < 0.00005:
            rounded = 0
        word = f"{rounded:g}"
        return "约"+word if abs(float(value)-rounded) > 1e-9 else word
    def vector(key):
        return f"横坐标{number(f[key][0])}、纵坐标{number(f[key][1])}"
    def matrix(key):
        a, b, c, d = f[key]
        return f"第一列为{number(a)}和{number(c)}，第二列为{number(b)}和{number(d)}"
    return {
        "vectors": [f"这是计算核验过的教学示例。绿色向量v的{vector('v')}，橙色向量w的{vector('w')}。",
                    "左右两幅图从相同输入开始。我们比较两条计算路径，来理解线性的含义。"],
        "add_then_transform": [f"先看左侧。把第二个向量接在第一个向量的末端，虚线构成平行四边形。蓝色对角线是向量和，{vector('sum')}。",
                               f"现在对这个和施加矩阵A。结果的{vector('A_sum')}，这就是先相加再变换。"],
        "transform_then_add": [f"再看右侧。先分别变换两个向量，绿色结果的{vector('Av')}，橙色结果的{vector('Aw')}。",
                               f"把这两个结果相加，蓝色向量的{vector('sum_images')}。它与左侧重合，所以A作用于向量和，等于两个像的和。"],
        "homogeneity": [f"再把原来的向量v乘以{number(p.scalar)}。左侧先改变输入倍数再变换，右侧先变换再改变倍数。",
                        f"两个结果都是{vector('scaled_image')}。这说明线性变换也保持数乘关系；加法和数乘两条规则缺一不可。"],
        "translation_counterexample": [f"现在看一个反例：在每个输入上加同一位移。原点被送到{vector('shift')}，已经离开原点。",
                                       "线性变换必须把零向量送到零向量，因此非零平移不是线性变换。保持原点只是必要条件，不能单凭这一点判定线性。"],
        "basis_vectors": ["这是教学示例。绿色的第一个标准基向量向右一个单位，橙色的第二个标准基向量向上一个单位。",
                          "任意向量的两个坐标，就是沿这两个基方向的线性组合系数。先追踪这两个基向量的去向。"],
        "basis_images": [f"对两个基向量施加同一个A。绿色基向量的像为{vector('e1_image')}，橙色基向量的像为{vector('e2_image')}。",
                         "颜色一直表示同一个基方向的身份。下面用这两个像构造矩阵。"],
        "matrix_columns": [f"把绿色像的两个坐标写进第一列，再把橙色像的两个坐标写进第二列。矩阵A的{matrix('A')}。",
                           "这里是列而不是行。列的顺序必须与输入基向量的顺序相同。"],
        "decompose": [f"先回到变换前的空间。蓝色向量v的{vector('v')}。它等于第一个基向量乘{number(p.vector[0])}，加上第二个基向量乘{number(p.vector[1])}。",
                      "图中沿两个基方向首尾相接的分量，正好合成原来的蓝色向量。此时还没有施加变换。"],
        "transform_combination": ["现在分别变换这两个分量。因为变换保持线性组合，组合系数保持不变，只把基向量替换成它们的像。",
                                  f"相加后得到Av，{vector('Av')}。所以矩阵乘向量，就是用输入坐标给矩阵的两列加权，再相加。"],
        "plane_start": [f"这是补充教学示例，面积结论由计算核验。矩阵A的{matrix('A')}。观察网格、橙色向量，以及面积为一的蓝色单位正方形。",
                        "它们共享同一坐标系；我们对每一个点使用同一矩阵规则。"],
        "plane_transform": [f"现在让网格、向量和正方形一起变化。向量从{vector('v')}移动到{vector('Av')}。",
                            "正方形的四个顶点也分别按A移动，形成一个平行四边形。网格展示整个平面的对应关系；中间帧只是从初态到终态的连续过渡。"],
        "area": [f"利用四个变换后顶点的坐标计算面积，得到{number(f['area'][0])}。独立计算行列式，得到{number(f['determinant'][0])}，它的绝对值与面积相同。",
                 "初始面积为一，因此这个值也是面积伸缩比。这是由矩阵决定的几何效果，不是任意的视觉拉伸。"],
        "projection_start": [f"这是教学示例。目标直线经过原点，与横轴夹角为{number(p.projection_degrees)}度。蓝色输入向量的{vector('v')}。",
                             "投影矩阵P把向量压到目标直线上；下面观察它沿什么路径移动。"],
        "project": ["从蓝色向量的端点向目标直线作垂线，橙色虚线就是投影路径。端点沿这条垂线移动，直到落在直线上。",
                    f"投影结果的{vector('Pv')}。已经位于直线上的结果再次投影不会改变，因此P乘P仍等于P。"],
        "eigen_parallel": ["绿色单位向量u沿着目标直线，本来就在直线上。投影后方向和长度都保持，所以P乘u等于u。",
                           "当非零向量变换后只是原向量的一个倍数时，它是特征向量。这里的倍数是一，所以这一方向的特征值是一。"],
        "eigen_perpendicular": ["橙色非零单位向量n垂直于目标直线。它沿法线缩到原点；半透明箭头保留原来的方向供比较。",
                                "投影后得到零向量，也就是零乘n，所以原来的非零向量n是特征向量，特征值是零。零向量本身不是特征向量。"],
        "change_basis": ["把平行方向u和垂直方向n依次作为新的基。第一个方向保持，第二个方向归零，因此新基下的投影矩阵是对角矩阵，对角线上依次是一和零。",
                         "原来的矩阵与这个对角矩阵描述同一个投影，只是使用了不同的坐标参照。这解释了换基公式。"],
        "composition_start": [f"这是教学示例。两侧从同一个向量开始，{vector('v')}。R表示旋转{number(p.rotation_degrees)}度，S把横坐标乘{number(p.stretch[0])}、纵坐标乘{number(p.stretch[1])}。",
                              "两侧使用完全相同的两种变换，只交换先后顺序。注意旋转过程中向量长度保持不变。"],
        "rotate_then_stretch": [f"先看左侧。先旋转，向量到达{vector('Rv')}；单位正方形跟着转动，向量长度保持。",
                                f"再施加S，得到{vector('SRv')}。公式是S乘R乘v，靠近v的R先作用。"],
        "stretch_then_rotate": [f"再看右侧。先施加S，得到{vector('Sv')}；正方形先随坐标伸缩。",
                                f"再旋转，得到{vector('RSv')}。这次公式是R乘S乘v，靠近v的S先作用。"],
        "compare_order": [f"左侧最终位置为{vector('SRv')}，右侧最终位置为{vector('RSv')}，两个结果不同。",
                          "所以矩阵乘法一般不能交换顺序。按列向量约定，最右边的矩阵先作用，左边的矩阵后作用。"],
    }


def bind_verified_narration(scene: MathScenePlan) -> dict:
    # Reject wrong claims before replacing prose; never silently accept bad math.
    verify_scene(scene)
    phrases = verified_narration_phrases(scene)
    originals = {beat.action: beat.narration for beat in scene.beats}
    for beat in scene.beats:
        beat.narration = "".join(phrases[beat.action])
    scene.narration_binding = "verified"
    scene.verification = verify_scene(scene)
    return {"method": "parameterized_verified_narration", "model_draft": originals,
            "reason": "自由口播与正确 claims 可能矛盾；数学断言按已计算状态绑定，保留模型草稿供审查。"}


def source_evidence(document: SourceDocument, kind: str) -> list[Evidence]:
    signatures = {
        "linearity": [r"a transformation\s+t\s+is linear", r"not a linear transformation", r"线性变换"],
        "basis": [r"(?:first|ﬁrst) column", r"linear combination of basis", r"基向量", r"矩阵.{0,8}列"],
        "plane": [r"given a matrix", r"transform a picture", r"矩阵.{0,8}变换"],
        "projection": [r"line at a\s+45", r"projects every vector", r"basis consists of eigenvectors", r"投影"],
        "composition": [r"product of two transformations", r"变换.{0,8}复合", r"复合.{0,8}变换"],
    }
    evidence: list[Evidence] = []
    for signature in signatures[kind]:
        for page in document.pages:
            text = re.sub(r"\s+", " ", page.text)
            match = re.search(signature, text, re.I)
            if match:
                start = max(text.rfind(". ", 0, match.start())+2, 0)
                if match.start()-start > 60:
                    start = match.start()
                quote = text[start:start+290].strip()
                item = Evidence(page=page.page, quote=quote, ocr=page.ocr)
                if item not in evidence:
                    evidence.append(item)
                break
    return evidence


def supports_math(document: SourceDocument) -> bool:
    text = " ".join(page.text for page in document.pages)
    if not re.search(r"linear transformations?|线性变换", text, re.I):
        return False
    if (re.search(r"\bR\s*3\b|three[- ]dimensional|3[- ]dimensional|三维", text, re.I)
            and not re.search(r"\bR\s*2\b|two[- ]dimensional|2[- ]dimensional|二维", text, re.I)):
        return False
    return sum(bool(source_evidence(document, kind)) for kind in ACTIONS) >= 3


def explicit_parameters(prompt: str) -> dict:
    """Preserve explicit numeric JSON examples even if a small model ignores them."""
    import json
    result = {}
    for label, field in (("A", "matrix"), ("v", "vector"), ("w", "second_vector"),
                         ("shift", "shift"), ("stretch", "stretch"), ("scalar", "scalar"),
                         ("rotation_degrees", "rotation_degrees"), ("projection_degrees", "projection_degrees")):
        matches = list(re.finditer(r"(?<![A-Za-z_])"+label+r"\s*=\s*", prompt))
        if not matches:
            continue
        try:
            value, _ = json.JSONDecoder().raw_decode(prompt[matches[-1].end():])
            result[field] = value
        except (ValueError, TypeError) as exc:
            raise MathAnimationError(f"{label} 参数有歧义，请使用数值 JSON（如 A=[[2,1],[0,1]]）。") from exc
    try:
        validate_parameters(MathParameters.model_validate(result))
    except ValueError as exc:
        raise MathAnimationError("教学参数必须是数值矩阵、二维向量和度数。") from exc
    return result


class MathCourseDraft(BaseModel):
    title: str = Field(min_length=4, max_length=80)
    objective: str = Field(min_length=8, max_length=200)
    parameters: MathParameters


class MathScriptDraft(BaseModel):
    question: str = Field(min_length=4, max_length=120)
    beats: list[MathBeat] = Field(min_length=3, max_length=5)


def plan_math_lesson(client, document: SourceDocument, prompt: str,
                     voice_mode: VoiceMode, progress=None) -> Lesson:
    import json
    from zhijiang.agents import validate_evidence
    if not supports_math(document):
        raise MathAnimationError("资料未提供可核对的二维线性变换主线，首轮数学动画暂不支持此内容。")
    overrides = explicit_parameters(prompt)
    sources = {kind: source_evidence(document, kind) for kind in ACTIONS}
    for references in sources.values():
        for reference in references:
            validate_evidence(document, reference)
    instruction = ("规划一章面向已懂坐标和向量的中文二维线性代数教学动画。"
                   "参数采用小整数或简单小数，生成原创教学示例；优先 matrix=[[2,1],[0,1]],vector=[1,2],"
                   "second_vector=[1,-1],shift=[1,0],scalar=2,rotation_degrees=45,projection_degrees=45,stretch=[2,1]。"
                   "如果用户指定矩阵或向量则使用用户参数。只支持二维；不要输出计算结果。用户要求：" + prompt)
    material = json.dumps({kind: [ref.model_dump() for ref in refs] for kind, refs in sources.items()}, ensure_ascii=False)
    draft = client.generate(MathCourseDraft, instruction, material)
    draft.parameters = MathParameters.model_validate(draft.parameters.model_dump() | overrides)
    validate_parameters(draft.parameters)
    facts = numeric_facts(draft.parameters)
    segments = []
    narration_bindings = {}
    for kind, actions in ACTIONS.items():
        if not sources[kind]:
            continue
        if progress:
            progress(f"规划数学分镜（{len(segments)+1}/{len(ACTIONS)}）：{TITLES[kind]}", 28+len(segments)*6)
        fact_keys = {"linearity": ["A", "v", "w", "Av", "Aw", "A_sum", "sum_images", "scaled_image", "shift"],
                     "basis": ["A", "v", "e1_image", "e2_image", "Av"],
                     "plane": ["A", "v", "Av", "determinant", "area", "e1_image", "e2_image"],
                     "projection": ["P", "v", "Pv", "parallel", "perpendicular", "diagonal_projection"],
                     "composition": ["v", "R", "S", "SRv", "RSv"]}[kind]
        scene_material = json.dumps({"kind": kind, "actions_in_order": actions,
            "parameters": draft.parameters.model_dump(), "verified_facts": {key: facts[key] for key in fact_keys},
            "sources": [ref.model_dump() for ref in sources[kind]]}, ensure_ascii=False)
        feedback = ""
        for attempt in range(2):
            script = client.generate(MathScriptDraft,
                "为这一数学场景写中文口播分镜。必须逐项使用 actions_in_order，顺序一致且一项对应一个 beat。"
                "每步用两三句说明画面中的对象、正在发生的操作以及原因；讲清坐标和公式的对应关系。"
                "第一步说明这是教学示例，最后一步总结。不要使用没有解释的术语。"
                "只规划对象、操作、原因，不做数值运算、不输出数值结果。具体坐标和公式由程序核验后填入。"
                "角度是度；不能把 45 度说成四十五弧度；列优先构成矩阵，不要把列说成行。"
                "投影中垂直方向归零，零向量不能称为特征向量；只有非零输入向量才是特征向量。"
                "composition 的 rotate_then_stretch 对应 SRv，stretch_then_rotate 对应 RSv。"
                "plane 的面积讨论是额外教学示例，不宣称引文原本讲了行列式。"
                "translation_counterexample 要通过非零平移导致 T(0)不等于0来解释。"
                "不要添加动画步骤或照搬原文。用户风格：" + prompt + feedback, scene_material)
            scene = MathScenePlan(kind=kind, question=script.question, parameters=draft.parameters,
                beats=script.beats, claims=[MathClaim(key=key, values=facts[key]) for key in fact_keys],
                evidence=sources[kind][0])
            try:
                narration_bindings[kind] = bind_verified_narration(scene)
                break
            except MathAnimationError as exc:
                feedback = "上次核验失败，请修正：" + str(exc)
        else:
            raise MathAnimationError(feedback)
        segments.append(LessonSegment(title=TITLES[kind], kind="process",
            narration=" ".join(beat.narration for beat in scene.beats),
            bullets=[scene.question, "对象变换与公式逐步对应", "教学示例 · 计算已核验"],
            evidence=scene.evidence, math_scene=scene))
    attribution = {}
    if ("linear transformations and their matrices" in document.pages[0].text.lower()
            and any("ocw.mit.edu" in page.text.lower() for page in document.pages)):
        attribution = {"title": "Linear transformations and their matrices", "author": "MIT OpenCourseWare, 18.06SC",
            "url": "https://ocw.mit.edu/courses/18-06sc-linear-algebra-fall-2011/resources/mit18_06scf11_ses3-6sum/",
            "license": "CC BY-NC-SA 4.0", "license_url": "https://ocw.mit.edu/pages/privacy-and-terms-of-use/"}
    return Lesson(title=draft.title, objective=draft.objective, segments=segments,
        mode=Mode.AI, voice_mode=voice_mode,
        notice="AI 生成：数学计算与页码引文已核验，教学解释和来源含义仍需人工复核。原创数值算例标为教学示例。",
        animation_report={"renderer": "Manim Cairo", "scene_count": len(segments),
            "explicit_parameters": overrides,
            "source_attribution": attribution,
            "narration_bindings": narration_bindings,
            "sources": {kind: [ref.model_dump() for ref in refs] for kind, refs in sources.items()},
            "coverage": "二维线性变换主线；三维与函数空间内容未制作数学动画。"})
