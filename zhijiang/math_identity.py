"""Source object identities and spatial relations, independent of scene design.

The source graph contains no coordinates or authored storyboard. The model
binds its entities to computed objects; the program checks spatial predicates
and assigns consistent colours to source categories and transformed copies.
This supplements mathematical claims, rather than proving source correctness.
"""
import json
import math
from typing import Literal

from pydantic import Field, create_model
from zhijiang.math_construction import StrictMathModel
from zhijiang.math_coverage import MathSubjectBindingError
from zhijiang.visual_planning import VisualSceneError


class SourceEntity(StrictMathModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,23}$')
    name: str = Field(min_length=1, max_length=24, pattern=r'[\s\S]*[\u4e00-\u9fff][\s\S]*')
    kind: Literal['point', 'segment', 'ray', 'line', 'polygon', 'circle', 'category']


def read_identity_graph(client, reviewer, mapping, material, images=None, history=None):
    relation = create_model('SourceIdentityRelation', __base__=StrictMathModel,
        first=(str, ...), second=(str, ...),
        predicate=(Literal['part_of', 'member_of', 'left_of', 'right_of', 'above', 'below'], ...),
        source_ids=(list[Literal[tuple(mapping)]], Field(min_length=1, max_length=4)),
        statement=(str, Field(min_length=8, max_length=160)))
    schema = create_model('SourceObjectIdentityGraph', __base__=StrictMathModel,
        entities=(list[SourceEntity], Field(default_factory=list, max_length=24)),
        relations=(list[relation], Field(default_factory=list, max_length=24)))
    feedback = ''
    history = history if history is not None else []
    for attempt in range(3):
        draft = client.generate(schema,
            '独立读取来源已完成的数学图解示例，提取对象身份与明确空间/归属关系。'
            '此时没有候选场景，禁止设计坐标、动作或新例子。'
            '只记录理解已解图例必需的明确关系，不记录照片、装饰图、未作答练习或一般常识。'
            '没有这样的明确关系时entities=[]、relations=[]，不是遗漏数学公式。'
            '每个几何实体是单个来源对象，name保留其所属整体、位置、编号/符号及身份；别名合并。'
            'category为领取者、对应编号、类别等非几何身份。member_of表示几何实体属于该身份类别；'
            '不能把编号当面积或把整体序号当领取者编号。'
            'part_of只用于有限多边形部分属于有限多边形整体；left_of/right_of/above/below表示同一原图明确标出的相对位置。'
            '用这些关系完整保留已经给出的分组/归属，不能只保留总面积。'
            'first、second严格选entities中的id；每条statement中文说明原图实际对应关系，source_ids保留依据。'
            '不要为计算公式强加空间关系。' + feedback, material,
            **({'images': images} if images else {}))
        record = {'attempt': attempt + 1, 'graph': draft.model_dump()}
        history.append(record)
        entities = {e.id: e for e in draft.entities}
        errors = []
        if len(entities) != len(draft.entities): errors.append('来源对象编号重复。')
        for r in draft.relations:
            if r.first not in entities or r.second not in entities or r.first == r.second:
                errors.append('来源关系必须绑定不同的已声明实体。')
            elif r.predicate == 'member_of' and (entities[r.first].kind == 'category' or entities[r.second].kind != 'category'):
                errors.append('归属关系必须由几何部分指向非几何身份类别。')
            elif r.predicate != 'member_of' and any(entities[n].kind == 'category' for n in (r.first, r.second)):
                errors.append('空间关系不能绑定非几何身份类别。')
        if not errors and draft.relations:
            review_schema = create_model('SourceIdentityMeaningReview', __base__=StrictMathModel,
                observation=(str, Field(min_length=12, max_length=600)),
                issues=(list[str], Field(default_factory=list, max_length=8)))
            review = reviewer.generate(review_schema,
                '只核对原文对象身份关系图，不接触任何候选场景。核对每个编号的含义、'
                '部分与整体、领取者与整体序号的区别、明确位置及全部给出的分配归属。'
                '关系图只能包含已完成图解明确的关系，不能补猜练习答案或常识。'
                '没有错误才issues=[]；指出实际缺漏/误读，不提供坐标或分镜。',
                material + '\n关系图：' + draft.model_dump_json(),
                **({'images': images} if images and reviewer is client else {}))
            record['meaning_review'] = review.model_dump()
            errors += review.issues
        if not errors: return draft.model_dump()
        record['errors'] = errors
        feedback = '\n修复来源误读，保留其余关系：' + '；'.join(errors) + '\n被拒图：' + draft.model_dump_json()
    raise VisualSceneError('来源对象身份三次核查仍未通过：' + '；'.join(errors))


def _center(points):
    return [sum(p[i] for p in points) / len(points) for i in (0, 1)]


