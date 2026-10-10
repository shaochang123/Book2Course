"""Subject retrieval, portable source assets and model selection constraints."""
import json
from pathlib import Path
import shutil
import pytest
from PIL import Image
from zhijiang.visual_assets import AssetCatalog, AssetError, validate_svg
from zhijiang.deck_planning import plan_deck, DeckDirectorDraft, DeckPageChoice, AssetReference
from zhijiang.agents import GenerationError
from test_deck_planning import example_lesson


def test_complete_original_catalog_and_every_directory_described(tmp_path):
    catalog=AssetCatalog()
    assert len(catalog.assets)==109
    assert len({a.domain for a in catalog.assets.values()})==12
    assert sum(a.license=='MIT' for a in catalog.assets.values())==100
    assert sum(a.license=='CC0-1.0' and a.kind=='illustration' for a in catalog.assets.values())==9
    assert all(a.source and a.description and a.limitations for a in catalog.assets.values())
    assert all((p/'README.md').is_file() for p in catalog.root.iterdir() if p.is_dir())
    catalog.write_index(tmp_path/'index.json')
    indexed=json.loads((tmp_path/'index.json').read_text(encoding='utf-8'))
    assert indexed['fingerprint']==catalog.fingerprint and len(indexed['assets'])==109


@pytest.mark.parametrize('query,expected',[
    ('用瓜瓤和瓜皮解释观察到的属性','life-agriculture.watermelon-slice'),
    ('an alveoli diagram for oxygen exchange','medicine.lungs'),
    ('本金的利息逐年加入下一期本金，比较复利增长','finance.growth-chart'),
    ('电池经开关向电阻供电的闭合电路','physics-engineering.circuit'),
    ('法庭通过证据审判案件','law.gavel'),
    ('DNA 与遗传信息','biology.dna'),
])
def test_retrieval_unrelated_domains_and_aliases(query,expected):
    assert expected in [item['id'] for item in AssetCatalog().search(query)]


def test_missing_query_does_not_force_a_picture():
    assert AssetCatalog().search('zxqvxyz')==[]


def test_all_original_svg_rasterize_with_alpha_and_nonempty_content(tmp_path):
    catalog=AssetCatalog()
    for asset in catalog.assets.values():
        output=catalog.rasterize(asset.id,tmp_path,96)
        with Image.open(output) as image:
            assert image.mode=='RGBA' and image.width==96 and image.height>0
            assert image.getpixel((0,0))[3]==0
            assert image.getchannel('A').getbbox()
        assert catalog.rasterize(asset.id,tmp_path,96)==output


def test_reviewed_art_outranks_symbols_for_the_same_named_object():
    catalog=AssetCatalog()
    for query,asset_id in [('西瓜样本的属性','life-agriculture.watermelon-sketch'),
                           ('电路中的灯泡','physics-engineering.light-bulb-sketch')]:
        assert catalog.search(query)[0]['id']==asset_id
    assert catalog.search('阅读教材书本')[0]['kind']=='illustration'
    assert all(a['kind']=='illustration' for a in catalog.search('西瓜') if a['id'].endswith('sketch'))


def test_empty_layout_art_gets_a_separate_bounded_model_selection(tmp_path):
    lesson=example_lesson(1)
    lesson.segments[0].title='一条西瓜记录'
    lesson.segments[0].narration='观察西瓜的颜色和瓜瓤，说明样本与特征。'
    lesson.segments[0].bullets=['西瓜是一条样本记录']
    class Chooses:
        model='mock';base_url='http://localhost'
        def __init__(self):self.stages=[]
        def generate(self,schema,instruction,material):
            self.stages.append(schema.__name__)
            if schema.__name__=='DeckDirectorDraft':
                return schema.model_validate({'hook_segment_id':1,'pages':[{'segment_id':1,
                    'role':'example','layout':'split','bullet_ids':[1],
                    'visual_groups':[{'bullet_id':1}],'asset_refs':[]}]})
            assert schema.__name__=='DeckIllustrationPlacement'
            data=json.loads(material)
            assert all(a['kind']=='illustration' for a in data['illustrations'])
            return schema.model_validate({'asset_id':'life-agriculture.watermelon-sketch',
                                          'group_id':1,'anchor_text':'西瓜'})
    client=Chooses();plan=plan_deck(lesson,'paper',client,output=tmp_path/'plan.json')
    assert client.stages==['DeckDirectorDraft','DeckIllustrationPlacement']
    assert plan['pages'][0]['asset_refs'][0]['asset_id']=='life-agriculture.watermelon-sketch'
    assert plan['illustration_placements'][0]['status']=='structurally_valid'


