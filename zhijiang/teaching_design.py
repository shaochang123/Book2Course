"""Source-grounded pedagogical design, independent of geometric syntax/subjects."""
from __future__ import annotations

import json
import hashlib
import re
import os
import unicodedata
from pathlib import Path
from typing import Literal,Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, model_validator
from pydantic_core import PydanticCustomError

from zhijiang.models import (TeachingDiagram, TeachingNode, TeachingRelation, TeachingStep, TeachingSourceFact,
                             SceneObject, VisualBeat, VisualScenePlan)


class TeachingDesignError(ValueError):
    pass


class DesignNodeDraft(BaseModel):
    id: int = Field(ge=1,le=6)
    label: str = Field(min_length=2,max_length=48,pattern=r'^[^\r\n]{2,48}$')
    source_id: int = Field(ge=1)
    source_term: str = Field(min_length=1,max_length=64,pattern=r'^[^\r\n]{1,64}$')
    kind: Literal['entity','operation','condition'] = 'entity'


class DesignRelationDraft(BaseModel):
    id: int = Field(ge=1,le=8)
    source: int = Field(ge=1,le=6)
    target: int = Field(ge=1,le=6)
    label: str = Field(min_length=1,max_length=32,pattern=r'^[^\r\n]{1,32}$')
    source_id: int = Field(ge=1)
    source_fact_id: int | None = Field(default=None,ge=1)
    binding: Literal['extractive', 'semantic'] = 'extractive'
    supporting_fact_ids: list[int] = Field(default_factory=list,max_length=2)
    source_proposition_id: int | None = Field(default=None,ge=1)


class FactRelationSelection(BaseModel):
    """Old extractive selections remain readable; new edges name a meaning."""
    @model_validator(mode='before')
    @classmethod
    def legacy_selection(cls,value):
        if isinstance(value,dict) and not value.get('label'):
            return {**value,'binding':'extractive','label':'来源关系'}
        return value


def source_condition(statement):
    """Retain a complete literal conditional clause, never infer a new one."""
    match=re.match(r'^((?:如果|若|当|只有|除非)[^，。！？；,]{2,110})[，,]',statement)
    return match.group(1) if match else ''


def condition_label(condition):
    return re.sub(r'^(?:如果|若|当|只有|除非)','',condition)


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
        tokens=[];offset=0;fact_names=set()
        for token in jieba.posseg.cut(text):
            tokens.append((token.word,offset,offset+len(token.word),token.flag));offset+=len(token.word)
        for index,(_,start,_,flag) in enumerate(tokens):
            # Actions also form entity names (审核人员、缓存结果、装配设备).
            # POS tags are lexical hints, not a whitelist of allowable concepts.
            if not (flag.startswith(('n','a','v','m')) or flag in {'eng','l','i','j'}):continue
            for count in range(1,6):
                if index+count>len(tokens):break
                end=tokens[index+count-1][2];value=text[start:end]
                end_flag=tokens[index+count-1][3]
                if (2<=len(value)<=24
                        and (end_flag.startswith(('n','a','v','m')) or end_flag in {'eng','l','i','j'})
                        and not re.search(r'[，。！？；：、（）()\[\]{};,:.!?]',value)):
                    fact_names.add(value)
        if not fact_names:
            # Some definitions/processes contain quantity phrases or actions,
            # not POS-tagged nouns. Offer only literal token spans for annotation;
            # the source review still decides whether the selected label teaches
            # this fact. No discipline glossary or invented object is involved.
            for index,(_,start,_,_) in enumerate(tokens):
                for count in range(1,6):
                    if index+count>len(tokens):break
                    value=text[start:tokens[index+count-1][2]]
                    if (2<=len(value)<=24 and re.search(r'[\u4e00-\u9fff]',value)
                            and not re.search(r'[，。！？；：、（）()\[\]{};,:.!?\s]',value)):
                        fact_names.add(value)
        labels.update(fact_names)
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
    if relation.binding == 'semantic':
        ids = [relation.source_fact_id, *relation.supporting_fact_ids]
        if len(set(ids)) != len(ids) or any(key not in by_id for key in ids):
            raise TeachingDesignError('关系必须选择不同且已有的来源事实编号。')
        selected = [by_id[key] for key in ids]
        premise=source_condition(fact['statement'])
        for node in (endpoints[relation.source], endpoints[relation.target]):
            if not any(fact_mentions_node(node,item) and (
                    getattr(node, 'source_quote', None) == item['source_quote']
                    or getattr(node, 'source_id', None) == item['source_id'])
                    and (not node.source_term or normalized(node.source_term) in normalized(item['source_quote']))
                    for item in selected):
                raise TeachingDesignError('关系端点必须分别绑定所选来源事实，不能仅凭同页共现连接。')
        source_node=endpoints[relation.source]
        if source_node.kind=='condition' and premise and source_node.label!=condition_label(premise):
            raise TeachingDesignError(f'条件分支错配：节点{source_node.id}（{source_node.label}）不能作为“{premise}”的条件起点；'
                '请从共同的检查步骤分别连接各条件和操作，不把不同条件连成同一分支。')
        if not relation.supporting_fact_ids and relation.source_proposition_id is None:
            try:
                direct=bind_fact_relation(relation.model_copy(update={'binding':'extractive'}),nodes,facts)
            except TeachingDesignError:
                pass  # Passive/conditional clauses require semantic review.
            else:
                relation.label=direct.label
        relation.source_id = fact['source_id']
        return relation
    left=endpoints[relation.source].label;right=endpoints[relation.target].label
    statement=fact['statement'];starts=[m.start() for m in re.finditer(re.escape(left),statement)]
    predicates=[]
    for start in starts:
        after=start+len(left);finish=statement.find(right,after)
        if finish<0:continue
        predicate=statement[after:finish].strip()
        if (1<=len(predicate)<=18 and not re.search(r'[，。！？；：、（）]',predicate)
                and predicate not in {'和','与','及','或','以及','或者','同时','之间','及其','和其','与其'}):
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


