"""Source-first lesson obligations, separate from the candidate's own design."""
import ast
import json
from typing import Literal,Union
from pydantic import Field, create_model,ValidationError
from zhijiang.math_construction import StrictMathModel
from zhijiang.visual_planning import VisualSceneError, object_geometry
from zhijiang.math_construction import resolve_parameters


class MathSubjectBindingError(VisualSceneError):
    def __init__(self,message,repair_target='construction'):
        super().__init__(message)
        self.repair_target=repair_target


class MathSourceSubject(StrictMathModel):
    name: str = Field(min_length=1,max_length=60)
    kind: Literal['point','segment','ray','line','polygon','circle','function','parametric']
    vertices: int | None = Field(default=None,ge=3,le=12)
    count: int = Field(default=1,ge=1,le=12)


def source_scope(client, mapping, material, *, images=None, reviewer=None, history=None):
    requirement=create_model('MathSourceRequirement',__base__=StrictMathModel,
        id=(int,Field(ge=1,le=12)),source_ids=(list[Literal[tuple(mapping)]],Field(min_length=1,max_length=4)),
        kind=(Literal['condition','claim','example','definition'],...),
        statement=(str,Field(min_length=8,max_length=240,pattern=r'[\s\S]*[\u4e00-\u9fff][\s\S]*')),
        subjects=(list[MathSourceSubject],Field(default_factory=list,max_length=6)))
    schema=create_model('MathSourceScope',__base__=StrictMathModel,
        requirements=(list[requirement],Field(min_length=1,max_length=12)))
    instruction=(
        '只依据教材原文，独立列出本选页数学课程必须涵盖的核心定义、必要条件、结论、已解核心算例。'
        '每项用中文说明，保留正负号、公式、基准整体、数值与限制；source_ids选择支持该条内容的原文摘录编号。'
        '不要重打、翻译或改写原文引文；程序按编号直接填入原文。跨段事实可选多个摘录，各自保留出处，不拼接成虚构句子。'
        'kind只取condition、claim、example、definition；编号不是PDF页码。区分条件、结论与算例；涉及不同符号或象限的已解算例不能只用正值例子替代。'
        '不要列背景历史、相邻无关练习或未作答题目；未作答题可说明问题，不能把选项或猜出的答案当事实。'
        '严格区分已解算例与概念插图：已给出计算、转换、推导结果，或原文明确展示已完成的带数量/对应标注的构造与分配方案，都列为example。'
        '已完成的图解示例不要求另有印出的算式；紧接着询问“为什么/解释思考”不意味着前面已经给出的图解方案是未作答题。'
        '用于说明定义的照片、装饰字形、格点绘画和未计算示意图，只需涵盖其所说明的概念，不要求复刻照片或形状。'
        '图形任务的定义和可用操作仍属于核心内容。不得把图形转录中的普通插图提升为必须重画的算例。'
        '不要添加原文没有陈述的独立命题；同一概念的定义及改述合并为一项，不逐词拆成重复要求。'
        'subjects记录本条数学结论或算例的核心几何/函数主语，只选实际必需的对象类型；不是画面设计。'
        '一个subject只含一种类型，count为该主语实际必需的对象数量；相互关系需要多个同类对象时明确数量。'
        '并列的不同类型分别记录subject（最多六项），不能将点、直线、线段、射线绑定在同一主语。'
        '复合图形或对象集合按来源必需的基本几何对象分别记录类型与数量；只使用Schema中的真实几何类型，不使用执行器内部的group类型。'
        'polygon填写vertices真实顶点数；不能用几个无关射线代替原页的多边形，不能用无关常数恒等式代替原函数。'
        '条件或纯代数定义没有明确图形主语时subjects=[]。辅助照片和装饰图形不列主语。'
        '不要设计任何场景或坐标，不接触候选稿。'
        'statement必须是中文完整说明，原文公式可在句内保留。编号从1开始且不重复，最多十二项。'
        '同一个数学结论的名称、一般性改述和公式合并为一项；符号名称并入定义，不占重复条目。'
        '合并不能遗漏必要条件或已解核心算例；各个不同数值的已解例子仍分别保留。')
    history=history if history is not None else []
    feedback=''
    for attempt in range(3):
        result=client.generate(schema,instruction+feedback,material,
            **({'images':images} if images else {}))
        record={'attempt':attempt+1,'scope':result.model_dump()};history.append(record)
        if reviewer is None:break
        check=create_model('MathScopeMeaningCheck',__base__=StrictMathModel,
            requirement_id=(Literal[tuple(r.id for r in result.requirements)],...),
            observation=(str,Field(min_length=8,max_length=300)),supported=(bool,...))
        review_schema=create_model('MathScopeMeaningReview',__base__=StrictMathModel,
            checks=(list[check],Field(min_length=len(result.requirements),max_length=len(result.requirements))),
            missing=(list[str],Field(default_factory=list,max_length=6)))
        review=reviewer.generate(review_schema,
            '在任何场景设计之前核对来源清单的含义，不接触候选动画。逐项比较原文与中文statement及主语。'
            '必须保留术语含义、数值、正负号、基准整体、必要条件、原文结论的强弱。'
            '核对subjects的类型和count是否确实对应来源主语，多个对象的关系不能写成只需要一个对象；并列不同类型不能被条数限制遗漏。'
            '翻译和命名错误、把概念插图当已解算例、把未作答题答案当事实均应supported=false。'
            '原文已明确给出的带数量和对应标注的完整图解方案也属于已解核心算例；不能因没有印出算式或随后要求解释理由而遗漏该方案。'
            '每个编号恰好核对一次，先填写实际原文含义与差异，再判supported。'
            '一个必要条件、公式或算例已在其他条目完整保留时，不要求每个相关条目重复；核对整份清单的联合覆盖。'
            'missing只列原文清楚陈述但清单实际遗漏的核心数学定义、必要条件、结论和已解算例，不能增补教材没有的证明。'
            '范围与前面的来源清单生成一致：不要列背景历史、人物或发现年代、相邻无关练习、未作答题目。'
            '核心数学结论的名称与符号可并入对应定义或结论，不能为了名称单独增加重复条目。'
            '必须保留核心数值、正负号、适用条件、函数定义域与来源已解例子；排除背景不等于删除数学内容。'
            '不提供坐标或替代教案；此处只核对来源含义，不批准图形或知识绝对正确。',
            material+'\n待核对清单：'+result.model_dump_json(),
            **({'images':images} if images and reviewer is client else {}))
        record['meaning_review']=review.model_dump()
        ids=[c.requirement_id for c in review.checks]
        errors=[c.observation for c in review.checks if not c.supported]+review.missing
        if len(set(ids))!=len(ids) or set(ids)!={r.id for r in result.requirements}:
            errors.append('来源含义检查编号缺失或重复。')
        if not errors:break
        if attempt==2:
            exc=VisualSceneError('来源清单含义三次修复仍未通过：'+'；'.join(errors))
            exc.source_scope_attempts=history
            raise exc
        feedback='\n上轮清单含义错误，须对照原文修复，保留其余事实与算例，不删除主题绕过核查：'+'；'.join(errors)+'\n被拒清单：'+result.model_dump_json()
    if len({r.id for r in result.requirements})!=len(result.requirements):
        raise VisualSceneError('来源覆盖清单编号重复。')
    grounded=[]
    for requirement in result.requirements:
        record=requirement.model_dump();ids=list(dict.fromkeys(record['source_ids']))
        excerpts=[{'source_id':index,'page':mapping[index]['page'],'quote':mapping[index]['quote']} for index in ids]
        record.update(source_ids=ids,source_id=ids[0],source_quote=excerpts[0]['quote'],
            source_page=excerpts[0]['page'],source_excerpts=excerpts,citation_method='selected_exact_source_excerpts')
        grounded.append(record)
    return grounded


