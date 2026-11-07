#!/usr/bin/env python3
"""Build the maimai Pair Finder site from a clone of zvuc/otoge-db.

Usage:
    pip install pillow pykakasi
    git clone --depth 1 https://github.com/zvuc/otoge-db.git
    python3 build.py ./otoge-db/maimai

translations.txt holds the romaji and English titles shown when you hover or tap a title.
Format: 'title || romaji || english', one per line. Edit it and rebuild to fix a translation.
The English titles are unofficial. Kana-only titles without a romaji entry get one from pykakasi.

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


MACRON = {"aa": "ā", "ii": "ī", "uu": "ū", "ee": "ē", "oo": "ō"}
_KKS = None


def load_translations(path: Path):
    """translations.txt: one 'title || romaji || english' per line. Either field may be empty."""
    rows = {}
    if not path.exists():
        return rows
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("||")]
        if len(parts) != 3:
            sys.exit(f"translations.txt line {n}: expected 'title || romaji || english'")
        # A title may appear on several lines; later non-empty fields fill in or replace earlier ones.
        old = rows.get(parts[0], ("", ""))
        rows[parts[0]] = (parts[1] or old[0], parts[2] or old[1])
    return rows


def auto_romaji(title: str) -> str:
    """Romaji for titles written only in kana, using pykakasi (pip install pykakasi). Empty if unavailable."""
    global _KKS
    try:
        import pykakasi
    except ImportError:
        return ""
    if _KKS is None:
        _KKS = pykakasi.kakasi()
    words = []
    for tok in _KKS.convert(title):
        h = tok["hepburn"]
        if "ー" in tok["orig"]:
            h = re.sub(r"aa|ii|uu|ee|oo", lambda m: MACRON[m.group()], h)
        words.append(h)
    s = " ".join(w for w in words if w.strip())
    s = re.sub(r"\s+([!?.,:;)\]」』】！？。、])", r"\1", s)
    s = re.sub(r"([(\[「『【])\s+", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return " ".join(w[:1].upper() + w[1:] for w in s.split(" "))


def load_region(path: Path, region: str, translations):
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
        # Romaji ("r") and English ("e") for the hover/tap popover and for search.
        romaji, english = translations.get(s["title"], ("", ""))
        if not romaji and re.search("[぀-ヿ]", s["title"]) and not re.search("[一-鿿]", s["title"]):
            romaji = auto_romaji(s["title"])
        if romaji and romaji != s["title"]:
            song["r"] = romaji
        if english and english != s["title"]:
            song["e"] = english
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

    translations = load_translations(HERE / "translations.txt")
    regions = {
        "intl": load_region(data_dir / "music-ex-intl.json", "intl", translations),
        "jp": load_region(data_dir / "music-ex.json", "jp", translations),
    }
    known = {s["t"] for songs in regions.values() for s in songs}
    unknown = [t for t in translations if t not in known]
    if unknown:
        print(f"warning: {len(unknown)} titles in translations.txt are not in the data, e.g. {unknown[:3]}")

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
