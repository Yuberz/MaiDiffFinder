#!/usr/bin/env python3
"""Build the maimai Pair Finder site from a clone of zvuc/otoge-db.

Usage:
    git clone --depth 1 https://github.com/zvuc/otoge-db.git
    python3 build.py ./otoge-db/maimai

Output (in ./dist):
    index.html    the page, with the slim song data inlined
    jackets.webp  one sprite sheet holding every jacket as a small thumbnail

Re-run after pulling a newer otoge-db to refresh the data.
"""
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
THUMB = 96          # px per jacket inside the sprite sheet
WEBP_QUALITY = 72

# Chart slots in the order the page uses them.
STD_KEYS = ["lev_bas", "lev_adv", "lev_exp", "lev_mas", "lev_remas"]
DX_KEYS = ["dx_lev_bas", "dx_lev_adv", "dx_lev_exp", "dx_lev_mas", "dx_lev_remas"]

# From otoge-db's own table config (src/js/maimai.table-config.js).
VERSION_NAMES = [
    (10000, "maimai"), (11000, "maimai PLUS"), (12000, "GreeN"),
    (13000, "GreeN PLUS"), (14000, "ORANGE"), (15000, "ORANGE PLUS"),
    (16000, "PiNK"), (17000, "PiNK PLUS"), (18000, "MURASAKi"),
    (18500, "MURASAKi PLUS"), (19000, "MiLK"), (19500, "MiLK PLUS"),
    (19900, "FiNALE"), (20000, "でらっくす"), (20500, "でらっくす PLUS"),
    (21000, "Splash"), (21500, "Splash PLUS"), (22000, "UNiVERSE"),
    (22500, "UNiVERSE PLUS"), (23000, "FESTiVAL"), (23500, "FESTiVAL PLUS"),
    (24000, "BUDDiES"), (24500, "BUDDiES PLUS"), (25000, "PRiSM"),
    (25500, "PRiSM PLUS"), (26000, "CiRCLE"), (26500, "CiRCLE PLUS"),
    (27000, "MAGiCAL"),
]


def version_index(code: int) -> int:
    idx = 0
    for i, (start, _) in enumerate(VERSION_NAMES):
        if code >= start:
            idx = i
    return idx


def load_region(path: Path, region: str):
    songs = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for s in songs:
        if s.get("lev_utage"):           # utage (party) charts have no normal levels
            continue
        if s.get("deleted_date"):        # removed from the game
            continue
        if region == "intl" and s.get("intl") != "1":
            continue                     # not released on the international version
        charts = []
        for chart_type, keys in ((0, STD_KEYS), (1, DX_KEYS)):
            for slot, key in enumerate(keys):
                label = s.get(key)
                if not label:
                    continue
                const = s.get(key + "_i")
                charts.append([chart_type, slot, label, float(const) if const else None])
        if not charts:
            continue
        song = {
            "t": s["title"],
            "a": s.get("artist", ""),
            "b": s.get("bpm", ""),
            "o": int(s.get("version", 0) or 0),
            "i": s["image_url"],
            "ch": charts,
        }
        # otoge-db's title_kana is a sort key: katakana with no dakuten or small kana (雑魚 is サコ).
        # Keep it only when it holds kana; the page uses it for romaji search.
        kana = s.get("title_kana", "")
        if re.search("[぀-ヿ]", kana):
            song["k"] = kana
        out.append(song)
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1]).resolve()
    data_dir, jacket_dir = src / "data", src / "jacket"
    for p in (data_dir, jacket_dir):
        if not p.is_dir():
            sys.exit(f"Not found: {p}\nPass the 'maimai' folder of an otoge-db clone.")

    regions = {
        "intl": load_region(data_dir / "music-ex-intl.json", "intl"),
        "jp": load_region(data_dir / "music-ex.json", "jp"),
    }

    # One shared sprite sheet for every jacket either region uses.
    names = sorted({s["i"] for songs in regions.values() for s in songs})
    index = {n: k for k, n in enumerate(names)}
    cols = math.ceil(math.sqrt(len(names)))
    rows = math.ceil(len(names) / cols)
    sheet = Image.new("RGB", (cols * THUMB, rows * THUMB), (24, 32, 46))
    for n, k in index.items():
        with Image.open(jacket_dir / n) as im:
            im = im.convert("RGBA").resize((THUMB, THUMB), Image.LANCZOS)
            flat = Image.new("RGB", im.size, (24, 32, 46))
            flat.paste(im, mask=im.getchannel("A"))
            im = flat
        sheet.paste(im, ((k % cols) * THUMB, (k // cols) * THUMB))

    for songs in regions.values():
        for s in songs:
            s["j"] = index[s.pop("i")]

    payload = {
        "versions": [name for _, name in VERSION_NAMES],
        "versionStarts": [start for start, _ in VERSION_NAMES],
        "atlas": {"cols": cols, "rows": rows},
        "regions": regions,
    }

    dist = HERE / "dist"
    dist.mkdir(exist_ok=True)
    sheet.save(dist / "jackets.webp", "WEBP", quality=WEBP_QUALITY, method=6)

    template = (HERE / "template.html").read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/")    # keep the JSON safe inside a <script> tag
    (dist / "index.html").write_text(template.replace("/*__DATA__*/null", blob), encoding="utf-8")

    print(f"intl songs: {len(regions['intl'])}   jp songs: {len(regions['jp'])}")
    print(f"jackets: {len(names)} in a {cols}x{rows} sheet")
    for f in ("index.html", "jackets.webp"):
        print(f"{f}: {(dist / f).stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
