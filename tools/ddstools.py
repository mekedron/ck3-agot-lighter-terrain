#!/usr/bin/env python3
"""
Regenerate the down-sized AGOT map/model textures shipped by this patch.

Pipeline (per texture)
  1. decode mip 0 of the AGOT source with Pillow (DX10 BC3_SRGB headers are
     patched to a legacy 'DXT5' header in memory because Pillow lacks dxgi 78);
  2. box-downsample (per channel, no alpha premultiplication) to the target size
     and build the full mip chain down to 1x1 the same way;
  3. encode every level with ImageMagick 7:
        magick <level>.png -define dds:compression=dxt1|dxt5 -define dds:mipmaps=0
               -define dds:cluster-fit=true -define dds:weight-by-alpha=false <level>.dds
     (mipmaps=0 = single level; cluster-fit = best quality; weight-by-alpha=false
      because alpha holds data (masks / normal component), not coverage);
  4. strip ImageMagick's 128-byte header from every level and write one DDS
     whose header mirrors the AGOT source header (same fourcc / DX10 block),
     updated for the new size, linear size, mip count and mipmap caps.
  5. read every level back with Pillow and print MAE per channel against the
     source down-sampled to the same size (verification).

Usage:
  tools/make_textures.py [--agot DIR] [--out DIR] [--only NAME ...] [--verify-only]

Requirements: python3, Pillow (>= 9, DDS read), numpy, ImageMagick 7 ('magick').
No sudo, no writes into the AGOT folder.
"""
import argparse
import io
import os
import struct
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

AGOT_DEFAULT = os.path.expanduser(
    "~/.local/share/Steam/steamapps/workshop/content/1158310/2962333032")
OUT_DEFAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# name -> (relative path, scale, compression)
#   scale 1.0 keeps the resolution (snow mask: only the format / mip chain change)
TEXTURES = {
    # "const": the source is one colour over the whole image (checked at run time), so a
    # 16x16 texture with a mip chain is the same texture to the shader
    "snow_mask":     ("gfx/map/textures/snow_mask.dds",              "const", "dxt5"),
    "cloud":         ("gfx/map/fog_of_war/cloud.dds",                0.5, "dxt5"),
    "surround_fade": ("gfx/map/surround_map/surround_fade.dds",      0.5, "dxt5"),
    "surround_mask": ("gfx/map/surround_map/surround_mask.dds",      0.5, "dxt1"),
    "foam_map":      ("gfx/map/water/foam_map.dds",                  "const", "dxt5"),
    "mtn_diffuse":   ("gfx/models/mapitems/mountains/mountain_01/mountains_mapobject_01_diffuse.dds",    0.5, "dxt5"),
    "mtn_normal":    ("gfx/models/mapitems/mountains/mountain_01/mountains_mapobject_01_normal.dds",     0.5, "dxt5"),
    "mtn_properties": ("gfx/models/mapitems/mountains/mountain_01/mountains_mapobject_01_properties.dds", 0.5, "dxt5"),
}

# ---------------------------------------------------------------- DDS header helpers
DDSD_CAPS, DDSD_HEIGHT, DDSD_WIDTH, DDSD_PITCH = 0x1, 0x2, 0x4, 0x8
DDSD_PIXELFORMAT, DDSD_MIPMAPCOUNT, DDSD_LINEARSIZE = 0x1000, 0x20000, 0x80000
DDSCAPS_COMPLEX, DDSCAPS_TEXTURE, DDSCAPS_MIPMAP = 0x8, 0x1000, 0x400000
DDPF_FOURCC = 0x4
BLOCK_BYTES = {b"DXT1": 8, b"DXT3": 16, b"DXT5": 16}
DXGI_LEGACY = {71: b"DXT1", 72: b"DXT1", 74: b"DXT3", 75: b"DXT3", 77: b"DXT5", 78: b"DXT5"}
DXGI_NAMES = {71: "BC1_UNORM", 72: "BC1_UNORM_SRGB", 77: "BC3_UNORM", 78: "BC3_UNORM_SRGB",
              98: "BC7_UNORM", 99: "BC7_UNORM_SRGB", 83: "BC5_UNORM"}


def parse_header(data):
    assert data[:4] == b"DDS ", "not a DDS file"
    size, flags, h, w, pitch, depth, mips = struct.unpack_from("<7I", data, 4)
    pfflags = struct.unpack_from("<I", data, 80)[0]
    fourcc = data[84:88]
    info = dict(w=w, h=h, mips=max(mips, 1), flags=flags, pitch=pitch, pfflags=pfflags,
                fourcc=fourcc, hdr_len=128, dxgi=None, bits=struct.unpack_from("<I", data, 88)[0])
    if fourcc == b"DX10":
        info["dxgi"] = struct.unpack_from("<I", data, 128)[0]
        info["hdr_len"] = 148
    return info


