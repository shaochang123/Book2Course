from io import BytesIO
from zipfile import ZipFile
from pathlib import Path
import pytest


@pytest.mark.parametrize('box', [[],[0,0,1],[-.1,0,.5,.5],[.9,0,.2,.5],[0,0,2,1],
    [0,0,float('nan'),.5],[0,0,.01,.5]])
def test_invalid_figure_geometry_never_opens_a_file(tmp_path,box):
    from zhijiang.source_figures import extract_figure
    assert extract_figure(tmp_path/'does-not-exist.pdf',1,box,folder=tmp_path,segment_id=1) is None


def test_real_source_figure_is_cited_and_shared_with_static_deck(tmp_path):
    from reportlab.pdfgen import canvas
    from zhijiang.source_figures import extract_figure
    pdf=tmp_path/'source.pdf';c=canvas.Canvas(str(pdf),pagesize=(600,800))
    c.line(60,680,290,570);c.line(290,570,60,460);c.line(60,460,60,680)
    c.drawString(60,730,'A triangular example from the original source.');c.showPage();c.save()
    figure=extract_figure(pdf,1,[.05,.1,.55,.48],folder=tmp_path/'source-figures',segment_id=1)
    assert figure and figure['page']==1
    from test_deck_planning import example_lesson
    from zhijiang.deck_planning import plan_deck
    from zhijiang.presentation import render_presentation
    lesson=example_lesson(1);lesson.ppt_template='academic'
    lesson.segments[0].narration='原图三角形由三条边连接构成，我们比较三条边的连接。'
    lesson.deck_plan=plan_deck(lesson,'academic',use_illustrations=False)
    lesson.deck_plan['source_figures']={'1':figure}
    lesson.deck_plan['visual_story']={'visuals':{'1':{'visual':{'representation':'key_idea',
        'items':[{'label':'原图三角形','caption':'比较三条边的连接','sentence_id':1}], 'links':[],'context':''}}}}
    render_presentation(lesson,tmp_path/'lesson.pptx')
    import json
    manifest=json.loads((tmp_path/'presentation-preview/manifest.json').read_text(encoding='utf-8'))
    assert any(page.get('source_figure')==figure for page in manifest['pages'])
    with ZipFile(tmp_path/'lesson.pptx') as archive:
        assert not any(name.endswith('.mp4') for name in archive.namelist())


def picture_pdf(tmp_path, *, scan=False):
    from PIL import Image,ImageDraw
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    image=Image.new('RGB',(360,160),'white');drawing=ImageDraw.Draw(image)
    drawing.line([(10,140),(170,10),(340,140),(10,140)],fill='navy',width=5)
    pdf=tmp_path/'pictures.pdf';c=canvas.Canvas(str(pdf),pagesize=(600,800))
    c.drawImage(ImageReader(image),0 if scan else 90,0 if scan else 220,
                width=600 if scan else 360,height=800 if scan else 160)
    c.showPage();c.save();return pdf


def test_source_image_candidates_bind_actual_bounds_and_exclude_full_scans(tmp_path):
    from zhijiang.source_figures import figure_candidates
    pdf=picture_pdf(tmp_path)
    found=figure_candidates(pdf.read_bytes(),[1])
    assert len(found)==1 and found[0]['box']==pytest.approx([.15,.525,.75,.725])
    assert found==figure_candidates(pdf.read_bytes(),[1])
    scan=picture_pdf(tmp_path,scan=True)
    assert not figure_candidates(scan.read_bytes(),[1])