def select_literal_source_facts(client,spans,repairs=None):
    """Retain readable source assertions when numeric guesses exhaust a draft."""
    from zhijiang.agents import _readable_source_clauses
    candidates={}
    for source_id,quote in spans.items():
        for clause in _readable_source_clauses({'quote':quote}):
            statement=clause+'。'
            try:SourceFactDraft(source_id=source_id,statement=statement)
            except ValueError:continue
            if scanned_fact_issues(statement,quote):continue
            if not any(item['statement']==statement for item in candidates.values()):
                candidates[len(candidates)+1]={'source_id':source_id,'statement':statement}
    if not candidates:return []
    schema=create_model('SourceFactClauseSelection',
        clause_ids=(list[Literal[tuple(candidates)]],Field(min_length=1,max_length=min(8,len(candidates)))))
    selection=client.generate(schema,
        '选择可独立讲解的完整原文说明句编号，只选句意明确的定义、规则或条件。'
        '忽略未作答的问题、残片和相邻背景，不凑条数，不补写公式。只返回clause_ids，程序逐字填入原句；后续仍须核对原文含义。',
        json.dumps({'source_clauses':[{'id':key,**item} for key,item in candidates.items()]},ensure_ascii=False))
    facts=[]
    for key in dict.fromkeys(selection.clause_ids):
        item=candidates[key];source_id=item['source_id']
        facts.append({'id':len(facts)+1,**item,'source_quote':spans[source_id]})
    if repairs is not None:
        repairs.append({'method':'literal_source_fact_clauses','selected_clause_ids':selection.clause_ids,
            'facts':facts})
    return facts


def extract_source_facts(client,spans,*,ocr=False,rejections=None,repairs=None):
    """Read source without seeing a candidate explanation or user style prompt.

    This separates comprehension from persuasive narration and avoids a reviewer
    merely copying the generator's unsupported assertions. It is not a formal
    proof of translation; full-page semantic review remains a separate gate.
    """
    if not spans:raise TeachingDesignError('没有可供理解的来源片段。')
    from zhijiang.agents import GenerationError
    # The complete container and source IDs must decode correctly. Each optional
    # record then passes the full statement contract independently, so a short
    # question cannot discard a valid definition in the same response.
    fact=create_model('SourceFactRecord',
        source_id=(Literal[tuple(spans)],Field(description='只选输入来源编号；没有完整原文依据的事实不输出，禁止-1或自拟编号。')),
        statement=(str,Field(min_length=1,max_length=120,pattern=r'^[^\r\n]{1,120}$',
            description='完整中文说明句，以中文句号结束；无依据或未作答的问题不输出。')))
    schema=create_model('SourceFactsDraft',
        facts=(list[fact],Field(min_length=1,max_length=8)))
    instruction=(
        '仅阅读原文，提取可用于讲解的事实，用中文忠实转述。你没有候选分镜或口播，不做教学设计。'
        '每条statement只翻译一个原文断言，保留原文主语、动作、宾语和条件；不要补充解释、类比、因果或评价。'
        '引用的完整术语、被操作的完整字符串和前后示例须原样保留，不拆开翻译或删去冠词、否定词、限定词。'
        '文字排版不足以辨别输入、输出或改动位置时不猜测改动后的示例，只提取明确说明的概念。'
        '原文描述数据时仍写数据，描述训练目标时仍写目标，描述实验结果时保留实验范围。'
        '有帮助或关键不能改写为必要条件、完整还原或成功保证。允许保留原文中的数字与科学名称。'
        'OCR中分数结构缺失、多列数字穿插或无法连读的数值片段不能猜补；优先提取可读的定义、步骤和条件。'
        '未作答的数量问题不作为statement事实；题目仍保留在原PDF页面中，不把问句改成句号来当结论。'
        '忽略作者、机构、参考文献、纯表头及无法理解的截断片段。source_id选择当前编号，statement为12至120字的完整中文句子，以中文句号结束；不能照抄英文或截断词尾。'
        'facts不要求覆盖每个sources条目，只选择清楚的原文断言。不得输出自行推算的结果，不得使用-1或虚构编号。无法绑定完整原文的内容不进入事实数组，不凑条数。')
    try:
        result=client.generate(schema,instruction,
            json.dumps({'sources':[{'id':key,'text':text} for key,text in spans.items()]},ensure_ascii=False))
    except GenerationError as exc:
        if not (ocr and '返回不符合数据契约的 JSON' in str(exc)):
            raise
        # Reject the whole malformed response, not selected fields from it.
        # Recovery can only choose current literal source clauses and still goes
        # through the independent meaning review before becoming a scene.
        if rejections is not None:rejections.append({'kind':'fact_format_error','error':str(exc)})
        facts=select_literal_source_facts(client,spans,repairs)
        if facts:return facts
        raise
    facts=[];seen=set()
    for record in result.facts:
        try:item=SourceFactDraft.model_validate(record.model_dump())
        except ValidationError as exc:
            if rejections is not None:
                issues=[f"{'.'.join(map(str,error['loc']))}:{error['type']}" for error in exc.errors()]
                rejections.append({'source_id':record.source_id,'statement':record.statement,'issues':issues})
            continue
        if item.source_id not in spans:raise TeachingDesignError('来源事实引用了不存在的片段。')
        if problems := scanned_fact_issues(item.statement,spans[item.source_id]):
            if rejections is not None:
                rejections.append({'source_id':item.source_id,'statement':item.statement,'issues':problems})
            continue  # Reject this optional assertion, not the course topic.
        if item.statement in seen:continue
        seen.add(item.statement)
        facts.append({'id':len(facts)+1,'source_id':item.source_id,
                      'source_quote':spans[item.source_id],'statement':item.statement})
    if not facts:
        if ocr:facts=select_literal_source_facts(client,spans,repairs)
        if not facts:
            raise TeachingDesignError('原文事实未通过OCR数值引用检查，需核对原页；不能补写缺失的公式或比例。')
    return facts


