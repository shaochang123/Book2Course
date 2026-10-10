"""Vendor reviewed public-domain sketches; source/license stay beside each asset.

This is a maintenance command, never a network operation during generation.
Use --cache to import already downloaded originals; otherwise download the
listed SVGs from their public source. Existing project symbols stay intact.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import httpx
from zhijiang.visual_assets import ASSET_ROOT, validate_svg

# Coordinates for the two books are crops of GDJ's single public-domain sheet;
# paths and brush texture are retained, without tracing them into flat icons.
ITEMS = [
    ('life-agriculture','watermelon-sketch','melon',299271,'Firkin / pencilparker',
     '手绘西瓜切片','自由笔触的红色瓜瓤、深色种子和绿色瓜皮。',
     ['西瓜','瓜瓤','瓜皮','watermelon'],['西瓜','watermelon'],'brush-sketch',None),
    ('life-agriculture','apple-sketch','apple',299273,'Firkin / pencilparker',
     '手绘苹果','松散的彩色笔触和叶柄，保留手画轮廓。',
     ['苹果','apple','fruit'],['苹果','apple'],'brush-sketch',None),
    ('life-agriculture','open-book-sketch','books',254442,'GDJ; source Pixabay, uploaded 2016',
     '手绘翻开的书','斜放的打开书本，彩铅排线、纸张阴影与不规则墨线。',
     ['书本','教材','book','textbook','reading'],['书本','书籍','book','textbook'],
     'pencil-sketch',(500,710,1350,650,2)),
    ('life-agriculture','book-stack-sketch','books',254442,'GDJ; source Pixabay, uploaded 2016',
     '手绘书本小叠','三本交错的小书，彩铅着色、纸边和自然排线。',
     ['书本','教材','books','reading'],['书本','书籍','books'],'pencil-sketch',(140,1360,770,550,4)),
    ('computing-ai','laptop-sketch','laptop',105031,'lmproulx',
     '手绘笔记本电脑','细墨线手画的打开笔记本电脑，空白屏幕可承载讲解。',
     ['电脑','计算机','笔记本电脑','laptop','computer'],['电脑','计算机','laptop','computer'],'ink-sketch',None),
    ('computing-ai','magnifier-sketch','magnifier',28419,'bitterjug',
     '手绘放大镜','不规则手画的蓝色镜片与木色手柄。',
     ['放大镜','观察','检索','magnifying glass'],['放大镜','magnifying glass'],'ink-sketch',None),
    ('physics-engineering','light-bulb-sketch','bulb',313198,'m1981',
     '手绘灯泡','自然起伏的蓝色墨线、黄色玻璃和灯座。',
     ['灯泡','电灯','light bulb'],['灯泡','电灯','light bulb'],'brush-sketch',None),
    ('medicine','lungs-ink','lungs',23460,'johnny_automatic; Simmons & Stenhouse, 1912',
     '历史墨线肺部插画','1912年教学插画的手画轮廓与支气管纹理；仅作对象配图。',
     ['肺部','肺泡','肺','lungs','alveoli'],['肺部','肺脏','lungs','lung'],'ink-sketch',None),
    ('biology','butterfly-sketch','butterfly',352665,'teck5',
     '手绘蝴蝶成虫','有翅的蝴蝶成虫：不对称彩色翅膀、起伏墨线和绿色身体；不是幼虫或蛹。',
     ['蝴蝶','昆虫','butterfly'],['蝴蝶','butterfly'],'ink-sketch',None),
]

def prepare(raw, crop=None):
    root=ET.fromstring(raw)
    # Drop editor metadata only; never flatten or redraw the artist's strokes.
    svg_ns='http://www.w3.org/2000/svg'
    for parent in list(root.iter()):
        for child in list(parent):
            if not child.tag.startswith('{'+svg_ns+'}') or child.tag.endswith('}metadata'):
                parent.remove(child)
        for key in list(parent.attrib):
            if key.startswith('{') and not key.startswith('{http://www.w3.org/XML/'):
                del parent.attrib[key]
    if crop:
        selected=list(root)[crop[4]]
        for child in list(root):
            if child is not selected:root.remove(child)
        root.set('viewBox',' '.join(str(v) for v in crop[:4]))
    vb=root.get('viewBox')
    if not vb:
        import re
        vb='0 0 '+' '.join(re.sub('[a-z]+','',root.get(k,'')) for k in ('width','height'))
        root.set('viewBox',vb)
    nums=vb.replace(',',' ').split()
    root.set('width',nums[2]);root.set('height',nums[3])
    ET.register_namespace('',svg_ns)
    return ET.tostring(root,encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cache',type=Path)
    args=parser.parse_args();by_domain={};hashes=[]
    downloaded={}
    for domain,key,cache_key,number,author,title,desc,tags,aliases,style,crop in ITEMS:
        if number not in downloaded:
            cache=args.cache/(cache_key+'.svg') if args.cache else None
            if cache and cache.exists():raw=cache.read_bytes()
            else:
                response=httpx.get(f'https://openclipart.org/download/{number}',timeout=60,follow_redirects=True)
                response.raise_for_status();raw=response.content
            downloaded[number]=raw
        raw=downloaded[number]
        folder=ASSET_ROOT/domain/'handdrawn';folder.mkdir(exist_ok=True)
        path=folder/(key+'.svg');path.write_bytes(prepare(raw,crop));validate_svg(path)
        source=f'https://openclipart.org/detail/{number}; author: {author}'
        record={'id':domain+'.'+key,'file':path.name,'title':title,'description':desc,
                'tags':tags,'entity_aliases':aliases,'domain':domain,'kind':'illustration','style':style,
                'usage':'本页确实讲解该对象时使用，作为相应观点旁的小插画。',
                'limitations':'仅作示意；不证明数学关系、解剖细节或实验结果。原画颜色不代表教材中的特征标签。',
                'source':source,'license':'CC0-1.0'}
        by_domain.setdefault(domain,[]).append(record)
        hashes.append({'asset_id':record['id'],'download_url':f'https://openclipart.org/download/{number}',
                       'original_sha256':hashlib.sha256(raw).hexdigest(),'crop':crop[:4] if crop else None,
                       'source_group_index':crop[4] if crop else None,
                       'stored_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    for domain,records in by_domain.items():
        lines=['# 有出处的手绘插画','','本目录没有下级目录。保留原画自由笔触；透明背景，不是自动描边的扁平图标。',
               '', '所有条目均采用 [Openclipart 的 CC0 公共领域许可](https://openclipart.org/share)。',
               '修改仅涉及编辑器元数据、SVG 尺寸单位，以及书本原有分组的单独裁切；作者与原作页面保留如下。','',
               '| 素材 | 描述 | 原作及作者 |','| --- | --- | --- |']
        lines += [f"| [{r['title']}]({r['file']}) | {r['description']} | {r['source']} |" for r in records]
        lines += ['', '## 检索元数据','','```toml', '\n\n'.join('[[assets]]\n'+'\n'.join(
            f'{k} = {json.dumps(v,ensure_ascii=False)}' for k,v in r.items()) for r in records),'```','']
        (ASSET_ROOT/domain/'handdrawn/README.md').write_text('\n'.join(lines),encoding='utf-8')
        parent=ASSET_ROOT/domain/'README.md';text=parent.read_text(encoding='utf-8')
        text=text.replace('本目录没有下级目录。','')
        nav='## 下级目录\n\n- [handdrawn：有出处的手绘插画](handdrawn/README.md)\n'
        if '## 下级目录' not in text:text += '\n'+nav
        parent.write_text(text,encoding='utf-8')
    root=ASSET_ROOT/'README.md';text=root.read_text(encoding='utf-8')
    text=text.replace('# 原创教学插画库','# 教学插画与符号库')
    text=text.replace('100 个可检索 SVG；透明背景、手绘线条，适配明暗课件。',
                      '100 个原创线条符号，加上 9 个经查看的 CC0 手绘插画。透明背景；自然笔触的插画优先用于具体实例。')
    text=text.replace('源码与插画均为 Book2Course 原创，MIT 许可。',
                      '原创符号采用 MIT 许可；handdrawn 子目录的外部原作采用 CC0-1.0，逐项记录出处，不能标称项目原创。')
    root.write_text(text,encoding='utf-8')
    report=Path('data/art-research/import-provenance.json');report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(hashes,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Imported {len(hashes)} reviewed illustrations; public origins retained.')

if __name__=='__main__':main()