def test_unknown_id_and_svg_external_content_rejected(tmp_path):
    with pytest.raises(AssetError,match='未知'): AssetCatalog().path('../private')
    for node in ['<script/>','<image href="https://example.com/image"/>','<path onclick="bad()"/>']:
        path=tmp_path/'bad.svg';path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'+node+'</svg>')
        with pytest.raises(AssetError): validate_svg(path)


def test_png_extension_and_metadata_change_invalidate_plan(tmp_path):
    catalog=AssetCatalog(); root=tmp_path/'catalog';shutil.copytree(catalog.root,root)
    first=AssetCatalog(root)
    output=tmp_path/'plan.json'; lesson=example_lesson(1)
    a=plan_deck(lesson,'paper',catalog=first,output=output)
    readme=root/'finance/README.md';readme.write_text(readme.read_text(encoding='utf-8')+'\n新的目录说明\n',encoding='utf-8')
    second=AssetCatalog(root); b=plan_deck(lesson,'paper',catalog=second,output=output)
    assert first.fingerprint!=second.fingerprint and a['fingerprint']!=b['fingerprint']
    # New transparent raster assets use the same contract as SVG files.
    image=root/'finance/new.png';Image.new('RGBA',(20,20),(123,150,90,128)).save(image)
    metadata='\n```toml\n[[assets]]\nid="finance.new"\nfile="new.png"\ntitle="新的图"\ndescription="原创图片"\ntags=["new"]\ndomain="finance"\nusage="测试"\nlimitations="符号"\nsource="原创"\nlicense="MIT"\n```\n'
    readme.write_text(readme.read_text(encoding='utf-8')+metadata,encoding='utf-8')
    assert AssetCatalog(root).rasterize('finance.new',tmp_path)==image


def test_model_selection_is_candidate_limited_and_anchors_to_existing_text(tmp_path):
    lesson=example_lesson(1)
    lesson.segments[0].title='观察西瓜的瓜皮'
    class Client:
        model='fake';base_url='local'
        def generate(self,schema,instruction,material):
            data=json.loads(material); candidates=data['segments'][0]['candidate_assets']
            assert 'life-agriculture.watermelon-sketch' in [a['id'] for a in candidates]
            return schema.model_validate({'hook_segment_id':1,'pages':[{
                'segment_id':1,'role':'example','layout':'illustrated','bullet_ids':[1],
                'visual_groups':[{'bullet_id':1}],
                'asset_refs':[{'asset_id':'life-agriculture.watermelon-sketch','usage':'main','anchor_text':'西瓜','group_id':1}]}]})
    plan=plan_deck(lesson,'paper',Client(),output=tmp_path/'plan.json')
    assert plan['pages'][0]['asset_refs'][0]['asset_id']=='life-agriculture.watermelon-sketch'
    assert plan['asset_retrieval'][0]['selected']
    assert plan_deck(lesson,'paper',Client(),output=tmp_path/'plan.json')==plan


@pytest.mark.parametrize('asset_id,anchor', [('law.gavel','西瓜'),('life-agriculture.watermelon','教材中没有的文字')])
def test_invalid_selection_does_not_export_successful_plan(tmp_path,asset_id,anchor):
    lesson=example_lesson(1);lesson.segments[0].title='西瓜的瓜皮'
    class Client:
        model='bad';base_url='local'
        def generate(self,*args):
            return DeckDirectorDraft(hook_segment_id=1,pages=[DeckPageChoice(segment_id=1,
                role='example',layout='illustrated',bullet_ids=[1],asset_refs=[AssetReference(
                    asset_id=asset_id,anchor_text=anchor)])])
    with pytest.raises(GenerationError,match='三次'): plan_deck(lesson,'paper',Client(),output=tmp_path/'plan.json')
    assert not (tmp_path/'plan.json').exists()


def test_disabled_illustrations_persist_empty_selection(tmp_path):
    lesson=example_lesson(1);lesson.segments[0].title='西瓜的瓜皮'
    a=plan_deck(lesson,'paper',output=tmp_path/'plan.json')
    b=plan_deck(lesson,'paper',use_illustrations=False,output=tmp_path/'plan.json')
    assert a['fingerprint']!=b['fingerprint'] and b['use_illustrations'] is False
    assert b['pages'][0]['asset_refs']==[] and b['asset_retrieval'][0]['candidates']==[]


