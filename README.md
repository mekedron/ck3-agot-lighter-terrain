# AGOT Lighter Terrain Textures (CK3)

The idea of [AGOT Micro](https://steamcommunity.com/sharedfiles/filedetails/?id=3254254511),
AGOT's official performance submod - the terrain textures at half size - rebuilt from the
current [A Game of Thrones](https://steamcommunity.com/sharedfiles/filedetails/?id=2962333032)
files - none of Micro's own files. Workshop title "AGOT Lighter Terrain Textures"
(kit in `steam-workshop/`); the description credits Micro and says why it is not used as it
stands. Micro's page asks for no re-creations or re-uploads of Micro; this mod is published
under its own name, with its own files, and the description points at the official one.

## Why not Micro itself

Checked against AGOT 0.5.2.1 on 2026-09-15 (the community update
[3764447931](https://steamcommunity.com/sharedfiles/filedetails/?id=3764447931) ships the same
644 textures byte for byte, plus 16 that the arrays do not use):

* **Arrays break.** CK3 loads each terrain material's diffuse, normal and properties texture
  into three texture arrays that must be uniform. Micro misses 41 textures of the current
  arrays (`gravel_01`, `mountain_01`, `mountain_01cracks`, `steppe_01` colour variants); they
  stay at 512x512 among 256x256 ones, and `error.log` gets 87 lines of
  `Texture "..." in texture array has inconsistent properties`.
* **Old art.** 238 of its 624 matching textures differ from AGOT's current ones by more than
  10/255 mean per channel: darker colours throughout, red sand about 80/255 off.
* **Artefacts.** Black blocks in several textures (coastline cliffs, red mountains).
* 20 files replace textures AGOT no longer has.

## What this is

`gfx/map/terrain/` with every texture of the three arrays - 470 files, the materials not
commented out in AGOT's `materials.settings` - at half AGOT's size (512 -> 256), the source's
compression, a full mip chain, a per-channel box filter (each band resized on its own:
Pillow resizes RGBA with premultiplied alpha, which blacks out the colour where the alpha
channel - height data here, not coverage - is near 0; the first build had black holes in
the cliff textures for that reason). `tools/make_micro.py` builds them
from the installed AGOT and checks that every array is uniform; the encoder and DDS writer
(`tools/ddstools.py`) are the ones from ck3-agot-performance-patch (Pillow decode, ImageMagick
7 DXT encode per mip level). Re-run it after an AGOT update.

Workshop: [3802303268](https://steamcommunity.com/sharedfiles/filedetails/?id=3802303268).

Load it directly below A Game of Thrones (and COW-AGOT), **instead of** AGOT Micro - not
together with it. It overlaps no other mod of the AGOT playset.

    steam-workshop/make_thumbnail.py   rebuild the Workshop preview from gfx/
    tools/bbcode_to_plain.py     regenerate the Paradox Mods texts
    tools/update.sh              after an AGOT update: rebuild if needed, then install
    ./install.sh                 copy into the Proton prefix mod folder
    tools/make_micro.py          rebuild every texture from the installed AGOT
    tools/make_micro.py --check-only   fails if AGOT changed since the build

`make_micro.py` reads the texture list from AGOT's `materials.settings` on every run, so
new AGOT materials are picked up and textures AGOT stopped using are deleted;
`agot_version.txt` records the AGOT version the textures were built from.

Requirements: python3, Pillow, numpy, ImageMagick 7.