def _inside(point, polygon):
    """Boundary-inclusive ray casting for finite simple polygons."""
    x, y = point; inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        cross = (x-a[0])*(b[1]-a[1])-(y-a[1])*(b[0]-a[0])
        if abs(cross) <= 1e-7 and min(a[0],b[0])-1e-7 <= x <= max(a[0],b[0])+1e-7 and min(a[1],b[1])-1e-7 <= y <= max(a[1],b[1])+1e-7:
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]: inside = not inside
    return inside


def validate_identity_bindings(graph, bindings, scene, program):
    from zhijiang.math_construction import Compiler
    compiled = Compiler(program)
    by_id = {b.entity_id: b for b in bindings}
    nodes = {e['id']: e for e in graph['entities'] if e['kind'] != 'category'}
    if len(by_id) != len(bindings) or set(by_id) != set(nodes):
        raise MathSubjectBindingError('来源身份绑定必须恰好覆盖全部几何实体。', 'behavior')
    if len({b.object_id for b in bindings}) != len(bindings):
        raise MathSubjectBindingError('不同来源实体不能绑定同一几何对象。', 'behavior')
    for node, binding in by_id.items():
        item = compiled.items[binding.object_id]; kind = nodes[node]['kind']
        match = (item['type']=='line' and item.get('extent','segment')==kind) if kind in {'line','ray','segment'} else item['type']==kind
        if not match: raise MathSubjectBindingError('来源身份对象类型不符：'+nodes[node]['name'], 'construction')
    for relation in graph['relations']:
        if relation['predicate'] == 'member_of': continue
        a,b = by_id[relation['first']],by_id[relation['second']]
        if a.step != b.step: raise MathSubjectBindingError('同一来源空间关系须绑定同一步骤。', 'behavior')
        state = scene.verification['states'][a.step-1]
        pa,pb = (state['end_geometry'][v.object_id]['points'] for v in (a,b))
        if not pa or not pb: raise MathSubjectBindingError('来源关系缺少实际几何。', 'construction')
        ca,cb = _center(pa),_center(pb); predicate = relation['predicate']
        checks = {'left_of':ca[0]<cb[0]-1e-7,'right_of':ca[0]>cb[0]+1e-7,
                  'above':ca[1]>cb[1]+1e-7,'below':ca[1]<cb[1]-1e-7}
        valid = all(_inside(p,pb) for p in pa) if predicate=='part_of' and compiled.items[b.object_id]['type']=='polygon' else checks.get(predicate,False)
        if not valid:
            raise MathSubjectBindingError('实际几何不满足来源身份关系：'+relation['statement']+'；核对对象对应及步骤，不可仅以面积相等替代。', 'construction')


def bind_identity_graph(client, graph, scene, program, source, history=None):
    """Select actual IDs; failed bindings never receive source category colours."""
    if not graph['relations']: return
    from zhijiang.math_construction import Compiler
    compiler = Compiler(program)
    nodes = [e for e in graph['entities'] if e['kind']!='category']
    item = create_model('SourceIdentityBinding', __base__=StrictMathModel,
        entity_id=(Literal[tuple(e['id'] for e in nodes)], ...),
        object_id=(Literal[tuple(compiler.items)], ...),
        step=(int, Field(ge=1, le=len(scene.beats))))
    schema = create_model('SourceIdentityBindings', __base__=StrictMathModel,
        bindings=(list[item], Field(min_length=len(nodes), max_length=len(nodes))))
    geometry = [{'step':state['step'],'geometry':{name:g for name,g in state['end_geometry'].items() if name in compiler.items}}
                for state in scene.verification['states']]
    feedback='';history=history if history is not None else []
    for attempt in range(3):
        result=client.generate(schema,
            '将独立来源对象身份绑定到候选真实对象，每个几何实体恰好一次，不绑定类别。'
            '按所属整体、位置、编号/符号辨认，不要因为面积相同就随意配对。'
            '步骤从一开始，空间关系两端须在同一步且实际坐标成立；可以绑定未显示的原始依赖对象，显示副本仍保留身份。'
            '不能改来源、对象或坐标。'+feedback,
            source+'\n来源身份图：'+json.dumps(graph,ensure_ascii=False)+
            '\n实际程序：'+program.model_dump_json()+'\n逐步计算几何：'+json.dumps(geometry,ensure_ascii=False))
        record={'attempt':attempt+1,'bindings':result.model_dump()};history.append(record)
        try:
            try:
                validate_identity_bindings(graph,result.bindings,scene,program)
            except MathSubjectBindingError as exc:
                repaired=repair_spatial_identity_permutation(graph,result.bindings,scene,program)
                if repaired is None: raise
                record['spatial_identity_repair']={'kind':'unique_source_spatial_permutation',
                    'error':str(exc),'before':result.model_dump(),
                    'after':{'bindings':[b.model_dump() for b in repaired]}}
                result=schema.model_validate({'bindings':[b.model_dump() for b in repaired]})
                validate_identity_bindings(graph,result.bindings,scene,program)
            apply_identity_colours(graph,result.bindings,scene,program)
            scene.mathematical_model['source_identity_graph']=graph
            scene.mathematical_model['source_identity_bindings']=result.model_dump()
            record['passed']=True
            return
        except MathSubjectBindingError as exc:
            record['error']=str(exc)
            if attempt==2: raise
            feedback='\n绑定失败，重新核对身份与实际几何：'+str(exc)+'\n被拒绑定：'+result.model_dump_json()


