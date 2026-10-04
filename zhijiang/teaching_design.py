"""Source-grounded pedagogical design, independent of geometric syntax/subjects."""
from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Literal,Union

from pydantic import BaseModel, Field, create_model, model_validator
from pydantic_core import PydanticCustomError

from zhijiang.models import (TeachingDiagram, TeachingNode, TeachingRelation, TeachingStep, TeachingSourceFact,
                             SceneObject, VisualBeat, VisualScenePlan, ReviewResult)


class TeachingDesignError(ValueError):
    pass


class DesignNodeDraft(BaseModel):
    id: int = Field(ge=1,le=6)
    label: str = Field(min_length=2,max_length=24,pattern=r'^[^\r\n]{0,12}[\u4e00-\u9fff][^\r\n]{0,11}$')
    source_id: int = Field(ge=1)
    source_term: str = Field(min_length=1,max_length=64,pattern=r'^[^\r\n]{1,64}$')


class DesignRelationDraft(BaseModel):
    id: int = Field(ge=1,le=8)
    source: int = Field(ge=1,le=6)
    target: int = Field(ge=1,le=6)
    label: str = Field(min_length=2,max_length=18,pattern=r'^[^\r\n]{0,8}[\u4e00-\u9fff][^\r\n]{0,9}$')
    source_id: int = Field(ge=1)
    source_fact_id: int | None = Field(default=None,ge=1)


class DesignStepDraft(TeachingStep):
    narration: str = Field(min_length=12,max_length=220,pattern=r'^[^\r\n]{12,220}$')


class TeachingDesignDraft(BaseModel):
    representation: Literal['geometry', 'process', 'relationship', 'comparison', 'source_figure']
    rationale: str = Field(min_length=8, max_length=180,pattern=r'^[^\r\n]{8,180}$')
    question: str = Field(min_length=4, max_length=100,pattern=r'^[^\r\n]{4,100}$')
    nodes: list[DesignNodeDraft] = Field(default_factory=list, max_length=6)
    relations: list[DesignRelationDraft] = Field(default_factory=list, max_length=8)
    steps: list[DesignStepDraft] = Field(default_factory=list, max_length=5)


class ResolvedTeachingDesign(TeachingDesignDraft):
    nodes: list[TeachingNode] = Field(default_factory=list,max_length=6)
    relations: list[TeachingRelation] = Field(default_factory=list,max_length=8)
    source_facts: list[TeachingSourceFact] = Field(default_factory=list,max_length=8)


class ScriptStepDraft(BaseModel):
    source_statement: str = Field(min_length=12,max_length=80,pattern=r'^[^\r\n]{12,80}$',description='One fact or condition supported by the source. No analogy or invented guarantee.')
    analogy: str = Field(default='',max_length=48,pattern=r'^[^\r\n]{0,48}$',description='Optional hypothetical everyday analogy, not a source fact or physical mechanism.')
    focus: list[int] = Field(min_length=1,max_length=6)
    relations: list[int] = Field(default_factory=list,max_length=8)


class TeachingScriptDraft(BaseModel):
    steps: list[ScriptStepDraft] = Field(min_length=3,max_length=3)


class SourceFactDraft(BaseModel):
    source_id: int = Field(ge=1)
    statement: str = Field(min_length=12,max_length=120,
        pattern=r'^[^\r\n]{12,120}$',
        description='A complete Chinese statement ending in Chinese sentence punctuation; retain scientific names if needed.')

    @model_validator(mode='before')
    @classmethod
    def final_punctuation(cls, value):
        if isinstance(value,dict) and isinstance(value.get('statement'),str):
            text = value['statement']
            # Formatting only: preserve all words and reject operators or
            # clipped hyphens rather than pretending they end a sentence.
            if (11 <= len(text) <= 119 and re.search(r'[\u4e00-\u9fff]',text)
                    and re.search(r'[\u4e00-\u9fffA-Za-z0-9]$',text)):
                value = {**value, 'statement': text+'。'}
        return value

    @model_validator(mode='after')
    def chinese_statement(self):
        # Bound the native decoder grammar, not just Pydantic's maxLength.
        # Chinese presence is checked separately without an unbounded branch.
        if not re.search(r'[\u4e00-\u9fff]', self.statement):
            raise ValueError('来源事实必须包含中文说明。')
        if not self.statement.endswith(('。','！','？')):
            raise ValueError('来源事实必须以中文句子标点结束。')
        return self


class SourceFactsDraft(BaseModel):
    facts: list[SourceFactDraft] = Field(min_length=1,max_length=8)


class GroundedStepDraft(BaseModel):
    fact_id: int = Field(ge=1)
    analogy: str = Field(default='',max_length=80,pattern=r'^(?:|[^\r\n]{11,79}[。！？])$')
    focus: list[int] = Field(min_length=1,max_length=6)
    relations: list[int] = Field(default_factory=list,max_length=8)


class EverydayExampleDraft(BaseModel):
    fact_id: int = Field(ge=1)
    analogy: str = Field(min_length=12,max_length=80,pattern=r'^[^\r\n]{11,79}[。！？]$')


def analogy_source_names(facts):
    """Derive named source entities, without a discipline-specific blacklist."""
    import jieba.posseg
    return sorted({token.word for fact in facts for token in jieba.posseg.cut(fact['statement'])
        if len(token.word)>=3 and (token.flag.startswith('n') or token.flag=='eng')})


def check_analogy(analogy,facts):
    if re.search(r'保证|确保|必然|必定|一定|绝对|不可能|才不会|永远|只要',analogy):
        raise TeachingDesignError('生活类比不能增加保证或必要条件；描述“更容易理解”而非承诺结果。')
    if any(name in analogy for name in analogy_source_names(facts)):
        raise TeachingDesignError('生活类比只描述日常对象，不加入教材中的技术对象或专有实体行为。')


class GroundedScriptDraft(BaseModel):
    steps: list[GroundedStepDraft] = Field(min_length=1,max_length=5)
    example: EverydayExampleDraft | None = None

    @model_validator(mode='after')
    def distinct_facts(self):
        if len({step.fact_id for step in self.steps})!=len(self.steps):
            raise PydanticCustomError('duplicate_source_fact','每个来源事实只讲解一次；同一事实的不同关系放在同一步，不换焦点重复口播。')
        if self.example and self.example.fact_id not in {step.fact_id for step in self.steps}:
            raise PydanticCustomError('example_fact_not_selected','生活类比必须对应已选择讲解的事实编号。')
        return self


def fact_labels(facts):
    """Choose Chinese names already present in independent source readings."""
    import jieba.posseg
    labels=set()
    for fact in facts:
        text=fact['statement']
        tokens=[];offset=0
        for token in jieba.posseg.cut(text):
            tokens.append((token.word,offset,offset+len(token.word),token.flag));offset+=len(token.word)
        for index,(_,start,_,flag) in enumerate(tokens):
            if not (flag.startswith(('n','a')) or flag in {'m','eng','vn','l','i','j'}):continue
            for count in range(1,6):
                if index+count>len(tokens):break
                end=tokens[index+count-1][2];value=text[start:end]
                end_flag=tokens[index+count-1][3]
                if (2<=len(value)<=24 and re.search(r'[\u4e00-\u9fff]',value)
                        and (end_flag.startswith(('n','a')) or end_flag in {'eng','vn','l','i','j'})
                        and not re.search(r'[，。！？；：、（）()\[\]{};,:.!?\s]',value)):
                    labels.add(value)
    return sorted(labels,key=lambda value:(len(value),value))[:384]