def ground_requirements(requirements,mapping):
    """Locate literal text across same-page chunks, never across PDF pages.

    A model's chunk index is not evidence. Correct an index only when the
    literal quotation locates uniquely, retaining the original index in logs.
    """
    pages={}
    for index,source in mapping.items():pages.setdefault(source['page'],[]).append((index,source['quote']))
    grounded=[]
    for r in requirements:
        record=r.model_dump();q=''.join(r.source_quote.split())
        matches=[index for index,source in mapping.items() if q in ''.join(source['quote'].split())]
        repaired=None
        if r.source_id not in matches:
            page_matches=[]
            for page,chunks in pages.items():
                full=''.join(''.join(text.split()) for _,text in chunks)
                start=full.find(q)
                if start<0 or full.find(q,start+1)>=0:continue
                offset=0
                for index,text in chunks:
                    end=offset+len(''.join(text.split()))
                    if offset<=start<end:page_matches.append((page,index));break
                    offset=end
            if len(page_matches)!=1:
                raise VisualSceneError('来源覆盖清单引用无法在原页唯一定位。')
            page,index=page_matches[0]
            repaired={'kind':'literal_source_location','before':r.source_id,'after':index,'page':page}
            record['source_id']=index
        record['source_page']=mapping[record['source_id']]['page']
        if repaired:record['citation_repair']=repaired
        grounded.append(record)
    return grounded


