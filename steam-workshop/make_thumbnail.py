"""Rebuilds thumbnail.png (Workshop preview) and thumbnail-200px.png (legibility check at
Steam's listing size, not uploaded).

No screenshots: a mosaic of this mod's own terrain textures (decoded from gfx/), the same
top band as the sibling mods, and one label with the size saving. Nothing about frame
rate - that depends on the machine."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "tools"))
from thumbnail_layout import S, BAND, GOLD, CREAM, DARK, FB, fit, finish
import ddstools

TITLE = "AGOT TERRAIN"
SUB = "TEXTURES AT HALF SIZE"
TAG = "157 MB → 39 MB"
TILES = ["grass_01_diffuse", "desert_red_flat_01_diffuse", "coastline_cliff_grey_diffuse", "snow_diffuse",
         "gravel_01_blue_diffuse", "farmland_01_diffuse", "forest_leaf_01_diffuse", "mountain_01_green_diffuse",
         "steppe_01_rust_diffuse", "beach_02_diffuse", "hills_01_diffuse", "wetlands_02_diffuse"]
COLS, ROWS = 4, 3

def pick():
    have = {}
    for r, _, fs in os.walk(os.path.join(ROOT, "gfx/map/terrain")):
        for f in fs:
            if f.endswith("_diffuse.dds"):
                have[f[:-4]] = os.path.join(r, f)
    chosen = [have[t] for t in TILES if t in have]
    rest = sorted(p for k, p in have.items() if p not in chosen)
    step = max(1, len(rest) // (COLS * ROWS))
    chosen += rest[::step]
    return chosen[:COLS * ROWS]

def main():
    canvas = Image.new("RGB", (S, S), DARK[:3])
    w, h = S // COLS, (S - BAND) // ROWS
    for i, p in enumerate(pick()):
        side = max(w, h)
        im = ddstools.decode_level0(open(p, "rb").read()).convert("RGB").resize((side, side), Image.LANCZOS)
        im = im.crop(((side - w) // 2, (side - h) // 2, (side - w) // 2 + w, (side - h) // 2 + h))
        canvas.paste(im, ((i % COLS) * w, BAND + (i // COLS) * h))
    d = ImageDraw.Draw(canvas, "RGBA")
    for c in range(1, COLS): d.rectangle([c * w - 2, BAND, c * w + 1, S], fill=DARK)
    for r in range(1, ROWS): d.rectangle([0, BAND + r * h - 2, S, BAND + r * h + 1], fill=DARK)
    f_title = fit(d, TITLE, 92, S - 60); f_sub = fit(d, SUB, 58, S - 60)
    tw = d.textlength(TITLE, font=f_title); d.text(((S - tw) / 2, 18), TITLE, font=f_title, fill=CREAM)
    sw = d.textlength(SUB, font=f_sub); d.text(((S - sw) / 2, 118), SUB, font=f_sub, fill=GOLD)
    d.rectangle([0, BAND - 4, S, BAND], fill=GOLD)
    f_tag = fit(d, TAG, 96, S - 100); pad = 22
    tw = d.textlength(TAG, font=f_tag); th = f_tag.size + pad * 2 - 8
    x, y = (S - tw) / 2 - pad, S - th - 30
    d.rectangle([x, y, x + tw + pad * 2, y + th], fill=(14, 12, 10, 225))
    d.rectangle([x, y, x + 6, y + th], fill=GOLD)
    d.text((x + pad + 4, y + pad - 8), TAG, font=f_tag, fill=CREAM)
    finish(canvas, os.path.join(ROOT, "thumbnail.png"))

if __name__ == "__main__":
    main()
