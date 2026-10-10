"""Bind reviewed source statements to speech, separately from computed values.

Models may choose steps through coverage review, but never rewrite these facts.
This closes a gap where source conditions existed only in review metadata.
"""
import re

from zhijiang.visual_planning import VisualSceneError


def bind_source_fact_schedule(scene, requirements, coverage):
    by_id={r['id']:r for r in requirements}
    checks={c.requirement_id:c for c in coverage.checks}
    if len(by_id)!=len(requirements) or set(checks)!=set(by_id):
        raise VisualSceneError('来源讲解绑定必须完整覆盖独立清单。')
    schedule=[[] for _ in scene.beats]
    for requirement in requirements:
        check=checks[requirement['id']]
        if not check.supported:raise VisualSceneError('未通过的来源要求不能进入配音。')
        step=1 if requirement['kind'] in {'condition','definition'} else min(check.steps or [1])
        if not 1<=step<=len(schedule):raise VisualSceneError('来源讲解步骤不存在。')
        schedule[step-1].append(requirement['id'])
    scene.mathematical_model['source_requirements']=requirements
    scene.mathematical_model['source_fact_schedule']=schedule
    validate_source_fact_schedule(scene)


def validate_source_fact_schedule(scene):
    model=scene.mathematical_model or {}
    if 'source_fact_schedule' not in model:return
    requirements=model.get('source_requirements',[])
    by_id={r['id']:r for r in requirements}
    schedule=model['source_fact_schedule']
    if not requirements or len(by_id)!=len(requirements) or len(schedule)!=len(scene.beats):
        raise VisualSceneError('来源讲解清单或步骤不完整。')
    ids=[i for batch in schedule for i in batch]
    if len(set(ids))!=len(ids) or set(ids)!=set(by_id):
        raise VisualSceneError('来源讲解要求遗漏、重复或编号无效。')
    for requirement in requirements:
        if not requirement.get('statement') or not requirement.get('source_excerpts'):
            raise VisualSceneError('来源讲解缺少已核对的陈述和出处。')
        if any(not e.get('quote') or not isinstance(e.get('page'),int) for e in requirement['source_excerpts']):
            raise VisualSceneError('来源讲解出处不完整。')


def source_facts(scene, index):
    validate_source_fact_schedule(scene)
    model=scene.mathematical_model or {}
    if 'source_fact_schedule' not in model:return []
    by_id={r['id']:r for r in model['source_requirements']}
    return [by_id[i] for i in model['source_fact_schedule'][index]]


def display_source_statement(statement):
    """Plain text only: no model TeX or other commands are executed."""
    text=statement.replace('$','').replace(r'\(','').replace(r'\)','')
    for _ in range(4):
        text=re.sub(r'\\frac\{([^{}]{1,100})\}\{([^{}]{1,100})\}',r'(\1)/(\2)',text)
        text=re.sub(r'\\sqrt\{([^{}]{1,100})\}',r'√(\1)',text)
    for before,after in {r'\infty':'∞',r'\pi':'π',r'\neq':'≠',r'\ne ':'≠ ',
            r'\leq':'≤',r'\geq':'≥',r'\cdot':'·',r'\log':'log'}.items():
        text=text.replace(before,after)
    return text


def speak_source_statement(statement):
    text=display_source_statement(statement)
    text=re.sub(r'log_([A-Za-z0-9]+)\(([^()]{1,80})\)',r'以\1为底的\2的对数',text)
    for before,after in [('>=','大于等于'),('<=','小于等于'),('!=','不等于'),
            ('≠','不等于'),('≥','大于等于'),('≤','小于等于'),('>','大于'),('<','小于'),
            ('=','等于'),('√','根号'),('∞','无穷大'),('π','圆周率'),
            ('**','的次方'),('^','上标'),('/','除以'),('·','乘以'),('*','乘以'),('_','下标')]:
        text=text.replace(before,after)
    return '教材说明。'+text
