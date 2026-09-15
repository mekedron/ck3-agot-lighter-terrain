#!/usr/bin/env python3
"""
Rebuild AGOT's terrain textures at half size: the idea of AGOT Micro, made from the
current AGOT files.

CK3 loads every terrain material's diffuse, normal and properties texture into three
texture arrays, and an array needs all its textures at the resolution and format of the
first one. AGOT Micro (Workshop 3254254511, last built for CK3 1.12.5; the community
update 3764447931 ships the same files) was checked against AGOT 0.5.2.1:
  * it misses 41 textures of the current arrays (gravel_01, mountain_01,
    mountain_01cracks, steppe_01 variants); they stay at 512x512 among 256x256 ones and
    the game logs 87 "in texture array has inconsistent properties" errors;
  * 238 of its 624 matching textures differ from current AGOT by more than 10/255 mean
    per channel - older art and darker colours (red sand about 80/255 off);
  * several carry black block artefacts (coastline cliffs, red mountains);
  * 20 of its files replace textures AGOT no longer has.

This script writes every texture of the three arrays (the materials not commented out
in AGOT's gfx/map/terrain/materials.settings) at half AGOT's size: the source's
compression, a full mip chain, a per-channel box filter. Encoder and DDS writer are in
ddstools.py (shared with ck3-agot-performance-patch). Afterwards it checks that every
array is uniform and prints the mean error of each output against the source.

Textures under gfx/map/terrain that the current arrays no longer use are deleted, and the
AGOT version the build came from is written to agot_version.txt; --check-only compares
it with the installed AGOT and fails if AGOT has changed since.

Usage: tools/make_micro.py [--agot DIR] [--check-only] [--threads N]
"""
import argparse, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ddstools

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def active_arrays(agot):
    s = open(os.path.join(agot, "gfx/map/terrain/materials.settings"), encoding="utf-8-sig", errors="replace").read()
    s = "\n".join(l.split("#")[0] for l in s.split("\n"))
    return {key: ["gfx/map/terrain/" + v for v in re.findall(key + r'\s*=\s*"([^"]+\.dds)"', s)]
            for key in ("diffuse", "normal", "material")}

def header(path):
    with open(path, "rb") as f:
        return ddstools.parse_header(f.read(148))

def mismatches(agot, root):
    """Array slots whose texture (from root if present, AGOT otherwise) differs from slot 0."""
    out = []
    for key, files in active_arrays(agot).items():
        pick = lambda rel: os.path.join(root, rel) if os.path.exists(os.path.join(root, rel)) else os.path.join(agot, rel)
        h0 = header(pick(files[0]))
        for rel in files:
            h = header(pick(rel))
            if (h["w"], h["h"], ddstools.fmt_name(h)) != (h0["w"], h0["h"], ddstools.fmt_name(h0)):
                out.append((key, rel))
    return out

def agot_version(agot):
    m = re.search(r'^version\s*=\s*"([^"]*)"', open(os.path.join(agot, "descriptor.mod"), encoding="utf-8-sig", errors="replace").read(), re.M)
    return m.group(1) if m else "unknown"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agot", default=ddstools.AGOT_DEFAULT)
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()
    files = sorted({rel for v in active_arrays(args.agot).values() for rel in v})
    stamp = os.path.join(HERE, "agot_version.txt")
    built = open(stamp).read().strip() if os.path.exists(stamp) else None
    have = {os.path.relpath(os.path.join(r, f), HERE) for r, _, fs in os.walk(os.path.join(HERE, "gfx/map/terrain")) for f in fs}
    print("AGOT installed %s, built from %s | array textures: %d, in this mod: %d, missing: %d, unused: %d | mismatched slots: %d"
          % (agot_version(args.agot), built, len(files), len(have), len(set(files) - have), len(have - set(files)),
             len(mismatches(args.agot, HERE))))
    if args.check_only:
        sys.exit(0 if built == agot_version(args.agot) and set(files) == have and not mismatches(args.agot, HERE) else 1)
    for rel in sorted(have - set(files)):
        os.remove(os.path.join(HERE, rel))
        print("removed, no longer used by AGOT:", rel)
    for rel in files:
        h = header(os.path.join(args.agot, rel))
        comp = ddstools.fmt_name(h).split("/")[-1].lower()
        comp = {"bc3_unorm": "dxt5", "bc3_unorm_srgb": "dxt5", "bc1_unorm": "dxt1", "bc1_unorm_srgb": "dxt1"}.get(comp, comp)
        ddstools.TEXTURES[rel] = (rel, 0.5, comp)
        ddstools.make_texture(rel, args.agot, HERE, args.threads)
    tot_s = tot_d = 0
    for rel in files:
        s, d = ddstools.verify(rel, args.agot, HERE, check_levels=(0,))
        tot_s += s; tot_d += d
    left = mismatches(args.agot, HERE)
    print("written %d textures: %.1f MB at AGOT's size -> %.1f MB | mismatched slots after: %d"
          % (len(files), tot_s / 2**20, tot_d / 2**20, len(left)))
    if not left:
        open(stamp, "w").write(agot_version(args.agot) + "\n")
    sys.exit(1 if left else 0)

if __name__ == "__main__":
    main()
