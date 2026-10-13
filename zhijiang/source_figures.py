"""Extract a selected source figure from a real PDF, never a model file path."""
from __future__ import annotations
import hashlib
import math
from pathlib import Path


def figure_candidates(data, pages):
    """Find actual embedded pictures; coordinates come from PDFium, not an LLM.

    Full-page scans are not figures. Vector drawings and rotated pages can still
    use the vision crop path; their bounds are not guessed by this extractor.
    """
    import pypdfium2
    fingerprint = hashlib.sha256(data).hexdigest()
    found = []
    with pypdfium2.PdfDocument(data) as document:
        for number in sorted(set(pages)):
            if type(number) is not int or not 1 <= number <= len(document):
                continue
            page=document[number-1]
            try:
                if page.get_rotation():
                    continue
                width, height = page.get_size()
                for index, obj in enumerate(page.get_objects()):
                    if obj.type != 3:
                        continue
                    left, bottom, right, top = obj.get_bounds()
                    box = [max(0, left/width), max(0, 1-top/height),
                           min(1, right/width), min(1, 1-bottom/height)]
                    w, h = box[2]-box[0], box[3]-box[1]
                    if w < .08 or h < .06 or w*h > .85:
                        continue
                    found.append({'id': f'figure-p{number}-{index}',
                                  'page': number, 'box': box,
                                  'kind': 'embedded_source_picture',
                                  'source_sha256': fingerprint})
            finally:
                page.close()
    return found


def page_preview(data,page):
    """Bound vision input size; source crops retain the original render scale."""
    from io import BytesIO
    from PIL import Image
    from zhijiang.math_sources import page_png
    with Image.open(BytesIO(page_png(data,page))) as image:
        image.thumbnail((1000,1400))
        result=BytesIO();image.save(result,format='PNG')
        return result.getvalue()


def extract_figure(pdf_path,page,box,*,folder,segment_id):
    if type(page) is not int or page<1 or len(box)!=4:return None
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in box):return None
    left,top,right,bottom=box
    if not (0<=left<right<=1 and 0<=top<bottom<=1 and right-left>=.08 and bottom-top>=.06):return None
    import pypdfium2
    data=Path(pdf_path).read_bytes()
    with pypdfium2.PdfDocument(data) as document:
        if page>len(document):return None
        source=document[page-1];bitmap=source.render(scale=2)
        try:image=bitmap.to_pil().convert('RGB')
        finally:bitmap.close();source.close()
    cropped=image.crop((round(left*image.width),round(top*image.height),
                        round(right*image.width),round(bottom*image.height)))
    if all(high-low<=2 for low,high in cropped.getextrema()):return None
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    destination=folder/f'segment-{segment_id:03d}.png';cropped.save(destination)
    return {'page':page,'box':box,'file':'source-figures/'+destination.name,
            'source_sha256':hashlib.sha256(data).hexdigest(),'image_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
            'kind':'cropped_source_figure_not_generated_illustration'}