def bind_fact_relation(relation,nodes,facts):
    """Extract the exact predicate between fact-bound endpoints.

    A diagram cannot create a second, contradictory proposition. Complex or
    passive clauses which do not admit this compact reading remain annotations.
    This checks extractive consistency, not the correctness of a translation.
    """
    by_id={fact['id']:fact for fact in facts}
    fact=by_id.get(relation.source_fact_id)
    if not fact:raise TeachingDesignError('连线必须选择独立来源事实编号，不能另造关系。')
    endpoints={node.id:node for node in nodes}
    if relation.source not in endpoints or relation.target not in endpoints:
        raise TeachingDesignError('连线引用不存在的对象。')
    left=endpoints[relation.source].label;right=endpoints[relation.target].label
    statement=fact['statement'];starts=[m.start() for m in re.finditer(re.escape(left),statement)]
    predicates=[]
    for start in starts:
        after=start+len(left);finish=statement.find(right,after)
        if finish<0:continue
        predicate=statement[after:finish].strip()
        if (2<=len(predicate)<=18 and not re.search(r'[，。！？；：、（）]',predicate)
                and predicate not in {'以及','或者','同时','之间','及其','和其','与其'}):
            predicates.append(predicate)
    if len(set(predicates))!=1:
        raise TeachingDesignError('独立事实没有直接支持该主语→关系→宾语顺序；请选择原文标注或比较表达。')
    for node in (endpoints[relation.source],endpoints[relation.target]):
        if normalized(node.source_term) not in normalized(fact['source_quote']):
            raise TeachingDesignError('连线两端术语必须属于所选的同一来源事实。')
    relation.label=predicates[0]
    relation.source_id=fact['source_id']
    return relation


def scanned_fact_issues(statement,source_quote):
    """OCR exercise questions are not established numerical assertions.

    Layout may have lost a denominator even when all statement digits occur in
    the OCR text. Keep the source page/question for review, not as a spoken fact.
    """
    from zhijiang.agents import source_number_issues
    problems=source_number_issues(statement,source_quote)
    if (re.search(r'[?？]',source_quote) and
            (statement.endswith(('?','？')) or re.search(r'多少[^，。！？?]{0,6}[。！？?]$',statement))):
        problems.append('尚未作答的数量问题不是来源事实；OCR数值与原页版式仍需核对。')
    return problems


def extract_source_facts(client,spans,*,ocr=False,rejections=None):
    """Read source without seeing a candidate explanation or user style prompt.

    This separates comprehension from persuasive narration and avoids a reviewer
    merely copying the generator's unsupported assertions. It is not a formal
    proof of translation; full-page semantic review remains a separate gate.
    """
    if not spans:raise TeachingDesignError('没有可供理解的来源片段。')
    fact=create_model('SourceFactDraft',__base__=SourceFactDraft,
        source_id=(Literal[tuple(spans)],Field(description='只选输入来源编号；没有完整原文依据的事实不输出，禁止-1或自拟编号。')))
    schema=create_model('SourceFactsDraft',__base__=SourceFactsDraft,
        facts=(list[fact],Field(min_length=1,max_length=8)))
    result=client.generate(schema,
        '仅阅读原文，提取可用于讲解的事实，用中文忠实转述。你没有候选分镜或口播，不做教学设计。'
        '每条statement只翻译一个原文断言，保留原文主语、动作、宾语和条件；不要补充解释、类比、因果或评价。'
        '原文描述数据时仍写数据，描述训练目标时仍写目标，描述实验结果时保留实验范围。'
        '有帮助或关键不能改写为必要条件、完整还原或成功保证。允许保留原文中的数字与科学名称。'
        'OCR中分数结构缺失、多列数字穿插或无法连读的数值片段不能猜补；优先提取可读的定义、步骤和条件。'
        '未作答的数量问题不作为statement事实；题目仍保留在原PDF页面中，不把问句改成句号来当结论。'
        '忽略作者、机构、参考文献、纯表头及无法理解的截断片段。source_id选择当前编号，statement为12至120字的完整中文句子，以中文句号结束；不能照抄英文或截断词尾。'
        'facts不要求覆盖每个sources条目，只选择清楚的原文断言。不得输出自行推算的结果，不得使用-1或虚构编号。无法绑定完整原文的内容不进入事实数组，不凑条数。',
        json.dumps({'sources':[{'id':key,'text':text} for key,text in spans.items()]},ensure_ascii=False))
    facts=[];seen=set()
    for item in result.facts:
        if item.source_id not in spans:raise TeachingDesignError('来源事实引用了不存在的片段。')
        if ocr:
            if problems := scanned_fact_issues(item.statement,spans[item.source_id]):
                if rejections is not None:
                    rejections.append({'source_id':item.source_id,'statement':item.statement,'issues':problems})
                continue  # Reject this optional assertion, not the course topic.
        if item.statement in seen:continue
        seen.add(item.statement)
        facts.append({'id':len(facts)+1,'source_id':item.source_id,
                      'source_quote':spans[item.source_id],'statement':item.statement})
    if not facts:
        raise TeachingDesignError('原文事实未通过OCR数值引用检查，需核对原页；不能补写缺失的公式或比例。')
    return facts


def source_reading_fingerprint(client,spans,ocr=False):
    return hashlib.sha256(json.dumps({'version':'ocr-source-reading-v2' if ocr else 'source-reading-v1','spans':spans,
        'endpoint':getattr(client,'base_url',''),'model':getattr(client,'model','')},sort_keys=True).encode()).hexdigest()