def source_reading_fingerprint(client,spans,ocr=False):
    return hashlib.sha256(json.dumps({'version':'ocr-source-reading-v4' if ocr else 'source-reading-v2','spans':spans,
        'semantic_thinking':getattr(client,'semantic_thinking',True),
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
    rejections=[];repairs=[]
    try:
        facts=extract_source_facts(client,spans,ocr=ocr,rejections=rejections,repairs=repairs)
    except TeachingDesignError:
        if path:
            path.write_text(json.dumps({'fingerprint':fingerprint,'facts':[],
                'rejected_facts':rejections,'repairs':repairs,'status':'rejected_requires_source_review'},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    if path:
        path.write_text(json.dumps({'fingerprint':fingerprint,'facts':facts,'rejected_facts':rejections,'repairs':repairs,'status':'draft_requires_semantic_review'},
            ensure_ascii=False,indent=2),encoding='utf-8')
    return facts,False


def structure_fingerprint(client,material,prompt,force_diagram=False):
    return hashlib.sha256(json.dumps({'version':'structure-v3','material':material,'prompt':prompt,
        'semantic_thinking':getattr(client,'semantic_thinking',True),
        'force_diagram':force_diagram,'endpoint':getattr(client,'base_url',''),'model':getattr(client,'model','')},sort_keys=True).encode()).hexdigest()


def save_structure(path,fingerprint,draft):
    if path:
        path.write_text(json.dumps({'fingerprint':fingerprint,'design':draft.model_dump(exclude={'steps'}),
            'status':'draft_requires_semantic_review'},ensure_ascii=False,indent=2),encoding='utf-8')


def literal_source_name(label,source_quote):
    """Return the original spelling of an explicit displayed name, if present."""
    if not label:return None
    pattern=r'\s*'.join(re.escape(char) for char in label)
    if re.match(r'[A-Za-z0-9]',label):pattern=r'(?<![A-Za-z0-9])'+pattern
    if re.search(r'[A-Za-z0-9]$',label):pattern+=r'(?![A-Za-z0-9])'
    match=re.search(pattern,source_quote)
    return match.group() if match else None


def fact_mentions_node(node,fact):
    label=node.label
    return label in fact['statement'] or (bool(re.search(r'[A-Za-z]',label)) and
        bool(literal_source_name(label,fact['source_quote'])))


def fact_covers_node(node,fact):
    """Original-language names can stay on a Chinese-narrated source graph."""
    return node.source_quote==fact['source_quote'] and fact_mentions_node(node,fact)


def bind_literal_node_terms(nodes,spans=None,repairs=None):
    for node in nodes:
        quote=spans.get(node.source_id,'') if spans is not None else node.source_quote
        name=literal_source_name(node.label,quote)
        if name and normalized(node.source_term)!=normalized(name):
            if repairs is not None:
                repairs.append({'field':'nodes','id':node.id,'repair':'literal_node_name',
                    'from_source_term':node.source_term,'to_source_term':name})
            node.source_term=name


def bind_annotation_anchors(draft,repairs):
    """Original-page notes locate full quotes unless the name is literal.

    A translated concept does not assert that a guessed English word is its
    translation. The full quote remains the reviewed evidence and highlight.
    Graph endpoints keep their stricter, independently bound term contract.
    """
    if draft.representation!='source_figure':return
    for node in draft.nodes:
        term=literal_source_name(node.label,node.source_quote) or ''
        if term!=node.source_term:
            repairs.append({'node':node.id,'repair':'annotation_quote_anchor',
                'from_source_term':node.source_term,'to_source_term':term,
                'anchor_scope':'literal_name' if term else 'source_quote'})
            node.source_term=term


def load_structure(path,fingerprint,source_text,*,repairs=None):
    if not path:return None
    try:
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved['fingerprint']!=fingerprint:return None
        draft=ResolvedTeachingDesign.model_validate(saved['design'])
        bind_literal_node_terms(draft.nodes,repairs=repairs)
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
    if draft.representation not in {'source_figure','comparison'}:
        # Explicit "first" is an ordering assertion, even in a graph view.
        # Do not infer a sequence merely from PDF sentence position.
        selected=diagram_source_facts(draft,facts)
        initial=[fact['id'] for fact in selected if re.search(r'首先|起始|最初|\b(?:first|initially)\b',fact['statement'],re.I)]
        if initial:
            return [*initial,*[fact['id'] for fact in selected if fact['id'] not in initial]]
        return []
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


def citation_fact_ids(facts,quote):
    """Identify facts carrying the topic's actual citation, not title synonyms."""
    key=normalized(quote)
    if len(key)<20:return []
    return [fact['id'] for fact in facts if key in normalized(fact['source_quote'])
            or (len(normalized(fact['source_quote']))>=max(20,len(key)*.6)
                and normalized(fact['source_quote']) in key)]


def preserve_topic_focus(draft,facts,topic,quote=''):
    """Bind the current question to its most specific sourced Chinese phrase.

    Phrase frequency discounts generic words across the local readings; no
    discipline glossary or topic-name routing is used. Synonyms still need review.
    """
    citation_ids=citation_fact_ids(facts,quote)
    if citation_ids:
        selected=diagram_source_facts(draft,facts)
        missing=set(citation_ids)-{fact['id'] for fact in selected}
        if missing and draft.representation not in {'source_figure','comparison'}:
            raise TeachingDesignError('当前图示遗漏知识点原始引文的核心事实，请重新选择来源命题或原页注释。')
        for key in missing:
            fact=next(fact for fact in facts if fact['id']==key)
            if len(draft.nodes)>=6:
                raise TeachingDesignError('原页注释遗漏知识点原始引文，请减少次要标注。')
            labels=fact_labels([fact])
            if not labels:raise TeachingDesignError('核心引文没有可标注的来源名称。')
            label=max(labels,key=lambda value:(value in topic,len(value)))
            draft.nodes.append(TeachingNode(id=next(i for i in range(1,7) if i not in {n.id for n in draft.nodes}),
                label=label,source_quote=fact['source_quote'],source_term=''))
        return citation_ids
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
    try:expected=preserve_topic_focus(scene.diagram.model_copy(deep=True),facts,topic,
        getattr(getattr(scene,'evidence',None),'quote',''))
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
    # An object name can be a faithful short meaning. Do not require padding
    # every noun into a fabricated sentence or duplicate length in regex syntax.
    source_meaning: str = Field(min_length=2,max_length=120)
    reason: str = Field(min_length=12,max_length=120)
    # Decode evidence before its verdict to avoid an early boolean followed by
    # an invented justification. An unsupported item still rejects the scene.
    supported: bool


class TeachingSourceReview(BaseModel):
    """Review meanings individually; a single approval flag is insufficient."""
    model_config=ConfigDict(populate_by_name=True)
    node_checks: list[MeaningCheck] = Field(default_factory=list)
    relation_checks: list[MeaningCheck] = Field(default_factory=list)
    step_checks: list[MeaningCheck] = Field(default_factory=list)
    approved: bool
    issues: list[str] = Field(default_factory=list)
    source_warnings: list[str] = Field(default_factory=list,max_length=8)


class ItemizedMeaningReview(BaseModel):
    """Candidate defects belong to an item; raw-source warnings stay separate."""
    model_config=ConfigDict(populate_by_name=True)
    node_checks: list[MeaningCheck] = Field(default_factory=list)
    relation_checks: list[MeaningCheck] = Field(default_factory=list)
    step_checks: list[MeaningCheck] = Field(default_factory=list)
    source_warnings: list[str] = Field(default_factory=list,max_length=8)


def compose_meaning_review(review):
    checks=[check for name in ('node_checks','relation_checks','step_checks') for check in getattr(review,name)]
    return TeachingSourceReview(**review.model_dump(),approved=all(check.supported for check in checks),
        issues=[check.reason for check in checks if not check.supported])


def meaning_review_schema(draft):
    fields={}
    for name,ids in [('node_checks',[n.id for n in draft.nodes]),
                     ('relation_checks',[r.id for r in draft.relations]),
                     ('step_checks',list(range(1,len(draft.steps)+1)))]:
        check=create_model('MeaningCheck_'+name,__base__=MeaningCheck,
            id=(Literal[tuple(ids)] if ids else int,Field(description='ID of the item being reviewed.')))
        alias='annotation_checks' if name=='node_checks' and draft.representation in {'source_figure','comparison'} else None
        fields[name]=(list[check],Field(min_length=len(ids),max_length=len(ids),alias=alias))
    return create_model('TeachingSourceReview',__base__=ItemizedMeaningReview,**fields)


def meaning_review_material(draft,source_page):
    design=draft.model_dump()
    names={node.id:node.label for node in draft.nodes}
    assertions=[{'id':edge.id,'subject':names[edge.source],'predicate':edge.label,'object':names[edge.target],
        'displayed_proposition':f'{names[edge.source]} → {edge.label} → {names[edge.target]}',
        'source_statements':getattr(edge,'source_statements',[]),
        'source_quotes':[edge.source_quote,*getattr(edge,'supporting_quotes',[])]} for edge in draft.relations]
    if draft.representation in {'source_figure','comparison'}:
        # These are labels on a source image/comparison, not independent graph
        # entities. Keep the same IDs, literal anchors and complete fact steps.
        design['annotations']=design.pop('nodes')
    return json.dumps({'source_page':source_page,'design':design,'relation_assertions':assertions},ensure_ascii=False)


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


def meaning_review_instruction(draft):
    roles={
        'source_figure':'nodes是原页文字或图形的注释标签，可标注数量短语、动作、条件或结果；不是一组必须独立成立的实体。',
        'comparison':'nodes是待对照的来源概念、动作、条件或结果，不要求每项都是独立实体。',
        'process':'nodes是来源支持的阶段、动作、材料或信息；关系须支持阶段之间的真实顺序或传递。',
        'relationship':'nodes是来源支持的概念、属性、数量或结果；关系须支持其具体主体、谓词与宾语。',
    }
    annotations=draft.representation in {'source_figure','comparison'}
    item_contract=(
        'annotation_checks逐项核对design.annotations：label是原文标注文字，source_term是其原文定位词。'
        'source_term为空时定位整段source_quote，不声称label是某个英文单词的逐字翻译；仍严格检查label是否由该完整来源事实支持。'
        '写出这个标注在原句中的指代，判断名称及定位词是否对应原文含义。数量、动作、条件、结果或修饰短语均可作为文字标注。'
        '标注文字本身没有断言独立实体或额外关系；有明确指代的原文短语可作为标注。' if annotations else
        'node_checks逐项核对design.nodes的来源指代与含义，按当前表达方式判断。')
    return (
        '核对教学图的对象、关系和逐步口播是否忠实于source_page。source_facts来自独立原文理解，核查其翻译是否忠实，不把候选设计当依据。每条source_quote已逐字核对，但还须检查它是否真的支持该节点/关系。'
        '当前讲解问题是design.question；source_page中的其他练习问句是资料内容，不是当前任务。只核对当前片段，不要求解答整页所有问题。'
        '先写每项的source_meaning与reason，再判断supported；程序根据逐项判定汇总结论。'
        '当前表达方式：'+draft.representation+'。'+roles.get(draft.representation,'')+
        item_contract+
        '指代不符、误译、引入来源没有的对象或含义时supported=false。'
        '没有连线时不假定节点之间存在乘法、因果或其他关系；有连线的关系单独严格检查。'
        '必须逐个完成'+('annotation_checks' if annotations else 'node_checks')+'、relation_checks、step_checks。source_meaning只转述原文实际表达的含义，reason比较它与候选内容，不复述候选当作依据。'
        'source_meaning忠实转述原文含义，2至120字；原文只提及对象时可保留简短名称，不凑句子、不补推论。reason用12至120字中文解释核对理由。节点、关系、事实和类比分别判断。'
        '每条关系核对原文实际的主体、谓词和宾语：共现不等于关系，修饰的对象不是该端点时supported=false，不能推断缺失的中间因果。'
        'relation_assertions展开了实际显示的端点名字；逐条核对该displayed_proposition，不把别的主语或宾语替换进去再批准。'
        'semantic关系可以概括被动句、条件句或相邻操作，但source_statements完整保留独立事实；'
        '必须结合所有这些事实核对方向、限定和否定。跨句共现或原文排版顺序不能证明先后、因果或传递。'
        '摘要label若省去关键否定、范围或条件以致改变关系含义，必须拒绝；可以用“条件成立时”等明确提示，并在对应步骤保留完整条件。'
        '逐句核对口播：原文只说有帮助，不能升级成保证、完整覆盖、必要条件或必然结果；原文没有的前提和普遍断言必须拒绝。'
        'step_checks核对source_statement是否保留原文事实与条件，并检查analogy是否仅辅助理解。原文的有时、可能等限定必须保留；原文未给出具体情境时，不要求候选额外推导或补写情境。'
        'analogy是用户允许的原创教学补充，不要求原文使用同一类比，不能以“原文未提到该类比”拒绝；只有类比歪曲概念、增加技术事实或保证时拒绝。'
        '逐项回查符号定义、时间范围、输入输出和每条关系的端点；不要混淆相邻句子的不同符号。'
        '来源只描述输入信息或表示方法时，不得声称这些输入自动保证物理规律、结果质量或预测成功。'
        '逐字核对source_term的中文label翻译；例如状态、变化、输入或输出不能混为一谈。'
        '不要批准虚构因果、误译、错误概念或把示意当物理模拟。只检查当前知识点。')


def structure_schema(spans,*,source_annotation=False,facts=None,propositions=None):
    """Select actual source phrases; no subject-specific object vocabulary."""
    if not spans:raise TeachingDesignError('没有可用于分镜设计的来源片段。')
    source_id=Literal[tuple(spans)]
    source_term=Literal[tuple(source_terms(spans))]
    if facts is not None:
        variants=[]
        for fact in facts:
            labels=fact_labels([fact])
            if propositions and not source_annotation:
                # Graph design chooses independently read roles, rather than
                # decoding thousands of arbitrary POS-token combinations.
                labels=sorted({p[field] for p in propositions for field in ('subject','object')
                    if p[field] in fact['statement']})
            if not labels:continue
            variants.append(create_model('FactNode_'+str(fact['id']),__base__=DesignNodeDraft,
                source_id=(Literal[fact['source_id']],Field()),
                label=(Literal[tuple(labels)],Field(description='Chinese phrase from this source fact.')),
                source_term=(Literal[tuple(source_terms({fact['source_id']:fact['source_quote']})[:96])],Field(description='Original-language term from this same source.'))))
        if not variants:raise TeachingDesignError('独立来源事实没有可用于标注的对象，请核对原文理解。')
        node=Union[tuple(variants)]
    else:
        node=create_model('DesignNodeDraft',__base__=DesignNodeDraft,
            source_id=(source_id,Field(description='Choose an existing source ID.')),
            source_term=(source_term,Field(description='Select an exact phrase from the current sources. NEVER translate.')))
    relation=create_model('DesignRelationDraft',__base__=DesignRelationDraft,
        source_id=(source_id,Field(description='Choose evidence containing both endpoint terms.')))
    if facts:
        # The model describes a relation, while its complete evidence is filled
        # from independent readings. Literal substring parsing cannot handle
        # passive clauses, conditions, or operations spanning sentences.
        relation=create_model('FactRelationSelection',__base__=FactRelationSelection,id=(int,Field(ge=1,le=8)),
            source=(int,Field(ge=1,le=6)),target=(int,Field(ge=1,le=6)),
            label=(str,Field(default='来源关系',min_length=1,max_length=32,pattern=r'^[^\r\n]{1,32}$',
                description='忠实的关系说明，保留否定与条件；共现不是因果。')),
            binding=(Literal['semantic','extractive'],Field(default='semantic')),
            source_fact_id=(Literal[tuple(fact['id'] for fact in facts)],Field()),
            supporting_fact_ids=(list[Literal[tuple(fact['id'] for fact in facts)]],
                Field(default_factory=list,max_length=2,description='跨句关系所需的补充事实；没有依据则不连接。')))
        if propositions:
            relation=create_model('SourcePropositionSelection',__base__=FactRelationSelection,
                id=(int,Field(ge=1,le=8)),source=(int,Field(ge=1,le=6)),target=(int,Field(ge=1,le=6)),
                source_proposition_id=(Literal[tuple(p['id'] for p in propositions)],Field()))
    fields={}
    if source_annotation:
        # Preserve actual source art/facts when relationship planning fails;
        # never weaken the source or semantic gates to connect the diagram.
        fields['representation']=(Literal['source_figure'],Field())
    return create_model('TeachingDesignDraft',__base__=TeachingDesignDraft,
        nodes=(list[node],Field(default_factory=list,max_length=4)),
        relations=(list[relation],Field(default_factory=list,max_length=0 if source_annotation or propositions==[] else 3)),
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
        eligible=[fact for fact in facts if any(fact_covers_node(node,fact) for node in draft.nodes)]
        if not eligible:raise TeachingDesignError('来源事实没有可对应的画面对象。')
        # Different facts can share one source excerpt. Counting quotations
        # underestimates required speech and can strand several annotations.
        required=set(source_examples)|set(source_sequence)|set(topic_facts)
        required.update(r.source_fact_id for r in draft.relations if r.source_fact_id)
        for node in draft.nodes:
            matches=[f['id'] for f in eligible if fact_covers_node(node,f)]
            if not matches:raise TeachingDesignError('对象没有对应的独立事实：'+node.label)
            if not required.intersection(matches):required.add(matches[0])
        if len(required)>5:raise TeachingDesignError('当前对象与关系需要超过五个独立事实，请拆分或简化当前片段。')
        step=create_model('GroundedStepSelection',
            fact_id=(Literal[tuple(item['id'] for item in eligible)],Field(description='Select an independent fact. Required coverage IDs: '+str(sorted(required)))))
        example=create_model('EverydayExampleDraft',__base__=EverydayExampleDraft,
            fact_id=(Literal[tuple(item['id'] for item in eligible)],Field()))
        schema=create_model('TeachingScriptDraft',__base__=GroundedScriptDraft,
            steps=(list[step],Field(min_length=max(1,len(required)),max_length=min(5,len(eligible)))),
            example=(example,Field(description='Exactly one complete everyday analogy for a selected fact.'))
                if require_analogy and not source_examples else
                (type(None),Field(default=None,description='Use source facts only; no additional everyday analogy was requested or the source already supplies an example.')))
        # Request a useful example once, rather than forcing an analogy per fact.
        def check_examples(self):
            if required-{step.fact_id for step in self.steps}:
                raise PydanticCustomError('source_coverage_required','讲解必须覆盖当前全部对象与关系的来源事实：'+str(sorted(required)))
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
        focus=[node.id for node in draft.nodes if fact_covers_node(node,fact)]
        relations=[relation.id for relation in draft.relations
                   if step.fact_id in [relation.source_fact_id,*relation.supporting_fact_ids]]
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


def resolve_design(draft, spans, repairs=None,facts=None,propositions=None):
    if propositions is not None:
        from zhijiang.teaching_graph import bind_source_propositions
        draft=bind_source_propositions(draft,propositions,facts)
    # Decoder models carry Literal constraints. Normalize before repairing a
    # literal PDF term, otherwise later serialization treats valid repairs as
    # values outside the original grammar and emits misleading union warnings.
    data=draft.model_dump()
    if facts:
        data['relations']=[{**value,'source_id':value.get('source_id',1),
                            'label':value.get('label','来源关系')} for value in data['relations']]
    draft=TeachingDesignDraft.model_validate(data)
    if facts:
        for node in draft.nodes:
            for fact in facts:
                if fact['source_id']!=node.source_id:continue
                if draft.representation in {'source_figure','comparison'} and node.label in fact['statement']:
                    import jieba.posseg
                    tokens=list(jieba.posseg.cut(node.label))
                    if tokens and tokens[-1].flag.startswith('v'):
                        start=fact['statement'].find(node.label)
                        phrase=re.split(r'[，。！？；：,;!?]',fact['statement'][start:],maxsplit=1)[0]
                        # Complete a verb-ending annotation from this exact
                        # independent statement, then review the expanded label.
                        if len(node.label)<len(phrase)<=24:
                            if repairs is not None:repairs.append({'field':'nodes','id':node.id,
                                'repair':'complete_source_phrase','from_label':node.label,'to_label':phrase})
                            node.label=phrase
                full=condition_label(source_condition(fact['statement']))
                # A truncated compound condition is not a meaningful entity.
                # Restore only an exact prefix of the independent statement.
                if full and (node.label==full or (len(node.label)>=6 and re.search(r'且|或|并',node.label)
                                                   and full.startswith(node.label))):
                    if len(full)>24:
                        raise TeachingDesignError('条件节点需使用完整条件；过长的条件请保留为原文标注。')
                    if repairs is not None and node.label!=full:
                        repairs.append({'field':'nodes','id':node.id,'repair':'complete_source_condition',
                            'from_label':node.label,'to_label':full})
                    node.label=full;node.kind='condition'
                    node.source_term=literal_source_name(full,spans[node.source_id]) or node.source_term
    bind_literal_node_terms(draft.nodes,spans,repairs)
    if facts:
        data=draft.model_dump()
        bound=[]
        for value in data['relations']:
            selection=DesignRelationDraft(**{**value,'label':value.get('label','来源关系'),'source_id':1})
            if selection.binding=='semantic':
                # Fill unambiguous endpoint citations, not an inferred relation.
                # The meaning/direction still has to pass the independent review.
                # Small models often select the right objects but omit an ID.
                supporting=list(selection.supporting_fact_ids)
                for node in draft.nodes:
                    if node.id not in (selection.source,selection.target):continue
                    matches=[fact['id'] for fact in facts if fact['source_id']==node.source_id
                             and node.label in fact['statement']]
                    if len(matches)==1 and matches[0] not in [selection.source_fact_id,*supporting]:
                        supporting.append(matches[0])
                if len(supporting)>2:
                    raise TeachingDesignError('关系涉及过多来源事实，请拆分为局部关系。')
                if supporting!=selection.supporting_fact_ids:
                    if repairs is not None:
                        repairs.append({'field':'relations','id':selection.id,'repair':'endpoint_fact_citations',
                            'from_fact_ids':selection.supporting_fact_ids,'to_fact_ids':supporting,
                            'reason':'Only bind exact endpoint facts; semantic review must still check the relation.'})
                    selection.supporting_fact_ids=supporting
            resolved=bind_fact_relation(selection,draft.nodes,facts)
            if repairs is not None and resolved.label!=value.get('label'):
                repairs.append({'field':'relations','id':resolved.id,'repair':'literal_fact_predicate',
                    'from_label':value.get('label'),'to_label':resolved.label})
            bound.append(resolved.model_dump())
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
            if field=='relations':
                item['directed']=draft.representation in {'process','relationship'}
                if item['binding']=='semantic':
                    by_id={fact['id']:fact for fact in facts}
                    selected=[by_id[i] for i in [item['source_fact_id'],*item['supporting_fact_ids']]]
                    item['supporting_quotes']=list(dict.fromkeys(f['source_quote'] for f in selected[1:]))
                    item['source_statements']=[f['statement'] for f in selected]
                    item['condition']=source_condition(selected[0]['statement'])
                    continue
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
    for node in anchored:
        name=literal_source_name(node.label,node.source_quote)
        if name and normalized(node.source_term)!=normalized(name):
            raise TeachingDesignError('节点名称在原文中明确出现时，source_term必须绑定该名称，不能高亮无关数字或符号：'+node.label)
    if not annotated and len({normalized(n.source_term) for n in anchored})!=len(anchored):
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
            if not any(fact_covers_node(node,fact.model_dump()) for fact in facts.values()):
                raise TeachingDesignError(f'节点{node.id}（{node.label}）的名称与所选来源不对应；中文名称必须出现在同一来源事实中，不能重新命名为不同概念。')
        for relation in diagram.relations:
            if relation.source_fact_id is None:
                raise TeachingDesignError('事实绑定图的连线缺少独立来源事实编号。')
            candidate=DesignRelationDraft(**relation.model_dump(exclude={'source_quote','source_term','supporting_quotes','directed','source_statements','condition'}),source_id=1)
            expected=bind_fact_relation(candidate,diagram.nodes,[fact.model_dump() for fact in facts.values()])
            if relation.label!=expected.label or relation.source_quote!=facts[relation.source_fact_id].source_quote:
                raise TeachingDesignError('连线主语、谓词和宾语必须与独立来源事实一致，不得改写或交换。')
            if relation.binding=='semantic':
                selected=[facts[key] for key in [relation.source_fact_id,*relation.supporting_fact_ids]]
                if (relation.source_statements!=[fact.statement for fact in selected]
                        or relation.supporting_quotes!=list(dict.fromkeys(fact.source_quote for fact in selected[1:]))):
                    raise TeachingDesignError('关系必须完整保留所选来源事实及条件，不能修改或删去补充来源。')
                if relation.condition!=source_condition(selected[0].statement):
                    raise TeachingDesignError('关系条件必须绑定完整来源条件，不能省略或改写。')
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
            context={step.source_fact_id}
            for key in step.relations:
                if key in edges and edges[key].binding=='semantic':
                    context.update([edges[key].source_fact_id,*edges[key].supporting_fact_ids])
            if any(not any(fact_covers_node(nodes[key],facts[fid].model_dump())
                           for fid in context) for key in step.focus if key in nodes):
                raise TeachingDesignError('讲解焦点必须对应当前来源事实中的对象，不能错配其他原文。')
            if any(step.source_fact_id not in [edges[key].source_fact_id,*edges[key].supporting_fact_ids]
                   for key in step.relations if key in edges):
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


def prepare_source_assets(pdf_path, output_dir, document, *, progress=None):
    """Retain original drawings, including vector figures and scanned images.

    Assets are local program-selected PDF pages, never model-selected file paths.
    Quote rectangles use the PDF's real text coordinates when available.
    """
    import pymupdf
    output_dir.mkdir(parents=True,exist_ok=True)
    fingerprint='source-page-assets-v1:'+hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    manifest=output_dir/'assets.json';saved={};entries={}
    try:
        metadata=json.loads(manifest.read_text(encoding='utf-8'))
        if metadata['fingerprint']==fingerprint:saved=metadata['pages']
    except (OSError,ValueError,KeyError):pass
    catalog={}
    with pymupdf.open(pdf_path) as pdf:
        for index,page_text in enumerate(document.pages,start=1):
            page=pdf[page_text.page-1]
            target=output_dir/f'page-{page_text.page:04d}.png'
            old=saved.get(str(page_text.page),{})
            try:cached=old.get('image_sha256')==hashlib.sha256(target.read_bytes()).hexdigest()
            except OSError:cached=False
            if not cached:
                scale=min(1.6,1400/max(page.rect.width,page.rect.height))
                page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False).save(target)
            entries[str(page_text.page)]={'image_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
            catalog[page_text.page]={'path':str(target.resolve()),'width':page.rect.width,'height':page.rect.height}
            if progress:progress(index,len(document.pages),'复用原页插图' if cached else '导出原页插图')
    temporary=manifest.with_suffix('.tmp')
    temporary.write_text(json.dumps({'fingerprint':fingerprint,'pages':entries}),encoding='utf-8')
    os.replace(temporary,manifest)
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
        'question、rationale用中文；label可保留原文语言的专业名称、符号或被操作字符串，不能截断或为凑中文加上句子动词。source_term保持原文语言，不翻译。'
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
    from zhijiang.teaching_graph import (source_propositions,validate_source_propositions,
        graph_design_schema,design_from_propositions)
    phase('独立提取来源命题')
    propositions_path=reading_path.with_name(reading_path.name.replace('reading','propositions')) if reading_path else None
    propositions=source_propositions(client,facts,propositions_path)
    material_data['source_facts']=facts
    material_data['source_propositions']=propositions
    material=json.dumps(material_data,ensure_ascii=False)
    structure_path=diagnostic_output.with_name(diagnostic_output.name.replace('teaching-design','source-structure').replace('teaching-redesign','source-restructure')) if diagnostic_output else None
    structure_hash=structure_fingerprint(client,material,prompt,force_diagram)
    cached_term_repairs=[]
    cached_structure=load_structure(structure_path,structure_hash,page.text,repairs=cached_term_repairs)
    for attempt in range(4):
        from zhijiang.agents import GenerationError
        attempts.append({})
        try:
            phase('设计对象与关系')
            # Without independently bound propositions, a link-free relation
            # diagram has no valid contract. Request source annotations now.
            annotation=attempt>=2 or not propositions
            if cached_structure is not None:
                draft=cached_structure;cached_structure=None
                attempts[-1]['structure_cached']=True
            else:
                schema=graph_design_schema(propositions) if propositions and not annotation else structure_schema(
                    spans,source_annotation=annotation,facts=facts,propositions=propositions)
                draft=client.generate(schema,instruction+
                '\n节点label只选择source_facts中实际出现的对象或操作名称。每条relations选择source_fact_id、两端编号和简短中文label。'
                '连线只能选择独立source_propositions的source_proposition_id，不写label或事实编号；程序复制主语、谓词、宾语及完整条件。'
                '两端节点label必须与该命题的subject、object完全相同，方向不能交换。没有命题可选时画比较或原页注释，不连线。'
                '依据含义确定关系方向，不要求两端在同一句中按字面顺序排列；被动句不要反向，否定不能变肯定，条件不能变必然。'
                '只有原文明确支持操作先后、材料/信息传递或条件依赖时才画箭头。同页共现不是关系，不同步骤在原文出现的顺序不自动构成流程。'
                '关系label保留否定和必要条件提示；完整条件由程序在口播中保留。不清楚的关系选择比较图或原页标注。'+
                ('\n修正依据：'+failures[-1] if failures else '')+
                ('\n若来源没有直接支持关系，请选择source_figure或comparison并保持relations=[]，保留独立的原文事实，不能为连接所有节点编造连线。' if failures else '')+
                ('\n前两次设计未通过，本次保留原PDF页面，只为来源事实设计中文注释对象，representation=source_figure，relations=[]；来源和口播含义仍须通过检查。' if annotation else '')+
                    '\n使用proposition_ids字段时，只选择1至3个相关来源命题，程序构建全部节点与连线，不输出nodes/relations/steps，不重写端点；'
                    '其余契约source_term必须逐字来自sources，steps=[]。',material)
            attempts[-1]['draft']=draft.model_dump()
            if hasattr(draft,'proposition_ids'):
                draft=design_from_propositions(draft,propositions,facts)
            if draft.representation=='geometry':
                if force_diagram: raise TeachingDesignError('本次必须重新选择表达方式。')
                phase('选择可计算几何')
                return draft,None,failures
            repairs=list(cached_term_repairs) if attempts[-1].get('structure_cached') else []
            if not attempts[-1].get('structure_cached'):
                draft=resolve_design(draft,spans,repairs,facts,propositions)
            bind_annotation_anchors(draft,repairs)
            validate_source_propositions(draft,propositions)
            topic_facts=preserve_topic_focus(draft,facts,segment.title,segment.evidence.quote)
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
            raw_review=client.generate(meaning_review_schema(draft),
                meaning_review_instruction(draft)+
                'source_warnings只记录原始资料的OCR或排版疑点，不进入口播。若疑点使当前标注、关系或口播无法确认，相应条目的supported必须为false；可确认的条目按其真实含义判断。',
                meaning_review_material(draft,page.text))
            review=compose_meaning_review(raw_review)
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
            report['source_propositions']=propositions
            from zhijiang.teaching_graph import design_digest,knowledge_graph
            report['reviewed_design_digest']=design_digest(draft)
            report['knowledge_graph']=knowledge_graph(diagram,segment.evidence.page)
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
