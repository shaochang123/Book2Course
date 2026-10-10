"""Local, described illustrations. Metadata is presentation data, not evidence."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
import hashlib
import json
import math
from pathlib import Path
import re
import tomllib
from xml.etree import ElementTree as ET

ASSET_ROOT = Path(__file__).parent / 'assets' / 'visuals'


def object_mentions(text, aliases):
    """Literal object names, with word boundaries for Latin-script aliases."""
    found=[]
    for word in aliases:
        if len(word)<2:continue
        pattern=re.escape(word)
        if re.fullmatch(r'[\x00-\x7f]+',word):
            pattern=r'(?<![A-Za-z0-9_])'+pattern+r'(?![A-Za-z0-9_])'
        if match:=re.search(pattern,text,re.I):found.append(match.group())
    return found
SCHEMA_VERSION = 2


class AssetError(ValueError):
    pass


def _terms(text):
    text = str(text).lower()
    result = re.findall(r'[a-z0-9]+', text)
    for run in re.findall(r'[\u3400-\u9fff]+', text):
        result.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run) == 1:
            result.append(run)
    return result


def validate_svg(path):
    raw = Path(path).read_bytes()
    if len(raw) > 4_000_000 or re.search(br'<!DOCTYPE|<!ENTITY', raw, re.I):
        raise AssetError('SVG 大小或实体声明不受支持。')
    root = ET.fromstring(raw)
    if root.tag != '{http://www.w3.org/2000/svg}svg' or not root.get('viewBox'):
        raise AssetError('SVG 必须有 viewBox。')
    for node in root.iter():
        if node.tag.split('}')[-1] in {'script', 'foreignObject', 'image', 'use'}:
            raise AssetError('SVG 不允许脚本、外部对象或引用。')
        for key, value in node.attrib.items():
            if key.lower().startswith('on') or key.split('}')[-1] == 'href' or 'url(' in value.lower():
                raise AssetError('SVG 不允许外部引用或事件。')
    return raw


@dataclass(frozen=True)
class VisualAsset:
    id: str
    file: str
    title: str
    description: str
    tags: tuple[str, ...]
    domain: str
    usage: str
    limitations: str
    source: str
    license: str
    entity_aliases: tuple[str, ...] = ()
    kind: str = 'symbol'
    style: str = 'line-symbol'

    def public(self):
        return {**asdict(self), 'tags': list(self.tags), 'entity_aliases':list(self.entity_aliases)}


class AssetCatalog:
    def __init__(self, root=ASSET_ROOT):
        self.root = Path(root).resolve()
        self.assets = {}
        digest = hashlib.sha256(str(SCHEMA_VERSION).encode())
        if not self.root.is_dir():
            raise AssetError('素材库不存在。')
        directories = [self.root, *sorted(p for p in self.root.rglob('*') if p.is_dir())]
        described = set()
        for folder in directories:
            readme = folder / 'README.md'
            if not readme.is_file():
                raise AssetError(f'素材目录缺少 README.md：{folder.name}')
            text = readme.read_text(encoding='utf-8')
            digest.update(readme.relative_to(self.root).as_posix().encode())
            digest.update(text.encode())
            for block in re.findall(r'```toml\s*\n(.*?)```', text, re.S):
                for item in tomllib.loads(block).get('assets', []):
                    asset = VisualAsset(**{**item, 'tags': tuple(item['tags']),
                                           'entity_aliases':tuple(item.get('entity_aliases',[]))})
                    if asset.kind not in {'symbol', 'illustration'}:
                        raise AssetError('素材 kind 须为 symbol 或 illustration。')
                    if not re.fullmatch(r'[a-z][a-z0-9_.-]{2,80}', asset.id) or asset.id in self.assets:
                        raise AssetError('素材 ID 非法或重复：'+asset.id)
                    path = (folder / asset.file).resolve()
                    if not path.is_relative_to(self.root) or not path.is_file():
                        raise AssetError('素材路径越界或不存在：'+asset.file)
                    if path.suffix.lower() == '.svg':
                        raw = validate_svg(path)
                    elif path.suffix.lower() == '.png':
                        from PIL import Image
                        with Image.open(path) as image:
                            image.verify()
                        raw = path.read_bytes()
                    else:
                        raise AssetError('仅支持 SVG 与 PNG。')
                    digest.update(asset.id.encode()); digest.update(raw)
                    relative = path.relative_to(self.root).as_posix()
                    self.assets[asset.id] = VisualAsset(**{**asdict(asset), 'file': relative})
                    described.add(path)
        actual = {p.resolve() for p in self.root.rglob('*') if p.suffix.lower() in {'.svg', '.png'}}
        if actual != described:
            raise AssetError('素材文件与目录说明不一致。')
        self.fingerprint = digest.hexdigest()
        self._documents = {key: Counter(_terms(' '.join([a.title]*3 + list(a.tags)*2 + [a.description])))
                           for key, a in self.assets.items()}
        self._df = Counter(term for doc in self._documents.values() for term in doc)

    def path(self, asset_id):
        if asset_id not in self.assets:
            raise AssetError('未知素材 ID：'+asset_id)
        return self.root / self.assets[asset_id].file

    def search(self, query, domain='', limit=8):
        tokens = set(_terms(query))
        matches = []
        for key, asset in self.assets.items():
            if domain and domain != asset.domain:
                continue
            document = self._documents[key]
            score = sum(math.log(1+len(self.assets)/(1+self._df[t])) * (document[t]/(document[t]+1.2))
                        for t in tokens if t in document)
            # Long named objects/aliases outrank incidental descriptive terms.
            phrases = [asset.title, *asset.entity_aliases, *asset.tags]
            score += sum(3 + min(4, len(p)/3) for p in phrases if object_mentions(query,[p]))
            # Favor inspected illustrations only when their actual object occurs.
            # This applies to every domain, not to a textbook or a named example.
            if asset.kind == 'illustration' and object_mentions(query,asset.entity_aliases):
                score += 8
            if score > 0:
                matches.append((score, asset))
        matches.sort(key=lambda pair: (-pair[0], pair[1].id))
        return [{**asset.public(), 'score': round(score, 4)} for score, asset in matches[:min(8, limit)]]

    def write_index(self, output):
        output = Path(output); output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'version': SCHEMA_VERSION, 'fingerprint': self.fingerprint,
            'assets': [a.public() for a in self.assets.values()]}, ensure_ascii=False, indent=2), encoding='utf-8')

    def rasterize(self, asset_id, cache, pixels=900):
        path = self.path(asset_id)
        if path.suffix.lower() == '.png':
            return path
        raw = validate_svg(path)
        key = hashlib.sha256(raw+str(pixels).encode()).hexdigest()
        output = Path(cache) / f'{key}.png'
        if not output.is_file():
            import resvg_py
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(resvg_py.svg_to_bytes(svg_string=raw.decode('utf-8'), width=pixels))
        return output


def segment_query(lesson, segment):
    """Use only entities associated with this passage, not all course entities."""
    text = ' '.join([segment.title, *segment.bullets, segment.narration])
    graph = lesson.animation_report.get('knowledge_graph', {})
    if isinstance(graph, dict):
        for node in graph.get('nodes', []):
            label = node.get('label', node.get('title', '')) if isinstance(node, dict) else ''
            if label and label in text:
                text += ' '+label
    return text