def test_actual_model_schema_forbids_two_main_illustrations():
    from zhijiang.deck_planning import director_schema
    from zhijiang.presentation_templates import get_template
    lesson=example_lesson(1);lesson.segments[0].title='西瓜和瓜苗'
    candidates={1:AssetCatalog().search('西瓜和瓜苗')}
    schema=director_schema(lesson,get_template('paper'),[1],candidates)
    payload={'hook_segment_id':1,'pages':[{'segment_id':1,'role':'explanation',
             'layout':'illustrated','bullet_ids':[1], 'visual_groups':[{'bullet_id':1}], 'asset_refs':[
                 {'asset_id':'life-agriculture.watermelon-sketch','usage':'main','anchor_text':'西瓜','group_id':1},
                 {'asset_id':'life-agriculture.melon-seedling','usage':'main','anchor_text':'瓜苗','group_id':1}]}]}
    with pytest.raises(ValueError): schema.model_validate(payload)
    payload['pages'][0]['asset_refs'][1]['usage']='support'
    assert len(schema.model_validate(payload).pages[0].asset_refs)==2


def test_native_schema_cannot_repeat_a_single_candidate_across_groups():
    from zhijiang.deck_planning import director_schema
    from zhijiang.presentation_templates import get_template
    lesson = example_lesson(1)
    lesson.segments[0].narration = '西瓜是本页讨论的具体对象。'
    candidate = AssetCatalog().search('西瓜')[0]
    candidates = {1: [candidate]}
    schema = director_schema(lesson, get_template('paper'), [1], candidates)
    anchor = next(a for a in candidate['entity_aliases'] if a in lesson.segments[0].narration)
    ref = {'asset_id': candidate['id'], 'usage': 'main', 'anchor_text': anchor, 'group_id': 1}
    payload = {'hook_segment_id': 1, 'pages': [{'segment_id': 1, 'role': 'explanation',
        'layout': 'split', 'bullet_ids': [1], 'visual_groups': [{'bullet_id': 1}],
        'asset_refs': [ref]}]}
    assert len(schema.model_validate(payload).pages[0].asset_refs) == 1
    payload['pages'][0]['asset_refs'].append({**ref, 'usage': 'support'})
    with pytest.raises(ValueError):
        schema.model_validate(payload)
    # The constraint is present in the JSON schema sent to Ollama, not only
    # in the Python post-validator.
    page = schema.model_json_schema()['$defs']['DeckSegment1']
    assert max(choice['maxItems'] for choice in page['properties']['asset_refs']['anyOf']) == 1


def test_abstract_learning_does_not_select_stationery_or_brain(tmp_path):
    lesson=example_lesson(1)
    lesson.segments[0].title='学习方法的科学价值'
    lesson.segments[0].narration='研究学习的计算模型，讨论模型适用于哪些条件。'
    plan=plan_deck(lesson,'paper',output=tmp_path/'plan.json')
    candidates=plan['asset_retrieval'][0]['candidates']
    assert not {'education.pencil','medicine.brain','history.scroll'} & {a['id'] for a in candidates}


@pytest.mark.parametrize('text,forbidden',[
    ('肺泡的氧气跨膜扩散','medicine.lungs-ink'),
    ('alveoli exchange gases','medicine.lungs'),
    ('nucleus contains genetic material','biology.cell'),
    ('固定条件下的复利金额','finance.growth-chart'),
    ('NotebookLM generation','life-agriculture.open-book-sketch'),
])
def test_related_concepts_and_word_fragments_are_not_object_aliases(text,forbidden):
    lesson=example_lesson(1);segment=lesson.segments[0]
    segment.title=text;segment.narration=text;segment.bullets=[text]
    plan=plan_deck(lesson,'paper')
    assert forbidden not in {a['id'] for a in plan['asset_retrieval'][0]['candidates']}


def test_one_illustration_per_named_object_across_domains():
    for text,expected,old in [('肺部的结构','medicine.lungs-ink','medicine.lungs'),
                              ('观察灯泡','physics-engineering.light-bulb-sketch','physics-engineering.light-bulb')]:
        lesson=example_lesson(1);segment=lesson.segments[0]
        segment.title=text;segment.narration=text;segment.bullets=[text]
        choices=plan_deck(lesson,'paper')['asset_retrieval'][0]['candidates']
        assert expected in {a['id'] for a in choices}
        assert old not in {a['id'] for a in choices}


def test_semantic_group_cannot_skip_a_selected_caption(tmp_path):
    from zhijiang.deck_planning import VisualGroup
    lesson=example_lesson(1)
    class Broken:
        def generate(self,*args):
            return DeckDirectorDraft(hook_segment_id=1,pages=[DeckPageChoice(segment_id=1,
                role='explanation',layout='split',bullet_ids=[1,2],visual_groups=[VisualGroup(bullet_id=1)])])
    with pytest.raises(GenerationError):plan_deck(lesson,'paper',Broken(),output=tmp_path/'plan.json')
