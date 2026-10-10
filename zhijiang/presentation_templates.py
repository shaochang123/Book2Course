"""Original, fixed layout contracts shared by the planner and PPT renderer."""
from dataclasses import dataclass
from typing import Literal
import html

PPTTemplate = Literal['classic', 'paper', 'academic', 'editorial']
DeckLayout = Literal['wide', 'split', 'captioned', 'evidence', 'illustrated', 'collage']


@dataclass(frozen=True)
class PresentationTemplate:
    id: str
    name: str
    description: str
    background: str
    ink: str
    accent: str
    muted: str
    panel: str
    layouts: tuple[str, ...]
    default_layout: str
    title_size: int
    # Diagram boxes in inches, independent of content or subject names.
    boxes: dict[str, tuple[float, float, float, float]]

    def public(self):
        return {'id': self.id, 'name': self.name, 'description': self.description,
                'colors': {'background': '#'+self.background, 'ink': '#'+self.ink,
                           'accent': '#'+self.accent, 'panel': '#'+self.panel},
                'layouts': list(self.layouts), 'default_layout': self.default_layout}


TEMPLATES = {
    'classic': PresentationTemplate('classic', '深色演示', '大幅图示与独立动画页，适合数学推演。',
        '081623', 'F4F7F9', '6DE2C0', 'A7C0CC', '10283A', ('wide',), 'wide', 32,
        {'wide': (.66, 1.55, 12.0, 5.0)}),
    'paper': PresentationTemplate('paper', '纸上讲解', '暖白纸面、黄色重点块；问题引入、图文分栏与回顾。',
        'FBFAF5', '242724', 'EBCB49', '626961', 'F0EEE3',
        ('split', 'captioned', 'evidence', 'wide'), 'split', 34,
        {'split': (5.05, 1.8, 7.45, 4.65), 'captioned': (.8, 1.5, 11.73, 4.6),
         'evidence': (.8, 1.7, 7.45, 4.8), 'wide': (.8, 1.5, 11.73, 5.1)}),
    'academic': PresentationTemplate('academic', '学术课堂', '蓝白课堂风格；标题层级、证据边栏与条件说明。',
        'F4F7FB', '182D49', '2864B4', '53657C', 'E5EDF8',
        ('evidence', 'split', 'wide'), 'evidence', 30,
        {'evidence': (.65, 1.5, 8.0, 5.15), 'split': (4.85, 1.55, 7.75, 5.0),
         'wide': (.65, 1.45, 12.0, 5.15)}),
    'editorial': PresentationTemplate('editorial', '杂志叙事', '红色章节带、较大标题；知识重点与辅助配图。',
        'F5F0E9', '292422', 'AA3F32', '6D625C', 'E9E0D6',
        ('captioned', 'split', 'wide'), 'captioned', 38,
        {'captioned': (1.3, 1.5, 10.8, 4.55), 'split': (5.0, 1.8, 7.5, 4.55),
         'wide': (1.25, 1.5, 11.3, 5.1)}),
}

# Subject-independent illustration layouts; retain each template's margins.
from dataclasses import replace
for _key, _template in list(TEMPLATES.items()):
    _left = 1.3 if _key == 'editorial' else .8
    TEMPLATES[_key] = replace(_template, title_size=max(36, _template.title_size),
        layouts=(*_template.layouts, 'illustrated', 'collage'),
        boxes={**_template.boxes, 'illustrated': (_left, 1.7, 5.1, 4.9),
               'collage': (_left, 1.7, 11.4-(_left-.8), 4.9)})


def get_template(template_id: str) -> PresentationTemplate:
    try:
        return TEMPLATES[template_id]
    except KeyError as exc:
        raise ValueError('未知 PPT 模板。') from exc


def template_instruction(template_id: str) -> str:
    template = get_template(template_id)
    return ('\n教学表达要求：先提出当前来源能够回答的问题，再解释概念或条件，'
            '沿用来源中合适的例子与对比，最后回顾。每个片段解决一个具体问题；'
            '画面提示词短，口播补充原因和前提，不朗读整页。'
            '适合比较、原文插图或定义的内容不强行做流程图或坐标动画。'
            '来源中的假设、适用范围和不确定性必须保留；不能为模仿视频简化掉条件。'
            '不要固定使用某学科例子，不复制参考视频的图像、文字或音色。'
            '\n所选 PPT 模板：'+template.name+'；'+template.description+
            '。版式可选：'+', '.join(template.layouts)+'。')


def template_preview_svg(template_id: str) -> str:
    template = get_template(template_id)
    x, y, w, h = template.boxes[template.default_layout]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720">',
        f'<title>{html.escape(template.name)}：版式示意</title>',
        f'<rect width="1280" height="720" fill="#{template.background}"/>',
        f'<rect x="48" y="35" width="12" height="70" fill="#{template.accent}"/>',
        f'<text x="82" y="84" font-family="Microsoft YaHei, sans-serif" font-size="38" fill="#{template.ink}">{html.escape(template.name)}</text>',
        f'<rect x="{x*96}" y="{y*96}" width="{w*96}" height="{h*96}" rx="18" fill="#{template.panel}"/>',
        f'<circle cx="{(x+w/2)*96}" cy="{(y+h/2)*96}" r="65" fill="none" stroke="#{template.accent}" stroke-width="8"/>',
        f'<text x="{(x+w/2)*96}" y="{(y+h/2)*96+120}" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="24" fill="#{template.ink}">图示 / 原文 / 演示</text>']
    if template.default_layout == 'split':
        lx, ly, lw = 120, 230, 280
    elif template.default_layout == 'evidence':
        lx, ly, lw = 884, 190, 265
    else:
        lx, ly, lw = 150, 650, 480
    for i in range(3 if template.default_layout != 'captioned' else 1):
        parts.append(f'<rect x="{lx}" y="{ly+i*86}" width="{lw}" height="16" rx="8" fill="#{template.accent}"/>')
    parts.append('</svg>')
    return ''.join(parts)