def source_reading(client,spans,path=None,*,ocr=False):
    """Cache unapproved comprehension drafts; every design still gets reviewed."""
    fingerprint=source_reading_fingerprint(client,spans,ocr)
    if path:
        try:
            saved=json.loads(path.read_text(encoding='utf-8'))
            facts=[TeachingSourceFact.model_validate(fact).model_dump() for fact in saved['facts']]
            # Old caches may contain untranslated or truncated model outputs.
            # Apply the current comprehension contract before reusing a draft.
            kept=[];rejections=list(saved.get('rejected_facts',[]))
            for fact in facts:
                fact['statement']=SourceFactDraft.model_validate(fact).statement
                if ocr:
                    if problems:=scanned_fact_issues(fact['statement'],spans.get(fact['source_id'],'')):
                        rejection={'source_id':fact['source_id'],'statement':fact['statement'],'issues':problems}
                        if rejection not in rejections:rejections.append(rejection)
                        continue
                kept.append(fact)
            if (saved['fingerprint']==fingerprint and facts and len({f['id'] for f in facts})==len(facts)
                    and all(f['source_quote']==spans.get(f['source_id']) for f in facts)):
                if kept!=facts:
                    path.write_text(json.dumps({**saved,'facts':kept,'rejected_facts':rejections,
                        'status':'draft_requires_semantic_review' if kept else 'rejected_requires_source_review'},
                        ensure_ascii=False,indent=2),encoding='utf-8')
                if kept:return kept,True
                raise TeachingDesignError('缓存事实未通过OCR数值引用检查，需核对原页。')
        except (OSError,ValueError,KeyError):pass
    rejections=[]
    try:
        facts=extract_source_facts(client,spans,ocr=ocr,rejections=rejections)
    except TeachingDesignError:
        if path:
            path.write_text(json.dumps({'fingerprint':fingerprint,'facts':[],
                'rejected_facts':rejections,'status':'rejected_requires_source_review'},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    if path:
        path.write_text(json.dumps({'fingerprint':fingerprint,'facts':facts,'rejected_facts':rejections,'status':'draft_requires_semantic_review'},
            ensure_ascii=False,indent=2),encoding='utf-8')
    return facts,False


def structure_fingerprint(client,material,prompt,force_diagram=False):
    return hashlib.sha256(json.dumps({'version':'structure-v1','material':material,'prompt':prompt,
        'force_diagram':force_diagram,'endpoint':getattr(client,'base_url',''),'model':getattr(client,'model','')},sort_keys=True).encode()).hexdigest()


def save_structure(path,fingerprint,draft):
    if path:
        path.write_text(json.dumps({'fingerprint':fingerprint,'design':draft.model_dump(exclude={'steps'}),
            'status':'draft_requires_semantic_review'},ensure_ascii=False,indent=2),encoding='utf-8')


def load_structure(path,fingerprint,source_text):
    if not path:return None
    try:
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved['fingerprint']!=fingerprint:return None
        draft=ResolvedTeachingDesign.model_validate(saved['design'])
        validate_diagram(draft,source_text,require_steps=False)
        return draft
    except (OSError,KeyError,ValueError):return None


def diagram_source_facts(draft,facts):
    """A step can explain only facts evidenced by objects/relations on this diagram."""
    quotes={normalized(quote) for item in [*draft.nodes,*draft.relations]
            for quote in [item.source_quote,*getattr(item,'supporting_quotes',[])]}
    selected=[fact for fact in facts if normalized(fact['source_quote']) in quotes]
    if not selected:raise TeachingDesignError('图中对象没有对应的独立来源事实，请重新选择教学对象。')
    return selected


def prefer_source_example(draft,facts,prompt):
    """Use explicit examples already in the source before inventing analogies.

    This is a language cue, not a subject classifier or a paper-specific rule.
    Independent examples are added only to views that permit unconnected notes.
    """
    requested=bool(re.search(r'类比|生活|例子',prompt)) and not bool(re.search(r'(?:不要|不用|不需要|不必|避免).{0,8}(?:类比|生活|例子)',prompt))
    if not requested or draft.representation not in {'source_figure','comparison'}:return []
    import jieba.posseg
    used=[]
    for fact in facts:
        if not re.search(r'\bfor (?:example|instance)\b|\be\.g\.|例如|比如|举例',fact['source_quote'],re.I):continue
        # Prefer a nonnumeric example for a request for everyday explanation.
        if re.search(r'[0-9０-９]',fact['statement']):continue
        existing=[node for node in draft.nodes if node.source_quote==fact['source_quote'] and node.label in fact['statement']]
        if not existing and len(draft.nodes)<6:
            names=[token.word for token in jieba.posseg.cut(fact['statement'])
                   if token.flag.startswith('n') and 2<=len(token.word)<=24 and re.search(r'[\u4e00-\u9fff]',token.word)]
            if not names:continue
            draft.nodes.append(TeachingNode(id=next(i for i in range(1,7) if i not in {node.id for node in draft.nodes}),label=names[0],
                source_quote=fact['source_quote'],source_term=''))
        elif not existing:continue
        used.append(fact['id']);break
    return used


def cached_source_examples_covered(scene,facts,prompt):
    """Apply current example policy to old reviewed scenes on every reuse."""
    if not scene.diagram:return True
    expected=prefer_source_example(scene.diagram.model_copy(deep=True),facts,prompt)
    return (not expected or (set(expected)<={step.source_fact_id for step in scene.diagram.steps}
            and not any(step.analogy for step in scene.diagram.steps)))


def preserve_source_sequence(draft,facts):
    """Retain explicit neighboring follow-up operations in guided-source views.

    Temporal language selects quoted facts, never inferred causes or physics.
    A source trace must not jump from an initial operation to its conclusion.
    """
    if draft.representation not in {'source_figure','comparison'}:return []
    selected={node.source_quote for node in draft.nodes};required=[]
    ordered=sorted(facts,key=lambda fact:fact['source_id'])
    for before,after in zip(ordered,ordered[1:]):
        if after['source_id']!=before['source_id']+1:continue
        begins=bool(re.search(r'\b(?:starts?|begins?|first|initial|followed)\b|首先|开始|起始|先将|先把',before['source_quote'],re.I))
        follows=bool(re.match(r'\s*(?:(?:we|they|it)\s+)?(?:then|next|subsequently|finally)\b|\s*(?:随后|接着|然后|之后|最后)',after['source_quote'],re.I))
        if not begins or not follows or not ({before['source_quote'],after['source_quote']} & selected):continue
        for fact in (before,after):
            anchored=any(node.source_quote==fact['source_quote'] and node.label in fact['statement'] for node in draft.nodes)
            if not anchored:
                # Reuse a phrase from the independent reading, not a guessed
                # source-language translation or a subject-specific vocabulary.
                names=fact_labels([fact])
                if not names or len(draft.nodes)>=5:continue
                label=min(names,key=lambda name:(len(name)<3,len(name)>8,-len(name),name))
                draft.nodes.append(TeachingNode(id=next(i for i in range(1,7) if i not in {node.id for node in draft.nodes}),
                    label=label,source_quote=fact['source_quote'],source_term=''))
                selected.add(fact['source_quote'])
            required.append(fact['id'])
    return list(dict.fromkeys(required))


def cached_source_sequence_covered(scene,facts):
    if not scene.diagram:return True
    expected=preserve_source_sequence(scene.diagram.model_copy(deep=True),facts)
    return set(expected)<={step.source_fact_id for step in scene.diagram.steps}


def preserve_topic_focus(draft,facts,topic):
    """Bind the current question to its most specific sourced Chinese phrase.

    Phrase frequency discounts generic words across the local readings; no
    discipline glossary or topic-name routing is used. Synonyms still need review.
    """
    if draft.representation not in {'source_figure','comparison'}:return []
    candidates=[(fact,name) for fact in facts for name in fact_labels([fact]) if name in topic]
    if not candidates:return []
    frequencies={name:sum(name in fact['statement'] for fact in facts) for _,name in candidates}
    fact,label=max(candidates,key=lambda item:(len(item[1])/frequencies[item[1]],len(item[1]),-item[0]['source_id']))
    if not any(node.source_quote==fact['source_quote'] and node.label in fact['statement'] for node in draft.nodes):
        if len(draft.nodes)>=5:
            raise TeachingDesignError('当前图示遗漏知识点主题的核心来源事实；请删去次要对象并重新规划。')
        draft.nodes.append(TeachingNode(id=next(i for i in range(1,7) if i not in {node.id for node in draft.nodes}),
            label=label,source_quote=fact['source_quote'],source_term=''))
    return [fact['id']]


def cached_topic_focus_covered(scene,facts,topic):
    if not scene.diagram:return True
    try:expected=preserve_topic_focus(scene.diagram.model_copy(deep=True),facts,topic)
    except TeachingDesignError:return False
    return set(expected)<={step.source_fact_id for step in scene.diagram.steps}


def compose_script(script,facts=None):
    if facts is not None:
        by_id={item['id']:item for item in facts}
        result=[]
        for step in script.steps:
            example=getattr(script,'example',None)
            analogy=example.analogy if example and example.fact_id==step.fact_id else getattr(step,'analogy','')
            statement=by_id[step.fact_id]['statement']
            result.append(DesignStepDraft(source_statement=statement,source_fact_id=step.fact_id,analogy=analogy,
                narration=statement+(' 做个生活类比：'+analogy if analogy else ''),focus=step.focus,relations=step.relations))
        return result
    return [DesignStepDraft(narration=step.source_statement+
        (' 做个生活类比：'+step.analogy if step.analogy else ''),
        **step.model_dump()) for step in script.steps]


class MeaningCheck(BaseModel):
    id: int = Field(ge=1)
    supported: bool
    # An object name can be a faithful short meaning. Do not require padding
    # every noun into a fabricated sentence or duplicate length in regex syntax.
    source_meaning: str = Field(min_length=2,max_length=120)
    reason: str = Field(min_length=12,max_length=120)


class TeachingSourceReview(ReviewResult):
    """Review meanings individually; a single approval flag is insufficient."""
    node_checks: list[MeaningCheck] = Field(default_factory=list)
    relation_checks: list[MeaningCheck] = Field(default_factory=list)
    step_checks: list[MeaningCheck] = Field(default_factory=list)


def meaning_review_schema(draft):
    fields={}
    for name,ids in [('node_checks',[n.id for n in draft.nodes]),
                     ('relation_checks',[r.id for r in draft.relations]),
                     ('step_checks',list(range(1,len(draft.steps)+1)))]:
        check=create_model('MeaningCheck_'+name,__base__=MeaningCheck,
            id=(Literal[tuple(ids)] if ids else int,Field(description='ID of the item being reviewed.')))
        fields[name]=(list[check],Field(min_length=len(ids),max_length=len(ids)))
    return create_model('TeachingSourceReview',__base__=TeachingSourceReview,**fields)


def validate_meaning_review(review,draft):
    for name,ids in [('node_checks',{n.id for n in draft.nodes}),
                     ('relation_checks',{r.id for r in draft.relations}),
                     ('step_checks',set(range(1,len(draft.steps)+1)))]:
        checks=getattr(review,name)
        if {check.id for check in checks}!=ids or len(checks)!=len(ids):
            raise TeachingDesignError('含义核对遗漏或重复项目：'+name)
        failed=[check for check in checks if not check.supported]
        if failed:
            raise TeachingDesignError('教学含义核对未通过：'+'；'.join(
                f'{name} {check.id}：{check.reason}' for check in failed[:3]))
    if not review.approved:
        raise TeachingDesignError('教学含义核对未通过：'+'；'.join(review.issues[:3]))


def structure_schema(spans,*,source_annotation=False,facts=None):
    """Select actual source phrases; no subject-specific object vocabulary."""
    if not spans:raise TeachingDesignError('没有可用于分镜设计的来源片段。')
    source_id=Literal[tuple(spans)]
    source_term=Literal[tuple(source_terms(spans))]
    if facts is not None:
        variants=[]
        for fact in facts:
            labels=fact_labels([fact])
            if not labels:continue
            variants.append(create_model('FactNode_'+str(fact['id']),__base__=DesignNodeDraft,
                source_id=(Literal[fact['source_id']],Field()),
                label=(Literal[tuple(labels)],Field(description='Chinese phrase from this source fact.')),
                source_term=(Literal[tuple(source_terms({fact['source_id']:fact['source_quote']})[:96])],Field(description='Original-language term from this same source.'))))
        if not variants:raise TeachingDesignError('独立来源事实没有可用于标注的中文对象，请核对原文理解。')
        node=Union[tuple(variants)]
    else:
        node=create_model('DesignNodeDraft',__base__=DesignNodeDraft,
            source_id=(source_id,Field(description='Choose an existing source ID.')),
            source_term=(source_term,Field(description='Select an exact phrase from the current sources. NEVER translate.')))
    relation=create_model('DesignRelationDraft',__base__=DesignRelationDraft,
        source_id=(source_id,Field(description='Choose evidence containing both endpoint terms.')))
    if facts:
        # No free predicate or source ID: both are filled from an existing fact.
        relation=create_model('FactRelationSelection',id=(int,Field(ge=1,le=8)),
            source=(int,Field(ge=1,le=6)),target=(int,Field(ge=1,le=6)),
            source_fact_id=(Literal[tuple(fact['id'] for fact in facts)],Field()))
    fields={}
    if source_annotation:
        # Preserve actual source art/facts when relationship planning fails;
        # never weaken the source or semantic gates to connect the diagram.
        fields['representation']=(Literal['source_figure'],Field())
    return create_model('TeachingDesignDraft',__base__=TeachingDesignDraft,
        nodes=(list[node],Field(default_factory=list,max_length=4)),
        relations=(list[relation],Field(default_factory=list,max_length=0 if source_annotation else 3)),
        steps=(list[DesignStepDraft],Field(default_factory=list,max_length=0)),**fields)


def source_terms(spans):
    """Extract lexical anchors by offsets, preserving literal PDF text.

    Language tokenization provides choices, not domain facts. Adjacent words can
    form phrases; punctuation cannot concatenate unrelated clauses. The model
    selects/labels concepts, while copied terms are controlled by the grammar.
    """
    stop=set('a an the to of and or for in on by is are was were as at from with this that these those which where be it its we our their they all can will'.split())
    stop.update(('的','了','是','和','与','在','对','把','为','也','就','将','中','这','其'))
    terms={}
    for quote in spans.values():
        if re.search(r'[\u4e00-\u9fff]',quote):
            import jieba
            tokens=[(word,start,end) for word,start,end in jieba.tokenize(quote) if re.search(r'\w',word)]
        else:
            tokens=[(m.group(),m.start(),m.end()) for m in re.finditer(r'[^\W_]+(?:[’\-−:][^\W_]+)*',quote)]
        for i,(word,start,_) in enumerate(tokens):
            for size in range(1,4):
                if i+size>len(tokens):continue
                last,_,end=tokens[i+size-1]
                if word.casefold() in stop or last.casefold() in stop:continue
                if any(quote[tokens[k][2]:tokens[k+1][1]].strip() for k in range(i,i+size-1)):continue
                term=quote[start:end]
                if 1<=len(term)<=64:
                    terms[term]=terms.get(term,0)+1
    if not terms:
        return [next(iter(spans.values()))[:64]]
    ranked=sorted(terms,key=lambda term:(-terms[term],len(term)>24,len(term)<3,term))
    return ranked[:256]


def script_schema(draft,facts=None,*,require_analogy=False,source_examples=(),source_sequence=(),topic_facts=()):
    node_id=Literal[tuple(n.id for n in draft.nodes)]
    relation_id=Literal[tuple(r.id for r in draft.relations)] if draft.relations else int
    if facts is not None:
        eligible=[fact for fact in facts if any(node.label in fact['statement'] and node.source_quote==fact['source_quote'] for node in draft.nodes)]
        if not eligible:raise TeachingDesignError('来源事实没有可对应的画面对象。')
        step=create_model('GroundedStepSelection',
            fact_id=(Literal[tuple(item['id'] for item in eligible)],Field(description='Select an independent fact. Visual focus and paths are filled from this exact fact.')))
        example=create_model('EverydayExampleDraft',__base__=EverydayExampleDraft,
            fact_id=(Literal[tuple(item['id'] for item in eligible)],Field()))
        schema=create_model('TeachingScriptDraft',__base__=GroundedScriptDraft,
            steps=(list[step],Field(min_length=min(5,len({node.source_quote for node in draft.nodes})),max_length=min(5,len(eligible)))),
            example=(example,Field(description='Exactly one complete everyday analogy for a selected fact.'))
                if require_analogy and not source_examples else
                (type(None),Field(default=None,description='Use source facts only; no additional everyday analogy was requested or the source already supplies an example.')))
        # Request a useful example once, rather than forcing an analogy per fact.
        def check_examples(self):
            count=int(self.example is not None)+sum(bool(getattr(step,'analogy','')) for step in self.steps)
            if count>1:raise PydanticCustomError('multiple_analogies','整个片段最多一个生活类比，其他步骤保留原文事实。')
            if require_analogy and not source_examples and count==0:raise PydanticCustomError('analogy_required','用户请求生活例子，请给出一个完整的生活类比。')
            if set(source_examples)-{step.fact_id for step in self.steps}:
                raise PydanticCustomError('source_example_required','讲解必须包含已选的原文示例事实。')
            if set(source_sequence)-{step.fact_id for step in self.steps}:
                raise PydanticCustomError('source_sequence_required','讲解必须保留原文明确给出的初始与随后操作，不能跳过中间步骤。')
            if set(topic_facts)-{step.fact_id for step in self.steps}:
                raise PydanticCustomError('topic_fact_required','讲解必须包含当前知识点主题的核心来源事实，不能只讲同页的其他内容。')
            positions={step.fact_id:index for index,step in enumerate(self.steps)}
            if any(positions[left]>=positions[right] for left,right in zip(source_sequence,source_sequence[1:])
                    if left in positions and right in positions):
                raise PydanticCustomError('source_sequence_order','原文操作按原文顺序讲解，不能先讲随后步骤。')
            if self.example:
                try:check_analogy(self.example.analogy,facts)
                except TeachingDesignError as exc:
                    raise PydanticCustomError('analogy_unsupported_guarantee_or_source_entity',str(exc)) from exc
            return self
        return create_model('TeachingScriptDraft',__base__=schema,
            __validators__={'check_examples':model_validator(mode='after')(check_examples)})
    # Permit named scientific concepts (e.g. a translated numbered name), but
    # prevent common quantitative assertions during decoding, not after rendering.
    names=sorted({n.label for n in draft.nodes},key=len,reverse=True)
    alternatives=r'[^0-9０-９零〇二三四五六七八九十百千万\r\n]|'+'|'.join(re.escape(n) for n in names)
    step=create_model('ScriptStepDraft',__base__=ScriptStepDraft,
        source_statement=(str,Field(min_length=12,max_length=80,pattern='^('+alternatives+'){12,80}$',description='Source fact only; do not add a guarantee or necessary condition.')),
        analogy=(str,Field(default='',max_length=48,pattern='^('+alternatives+'){0,48}$',description='Optional hypothetical analogy; never present it as a source fact.')),
        focus=(list[node_id],Field(min_length=1,max_length=len(draft.nodes))),
        relations=(list[relation_id],Field(default_factory=list,max_length=len(draft.relations))))
    return create_model('TeachingScriptDraft',__base__=TeachingScriptDraft,
        steps=(list[step],Field(min_length=3,max_length=3)))


def bind_script_focus(script,draft,facts):
    """The spoken fact determines its picture; the model cannot swap focus."""
    by_id={fact['id']:fact for fact in facts};steps=[]
    for step in script.steps:
        fact=by_id[step.fact_id]
        focus=[node.id for node in draft.nodes if node.label in fact['statement'] and node.source_quote==fact['source_quote']]
        relations=[relation.id for relation in draft.relations if relation.source_fact_id==step.fact_id]
        steps.append(GroundedStepDraft(fact_id=step.fact_id,focus=focus,relations=relations))
    return GroundedScriptDraft(steps=steps,example=script.example)


def source_spans(text):
    """Preserve complete sentences where possible, then split on word boundaries.

    PDF line wrapping must not split the subject from its predicate merely to
    satisfy a character limit. Each retained excerpt still matches original text.
    """
    abstract=re.search(r'(?mi)^\s*Abstract\s*$',text)
    if abstract:text=text[abstract.end():]
    flat=' '.join(text.split())
    sentences=[];start=0;depth=0
    for index,char in enumerate(flat):
        if char in '[({（【':depth+=1
        elif char in '])}）】':depth=max(0,depth-1)
        boundary=char in '。！？!?'
        if char=='.' and re.match(r'\s+[A-Z\u4e00-\u9fff]',flat[index+1:]):boundary=True
        if boundary and depth==0:
            sentences.append(flat[start:index+1].strip());start=index+1
    if flat[start:].strip():sentences.append(flat[start:].strip())
    quotes=[]
    for sentence in sentences:
        while len(sentence)>300:
            boundary=max(sentence.rfind(';',0,300),sentence.rfind(',',0,300),sentence.rfind(' ',0,300))
            if boundary<40:boundary=300
            else:boundary+=1
            part=sentence[:boundary].strip();sentence=sentence[boundary:].strip()
            if len(normalized(part))>=8:quotes.append(part)
        if len(normalized(sentence))>=8:quotes.append(sentence)
    return {i+1:quote for i,quote in enumerate(quotes)}


def resolve_design(draft, spans, repairs=None,facts=None):
    if facts:
        data=draft.model_dump()
        bound=[]
        for value in data['relations']:
            selection=DesignRelationDraft(**value,label='来源关系',source_id=1)
            bound.append(bind_fact_relation(selection,draft.nodes,facts).model_dump())
        data['relations']=bound
        draft=TeachingDesignDraft.model_validate(data)
    if any(item.source_id not in spans for item in [*draft.nodes,*draft.relations]):
        raise TeachingDesignError('source_id必须选择当前sources中的编号，不能编造。')
    data=draft.model_dump()
    for field in ('nodes','relations'):
        for item in data[field]:
            key=item.pop('source_id')
            term=item.get('source_term','')
            if term and normalized(term) not in normalized(spans[key]):
                matches=[i for i,q in spans.items() if normalized(term) in normalized(q)]
                # Recover only an unambiguous index mistake. Never invent/translate
                # a source term or choose between conflicting definitions.
                nearest=sorted(matches,key=lambda i:abs(i-key))
                if len(matches)==1 or (nearest and abs(nearest[0]-key)==1 and
                        (len(nearest)==1 or abs(nearest[1]-key)>1)):
                    if repairs is not None: repairs.append({'field':field,'id':item['id'],
                        'from_source_id':key,'to_source_id':nearest[0],'term':term})
                    key=nearest[0]
            item['source_quote']=spans[key]
            if field=='relations':item['directed']=draft.representation=='process'
            if field=='relations' and draft.representation!='comparison':
                endpoints=[n.source_term for n in draft.nodes if n.id in (item['source'],item['target'])]
                missing=[term for term in endpoints if normalized(term) not in normalized(spans[key])]
                neighbors=[q for i,q in spans.items() if abs(i-key)==1 and any(normalized(term) in normalized(q) for term in missing)]
                item['supporting_quotes']=neighbors
    return ResolvedTeachingDesign.model_validate(data)


def normalized(text):
    return ''.join(unicodedata.normalize('NFKC', text).split()).casefold()


def has_unbound_quantity(prose):
    """Distinguish measurements from indefinite articles and marked analogies.

    This is a conservative language check, not a proof of domain claims.
    Semantic review still checks examples and every factual assertion.
    """
    if re.search(r'[0-9０-９]',prose):return True
    prose=prose.replace('每一步','各步').replace('同一个','同样的').replace('每一个','各个')
    numerals=r'[零〇一二两三四五六七八九十百千万]+'
    for match in re.finditer('('+numerals+r')(?:个)?(维(?:度)?|步|倍|次|年|秒|时间|时刻)',prose):
        clause=re.split(r'[。！？；]',prose[:match.start()])[-1]
        if match.group(2) in ('步','次') and re.search(r'就像|好比|类比',clause):continue
        return True
    for match in re.finditer('('+numerals+r')个',prose):
        prefix=prose[:match.start()]
        # 一个 is also the Chinese indefinite article. Exact-count assertions
        # retain their numerical meaning; unit-bearing quantities above remain
        # forbidden even inside analogies.
        if match.group(1)=='一' and not re.search(r'(?:只有|仅有|恰好|正好|总共|至少|至多)(?:有|包含)?\s*$',prefix):
            continue
        clause=re.split(r'[。！？；]',prefix)[-1]
        if match.group(1)=='两' and re.search(r'就像|好比|类比',clause):
            continue
        return True
    return False


def complete_relation_focus(script, relations):
    """Make referenced paths readable without changing the model's facts."""
    edges={r.id:r for r in relations};repairs=[]
    for index,step in enumerate(script.steps):
        step.focus=list(dict.fromkeys(step.focus))
        step.relations=list(dict.fromkeys(step.relations))
        for key in step.relations:
            edge=edges.get(key)
            if edge:
                for endpoint in (edge.source,edge.target):
                    if endpoint not in step.focus:
                        step.focus.append(endpoint)
                        repairs.append({'step':index+1,'relation':key,'added_focus':endpoint,
                            'reason':'Emphasize both endpoints of the selected relation without changing its meaning.'})
    return repairs


def validate_diagram(diagram, source_text=None, *, require_steps=True):
    nodes={n.id:n for n in diagram.nodes}
    edges={r.id:r for r in diagram.relations}
    annotated=diagram.representation=='source_figure'
    comparison=diagram.representation=='comparison'
    if len(nodes)<(1 if annotated else 2) or (not edges and not (annotated or comparison)):
        raise TeachingDesignError('教学表达至少需要两个有来源的对象和一条有含义的关系。')
    if len(nodes)!=len(diagram.nodes) or len(edges)!=len(diagram.relations):
        raise TeachingDesignError('节点及关系编号必须唯一。')
    if any(r.source not in nodes or r.target not in nodes or r.source==r.target for r in diagram.relations):
        raise TeachingDesignError('关系必须连接两个已有且不同的教学对象。')
    connected={key for relation in diagram.relations for key in (relation.source,relation.target)}
    if not (annotated or comparison) and connected!=nodes.keys():
        raise TeachingDesignError('存在孤立节点，关系图没有解释这些对象；请为每个对象规划有来源的关系，或删去无关对象。')
    for item in [*diagram.nodes,*diagram.relations]:
        if item.source_term and normalized(item.source_term) not in normalized(item.source_quote):
            raise TeachingDesignError('source_term必须从所选原文片段逐字复制，不能翻译或改写：'+item.source_term)
    anchored=[n for n in diagram.nodes if n.source_term]
    if len({normalized(n.source_term) for n in anchored})!=len(anchored):
        raise TeachingDesignError('不同对象必须有可区分的原文术语，不得用同一个笼统词代替。')
    for relation in diagram.relations:
        terms=[nodes[key].source_term for key in (relation.source,relation.target)]
        evidence=' '.join([relation.source_quote,*relation.supporting_quotes])
        if diagram.representation!='comparison' and all(terms) and any(
                normalized(term) not in normalized(evidence) for term in terms):
            raise TeachingDesignError('关系来源没有同时支持两个端点的原文术语：'+str(terms)+
                '。请选择能同时支持两个对象的片段，或重新规划对象与关系；不同段落里出现的术语不能自动组成推导。')
    facts={fact.id:fact for fact in getattr(diagram,'source_facts',[])}
    if len(facts)!=len(getattr(diagram,'source_facts',[])):
        raise TeachingDesignError('来源事实编号必须唯一。')
    from zhijiang.agents import _NUMBER
    for fact in facts.values():
        if set(_NUMBER.findall(fact.statement))-set(_NUMBER.findall(fact.source_quote)):
            raise TeachingDesignError('来源事实包含原文没有的数值。')
    if facts:
        for node in diagram.nodes:
            if not any(node.label in fact.statement and node.source_quote==fact.source_quote for fact in facts.values()):
                raise TeachingDesignError(f'节点{node.id}（{node.label}）的名称与所选来源不对应；中文名称必须出现在同一来源事实中，不能重新命名为不同概念。')
        for relation in diagram.relations:
            if relation.source_fact_id is None:
                raise TeachingDesignError('事实绑定图的连线缺少独立来源事实编号。')
            candidate=DesignRelationDraft(**relation.model_dump(exclude={'source_quote','source_term','supporting_quotes','directed'}),source_id=1)
            expected=bind_fact_relation(candidate,diagram.nodes,[fact.model_dump() for fact in facts.values()])
            if relation.label!=expected.label or relation.source_quote!=facts[relation.source_fact_id].source_quote:
                raise TeachingDesignError('连线主语、谓词和宾语必须与独立来源事实一致，不得改写或交换。')
    if source_text is not None:
        text=normalized(source_text)
        for item in [*diagram.nodes,*diagram.relations,*facts.values()]:
            if normalized(item.source_quote) not in text:
                raise TeachingDesignError('来源依据必须逐字复制原文，不得翻译或改写：'+item.source_quote[:60])
            for quote in getattr(item,'supporting_quotes',[]):
                if normalized(quote) not in text:
                    raise TeachingDesignError('补充关系来源必须逐字匹配原文。')
    if not require_steps:
        return {'passed':True,'scope':'对象、关系、来源术语；尚未生成讲解步骤'}
    used_nodes=set(); used_edges=set(); signatures=set();used_facts=set()
    for step in diagram.steps:
        if facts:
            if step.source_fact_id not in facts or step.source_statement!=facts[step.source_fact_id].statement:
                raise TeachingDesignError('口播必须引用独立提取的来源事实，不能改写或增加断言。')
            if step.source_fact_id in used_facts:
                raise TeachingDesignError('同一来源事实只能讲解一次，不能用不同焦点重复口播。')
            used_facts.add(step.source_fact_id)
            fact=facts[step.source_fact_id]
            if any(nodes[key].source_quote!=fact.source_quote or nodes[key].label not in fact.statement
                   for key in step.focus if key in nodes):
                raise TeachingDesignError('讲解焦点必须对应当前来源事实中的对象，不能错配其他原文。')
            if any(edges[key].source_fact_id!=step.source_fact_id for key in step.relations if key in edges):
                raise TeachingDesignError('追踪关系必须对应当前口播的独立来源事实。')
            if step.analogy:check_analogy(step.analogy,[fact.model_dump() for fact in facts.values()])
        if anchored:
            import re
            prose=step.source_statement or step.narration
            for node in sorted(anchored,key=lambda n:len(n.source_term),reverse=True):
                prose=prose.replace(node.source_term,'')
            # Diagram cardinalities are program-known, unlike predicted steps,
            # dimensions, durations or domain measurements.
            counts={'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8}
            def structural_count(match):
                quantity,kind=match.groups()
                allowed={2} if kind=='端点' else ({len(nodes),len(step.focus)} if kind=='节点' else {len(edges),len(step.relations)})
                return '' if counts.get(quantity) in allowed else match.group()
            prose=re.sub(r'([一二两三四五六七八])个(端点|节点|关系)',structural_count,prose)
            if not facts and has_unbound_quantity(prose):
                raise TeachingDesignError('图示口播数值没有绑定原文：请用定性解释，原文术语与数值通过所选来源保留，不要自行断言步数、维数或预测值。')
            if step.analogy and has_unbound_quantity('生活类比：'+step.analogy):
                raise TeachingDesignError('生活类比不得加入未经核验的技术测量或数值。')
        if step.source_statement and step.narration!=step.source_statement+(' 做个生活类比：'+step.analogy if step.analogy else ''):
            raise TeachingDesignError('实际口播必须对应所记录的原文事实与明确标注的类比。')
        if set(step.focus)-nodes.keys() or set(step.relations)-edges.keys():
            raise TeachingDesignError('步骤引用了不存在的节点或关系。')
        for key in step.relations:
            # Context nodes stay visible while one endpoint is emphasized.
            if not {edges[key].source,edges[key].target} & set(step.focus):
                raise TeachingDesignError('关系讲解必须聚焦至少一个相关端点。')
        signature=(tuple(sorted(step.focus)),tuple(sorted(step.relations)),step.source_statement)
        if signature in signatures:
            raise TeachingDesignError('步骤重复同一状态，请推进关系解释或进行比较。')
        signatures.add(signature); used_nodes.update(step.focus); used_edges.update(step.relations)
    if used_nodes!=nodes.keys() or used_edges!=edges.keys():
        raise TeachingDesignError('每个图形对象与关系都必须有对应讲解步骤。遗漏节点：'+
            str(sorted(nodes.keys()-used_nodes))+'；遗漏关系：'+str(sorted(edges.keys()-used_edges))+
            '。补充对应来源事实或在相关步骤中讲解，不能重复同一事实。')
    if not used_edges and not (annotated or comparison):
        raise TeachingDesignError('教学图需要解释对象间关系，不能只有要点列表。')
    return {'passed':True,'representation':diagram.representation,'source_quotes_checked':source_text is not None,
            'node_count':len(nodes),'relation_count':len(edges),'step_count':len(diagram.steps),
            'scope':'原文摘录、对象关系引用与讲解状态推进；语义、专业事实与表达质量仍需复核'}


def prepare_source_assets(pdf_path, output_dir, document):
    """Retain original drawings, including vector figures and scanned images.

    Assets are local program-selected PDF pages, never model-selected file paths.
    Quote rectangles use the PDF's real text coordinates when available.
    """
    import pymupdf
    output_dir.mkdir(parents=True,exist_ok=True)
    catalog={}
    with pymupdf.open(pdf_path) as pdf:
        for page_text in document.pages:
            page=pdf[page_text.page-1]
            target=output_dir/f'page-{page_text.page:04d}.png'
            scale=min(1.6,1400/max(page.rect.width,page.rect.height))
            page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).save(target)
            catalog[page_text.page]={'path':str(target.resolve()),'width':page.rect.width,'height':page.rect.height}
    return catalog


def attach_source_regions(diagram, asset, pdf_path, page_number):
    import pymupdf
    diagram.source_asset=asset['path']
    with pymupdf.open(pdf_path) as pdf:
        page=pdf[page_number-1]
        for node in diagram.nodes:
            rects=page.search_for(node.source_quote)
            if not rects and node.source_term:
                candidates=page.search_for(node.source_term)
                # An ambiguous repeated keyword is not a located source region.
                if len(candidates)==1:rects=candidates
            if rects:
                # Multiple rectangles can span lines; preserve the containing box.
                box=pymupdf.Rect(rects[0])
                for r in rects[1:]: box |= r
                diagram.source_regions[str(node.id)]=[box.x0/page.rect.width,box.y0/page.rect.height,
                                                     box.x1/page.rect.width,box.y1/page.rect.height]


def plan_teaching_representation(client, segment, document, prompt, *, force_diagram=False,diagnostic_output=None,on_phase=None):
    page=next(p for p in document.pages if p.page==segment.evidence.page)
    # Full source page provides context that a short citation alone cannot carry.
    spans=source_spans(page.text)
    if not spans:
        raise TeachingDesignError('当前来源页只有零碎符号或短标签，缺少可核对的说明文字；请核对OCR或提供包含定义与条件的页面。')
    # Ground the design in the cited local context, rather than handing a small
    # model every unrelated formula on a dense page. Review still sees the page.
    from difflib import SequenceMatcher
    citation=normalized(segment.evidence.quote)
    anchor=max(spans,key=lambda key:SequenceMatcher(None,citation,normalized(spans[key]),autojunk=False).find_longest_match().size)
    spans={key:value for key,value in spans.items() if abs(key-anchor)<=3}
    facts=[]
    material_data={'topic':segment.title,'citation':segment.evidence.model_dump(),
                   'sources':[{'id':key,'text':text} for key,text in spans.items()]}
    instruction=(
        '先分析教学内容再选择表达方式。此任务没有学科白名单。本轮只设计对象与关系，不编写口播，steps=[]。'
        'source_facts是先独立理解原文所得的事实，节点和连线只能表达这些事实及其原文依据，不增加中间推论。'
        'question、rationale、label用中文；source_term必须保持原文语言，逐字复制英文、中文或符号，不翻译。'
        'geometry仅用于来源或用户明确给出可计算公式、变量和变化关系的情况；不要凭空编造坐标、斜率或物理路径。'
        'process解释阶段和数据/材料/信息流；relationship解释组成、描述或有原文依据的依赖，不得把描述或相关说成因果；comparison比较方法、条件或结果；'
        'source_figure以原PDF页面和原图为背景逐步讲解，适合实体外观、实验装置或复杂结构。'
        'process/relationship输出2至4个简短节点、1至3个有来源的关系；没有依据的连线不得编造。comparison可不画连线；source_figure可用1至4个对象注释原文页面，也可不画连线。优先解释一个局部核心关系或观察。节点编号从1开始，关系编号从1开始。'
        '每个节点和关系的source_id必须选择sources中已有的编号，程序填入对应的原文摘录；不要自行复制或改写引文。'
        '节点source_term只复制该片段中一个准确的原文术语，优先选择简短对象名或单个符号，不要把整个公式、维数或条件塞入术语。关系只选source_id，程序保留其原文。'
        '关系原文及紧邻片段必须包含两端节点的source_term；不同对象的source_term不能相同。比较模式可对照两个有依据的对象，但不要捏造因果。'
        '口播只作定性解释，不写步数、维数、预测值或其他具体数字；符号中的数字只能作为已声明source_term的一部分。'
        '严格辨别相邻句子的术语指代；多个符号出现于同一页，并不证明它们组成同一个公式或共同保证某个性质。'
        '只画当前片段的核心概念。所有节点保持可见；讲解步骤将在后续单独设计。'
        '画图坐标、颜色、布局、连线和逐步高亮由程序生成，你只设计教学对象及有依据的关系。'
        '口播用节点名称指代对象，不猜测颜色。'
        '动效表示讲解顺序和关系追踪，不冒充来源未给出的三维运动或物理模拟。'
        '不输出未核验数字，不把先前例子的对象或参数套用在本资料。geometry时nodes/relations/steps为空数组。'
        '\n用户偏好：'+prompt)
    if force_diagram:
        instruction+='\n几何候选已不可执行。本次选择有原文依据的process/relationship/comparison/source_figure，不再输出geometry。'
    failures=[];attempts=[]
    def phase(name):
        if on_phase:on_phase(name)
        if diagnostic_output:
            diagnostic_output.write_text(json.dumps({'sources':spans,'source_facts':facts,'phase':name,'attempts':attempts},ensure_ascii=False,indent=2),encoding='utf-8')
    phase('独立理解原文事实')
    reading_path=diagnostic_output.with_name(diagnostic_output.name.replace('teaching-design','source-reading').replace('teaching-redesign','source-rereading')) if diagnostic_output else None
    facts,reading_cached=source_reading(client,spans,reading_path,ocr=page.ocr)
    material_data['source_facts']=facts
    material=json.dumps(material_data,ensure_ascii=False)
    structure_path=diagnostic_output.with_name(diagnostic_output.name.replace('teaching-design','source-structure').replace('teaching-redesign','source-restructure')) if diagnostic_output else None
    structure_hash=structure_fingerprint(client,material,prompt,force_diagram)
    cached_structure=load_structure(structure_path,structure_hash,page.text)
    for attempt in range(3):
        from zhijiang.agents import GenerationError
        attempts.append({})
        try:
            phase('设计对象与关系')
            annotation=attempt==2
            if cached_structure is not None:
                draft=cached_structure;cached_structure=None
                attempts[-1]['structure_cached']=True
            else:
                draft=client.generate(structure_schema(spans,source_annotation=annotation,facts=facts),instruction+
                '\n中文label只选择source_facts中实际出现的对象名。每条relations只选择source_fact_id和两端编号，不输出label/source_id。'
                '程序取该事实中两个中文端点之间的原文词语作为谓词；顺序必须为主语→谓词→宾语，中间不可跨标点、不可遗漏否定词或条件。'
                '被动句、复杂从句或无法直接表达的关系选择比较图或原页标注，不强行改写为箭头。'+
                ('\n修正依据：'+failures[-1] if failures else '')+
                ('\n若来源没有直接支持关系，请选择source_figure或comparison并保持relations=[]，保留独立的原文事实，不能为连接所有节点编造连线。' if failures else '')+
                ('\n前两次设计未通过，本次保留原PDF页面，只为来源事实设计中文注释对象，representation=source_figure，relations=[]；来源和口播含义仍须通过检查。' if annotation else '')+
                    '\n最后检查：source_term必须是sources原文中的连续片段，绝不能翻译；本轮steps必须为空数组。',material)
            attempts[-1]['draft']=draft.model_dump()
            if draft.representation=='geometry':
                if force_diagram: raise TeachingDesignError('本次必须重新选择表达方式。')
                phase('选择可计算几何')
                return draft,None,failures
            repairs=[]
            if not attempts[-1].get('structure_cached'):
                draft=resolve_design(draft,spans,repairs,facts)
            topic_facts=preserve_topic_focus(draft,facts,segment.title)
            source_examples=prefer_source_example(draft,facts,prompt)
            source_sequence=preserve_source_sequence(draft,facts)
            attempts[-1]['topic_facts']=topic_facts
            attempts[-1]['source_examples']=source_examples
            attempts[-1]['source_sequence']=source_sequence
            selected_facts=diagram_source_facts(draft,facts)
            draft.source_facts=[TeachingSourceFact.model_validate(fact) for fact in selected_facts]
            attempts[-1]['reference_repairs']=repairs
            validate_diagram(draft,page.text,require_steps=False)
            # Metadata describes the selected view, without introducing another
            # unbound technical claim into the page or PPT heading.
            view_names={'process':'过程图','relationship':'关系图','comparison':'比较图','source_figure':'原文图示讲解'}
            draft.question=f'怎样理解{segment.title[:60]}？'
            draft.rationale=f'采用{view_names[draft.representation]}，按独立来源事实逐步讲解，保留原文条件。'
            attempts[-1]['bound_metadata']={'question':draft.question,'rationale':draft.rationale}
            save_structure(structure_path,structure_hash,draft)
            phase('规划逐步讲解')
            script_instruction=(
                '为已确定且有原文依据的教学对象和关系选择一至五步中文讲解，条数由资料实际含义决定，不凑数。'
                '只解释本图，不扩展到同页的其他内容。fact_id只选择source_facts中已存在的事实编号；程序直接使用该事实，不输出source_statement或narration，也不能改写事实。'
                'steps只选择fact_id，不写focus/relations/analogy。程序将当前事实对应的对象与关系绑定到画面，不能为一个事实高亮另一个事实的对象。根级example单独保存一个生活类比，包含fact_id和analogy。'
                '只有用户明确请求生活例子或类比且原文未提供示例时，才生成example；其他情况example必须为null。example.fact_id必须属于steps里已选择的事实；analogy为12至80字完整句子，以句号结束，不截断。'
                '类比只描述日常对象的操作及对应关系，不描述教材中的技术对象做了什么、感到了什么或必然成功。'
                '避免保证、确保、一定、才不会、只要就能等承诺句，不把测试说成成功保证；只说明更容易观察或理解的对应关系。'
                '类比不要出现这些当前来源实体名：'+ '、'.join(analogy_source_names(selected_facts))+ '。'+
                '类比不需要出现在原文中，但不能添加技术事实或声称物理等价。程序把事实和明确标注的类比合成口播。'
                '每步选择不同的来源观察或追踪不同的关系，不要换个类比重复同一事实。'
                '普通不定指和明确标注的生活类比可以自然表达，不能把类比说成技术性的精确数量或规律。'
                '已请求的生活类比必须明确标注，不添加来源没有的保证或因果；数值推演交由计算场景核验，不在类比里补写数值。'
                '选择的事实必须覆盖每个节点和关系；同一对象的不同原文事实可以逐步解释，但不能重复同一事实。'
                '所有对象始终可见，图示追踪信息或解释关系，不冒充真实物理运动。'
                '\n用户偏好：'+prompt)
            script_errors=[];attempts[-1]['script_attempts']=[]
            require_analogy=bool(re.search(r'类比|生活|例子',prompt)) and not bool(
                re.search(r'(?:不要|不用|不需要|不必|避免).{0,8}(?:类比|生活|例子)',prompt))
            for _ in range(3):
                try:
                    script=client.generate(script_schema(draft,selected_facts,require_analogy=require_analogy,source_examples=source_examples,source_sequence=source_sequence,topic_facts=topic_facts),script_instruction+
                        ('\n当前主题必须讲清这些核心来源事实：'+str(topic_facts)+'。先介绍主题，按原文操作顺序讲解，最后总结结果。' if topic_facts else '')+
                        ('\n必须保留这些明确的原文操作，并按此顺序讲解：'+str(source_sequence)+'；不能从初态直接跳到结论。' if source_sequence else '')+
                        ('\n原文已经提供示例，必须选择这些事实编号作为独立讲解步骤：'+str(source_examples)+'。example=null，不另编类比。' if source_examples else
                         ('\n用户请求生活例子，必须在example中给出一个完整生活类比，不在steps中写类比。' if require_analogy else ''))+
                        ('\n必须修正：'+script_errors[-1] if script_errors else ''),
                        json.dumps({'design':draft.model_dump(exclude={'steps'})},ensure_ascii=False))
                except GenerationError as exc:
                    script_errors.append(str(exc));attempts[-1]['script_attempts'].append({'error':str(exc)})
                    phase('修正讲解格式');continue
                raw_script=script.model_dump()
                script=bind_script_focus(script,draft,selected_facts)
                display_repairs=complete_relation_focus(script,draft.relations)
                draft.steps=compose_script(script,selected_facts)
                attempts[-1]['script_attempts'].append({'script':raw_script,'display_repairs':display_repairs})
                try:
                    diagram=TeachingDiagram.model_validate(draft.model_dump(exclude={'question'}))
                    report=validate_diagram(diagram,page.text)
                    report['display_repairs']=display_repairs
                    break
                except (TeachingDesignError,ValueError) as exc:
                    script_errors.append(str(exc))
                    attempts[-1]['script_attempts'][-1]['error']=str(exc)
                    phase('修正讲解步骤')
            else:
                raise TeachingDesignError('逐步讲解未通过：'+script_errors[-1])
            phase('核对来源含义')
            review=client.generate(meaning_review_schema(draft),
                '核对教学图的对象、关系和逐步口播是否忠实于source_page。source_facts来自独立原文理解，核查其翻译是否忠实，不把候选设计当依据。每条source_quote已逐字核对，但还须检查它是否真的支持该节点/关系。'
                '必须逐个完成node_checks、relation_checks、step_checks。source_meaning只转述原文实际表达的含义，reason比较它与候选内容，不复述候选当作依据。'
                'source_meaning忠实转述原文含义，2至120字；原文只提及对象时可保留简短名称，不凑句子、不补推论。reason用12至120字中文解释核对理由。节点、关系、事实和类比分别判断；不能因为连线错误而否认原文明确提到的独立对象。'
                '每条关系核对原文实际的主体、谓词和宾语：共现不等于关系，修饰的对象不是该端点时supported=false，不能推断缺失的中间因果。'
                '逐句核对口播：原文只说有帮助，不能升级成保证、完整覆盖、必要条件或必然结果；原文没有的前提和普遍断言必须拒绝。'
                'step_checks核对source_statement是否保留原文事实与条件，并检查analogy是否仅辅助理解。analogy是用户允许的原创教学补充，不要求原文使用同一类比，不能以“原文未提到该类比”拒绝；只有类比歪曲概念、增加技术事实或保证时拒绝。'
                '逐项回查符号定义、时间范围、输入输出和每条关系的端点；不要混淆相邻句子的不同符号。'
                '来源只描述输入信息或表示方法时，不得声称这些输入自动保证物理规律、结果质量或预测成功。'
                '逐字核对source_term的中文label翻译；例如状态、变化、输入或输出不能混为一谈。'
                '不要批准虚构因果、误译、错误概念或把示意当物理模拟。只检查当前知识点。',
                json.dumps({'source_page':page.text,'design':draft.model_dump()},ensure_ascii=False))
            attempts[-1]['semantic_review']=review.model_dump()
            if diagnostic_output:
                diagnostic_output.write_text(json.dumps({'sources':spans,'source_facts':facts,'attempts':attempts},ensure_ascii=False,indent=2),encoding='utf-8')
            validate_meaning_review(review,draft)
            report['semantic_review']=review.model_dump()
            report['source_facts']=selected_facts
            report['source_reading_cached']=reading_cached
            report['source_examples']=source_examples
            report['source_sequence']=source_sequence
            report['topic_facts']=topic_facts
            report['reference_repairs']=repairs
            return draft,report,failures
        except (TeachingDesignError,ValueError,GenerationError) as exc:
            failures.append(str(exc))
            attempts[-1]['error']=str(exc)
            if diagnostic_output:
                diagnostic_output.write_text(json.dumps({'sources':spans,'source_facts':facts,'attempts':attempts},ensure_ascii=False,indent=2),encoding='utf-8')
    raise TeachingDesignError('教学表达设计未通过：'+failures[-1])


def compile_teaching_scene(draft, segment, report, *, source_assets=None, pdf_path=None, source_text=''):
    diagram=TeachingDiagram.model_validate(draft.model_dump(exclude={'question'}))
    if diagram.representation=='source_figure' and source_assets and pdf_path:
        attach_source_regions(diagram,source_assets[segment.evidence.page],pdf_path,segment.evidence.page)
    # Legacy consumers retain a valid visual_scene; its diagram drives rendering.
    scene=VisualScenePlan(domain=segment.title[:40],question=draft.question,evidence=segment.evidence,
        objects=[SceneObject(id='reference',position=['0','0']),SceneObject(id='explanation',position=['1','0'])],
        beats=[VisualBeat(narration=s.narration) for s in diagram.steps],diagram=diagram,
        domain_data={'source_page_text':source_text},
        teaching_example=any(step.analogy for step in diagram.steps),
        simplifications=['原文页面标注与关系追踪表示讲解顺序，不是实体运动或真实动力学。',
            '明确标注的生活类比是教学补充，原文事实与类比分开记录。'])
    scene.verification=report
    return scene