def test_revision_resolves_only_current_candidate_id_without_model_coordinates(tmp_path):
    from zhijiang.source_figures import figure_candidates
    from zhijiang.draft_source_repair import revise_batch
    from pydantic import ValidationError
    from test_draft_generation import DraftClient,inputs
    from zhijiang.draft_generation import build_draft_lesson
    from zhijiang.models import VoiceMode
    document,bundle=inputs(1);client=DraftClient()
    build_draft_lesson(client,bundle,document,'',VoiceMode.SYSTEM,template_id='paper',
        use_illustrations=False,folder=tmp_path,progress=lambda *args:None)
    import json
    from pydantic import create_model
    from zhijiang.draft_generation import DraftPage
    schema=create_model('Draft',title=(str,...),objective=(str,...),pages=(list[DraftPage],...))
    raw=json.loads((tmp_path/'batch-001.json').read_text(encoding='utf-8'))['data']
    draft=schema.model_validate(raw);pdf=picture_pdf(tmp_path)
    material={'points':[{'source_id':1}], 'source_pages':[{'page':1,'text':'The original source picture shows a triangle.'}]}
    selected=figure_candidates(pdf.read_bytes(),[1])[0]
    class Selecting:
        def generate(self,schema,instruction,payload,**kwargs):
            if schema.__name__=='SourcePictureReading':
                assert 'pages' not in payload and kwargs['images']
                return schema(image_role='teaching_diagram',observations=['原图为三条边连接构成的三角形。'])
            payload=json.loads(payload)
            if schema.__name__=='SourceFigureAlignment':
                assert 'pages' not in payload  # Do not feed a bad draft back as the answer.
                page={**raw['pages'][0],'title':'真实来源三角形','render_kind':'story','graphic_group':'',
                    'context_is_condition':False,'figure_page':0,'figure_box':[], 'figure_id':selected['id']}
                return schema.model_validate({'reading':payload['picture_reading'],'pages':[page]})
            assert payload['figure_candidates']==[selected] and kwargs['images']
            page={**raw['pages'][0],'title':'真实来源三角形','render_kind':'story','graphic_group':'',
                'context_is_condition':False,'figure_page':0,'figure_box':[], 'figure_id':selected['id']}
            with pytest.raises(ValidationError):
                schema.model_validate({**raw,'pages':[{**page,'figure_id':'untrusted/path.png'}]})
            return schema.model_validate({**raw,'pages':[page]})
    revised,_=revise_batch(Selecting(),draft,material,folder=tmp_path,pdf_path=pdf)
    assert revised.pages[0].figure_page==1 and revised.pages[0].figure_box==selected['box']


def test_picture_alignment_failure_preserves_topics_and_removes_unconfirmed_picture(tmp_path):
    from zhijiang.source_figure_alignment import align_picture_pages
    from zhijiang.draft_source_repair import RevisedPage
    from zhijiang.source_figures import figure_candidates
    from zhijiang.agents import GenerationError
    pdf=picture_pdf(tmp_path);figure=figure_candidates(pdf.read_bytes(),[1])[0]
    page=RevisedPage(source_id=1,title='教材里的实际三角形',narration='原图的三条边连接成三角形，我们观察实际对象。',
        bullets=['三条边连接成三角形'],
        visual={'representation':'key_idea','items':[{'label':'实际对象','caption':'三条边连接','sentence_id':1}]},
        render_kind='story',graphic_group='',context_is_condition=False,
        figure_id=figure['id'],figure_page=1,figure_box=figure['box'])
    class Offline:
        def generate(self,*args,**kwargs):raise GenerationError('服务断开')
    result,records=align_picture_pages(Offline(),[page],{},[figure],folder=tmp_path,pdf_path=pdf)
    assert result[0].source_id==1 and result[0].narration==page.narration
    assert not result[0].figure_id and result[0].figure_page==0 and records


