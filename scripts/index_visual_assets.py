"""Validate descriptions, rebuild an ignored index and render a contact sheet."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zhijiang.visual_assets import AssetCatalog

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--rebuild', action='store_true')
    parser.add_argument('--contact-sheet', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('data/visual-assets'))
    args = parser.parse_args()
    catalog = AssetCatalog()
    if args.rebuild:
        catalog.write_index(args.output/'index.json')
    if args.contact_sheet:
        from PIL import Image, ImageDraw
        from zhijiang.presentation import _font
        assets = list(catalog.assets.values())
        for start in range(0, len(assets), 25):
            sheet = Image.new('RGB', (1500, 1600), '#FBFAF5'); draw = ImageDraw.Draw(sheet)
            for i, asset in enumerate(assets[start:start+25]):
                x, y = (i%5)*300, (i//5)*320
                with Image.open(catalog.rasterize(asset.id, args.output/'cache', 256)) as icon:
                    icon=icon.copy();icon.thumbnail((256,256),Image.Resampling.LANCZOS)
                    sheet.paste(icon, (x+22+(256-icon.width)//2,y+8+(256-icon.height)//2), icon)
                draw.text((x+12,y+272), asset.title, font=_font(22), fill='#242724')
            args.output.mkdir(parents=True, exist_ok=True)
            sheet.save(args.output/f'contact-{start//25+1}.png')
    print(f'{len(catalog.assets)} valid assets; fingerprint={catalog.fingerprint}')

if __name__ == '__main__':
    main()