def apply_identity_colours(graph, bindings, scene, program=None):
    colours=['#6DE2C0','#FFA458','#C79BFF','#78BAFF','#FF8097','#E8DC76']
    categories=[e for e in graph['entities'] if e['kind']=='category']
    if len(categories)>len(colours): raise MathSubjectBindingError('同屏身份类别过多，请拆分说明。', 'construction')
    by_id={b.entity_id:b.object_id for b in bindings};actors=scene.mathematical_model['actor_of']
    names={e['id']:e['name'] for e in graph['entities']}
    roles=scene.mathematical_model['roles']
    for entity,obj_id in by_id.items():
        root=actors.get(obj_id,obj_id)
        for obj in scene.objects:
            if actors.get(obj.id,obj.id)==root and obj.kind!='label':
                roles[obj.id]=('参照·' if obj.reference else '')+names[entity]
                if program is not None:program.roles[obj.id]=names[entity]
    groups=[];assigned={}
    for category,colour in zip(categories,colours):
        members=[by_id[r['first']] for r in graph['relations'] if r['predicate']=='member_of' and r['second']==category['id']]
        if not members: continue
        roots={actors.get(v,v) for v in members}
        for root in roots:
            if root in assigned and assigned[root]!=colour: raise MathSubjectBindingError('同一部分被绑定给不同来源身份。', 'construction')
            assigned[root]=colour
        groups.append({'name':category['name'],'colour':colour,'objects':members})
    for obj in scene.objects:
        root=actors.get(obj.id,obj.id)
        if root in assigned: obj.color=assigned[root]
    if program is not None:
        program.constructions=[o.model_copy(update={'color':assigned[actors.get(o.id,o.id)]})
            if actors.get(o.id,o.id) in assigned else o for o in program.constructions]
        scene.mathematical_model['program']=program.model_dump()
    scene.mathematical_model['identity_colour_groups']=groups


def repair_spatial_identity_permutation(graph, bindings, scene, program):
    """Solve a uniquely constrained sibling permutation; never invent objects.

    Parents, steps and the model's candidate object set stay fixed. All source
    relations must hold. Ambiguous or excessive searches stay rejected. This
    corrects identity selection only; it never changes geometry or claims.
    """
    import itertools
    parents={r['first']:r['second'] for r in graph['relations'] if r['predicate']=='part_of'}
    kinds={e['id']:e['kind'] for e in graph['entities']}
    by_id={b.entity_id:b for b in bindings}
    if len(by_id)!=len(bindings): return None
    groups={}
    for name,parent in parents.items():
        if name not in by_id: return None
        b=by_id[name]
        groups.setdefault((parent,kinds[name],b.step),[]).append(name)
    groups=[names for names in groups.values() if len(names)>1]
    count=math.prod(math.factorial(len(names)) for names in groups)
    if not groups or count>4096: return None
    choices=[list(itertools.permutations([by_id[n].object_id for n in names])) for names in groups]
    solution=None
    for combination in itertools.product(*choices):
        candidates=dict(by_id)
        for names,objects in zip(groups,combination):
            for name,obj in zip(names,objects):
                value=by_id[name]
                candidates[name]=value.model_copy(update={'object_id':obj}) if hasattr(value,'model_copy') else type(value)(**{**vars(value),'object_id':obj})
        result=[candidates[b.entity_id] for b in bindings]
        try: validate_identity_bindings(graph,result,scene,program)
        except MathSubjectBindingError: continue
        if solution is not None: return None
        solution=result
    return solution