def validate_subject_bindings(requirements, result, scene, program):
    """Bind source subjects to actual objects and their measured dependency graph.

    This is a structural guard, not a knowledge correctness guarantee. Polygon
    cycles may be represented by a polygon or connected finite edge objects.
    No textbook names or topic-specific coordinates are used.
    """
    from zhijiang.math_construction import Compiler
    compiled=Compiler(program);objects={o.id:o for o in scene.objects}
    definitions={o.id:o for o in program.constructions}
    dependencies={id:set(item.refs) for id,item in definitions.items()}
    for id,item in compiled.items.items():
        if item.get('type')=='group':dependencies[id]=set(item['members'])
    def closure(ids):
        seen=set(ids);pending=list(ids)
        while pending:
            for dep in dependencies.get(pending.pop(),set()):
                if dep not in seen:seen.add(dep);pending.append(dep)
        return seen
    for requirement in requirements:
        # Requirement IDs are not necessarily contiguous or sorted in input.
        check=next(c for c in result.checks if c.requirement_id==requirement['id'])
        subjects=requirement.get('subjects',[])
        if not check.supported:continue
        by_index={b.subject_index:b for b in check.bindings}
        if len(by_index)!=len(check.bindings) or set(by_index)!=set(range(1,len(subjects)+1)):
            raise MathSubjectBindingError('来源主语绑定缺失或重复：'+requirement['statement'],'behavior')
        for index,subject in enumerate(subjects,1):
            binding=by_index[index];ids=binding.objects;kind=subject['kind']
            if not ids:raise MathSubjectBindingError('来源主语没有实际对象：'+subject['name'])
            if len(set(ids))!=len(ids):raise MathSubjectBindingError('来源主语对象重复：'+subject['name'],'behavior')
            count=subject.get('count',1)
            valid=False
            if kind=='polygon' and count==1 and len(ids)>1:
                edges=[compiled.items[id] for id in ids]
                if all(e['type']=='line' and e.get('extent','segment')=='segment' for e in edges):
                    counts={}
                    for e in edges:
                        for p in (e['a'],e['b']):
                            key=tuple(map(str,p));counts[key]=counts.get(key,0)+1
                    count=subject.get('vertices')
                    valid=len(counts)==len(edges) and all(n==2 for n in counts.values()) and (count is None or count==len(edges))
                    # A single connected cycle, not two disjoint polygons.
                    adjacency={p:set() for p in counts}
                    for e in edges:
                        a,b=tuple(map(str,e['a'])),tuple(map(str,e['b']));adjacency[a].add(b);adjacency[b].add(a)
                    reached=set();pending=[next(iter(adjacency))] if adjacency else []
                    while pending:
                        p=pending.pop()
                        if p not in reached:reached.add(p);pending.extend(adjacency[p]-reached)
                    valid=valid and len(reached)==len(counts)
            elif len(ids)==count:
                def matches(obj):
                    valid=(obj['type']=='line' and obj.get('extent','segment')==kind) if kind in {'segment','ray','line'} else obj['type']==kind
                # A computed y=f(x) graph is also the parametric curve (t,f(t)).
                # Source classification must not dictate the renderer's formula
                # representation. Actual source equations and motion still need
                # full review; polygons/flowcharts cannot substitute for curves.
                    if kind=='parametric' and obj['type']=='function':valid=True
                    if kind=='polygon' and subject.get('vertices') is not None:
                        valid=valid and len(obj.get('vertices',[]))==subject['vertices']
                    return valid
                valid=all(matches(compiled.items[obj_id]) for obj_id in ids)
            if not valid:raise MathSubjectBindingError('来源主语类型与实际对象不符：'+subject['name']+' / '+str(ids))
            candidate_claims=[c for c in program.claims if not c.steps or set(c.steps)&set(check.steps)]
            measured=set()
            for claim in candidate_claims:
                for expression in (claim.lhs,claim.rhs):
                    measured.update(n.id for n in ast.walk(ast.parse(expression,mode='eval')) if isinstance(n,ast.Name) and n.id in compiled.items)
            if not all(closure([obj_id]).intersection(closure(measured)) for obj_id in ids):
                raise MathSubjectBindingError('来源主语未参与实际数学关系：'+subject['name']+'；保留正确对象，在核心claims中实际测量并关联该主语，不能用无关对象的恒等式替代。','behavior')
            visible=set()
            for step in check.steps:
                state=scene.verification['states'][step-1]
                for obj_id in ids:
                    members=compiled.items[obj_id].get('members',[obj_id])
                    # A transformed subject retains the original identity.
                    actors=scene.mathematical_model.get('actor_of',{})
                    if all(any(v==member or actors.get(v)==actors.get(member,member) for v in state['visible']) for member in members):
                        visible.add(obj_id)
            if visible!=set(ids):raise MathSubjectBindingError('来源主语在声明步骤未可见：'+subject['name'],'behavior')
            if kind in {'segment','ray','line'}:
                for obj_id in ids:
                    if not any(_extent_distinguishable(obj_id,step,scene,objects)
                               for step in check.steps):
                        raise MathSubjectBindingError('来源对象的线段/射线/直线形态被同色共线对象遮蔽：'+obj_id+
                            '；在对应步骤隐藏覆盖它的其他形态，或分开位置/颜色后重新核查。','behavior')