def fmt_name(info):
    if info["dxgi"] is not None:
        return "DX10/%s" % DXGI_NAMES.get(info["dxgi"], "dxgi%d" % info["dxgi"])
    if info["pfflags"] & DDPF_FOURCC:
        return info["fourcc"].decode("ascii", "replace")
    return "uncompressed %d-bit" % info["bits"]


def block_bytes(info):
    if info["dxgi"] is not None:
        return 16 if info["dxgi"] not in (71, 72) else 8
    return BLOCK_BYTES[info["fourcc"]]


def level_size(w, h, bb):
    return max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bb


def mip_dims(w, h):
    dims = [(w, h)]
    while w > 1 or h > 1:
        w, h = max(1, w // 2), max(1, h // 2)
        dims.append((w, h))
    return dims


def decode_level0(data):
    """Pillow RGBA of mip 0. Works around Pillow's missing DX10 BC1/BC3 support."""
    info = parse_header(data)
    if info["dxgi"] in DXGI_LEGACY:
        hdr = bytearray(data[:128])
        hdr[84:88] = DXGI_LEGACY[info["dxgi"]]
        data = bytes(hdr) + data[148:]
    return Image.open(io.BytesIO(data)).convert("RGBA")


def decode_level(data, level):
    """Decode one mip level of a block-compressed DDS by re-wrapping it as a 1-level DDS."""
    info = parse_header(data)
    bb = block_bytes(info)
    off = info["hdr_len"]
    dims = mip_dims(info["w"], info["h"])
    for i in range(level):
        off += level_size(*dims[i], bb)
    w, h = dims[level]
    n = level_size(w, h, bb)
    hdr = bytearray(data[:info["hdr_len"]])
    struct.pack_into("<7I", hdr, 4, 124, (info["flags"] & ~DDSD_MIPMAPCOUNT), h, w, n, 0, 1)
    struct.pack_into("<I", hdr, 108, DDSCAPS_TEXTURE)
    return decode_level0(bytes(hdr) + data[off:off + n])


def build_header(src_hdr, w, h, mips, compression):
    """Header mirroring the source's pixel format block (fourcc or DX10), new geometry."""
    src = parse_header(src_hdr)
    hdr = bytearray(src_hdr[:src["hdr_len"]])
    if not (src["pfflags"] & DDPF_FOURCC):
        # uncompressed source (snow mask): replace the pixel format block by a fourcc one
        fourcc = compression.upper().encode()
        struct.pack_into("<8I", hdr, 76, 32, DDPF_FOURCC, int.from_bytes(fourcc, "little"), 0, 0, 0, 0, 0)
        hdr = hdr[:128]
    fourcc = bytes(hdr[84:88])
    if fourcc == b"DX10":
        bb = 16 if struct.unpack_from("<I", hdr, 128)[0] not in (71, 72) else 8
    else:
        bb = BLOCK_BYTES[fourcc]
    assert compression.upper().encode() == (fourcc if fourcc != b"DX10" else DXGI_LEGACY[struct.unpack_from("<I", hdr, 128)[0]]), \
        "output compression must match the source family"
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if mips > 1:
        flags |= DDSD_MIPMAPCOUNT
    struct.pack_into("<7I", hdr, 4, 124, flags, h, w, level_size(w, h, bb), 0, mips)
    caps1 = DDSCAPS_TEXTURE | (DDSCAPS_COMPLEX | DDSCAPS_MIPMAP if mips > 1 else 0)
    struct.pack_into("<4I", hdr, 108, caps1, 0, 0, 0)
    return bytes(hdr)


# ---------------------------------------------------------------- image helpers
def downsample(img, w, h):
    """Per-channel box filter. Each band is resized as its own 'L' image: Pillow resizes an
    RGBA image with premultiplied alpha, which blacks out the colour wherever alpha is near
    0 - and in terrain and map textures alpha is data (height, masks), not coverage."""
    if img.size == (w, h):
        return img
    return Image.merge(img.mode, [b.resize((w, h), Image.BOX) for b in img.split()])


def encode_level(png_path, dds_path, compression):
    cmd = ["magick", png_path,
           "-define", "dds:compression=" + compression,
           "-define", "dds:mipmaps=0",
           "-define", "dds:cluster-fit=true",
           "-define", "dds:weight-by-alpha=false",
           dds_path]
    subprocess.run(cmd, check=True)
    with open(dds_path, "rb") as f:
        data = f.read()
    info = parse_header(data)
    assert info["fourcc"] == compression.upper().encode() and info["mips"] == 1, info
    return data[128:]


def make_texture(name, agot, out, threads):
    rel, scale, compression = TEXTURES[name]
    src_path = os.path.join(agot, rel)
    dst_path = os.path.join(out, rel)
    with open(src_path, "rb") as f:
        src_data = f.read()
    src = parse_header(src_data)
    img0 = decode_level0(src_data)
    if scale == "const":
        import numpy as np
        a = np.asarray(img0.convert("RGBA")).reshape(-1, 4)
        if not (a.min(0) == a.max(0)).all():
            raise SystemExit("%s is no longer a constant colour - give it a real scale" % rel)
        img0 = Image.new("RGBA", (16, 16), tuple(int(v) for v in a[0]))
        tw, th = 16, 16
    else:
        tw, th = max(1, int(round(src["w"] * scale))), max(1, int(round(src["h"] * scale)))
    dims = mip_dims(tw, th)
    print("[%s] %s %dx%d %s mips=%d -> %dx%d %s mips=%d" % (
        name, rel, src["w"], src["h"], fmt_name(src), src["mips"], tw, th, compression.upper(), len(dims)))

    levels = []
    img = img0
    for (w, h) in dims:
        img = downsample(img, w, h)      # successive halving = proper mip chain
        levels.append(img)

    with tempfile.TemporaryDirectory(prefix="ck3tex_") as tmp:
        def work(i):
            png = os.path.join(tmp, "l%02d.png" % i)
            dds = os.path.join(tmp, "l%02d.dds" % i)
            levels[i].save(png)
            return encode_level(png, dds, compression)
        with ThreadPoolExecutor(max_workers=threads) as ex:
            payloads = list(ex.map(work, range(len(dims))))

    hdr = build_header(src_data, tw, th, len(dims), compression)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "wb") as f:
        f.write(hdr)
        for p in payloads:
            f.write(p)
    return src_path, dst_path


