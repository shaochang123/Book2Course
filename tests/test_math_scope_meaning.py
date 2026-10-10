import pytest
from zhijiang.math_coverage import source_scope
from zhijiang.visual_planning import VisualSceneError


def test_independent_source_meaning_repair_precedes_scene_and_keeps_exact_evidence():
    mapping={1:{'page':5,'quote':'The ray has one endpoint and extends in one direction.'}}
    histories=[];seen=[]
    class Vision:
        attempts=0
        def generate(self,schema,instruction,material,**kwargs):
            assert kwargs['images']==[b'original page']
            self.attempts+=1
            if self.attempts>1:assert '翻译为双向是错误的' in instruction
            return schema.model_validate({'requirements':[{'id':1,'source_ids':[1],
                'kind':'definition','statement':'射线有一个端点并向'+('两个' if self.attempts==1 else '一个')+'方向延伸。',
                'subjects':[{'name':'射线','kind':'ray'}]}]})
    class Review:
        attempts=0
        def generate(self,schema,instruction,material,**kwargs):
            assert not kwargs.get('images')
            assert schema.__name__=='MathScopeMeaningReview'
            assert '不接触候选动画' in instruction
            assert mapping[1]['quote'] in material
            self.attempts+=1;seen.append(material)
            return schema.model_validate({'checks':[{'requirement_id':1,
                'observation':'原文为单向，翻译为双向是错误的。' if self.attempts==1 else '原文单向与中文定义及射线主语一致。',
                'supported':self.attempts>1}]})
    result=source_scope(Vision(),mapping,mapping[1]['quote'],images=[b'original page'],reviewer=Review(),history=histories)
    assert len(histories)==2 and not histories[0]['meaning_review']['checks'][0]['supported']
    assert result[0]['statement']=='射线有一个端点并向一个方向延伸。'
    assert result[0]['source_quote']==mapping[1]['quote'] and result[0]['source_page']==5


def test_persistent_source_meaning_error_is_rejected_with_all_attempts():
    class Client:
        def generate(self,schema,*args,**kwargs):
            if schema.__name__=='MathSourceScope':return schema.model_validate({'requirements':[{'id':1,
                'source_ids':[1],'kind':'definition','statement':'错误的来源说明仍然必须核查。'}]})
            return schema.model_validate({'checks':[{'requirement_id':1,'observation':'实际来源含义与当前清单声明不一致。','supported':False}]})
    c=Client();history=[]
    with pytest.raises(VisualSceneError,match='含义三次修复') as exc:
        source_scope(c,{1:{'page':1,'quote':'Original statement.'}},'Original statement.',reviewer=c,history=history)
    assert exc.value.source_scope_attempts is history and len(history)==3