def _extent_distinguishable(obj_id,step,scene,objects):
    """Reject a same-colored carrier hiding an endpoint/extent distinction.

    Checks actual drawn endpoints, independent of subject names or textbooks.
    It is intentionally limited to complete coverage by another line extent;
    different colors, references, partial overlap and isolated steps remain
    available for legitimate teaching comparisons.
    """
    import math
    state=scene.verification['states'][step-1]
    obj=objects[obj_id]
    if obj_id not in state['visible']:
        actors=scene.mathematical_model.get('actor_of',{})
        identity=actors.get(obj_id,obj_id)
        return any(_extent_distinguishable(v,step,scene,objects) for v in state['visible']
                   if actors.get(v,v)==identity and objects[v].kind in {'line','arrow'})
    points=state['end_geometry'][obj_id]['points']
    if len(points)<2:return False
    a,b=points[0],points[-1]
    for other_id in state['visible']:
        other=objects[other_id]
        if (other_id==obj_id or other.kind not in {'line','arrow'} or other.reference or
            other.line_extent==obj.line_extent or other.color.lower()!=obj.color.lower()):continue
        carrier=state['end_geometry'][other_id]['points']
        if len(carrier)<2:continue
        c,d=carrier[0],carrier[-1];vx,vy=d[0]-c[0],d[1]-c[1]
        length2=vx*vx+vy*vy
        if length2<=1e-14:continue
        def covered(p):
            px,py=p[0]-c[0],p[1]-c[1]
            t=(px*vx+py*vy)/length2
            return abs(px*vy-py*vx)/math.sqrt(length2)<=1e-7 and -1e-7<=t<=1+1e-7
        if covered(a) and covered(b):return False
    return True