def verify(name, agot, out, check_levels=(0, 1, 3, 6)):
    rel, scale, compression = TEXTURES[name]
    src_path = os.path.join(agot, rel)
    dst_path = os.path.join(out, rel)
    with open(src_path, "rb") as f:
        src_data = f.read()
    with open(dst_path, "rb") as f:
        dst_data = f.read()
    src, dst = parse_header(src_data), parse_header(dst_data)
    dims = mip_dims(dst["w"], dst["h"])
    expected = dst["hdr_len"] + sum(level_size(w, h, block_bytes(dst)) for (w, h) in dims)
    print("== %s" % rel)
    print("   source: %dx%d %-22s mips=%2d %10d bytes" % (src["w"], src["h"], fmt_name(src), src["mips"], len(src_data)))
    print("   output: %dx%d %-22s mips=%2d %10d bytes  header ok=%s magic=%s flags=%#x pfflags=%#x pitch=%d payload ok=%s" % (
        dst["w"], dst["h"], fmt_name(dst), dst["mips"], len(dst_data), dst["mips"] == len(dims),
        dst_data[:4], dst["flags"], dst["pfflags"], dst["pitch"], expected == len(dst_data)))
    ref = decode_level0(src_data)
    img = decode_level0(dst_data)
    print("   pillow: mode=%s size=%s" % (img.mode, img.size))
    for lvl in check_levels:
        if lvl >= len(dims):
            continue
        w, h = dims[lvl]
        a = np.asarray(decode_level(dst_data, lvl)).astype(np.float32)
        r = ref
        for (ww, hh) in dims[:lvl + 1]:
            r = downsample(r, ww, hh)
        b = np.asarray(r).astype(np.float32)
        mae = np.abs(a - b).mean(axis=(0, 1))
        print("   mip %2d %5dx%-5d MAE R=%.3f G=%.3f B=%.3f A=%.3f  max=%.0f" % (lvl, w, h, *mae, np.abs(a - b).max()))
    return len(src_data), len(dst_data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agot", default=AGOT_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--only", nargs="*", default=list(TEXTURES))
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()
    if not args.verify_only:
        for name in args.only:
            make_texture(name, args.agot, args.out, args.threads)
    tot_src = tot_dst = 0
    for name in args.only:
        s, d = verify(name, args.agot, args.out)
        tot_src += s
        tot_dst += d
    print("TOTAL source %.1f MB -> output %.1f MB, saved %.1f MB" % (tot_src / 2**20, tot_dst / 2**20, (tot_src - tot_dst) / 2**20))


if __name__ == "__main__":
    main()
