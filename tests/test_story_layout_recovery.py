"""Layout recovery must retain teaching facts, edges and readable type."""
import xml.etree.ElementTree as ET

import pytest

from zhijiang.presentation_templates import get_template
from zhijiang.story_svg import visual_svg

NS = {'s': 'http://www.w3.org/2000/svg'}


def crowded_graph():
    return {'representation': 'relationship', 'items': [
        {'label': '生态系统', 'caption': '生物与环境共同构成的相互作用系统', 'sentence_id': 1},
        {'label': '能量流动', 'caption': '能量沿食物关系流动并逐级散失', 'sentence_id': 2},
        {'label': '太阳辐射', 'caption': '为多数生态系统提供初始能量', 'sentence_id': 3},
        {'label': '物质循环', 'caption': '不同组成部分之间发生物质交换', 'sentence_id': 4}],
        'links': [{'source': 3, 'target': 1, 'label': '提供能量', 'kind': 'directed'},
                  {'source': 1, 'target': 2, 'label': '发生', 'kind': 'directed'},
                  {'source': 1, 'target': 4, 'label': '参与', 'kind': 'directed'}],
        'context': '能量逐级散失，物质可以循环，二者不能混淆'}


@pytest.mark.parametrize('template', ['classic', 'paper', 'academic', 'editorial',
    'newtouch_cloud','newtouch_blue','newtouch_white','newtouch_dark'])
def test_crowded_graph_and_four_way_comparison_paginate_without_discarding_content(template):
    from zhijiang.story_svg import visual_pages
    original = crowded_graph()
    for view in ['relationship', 'comparison']:
        visual = {**original, 'representation': view,
                  'links': original['links'] if view == 'relationship' else []}
        pages = visual_pages(visual, get_template(template), 1080, 390)
        labels = set(); relations = set()
        for page in pages:
            svg, boxes = visual_svg(page, get_template(template), 1080, 390)
            root = ET.fromstring(svg)
            labels.update(item['label'] for item in page['items'])
            relations.update((page['items'][e['source']-1]['label'], e['label'],
                              page['items'][e['target']-1]['label']) for e in page['links'])
            assert page['context'] == visual['context']
            assert all(float(t.get('font-size')) >= 28 for t in root.findall('.//s:text', NS))
            assert all(x >= 0 and y >= 0 and x+w <= 1081 and y+h <= 391 for x,y,w,h in boxes)
        assert labels == {v['label'] for v in visual['items']}
        assert relations == {(visual['items'][e['source']-1]['label'], e['label'],
                              visual['items'][e['target']-1]['label']) for e in visual['links']}


def test_explicit_semantic_shapes_are_not_all_rectangles():
    visual = {'representation': 'process', 'items': [
        {'label': '样本记录', 'caption': '读入观测数据', 'shape': 'data'},
        {'label': '判断条件', 'caption': '根据已有条件判断', 'shape': 'decision'},
        {'label': '得到结果', 'caption': '保留满足条件的记录', 'shape': 'result'}],
        'links': [{'source': 1, 'target': 2, 'label': '输入', 'kind': 'directed'},
                  {'source': 2, 'target': 3, 'label': '满足', 'kind': 'directed'}], 'context': ''}
    svg, _ = visual_svg(visual, get_template('paper'), 1100, 490)
    root = ET.fromstring(svg)
    assert root.findall('.//s:polygon', NS)
    assert root.findall('.//s:ellipse', NS)
    assert len(root.findall('.//s:path[@marker-end]', NS)) == 2


def test_comparisons_use_open_space_instead_of_dashboard_cards():
    visual = {**crowded_graph(), 'representation': 'comparison', 'links': [], 'context': ''}
    svg, _ = visual_svg(visual, get_template('paper'), 1100, 490)
    root = ET.fromstring(svg)
    assert not root.findall('.//s:rect', NS)
    assert not root.findall('.//s:path[@marker-end]', NS)


def test_dense_edge_can_separate_explanations_without_losing_them():
    from zhijiang.story_svg import visual_pages
    visual={'representation':'relationship','items':[
        {'label':'原始观测资料','caption':'需要完整保留的定义与说明以及必要前提不能因排版问题省略条件'},
        {'label':'用于预测的模型','caption':'这是另一个对象的完整说明及应用前提需要在连续画面中保留'}],
        'links':[{'source':1,'target':2,'label':'提供构建所需的实际观测资料','kind':'directed'}],
        'context':'前提条件保持不变'}
    pages=visual_pages(visual,get_template('paper'),940,390)
    assert any(p['links'] for p in pages)
    for item in visual['items']:
        assert any(item in p['items'] for p in pages)