def _check_coverage_batch(client, requirements, scene, program, material, operator_reference='', *, history=None):
    from zhijiang.math_construction import Compiler
    math_ids=set(Compiler(program).items)
    known=math_ids|{o.id for o in scene.objects}
    binding=create_model('MathSubjectBinding',__base__=StrictMathModel,
        subject_index=(int,Field(ge=1,le=6)),
        objects=(list[Literal[tuple(sorted(math_ids))]],Field(min_length=1,max_length=12)))
    check=create_model('MathCoverageItem',__base__=StrictMathModel,
        requirement_id=(Literal[tuple(r['id'] for r in requirements)],...),
        observation=(str,Field(min_length=8,max_length=400)),
        steps=(list[Literal[tuple(range(1,len(scene.beats)+1))]],Field(default_factory=list,max_length=10)),
        objects=(list[Literal[tuple(sorted(known))]],Field(default_factory=list,max_length=24)),
        supported=(bool,...),
        bindings=(list[binding],Field(max_length=6)))
    schema=create_model('MathCoverageReview',__base__=StrictMathModel,
        checks=(list[check],Field(min_length=len(requirements),max_length=len(requirements))),
        repair_target=(Literal['construction','behavior'],'behavior'))
    # Exact curve endpoints expose wrong joins even when an invariant angle sum
    # is true. These are actual rendered coordinates, not model assertions.
    geometry=[]
    for step_index,state in enumerate(scene.verification['states'],1):
        values=resolve_parameters(scene,state['parameters'])
        snapshot={}
        for obj in scene.objects:
            g=object_geometry(obj,values);points=g.get('points',[])
            snapshot[obj.id]={'visible':obj.id in state['visible'],
                'endpoints':([points[0],points[-1]] if points else [])}
        geometry.append({'step':step_index,'objects':snapshot})
    instruction=(
        '执行器接口（用于理解参数，不是教材事实）：'+operator_reference+'\n'
        '逐项审核本批独立来源清单，不能只重复候选稿自称已覆盖的内容。先填写实际观察，再判supported。'
        '本批之外的要求由其他批次检查，不添加额外编号。observation用一两句写关键依据或缺漏，避免重述整个教案。'
        '本流程将按checks.steps把每条已核对statement逐字填入来源说明卡和配音，定义与条件在第一步运动前说明。'
        '审核来源含义、自由口播是否矛盾及实际演示覆盖；说明卡不算几何证明，不能用存在引文或说明卡来代替算例取值或核心运动。'
        '每个要求的已解核心算例须在实际对象或operations取值中出现；写在引文或不参与演示的元数据不算。'
        '概念插图允许用正确的等价数学示意说明同一概念；照片、装饰字形、未计算示意图不要求逐一复刻。'
        '正负号、象限、展开中心、分数基准整体不能偷换或遗漏。'
        '对对齐、拼接、重合结论，核对实际曲线端点坐标及终点claims；仅角度和或面积守恒不能证明拼接正确。'
        '弧有方向，必须核对首尾方向与共同中心，不能把旋转角近似猜值当已验证。'
        '每条supported=true的要求必须为其subjects逐项提供bindings：subject_index从1开始，objects为实际对象ID。'
        '每个主语按count绑定恰好该数量的同类型、不同ID对象（单个多边形也可绑定其闭合有限边环）；不得混合不同对象类型。'
        '没有来源主语时bindings=[]。主语须真实存在并参与核心claims，不能用无关或未参与测量的占位图形冒充。'
        '每个编号恰好检查一次；steps从1开始，第一步是1，objects严格选择Schema中的实际对象或分割组。缺少图形/控制量要求construction修复；'
        '仅遗漏口播、操作或测量则behavior修复。不要输出替代教案或自行补造教材事实。')
    candidate_material=(material+'\n独立来源清单：'+json.dumps(requirements,ensure_ascii=False)+
        '\n实际候选及逐步渲染几何：'+json.dumps({'program':program.model_dump(),
            'geometry':geometry,'claims':scene.mathematical_model['claims']},ensure_ascii=False))
    history=[] if history is None else history
    feedback=''
    for attempt in range(3):
        try:
            result=client.generate(schema,instruction+feedback,candidate_material)
        except Exception as exc:
            history.append({'requirement_ids':[r['id'] for r in requirements],
                'attempt':attempt+1,'error':f'{type(exc).__name__}: {exc}'})
            exc.binding_attempts=history
            raise
        record={'requirement_ids':[r['id'] for r in requirements],
            'attempt':attempt+1,'review':result.model_dump()};history.append(record)
        try:
            ids=[c.requirement_id for c in result.checks]
            if set(ids)!={r['id'] for r in requirements} or len(set(ids))!=len(ids):
                raise VisualSceneError('来源覆盖复核必须逐项覆盖且不重复。')
            for c in result.checks:
                if any(i<1 or i>len(scene.beats) for i in c.steps) or set(c.objects)-known:
                    raise VisualSceneError('来源覆盖复核引用不存在的步骤或对象。')
            validate_subject_bindings(requirements,result,scene,program)
            record['passed']=True
            return result
        except VisualSceneError as exc:
            record['error']=str(exc)
            if isinstance(exc,MathSubjectBindingError) and any(term in str(exc) for term in
                    ['绑定缺失或重复','类型与实际对象不符','来源主语对象重复']):
                try:
                    repairs=repair_subject_selection(client,requirements,result,scene,program,candidate_material)
                    validate_subject_bindings(requirements,result,scene,program)
                    record['selection_repairs']=repairs
                    record['selection_repaired_review']=result.model_dump();record['passed']=True
                    return result
                except (VisualSceneError,ValidationError) as repair_error:
                    record['selection_repair_error']=str(repair_error)
                except Exception as repair_error:
                    from zhijiang.agents import ModelContractError
                    if not isinstance(repair_error,ModelContractError): raise
                    record['selection_repair_error']=str(repair_error)
            if attempt==2:
                exc.binding_attempts=history
                raise
            feedback='\n复核格式/绑定修复，候选对象不变：'+str(exc)+(
                '。请重新核对原候选，修正对应编号、步骤和主语绑定。polygon绑定一个实际多边形，'
                '或全部闭合有限边的ID；仅点列表不算已画出的多边形。'
                '主语必须参与核心测量且在步骤可见；缺少对应对象或真实关系时必须supported=false，'
                '说明具体缺漏，不能选择无关对象来绕过检查。没有主语也要填写bindings=[]。'
                '不要改写候选对象或补造步骤。被拒复核：')+result.model_dump_json()