def test_scan_selected_crop_uses_picture_alignment_even_without_embedded_candidates(tmp_path):
    import json
    from pydantic import create_model
    from zhijiang.draft_generation import DraftPage
    from zhijiang.draft_source_repair import revise_batch
    from zhijiang.source_figures import figure_candidates
    pdf=picture_pdf(tmp_path,scan=True)
    assert not figure_candidates(pdf.read_bytes(),[1])
    raw={'title':'来源里的对象','objective':'解释来源里的实际对象及其连接。','pages':[{
        'source_id':1,'narration':'来源图显示三条边连接成三角形，需要观察实际连接。',
        'bullets':['观察实际三角形'],'visual':{'representation':'key_idea',
        'items':[{'label':'实际三角形','caption':'三条边连接','sentence_id':1}]}}]}
    draft=create_model('Draft',title=(str,...),objective=(str,...),pages=(list[DraftPage],...)).model_validate(raw)
    calls=[]
    class Client:
        def generate(self,schema,instruction,material,**kwargs):
            calls.append(schema.__name__)
            if schema.__name__=='TeachingDraftRevision':
                return schema.model_validate({**raw,'pages':[{**raw['pages'][0],'title':raw['title'],
                    'render_kind':'story','graphic_group':'','context_is_condition':False,
                    'figure_page':1,'figure_box':[.1,.1,.9,.9]}]})
            if schema.__name__=='SourcePictureReading':
                return schema(image_role='teaching_diagram',observations=['实际原图显示三角形。'])
            payload=json.loads(material)
            return schema.model_validate({'reading':payload['picture_reading'],'pages':[{**raw['pages'][0],
                'title':raw['title'],'render_kind':'story','graphic_group':'','context_is_condition':False,
                'figure_id':payload['figure']['id'],'figure_page':1,'figure_box':payload['figure']['box']}]})
    revised,_=revise_batch(Client(),draft,{'points':[{'source_id':1}],'source_pages':[{'page':1}]},
        folder=tmp_path,pdf_path=pdf)
    assert calls==['TeachingDraftRevision','SourcePictureReading','SourceFigureAlignment']
    assert revised.pages[0].figure_id.startswith('crop-p1-') and revised.pages[0].figure_page==1


def test_wide_source_picture_has_full_page_instead_of_half_width(tmp_path):
    import json
    from test_deck_planning import example_lesson
    from zhijiang.deck_planning import plan_deck
    from zhijiang.source_figures import figure_candidates,extract_figure
    from zhijiang.presentation import render_presentation
    pdf=picture_pdf(tmp_path);candidate=figure_candidates(pdf.read_bytes(),[1])[0]
    figure=extract_figure(pdf,1,candidate['box'],folder=tmp_path/'source-figures',segment_id=1)
    lesson=example_lesson(1);lesson.ppt_template='academic'
    lesson.segments[0].narration='原图的边线连接成三角形，说明边线之间的实际连接。'
    lesson.deck_plan=plan_deck(lesson,'academic',use_illustrations=False)
    lesson.deck_plan['source_figures']={'1':figure}
    lesson.deck_plan['visual_story']={'visuals':{'1':{'visual':{'representation':'comparison',
        'items':[{'label':'边线','caption':'相互连接','sentence_id':1},
                 {'label':'三角形','caption':'封闭图形','sentence_id':1}], 'links':[], 'context':''}}}}
    render_presentation(lesson,tmp_path/'lesson.pptx')
    manifest=json.loads((tmp_path/'presentation-preview/manifest.json').read_text(encoding='utf-8'))
    pages=[p for p in manifest['pages'] if p.get('segment_id')==1 and p['kind']=='content']
    assert any(p.get('representation')=='source_figure' and p['layout']=='wide' for p in pages)
    assert any(p.get('representation')=='comparison' and not p.get('source_figure') for p in pages)


def test_single_page_recovery_keeps_vision_crop_bytes_and_repair_record(tmp_path):
    import json
    from pydantic import create_model
    from zhijiang.agents import ModelContractError
    from zhijiang.draft_generation import DraftPage
    from zhijiang.draft_source_repair import revise_batch
    pdf=picture_pdf(tmp_path,scan=True)
    raw={'title':'真实来源里的对象','objective':'解释来源里的对象与其实际连接。','pages':[{
        'source_id':1,'narration':'原图展示三条边的实际连接，我们观察这个对象。',
        'bullets':['观察实际连接'],'visual':{'representation':'key_idea',
        'items':[{'label':'实际连接','caption':'三条边构成三角形','sentence_id':1}]}}]}
    draft=create_model('Draft',title=(str,...),objective=(str,...),pages=(list[DraftPage],...)).model_validate(raw)
    class Client:
        def __init__(self):self.revision_calls=0
        def generate(self,schema,instruction,material,**kwargs):
            if schema.__name__=='SourcePictureReading':return schema(image_role='teaching_diagram',observations=['原图的三条边连接成三角形。'])
            payload=json.loads(material)
            page={**raw['pages'][0],'title':raw['title'],'render_kind':'story','graphic_group':'',
                'context_is_condition':False,'figure_page':1,'figure_box':[.1,.1,.9,.9]}
            if schema.__name__=='TeachingDraftRevision':
                self.revision_calls+=1
                assert kwargs['images']
                if self.revision_calls==1:
                    broken={**page,'visual':{'representation':'key_idea','items':[{
                        'label':'实际连接','caption':'','sentence_id':1}]}}
                    raise ModelContractError('blank caption',content=json.dumps({**raw,'pages':[broken]}))
                assert 'visual' not in payload['draft']['pages'][0]
                return schema.model_validate({**raw,'pages':[page]})
            return schema.model_validate({'reading':payload['picture_reading'],'pages':[
                {**page,'figure_id':payload['figure']['id']}]})
    revised,records=revise_batch(Client(),draft,{'points':[{'source_id':1}],'source_pages':[{'page':1}]},
        folder=tmp_path,pdf_path=pdf)
    assert revised.pages[0].figure_id.startswith('crop-p1-')
    assert any('单独重新生成' in record['issue'] for record in records)


