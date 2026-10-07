"""Small provenance graph shared by scene layout, review, and course output.

An edge is a sourced proposition, not an inference from co-occurrence. Node IDs
are local to a scene so homonyms from different contexts are never merged.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel,Field,create_model
from typing import Literal


class SourceProposition(BaseModel):
    subject: str = Field(min_length=2,max_length=48)
    predicate: str = Field(min_length=1,max_length=32)
    object: str = Field(min_length=2,max_length=48)
    fact_ids: list[int] = Field(min_length=1,max_length=3)
    subject_source_term: str = Field(default='',max_length=64)
    object_source_term: str = Field(default='',max_length=64)


def complete_graph_label(label):
    """Reject grammatical fragments, independent of the textbook's subject.

    This is a conservative check, not a parser or a correctness guarantee.
    Unresolved pronouns and dangling function words cannot name graph entities.
    Complex prose remains available as a full source-page annotation.
    """
    text=label.strip();words=re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?",text.lower())
    if text.lower() in {'i','we','you','he','she','it','they','this','that','these','those',
                         '我','我们','你','你们','他','她','它','他们','这些','那些','这','那'}:
        return False
    if re.match(r'^(?:这|那)(?:些|个|组|种|一)',text):return False
    if words and re.fullmatch(r'[\x00-\x7f]+',text) and words[-1] in {
            'a','an','the','of','to','from','with','for','by','in','on','at','and','or',
            'but','not','is','are','was','were','be','been','will','would','could','should',
            'can','may','must','has','have','had','our','your','their','its'}:
        return False
    return not text.endswith(('的','以及','或者','并且','与','和','、','，',','))


def _copula_supported(p,facts):
    """A direct identity edge needs its actual subject before the copula.

    Merely mentioning an activity near its property cannot establish identity.
    More complex constructions can use non-identity predicates or annotations.
    """
    if not re.match(r'^(?:是|为|等于|(?:is|are|was|were)\b)',p['predicate'].strip(),re.I):
        return True
    for fact in facts:
        for text,left,right in [(fact['statement'],p['subject'],p['object']),
                (fact['source_quote'],p.get('subject_source_term') or p['subject'],
                 p.get('object_source_term') or p['object'])]:
            for a in re.finditer(re.escape(left),text):
                for b in re.finditer(re.escape(right),text[a.end():]):
                    between=text[a.end():a.end()+b.start()]
                    if re.search(r'[。；;!?\n]',between):continue
                    if re.search(r'不是|不等于|并非|\b(?:not|never)\b',between,re.I):continue
                    if re.search(r'是|为|等于|\b(?:is|are|was|were)\b',between,re.I):return True
    return False


def _checked_propositions(items,facts):
    """Bind exact endpoint names and facts; do not derive a missing predicate."""
    by_id={f['id']:f for f in facts};kept=[];rejected=[]
    from zhijiang.teaching_design import literal_source_name
    for raw in items:
        try:
            p=SourceProposition.model_validate(raw).model_dump()
            ids=p['fact_ids']
            if len(set(ids))!=len(ids) or any(i not in by_id for i in ids):
                raise ValueError('命题事实编号无效。')
            if p['subject']==p['object']:
                raise ValueError('命题端点不能相同。')
            if re.search(r'\.{2,}|…',p['predicate']):
                raise ValueError('命题谓词不能使用省略号代替完整关系。')
            for field in ('subject','object'):
                if not complete_graph_label(p[field]):
                    raise ValueError('命题端点包含未解析代词或截断短语，需使用完整名称或原页注释。')
                if not any(p[field] in by_id[i]['statement'] or literal_source_name(p[field],by_id[i]['source_quote']) for i in ids):
                    raise ValueError('命题对象必须是所选独立事实中的完整名称。')
                term=p[field+'_source_term']
                if term and not any(term in by_id[i]['source_quote'] for i in ids):
                    raise ValueError('命题原文定位词必须逐字属于当前来源。')
            if not _copula_supported(p,[by_id[i] for i in ids]):
                raise ValueError('身份关系缺少原文中同一主语、系词和宾语的支持，不能把对象与其属性互换。')
            p['id']=len(kept)+1;kept.append(p)
        except ValueError as exc:
            rejected.append({'draft':raw,'error':str(exc)})
    return kept,rejected


def source_propositions(client,facts,path: Path | None=None):
    """Read relations before seeing any diagram, label choices, or user style.

    These drafts constrain the later design; they are not proof of entailment.
    Accepted designs still receive full-page itemized source review.
    """
    fingerprint=hashlib.sha256(json.dumps({'version':'source-propositions-v5','facts':facts,
        'provider':getattr(client,'base_url',''),'model':getattr(client,'model',''),
        'semantic_thinking':getattr(client,'semantic_thinking',True)},
        ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if path and path.exists():
        try:
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved.get('fingerprint')==fingerprint:
                kept,rejected=_checked_propositions(saved['propositions'],facts)
                if not rejected:return kept
        except (ValueError,OSError,KeyError):pass
    proposition=create_model('SourcePropositionDraft',__base__=SourceProposition,
        fact_ids=(list[Literal[tuple(f['id'] for f in facts)]],Field(min_length=1,max_length=3)))
    schema=create_model('SourcePropositionsDraft',propositions=(list[proposition],Field(max_length=8)))
    result=client.generate(schema,
        '独立阅读sources，提取原文明确断言的主语、谓词、宾语三元命题，不做教学设计。'
        '你没有候选图。subject/object复制statement中的完整实体、操作名称或原语言术语，predicate用中文忠实保留否定、可能、范围和条件提示。'
        'subject_source_term和object_source_term分别逐字复制source_quote里对应该对象的完整原语言定位词，不翻译；同一对象在不同命题中保留相同名称。'
        '以原文source_quote含义为依据，发现statement误译时不提取该命题。'
        '同一主体的属性不是另一个主体的属性；被动句恢复真正施事与受事；共同拥有某属性不能写成彼此拥有对方。'
        '并列对象不是互为因果。跨句只有明确指代、操作顺序或依赖才能组合，分别出现两个概念不足以连接。'
        '条件成立才有结果，不省略条件；必要条件与充分条件不交换。'
        'fact_ids选择支持整条命题的1至3个编号，不添加只提及某词的无关事实。'
        '命题可表达组成、属性、用途、顺序、条件或材料信息传递，不能增加来源没说的关系。'
        '优先复制独立中文statement的完整概念名；原语言专名可保留。端点不能是未解析的我们、你、它、那组单词等指代，应使用明确名称，或不提取。'
        'predicate是完整关系，不能用省略号占位；概念与其属性不得混为同一对象。'
        '名称不能截断从句、动词短语或并列列表充当实体，不要为了长度限制删除末尾实词或保留悬空介词。'
        '系词关系必须由原文实际的主语与宾语支持；对象的成本或性质不能写成该对象本身就是其成本或性质。'
        '无法用完整短名忠实表示的复杂从句可不提取，propositions=[]是有效结果。',
        json.dumps({'sources':facts},ensure_ascii=False))
    kept,rejected=_checked_propositions([p.model_dump() for p in result.propositions],facts)
    if path:
        path.write_text(json.dumps({'fingerprint':fingerprint,'propositions':kept,'rejected':rejected,
            'status':'draft_requires_semantic_review'},ensure_ascii=False,indent=2),encoding='utf-8')
    return kept


def graph_design_schema(propositions):
    """Select propositions rather than regenerate their endpoint roles."""
    return create_model('TeachingDesignDraft',
        representation=(Literal['process','relationship','geometry'],Field()),
        rationale=(str,Field(min_length=8,max_length=180)),question=(str,Field(min_length=4,max_length=100)),
        proposition_ids=(list[Literal[tuple(p['id'] for p in propositions)]],Field(min_length=1,max_length=3)))


def design_from_propositions(selection,propositions,facts):
    from zhijiang.teaching_design import TeachingDesignDraft,TeachingDesignError,literal_source_name
    chosen=selection.proposition_ids
    if len(set(chosen))!=len(chosen):raise TeachingDesignError('不能重复选择来源命题。')
    if selection.representation=='geometry':
        return TeachingDesignDraft(**selection.model_dump(exclude={'proposition_ids'}))
    by_id={p['id']:p for p in propositions};by_fact={f['id']:f for f in facts}
    nodes=[];edges=[];node_ids={}
    for key in chosen:
        p=by_id[key];endpoints=[]
        for field in ('subject','object'):
            label=p[field];term=p.get(field+'_source_term','')
            candidates=[by_fact[i] for i in p['fact_ids'] if (label in by_fact[i]['statement'] or literal_source_name(label,by_fact[i]['source_quote']))
                and (not term or term in by_fact[i]['source_quote'])]
            if not candidates:raise TeachingDesignError('来源命题对象缺少同一事实中的原文定位词。')
            fact=candidates[0];literal=literal_source_name(label,fact['source_quote'])
            term=literal or term
            if not term:raise TeachingDesignError('来源命题对象没有原文定位词，需改为原页注释。')
            identity=(label,term)
            if identity not in node_ids:
                node_ids[identity]=len(nodes)+1
                nodes.append({'id':node_ids[identity],'label':label,'source_term':term,'source_id':fact['source_id']})
            endpoints.append(node_ids[identity])
        edges.append({'id':len(edges)+1,'source':endpoints[0],'target':endpoints[1],
            'source_id':by_fact[p['fact_ids'][0]]['source_id'],'source_proposition_id':key,'label':p['predicate']})
    if len(nodes)>6:raise TeachingDesignError('当前命题对象过多，请选择一个局部核心关系。')
    return TeachingDesignDraft(representation=selection.representation,rationale=selection.rationale,
        question=selection.question,nodes=nodes,relations=edges)


def bind_source_propositions(draft,propositions,facts):
    from zhijiang.teaching_design import TeachingDesignDraft,TeachingDesignError
    data=draft.model_dump();by_id={p['id']:p for p in propositions};by_fact={f['id']:f for f in facts}
    nodes={n['id']:n for n in data['nodes']}
    for edge in data['relations']:
        p=by_id.get(edge.get('source_proposition_id'))
        if p is None:raise TeachingDesignError('连线必须选择独立来源命题，不能从共现词另造关系。')
        if (nodes.get(edge['source'],{}).get('label'),nodes.get(edge['target'],{}).get('label'))!=(p['subject'],p['object']):
            raise TeachingDesignError('连线主语和宾语必须与独立来源命题完全对应，不能交换或截断实体。')
        edge.update(label=p['predicate'],binding='semantic',source_fact_id=p['fact_ids'][0],
                    supporting_fact_ids=p['fact_ids'][1:],source_id=by_fact[p['fact_ids'][0]]['source_id'])
    return TeachingDesignDraft.model_validate(data)


def validate_source_propositions(diagram,propositions):
    from zhijiang.teaching_design import TeachingDesignError
    nodes={n.id:n.label for n in diagram.nodes};by_id={p['id']:p for p in propositions}
    for edge in diagram.relations:
        p=by_id.get(edge.source_proposition_id)
        if p is None or (nodes.get(edge.source),edge.label,nodes.get(edge.target))!=(p['subject'],p['predicate'],p['object']):
            raise TeachingDesignError('连线与独立来源命题不一致。')
        if not set(p['fact_ids']).issubset({edge.source_fact_id,*edge.supporting_fact_ids}):
            raise TeachingDesignError('连线缺少独立命题的完整来源事实。')


def design_digest(diagram):
    data=diagram.model_dump(exclude={'question','source_asset','source_regions'})
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def knowledge_graph(diagram, page=None):
    from zhijiang.teaching_design import fact_covers_node
    facts={fact.id:fact for fact in diagram.source_facts}
    return {
        'page':page,
        'nodes':[{'id':node.id,'label':node.label,'kind':node.kind,'source_term':node.source_term,
                  'source_quote':node.source_quote,
                  'fact_ids':[key for key,fact in facts.items()
                              if fact_covers_node(node,fact.model_dump())]}
                 for node in diagram.nodes],
        'triples':[{'id':edge.id,'subject':edge.source,'predicate':edge.label,'object':edge.target,
                    'source_proposition_id':edge.source_proposition_id,
                    'directed':edge.directed,'binding':edge.binding,
                    'condition':edge.condition,
                    'fact_ids':([edge.source_fact_id,*edge.supporting_fact_ids] if edge.source_fact_id else []),
                    'statements':edge.source_statements or ([facts[edge.source_fact_id].statement]
                                    if edge.source_fact_id in facts else []),
                    'source_quotes':list(dict.fromkeys([edge.source_quote,*edge.supporting_quotes]))}
                   for edge in diagram.relations],
        'scope':'仅组织当前来源已核验的事实与关系，不推断未给出的因果；专业事实仍需复核',
    }


def graph_layers(diagram):
    """Topological layers from edge direction, independent of subject/name/IDs.

    Cycles stay explicit and use a ring layout; a feedback process must not be
    silently rendered as a chain. Comparisons/annotations have no order.
    """
    ids=[node.id for node in diagram.nodes]
    if not diagram.relations or diagram.representation in {'comparison','source_figure'}:
        return None
    incoming={key:set() for key in ids};outgoing={key:set() for key in ids}
    for edge in diagram.relations:
        if not edge.directed:return None
        incoming[edge.target].add(edge.source);outgoing[edge.source].add(edge.target)
    remaining=set(ids);layers=[]
    while remaining:
        layer=[key for key in ids if key in remaining and not incoming[key]&remaining]
        if not layer:return []
        layers.append(layer);remaining.difference_update(layer)
    return layers