def check_coverage(client, requirements, scene, program, material, operator_reference=''):
    """Bound each review's response size, preserving every source obligation.

    All batches inspect the same complete candidate and original source. No
    requirement is removed on failure; structural bindings remain mandatory.
    """
    history=[]
    scene.mathematical_model['coverage_binding_attempts']=history
    checks=[];targets=[]
    for start in range(0,len(requirements),2):
        result=_check_coverage_batch(client,requirements[start:start+2],scene,program,
            material,operator_reference,history=history)
        checks.extend(result.checks)
        if any(not c.supported for c in result.checks):targets.append(result.repair_target)
    if not checks:raise VisualSceneError('来源覆盖清单不能为空。')
    # Each batch has its own enum of requirement IDs. The aggregate uses a
    # shared broad item model, retaining original validated objects verbatim.
    binding=create_model('MathCoverageAggregateBinding',__base__=StrictMathModel,
        subject_index=(int,Field(ge=1,le=6)),
        objects=(list[str],Field(min_length=1,max_length=12)))
    aggregate=create_model('MathCoverageAggregateItem',__base__=StrictMathModel,
        requirement_id=(int,...),observation=(str,Field(min_length=8,max_length=400)),
        steps=(list[int],Field(max_length=10)),objects=(list[str],Field(max_length=24)),
        supported=(bool,...),bindings=(list[binding],Field(max_length=6)))
    schema=create_model('MathCoverageReviewResult',__base__=StrictMathModel,
        checks=(list[aggregate],Field(min_length=len(requirements),max_length=len(requirements))),
        repair_target=(Literal['construction','behavior'],'behavior'))
    result=schema.model_validate({'checks':[c.model_dump() for c in checks],
        'repair_target':'construction' if 'construction' in targets else 'behavior'})
    if {c.requirement_id for c in result.checks}!={r['id'] for r in requirements}:
        raise VisualSceneError('来源覆盖汇总必须保留所有编号。')
    validate_subject_bindings(requirements,result,scene,program)
    return result