def validate_translation_narration(scene):
    """Reject explicit direction words contradicted by every visible movement.

    Checks genuine rigid translation from computed sampled geometry, not just
    a moving centroid. It is a limited language guard, not full prose proof.
    """
    import re
    from zhijiang.visual_planning import states, object_geometry
    from zhijiang.math_construction import resolve_parameters
    patterns={'left':r'(?:向|往|朝)左(?:方|侧)?(?:平移|移动)',
              'right':r'(?:向|往|朝)右(?:方|侧)?(?:平移|移动)',
              'up':r'(?:向|往|朝)上(?:方)?(?:平移|移动)',
              'down':r'(?:向|往|朝)下(?:方)?(?:平移|移动)'}
    for i,((before,after,visible),beat) in enumerate(zip(states(scene),scene.beats)):
        directions=[d for d,p in patterns.items() if re.search(p,beat.narration)]
        if not directions: continue
        vectors=[]
        for obj in scene.objects:
            if obj.id not in visible or obj.kind=='label' or obj.reference: continue
            samples=[object_geometry(obj,resolve_parameters(scene,{k:before[k]+t*(after[k]-before[k]) for k in before}))['points'] for t in [0,.25,.5,.75,1]]
            if not samples[0] or any(len(s)!=len(samples[0]) for s in samples): continue
            deltas=[[b[j]-a[j] for j in (0,1)] for a,b in zip(samples[0],samples[-1])]
            delta=deltas[0]
            if math.hypot(*delta)<1e-7 or any(math.dist(q,delta)>1e-6 for q in deltas): continue
            if any(math.dist([p[j]-a[j] for j in (0,1)],[t*v for v in delta])>1e-6 for t,s in zip([0,.25,.5,.75,1],samples) for p,a in zip(s,samples[0])): continue
            vectors.append(delta)
        for direction in directions:
            axis,sign={'left':(0,-1),'right':(0,1),'up':(1,1),'down':(1,-1)}[direction]
            if not any(sign*v[axis]>1e-7 for v in vectors):
                error=VisualSceneError(f'口播平移方向无效：第{i+1}步，{direction}；实际平移向量{vectors}。只描述真正发生的动作，不能用静止对象或旋转冒充平移。')
                error.repair_target='behavior'
                raise error


def hide_incidental_points(program, requirements):
    """Auxiliary construction coordinates are not automatic teaching labels."""
    if not requirements: return program
    if any(s['kind']=='point' for r in requirements for s in r.get('subjects',[])): return program
    point_ops={'point','midpoint','projection','intersection','polar_point','point_on_curve','point_on_function'}
    from zhijiang.math_construction import Compiler
    compiler=Compiler(program)
    hidden={o.id for o in program.constructions if o.op in point_ops and o.id not in program.roles and
        not any(v.free_symbols for v in compiler.items[o.id]['p'])}
    return program.model_copy(update={
        'constructions':[o.model_copy(update={'visible':False}) if o.id in hidden else o for o in program.constructions],
        'operations':[op.model_copy(update={'show':[v for v in op.show if v not in hidden]}) for op in program.operations]})


def normalize_single_actor_visibility(program):
    """A sole visible dependent transform replaces its non-reference source.

    Record the visibility edits. Multiple visible copies remain errors and
    explicit reference objects remain visible; no coordinates are changed.
    """
    from zhijiang.math_construction import Compiler
    compiler=Compiler(program);objects={o.id:o for o in compiler.shapes}
    visible={o.id for o in compiler.shapes if o.visible}
    operations=[];history=[]
    for index,operation in enumerate(program.operations):
        visible.update(compiler.expand_ids(operation.show))
        visible.difference_update(compiler.expand_ids(operation.hide))
        actors={}
        for name in visible:
            obj=objects[name]
            if obj.reference: continue
            actors.setdefault(compiler.actor_of.get(name,name),[]).append(name)
        hidden=[]
        for actor,members in actors.items():
            if len(members)==2 and actor in members and actor in objects:
                copy=next(m for m in members if m!=actor)
                hidden.append(actor);visible.remove(actor)
                history.append({'step':index+1,'source':actor,'visible_transform':copy,
                    'kind':'single_actor_visibility','coordinates_changed':False})
        operations.append(operation.model_copy(update={'hide':list(dict.fromkeys(operation.hide+hidden))}))
    return program.model_copy(update={'operations':operations}),history


def legend_entries(scene, visible):
    groups=scene.mathematical_model.get('identity_colour_groups',[])
    actors=scene.mathematical_model.get('actor_of',{})
    roles=scene.mathematical_model.get('roles',{})
    entries=[];grouped=set()
    for group in groups:
        roots={actors.get(v,v) for v in group['objects']}
        actual={o.id for o in scene.objects if actors.get(o.id,o.id) in roots}
        grouped.update(actual)
        if actual.intersection(visible): entries.append((group['name'],group['colour']))
    for obj in scene.objects:
        if obj.id in visible and obj.id not in grouped and obj.id in roles and obj.kind not in {'dot','label'}:
            pair=(roles[obj.id],obj.color)
            if pair not in entries: entries.append(pair)
    return entries
