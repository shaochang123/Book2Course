import pytest
from zhijiang.agents import AIAgents, GenerationError
from zhijiang.models import KnowledgeBundle, KnowledgePoint, Evidence, CourseOutline


def bundle():
    return KnowledgeBundle(points=[KnowledgePoint(title=name,kind='concept',
        explanation='定义以及适用范围均由原文给出。',
        evidence=Evidence(page=i,quote='定义以及适用范围均由原文给出。'))
        for i,name in enumerate(['甲条件与范围','乙结论的含义'],1)])


def test_outline_uses_exact_titles_and_repairs_only_coverage():
    class Client:
        def __init__(self):self.stages=[]
        def generate(self,schema,instruction,material):
            self.stages.append(schema.__name__)
            if len(self.stages)==1:
                return CourseOutline(title='原创条件课程',objective='明确条件与结论之间的关系。',
                    point_titles=['甲条件与范围','甲条件与范围'])
            with pytest.raises(ValueError):
                schema.model_validate({'title':'原创条件课程','objective':'明确条件与结论之间的关系。',
                                       'point_titles':['改写标题','乙结论的含义']})
            return schema.model_validate({'title':'原创条件课程','objective':'明确条件与结论之间的关系。',
                                         'point_titles':['乙结论的含义','甲条件与范围']})
    client=Client();material=bundle();before=material.model_dump_json()
    result=AIAgents(client).plan(material)
    assert result.point_titles==['乙结论的含义','甲条件与范围']
    assert client.stages==['CourseOutline','CourseOutlineRepair']
    assert material.model_dump_json()==before


def test_outline_service_failure_does_not_turn_into_demo():
    class Client:
        def generate(self,*args):raise GenerationError('service unavailable')
    with pytest.raises(GenerationError,match='service unavailable'):
        AIAgents(Client()).plan(bundle())


def test_outline_invalid_coverage_has_bounded_repair():
    class Client:
        calls=0
        def generate(self,*args):
            self.calls+=1
            return CourseOutline(title='原创条件课程',objective='明确条件与结论之间的关系。',
                                 point_titles=['甲条件与范围','甲条件与范围'])
    client=Client()
    with pytest.raises(GenerationError,match='两次'):AIAgents(client).plan(bundle())
    assert client.calls==2


def test_same_title_on_different_source_points_is_not_lost():
    material=bundle();material.points[1].title=material.points[0].title
    class Client:
        def generate(self,schema,*args):
            return schema.model_validate({'title':'原创条件课程','objective':'明确不同来源的适用范围。',
                'point_titles':[material.points[0].title,material.points[1].title]})
    assert len(AIAgents(Client()).plan(material).point_titles)==2