def repair_subject_selection(client,requirements,result,scene,program,material):
    """Repair only ID selections using exact source indexes and tool types.

    A fixed tuple preserves every subject. Unsupported items, steps, source,
    geometry and mathematical claims are never changed by this operation.
    """
    from zhijiang.math_construction import Compiler
    inventory=Compiler(program).items
    repairs=[]
    for requirement in requirements:
        check=next(c for c in result.checks if c.requirement_id==requirement['id'])
        if not check.supported or not requirement.get('subjects'): continue
        try:
            validate_subject_bindings([requirement],result,scene,program)
            continue
        except MathSubjectBindingError as exc:
            if not any(term in str(exc) for term in ['绑定缺失或重复','类型与实际对象不符','来源主语对象重复']): raise
        models=[]
        for index,subject in enumerate(requirement['subjects'],1):
            kind=subject['kind'];count=subject.get('count',1)
            if kind in {'segment','ray','line'}:
                candidates=[name for name,item in inventory.items() if item['type']=='line' and item.get('extent','segment')==kind]
            else:
                candidates=[name for name,item in inventory.items() if item['type']==kind or kind=='parametric' and item['type']=='function']
            if kind=='polygon' and subject.get('vertices'):
                candidates=[name for name in candidates if len(inventory[name]['vertices'])==subject['vertices']]
            variants=[]
            if candidates and len(candidates)>=count:
                variants.append(create_model(f'Subject{index}ObjectSelection',__base__=StrictMathModel,
                    subject_index=(Literal[index],...),
                    objects=(list[Literal[tuple(candidates)]],Field(min_length=count,max_length=count))))
            if kind=='polygon' and count==1:
                edges=[name for name,item in inventory.items() if item['type']=='line' and item.get('extent','segment')=='segment']
                vertices=subject.get('vertices')
                if len(edges)>=(vertices or 3):
                    variants.append(create_model(f'Subject{index}EdgeCycleSelection',__base__=StrictMathModel,
                        subject_index=(Literal[index],...),
                        objects=(list[Literal[tuple(edges)]],Field(min_length=vertices or 3,max_length=vertices or 12))))
            if not variants: raise MathSubjectBindingError('来源主语没有足够的实际同类型对象：'+subject['name'])
            models.append(variants[0] if len(variants)==1 else Union[tuple(variants)])
        schema=create_model('MathExactSubjectSelection',__base__=StrictMathModel,
            bindings=(tuple[tuple(models)],...))
        selected=client.generate(schema,
            '只修复当前来源主语的对象选择。按固定顺序逐一填写全部subject_index，编号不能缺失或重复。'
            '对象类型与数量由Schema限定，多边形也可选择完整闭合有限边环。'
            '不修改原来源、对象、步骤、测量或批准判断；仅根据真实依赖与原要求选择ID。'
            '不能用点列表冒充多边形，不选择无关对象来凑数量。',
            material+'\n本次仅修复的来源主语：'+json.dumps(requirement,ensure_ascii=False)+
            '\n原覆盖复核：'+check.model_dump_json())
        repairs.append({'requirement_id':requirement['id'],'before':[b.model_dump() for b in check.bindings],
            'after':selected.model_dump()['bindings']})
        check.bindings=list(selected.bindings)
    return repairs
