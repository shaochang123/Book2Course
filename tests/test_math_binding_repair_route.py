from types import SimpleNamespace
from zhijiang.models import SourceDocument,PageText
from zhijiang.mathematical_planning import plan_constructed_lesson
from zhijiang import math_coverage,math_inventory
from tests.test_mathematical_planning import CHECKS


def test_missing_source_measurement_repairs_behavior_without_rebuilding_graph(monkeypatch):
    requirement={'id':1,'kind':'claim','statement':'点在函数上，实际纵坐标与函数值对应。',
        'subjects':[{'name':'实际函数','kind':'function'}],
        'source_excerpts':[{'page':1,'quote':'The point lies on the function.'}]}
    monkeypatch.setattr(math_coverage,'source_scope',lambda *args,**kwargs:[requirement])
    monkeypatch.setattr(math_inventory,'check_construction_readiness',lambda *args,**kwargs:
        SimpleNamespace(checks=[],model_dump=lambda:{'checks':[]}))
    original=math_coverage.check_coverage;coverage_calls=[]
    def coverage(*args,**kwargs):
        coverage_calls.append(True)
        if len(coverage_calls)==1:
            raise math_coverage.MathSubjectBindingError('来源主语未参与实际数学关系：实际函数','behavior')
        return original(*args,**kwargs)
    monkeypatch.setattr(math_coverage,'check_coverage',coverage)
    calls=[]
    class Client:
        model='test-model'
        def generate(self,schema,instruction,material,**kwargs):
            calls.append(schema.__name__)
            if schema.__name__=='MathConstructionIntent':return schema.model_validate({
                'core_question':'动态对应','source_conditions':[],'construction_plan':'沿实际函数移动点。',
                'continuous_operations':['观察','移动','比较'],'actual_object_checks':['实际输出']})
            if schema.__name__=='MathConstructionDraft':return schema.model_validate({
                'title':'动态函数对应','objective':'观察输入变化时实际函数输出如何变化。',
                'source_id':1,'parameters':{'u':0},'constructions':[
                    {'id':'f','op':'function','expr':['exp(x)'],'domain':[-.2,1]},
                    {'id':'m','op':'point_on_function','refs':['f'],'expr':['u']}]})
            if schema.__name__=='MathBehaviorDraft':return schema.model_validate({
                'operations':[{'narration':'移动曲线上的点，比较输入与实际输出。','changes':{'u':v}}
                    for v in [.2,.5,.8]],'claims':[{'source_id':1,
                    'left':{'terms':[{'kind':'ycoord','point':'m'}]},
                    'right':{'terms':[{'kind':'value','function':'f','at':'u'}]}}]})
            if schema.__name__=='MathCoverageReview':return schema.model_validate({
                'checks':[{'requirement_id':1,'observation':'实际函数及曲线上的点参与同一函数值关系。',
                    'supported':True,'steps':[1,2,3],'objects':['f'],
                    'bindings':[{'subject_index':1,'objects':['f']}]}]})
            assert schema.__name__=='MathProgramReview'
            return schema.model_validate({'checks':CHECKS,'approved':True,'source_coverage':['函数对应关系']})
    source=SourceDocument(filename='fresh.pdf',pages=[PageText(page=1,
        text='The point lies on the function.',math_reading={'review':{'approved':True}})])
    lesson=plan_constructed_lesson(Client(),source)
    assert calls.count('MathConstructionDraft')==1
    assert calls.count('MathBehaviorDraft')==2
    assert len(coverage_calls)==2
    assert lesson.segments[0].visual_scene.verification['passed']