@pytest.mark.parametrize('role',['video_thumbnail','decoration','uncertain'])
def test_non_teaching_picture_is_excluded_before_slide_rewrite(tmp_path,role):
    from zhijiang.draft_source_repair import RevisedPage
    from zhijiang.source_figures import figure_candidates
    from zhijiang.source_figure_alignment import align_picture_pages
    pdf=picture_pdf(tmp_path);figure=figure_candidates(pdf.read_bytes(),[1])[0]
    page=RevisedPage(source_id=2,title='来源里的教学对象',narration='我们解释来源里的实际对象及其关系，不把封面当成过程。',
        bullets=['观察实际对象'],visual={'representation':'key_idea',
        'items':[{'label':'实际对象','caption':'解释实际关系','sentence_id':1}]},
        render_kind='story',graphic_group='',context_is_condition=False,
        figure_id=figure['id'],figure_page=1,figure_box=figure['box'])
    class Reader:
        def generate(self,schema,*args,**kwargs):
            assert schema.__name__=='SourcePictureReading'
            return schema(image_role=role,visible_text=['视频标题或装饰'],observations=['没有能解释机制的清晰对象。'])
    result,records=align_picture_pages(Reader(),[page],{},[figure],folder=tmp_path,pdf_path=pdf)
    assert result[0].narration==page.narration and not result[0].figure_id
    assert role in records[0]['issue'] and list(tmp_path.rglob('excluded-picture.json'))


def test_picture_rewrite_is_scoped_to_selected_topics_not_all_source_points(tmp_path):
    import json
    from pydantic import ValidationError
    from zhijiang.draft_source_repair import RevisedPage
    from zhijiang.source_figures import figure_candidates
    from zhijiang.source_figure_alignment import align_picture_pages
    pdf=picture_pdf(tmp_path);figure=figure_candidates(pdf.read_bytes(),[1])[0]
    page=RevisedPage(source_id=2,title='来源里的实际对象',narration='我们解释来源里三条边的连接关系，不把图示扩展为别的主题。',
        bullets=['实际边线关系'],visual={'representation':'key_idea',
        'items':[{'label':'实际连接','caption':'三条边连接','sentence_id':1}]},
        render_kind='story',graphic_group='',context_is_condition=False,
        figure_id=figure['id'],figure_page=1,figure_box=figure['box'])
    class Reader:
        def generate(self,schema,instruction,material,**kwargs):
            if schema.__name__=='SourcePictureReading':
                return schema(image_role='teaching_diagram',observations=['三条边连接成三角形。'])
            data=json.loads(material)
            assert [p['source_id'] for p in data['source']['points']]==[2]
            response={'reading':data['picture_reading'],'pages':[page.model_dump()]}
            with pytest.raises(ValidationError):
                schema.model_validate({**response,'pages':[{**page.model_dump(),'source_id':1}]})
            return schema.model_validate(response)
    result,_=align_picture_pages(Reader(),[page],{'points':[{'source_id':1},{'source_id':2}]},
        [figure],folder=tmp_path,pdf_path=pdf)
    assert result[0].source_id==2 and result[0].figure_id==figure['id']
