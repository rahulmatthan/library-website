#!/usr/bin/env python3
"""Rebuild the Living Bookshelf data from the Eden/Alexandria vault.

Reads every book note in ~/Vaults/Eden/Alexandria, keeps the ones marked Read,
parses frontmatter + the Summary callout, caches each cover locally, and writes
static/library.json (the single source of truth the site loads) plus a
static/covers/ image cache.

Re-run any time you shelf new books:  python3 build_library.py
Add --no-covers to skip the (slow) cover download and reuse whatever is cached.

The vault is never modified.
"""
import sys, os, re, json, subprocess, hashlib, zlib, struct, colorsys
from pathlib import Path
from datetime import datetime, timezone

VAULT = Path.home() / "Vaults" / "Eden" / "Alexandria"
HERE = Path(__file__).resolve().parent
COVERS_DIR = HERE / "static" / "covers"
THUMBS_DIR = HERE / "static" / "covers_thumb"
OUT_JSON = HERE / "static" / "library.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")

# Physical shelf-walk order for the non-fiction room (matches shelf-books skill).
SHELF_ORDER = {"science": 1, "technology": 2, "history": 3, "biography": 4,
               "politics": 5, "law-policy": 6, "economics": 7, "society": 8,
               "self_help": 9, "arts": 10, "food": 11}
SHELF_ZONE = {"science": "1 STEM", "technology": "1 STEM",
              "history": "2 History", "biography": "2 History",
              "politics": "3 Society", "law-policy": "3 Society",
              "economics": "3 Society", "society": "3 Society",
              "self_help": "3 Society", "arts": "4 Craft", "food": "4 Craft"}
# Order zones appear as you walk the room; Fiction is its own room, shown last.
# Temporarily hide fiction (incl. science fiction) until the library is updated.
# Set to empty set() to bring the Fiction room back.
EXCLUDE_GENRES = {"fiction"}
ZONE_ORDER = ["1 STEM", "2 History", "3 Society", "4 Craft"]
FICTION_SUBS = ["fiction", "science-fiction"]  # display order within the room
SUB_LABEL = {
    "science": "Science", "technology": "Technology", "history": "History",
    "biography": "Biography", "politics": "Politics", "law-policy": "Law & Policy",
    "economics": "Economics", "society": "Society", "self_help": "Self-Help",
    "arts": "Arts", "food": "Food", "fiction": "Fiction",
    "science-fiction": "Science Fiction",
}


# ---------------------------------------------------------------- frontmatter
def split_frontmatter(text):
    """Return (frontmatter_dict, body_text). Handles inline scalars and simple
    block lists (`key:` then indented `  - item` lines). Empty/malformed -> {}."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text
    fm, body = {}, "\n".join(lines[end + 1:])
    i = 1
    while i < end:
        raw = lines[i]
        m = re.match(r'^([A-Za-z0-9_ -]+):\s*(.*)$', raw)
        if not m:
            i += 1
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        if val == "":
            # could be a block list on following indented `- ` lines
            items, j = [], i + 1
            while j < end and re.match(r'^\s+-\s+', lines[j]):
                items.append(re.sub(r'^\s+-\s+', '', lines[j]).strip())
                j += 1
            if items:
                fm[key] = [strip_wikilink(x) for x in items]
                i = j
                continue
            fm[key] = None
        else:
            fm[key] = strip_wikilink(val)
        i += 1
    return fm, body


def strip_wikilink(v):
    if not isinstance(v, str):
        return v
    v = v.strip().strip('"').strip("'")
    m = re.match(r'^\[\[(.+?)\]\]$', v)
    return m.group(1) if m else v


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


# ---------------------------------------------------------------- summary body
def extract_summary(body):
    """Return the note's summary. Prefers the `> [!note] Summary` callout; if
    that is absent or empty, falls back to a `## Summary` heading section (some
    older notes use that form)."""
    text = _callout_summary(body)
    if not text:
        text = _heading_summary(body)
    if not text:
        text = _freeform_summary(body)
    return re.sub(r'\n{3,}', '\n\n', text)


def _freeform_summary(body):
    """Some notes write the summary as plain prose right after the frontmatter,
    before any heading. Grab that (bail out at the first heading/callout)."""
    out = []
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("#") or s.startswith(">"):
            break
        if re.match(r'^\[\[.*\]\]$', s):
            continue
        out.append(ln)
    text = _clean_summary("\n".join(out).strip())
    return text if len(re.sub(r'\s', '', text)) > 60 else ""


def _clean_summary(text):
    text = re.sub(r'^[_*]+|[_*]+$', '', text.strip()).strip()  # wrapping italics/bold
    return text


def _callout_summary(body):
    lines = body.splitlines()
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r'^>\s*\[!note\]\s*Summary', ln, re.I)), None)
    if start is None:
        return ""
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith(">"):
            out.append(re.sub(r'^>\s?', '', ln))
        elif ln.strip() == "":
            if out and out[-1].strip() == "":
                break
            out.append("")
        else:
            break
    return _clean_summary("\n".join(out).strip())


def _heading_summary(body):
    m = re.search(r'^#+\s*Summary\s*$', body, re.M | re.I)
    if not m:
        return ""
    seg = re.split(r'^#+\s', body[m.end():], flags=re.M)[0]  # until next heading
    # drop stray callout/link lines, keep prose
    seg = "\n".join(ln for ln in seg.splitlines()
                    if not re.match(r'^\[\[.*\]\]$', ln.strip()))
    return _clean_summary(seg.strip())


# ---------------------------------------------------------------- helpers
def slugify(name):
    s = re.sub(r'\.md$', '', name)
    s = re.sub(r"[^\w\s-]", '', s).strip().lower()
    s = re.sub(r'[\s]+', '-', s)
    return s[:80] or hashlib.md5(name.encode()).hexdigest()[:8]


def norm_date(v):
    if not v:
        return None
    v = str(v).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(v[:len(fmt) + 2] if "T" in fmt else v, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r'(\d{4})', v)
    return f"{m.group(1)}-01-01" if m else None


def is_read(fm):
    for v in as_list(fm.get("readingStatus")):
        if isinstance(v, str) and v.strip().lower() == "read":
            return True
    return False


# ---------------------------------------------------------------- spine colour
# Each spine takes a representative colour sampled from its cover, so a shelf
# reads like a real, multi-coloured bookshelf. sips (macOS) shrinks the cover to
# a tiny grid; we decode that PNG in pure Python and pick the dominant hue.
COLOR_CACHE = COVERS_DIR / "_colors.json"
_TMP_PNG = COVERS_DIR / "_tmp_color.png"


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _decode_png(data):
    """Minimal PNG decoder: 8-bit greyscale/RGB/RGBA/palette. -> [(r,g,b), ...]."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, width, height, colortype = 8, None, None, None
    idat, palette = bytearray(), None
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, _bd, colortype = struct.unpack(">IIBB", chunk[:10])
        elif ctype == b"PLTE":
            palette = chunk
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(colortype)
    if ch is None:
        return None
    stride = width * ch
    out, prev = bytearray(), bytearray(stride)
    i = 0
    for _y in range(height):
        f = raw[i]; i += 1
        line = bytearray(raw[i:i + stride]); i += stride
        if len(line) < stride:
            break
        for x in range(stride):
            a = line[x - ch] if x >= ch else 0
            b = prev[x]
            c = prev[x - ch] if x >= ch else 0
            if f == 1:   line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + ((a + b) >> 1)) & 255
            elif f == 4: line[x] = (line[x] + _paeth(a, b, c)) & 255
        out += line; prev = line
    px = []
    if colortype == 3 and palette:
        for idx in out:
            px.append((palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]))
    elif ch >= 3:
        for k in range(0, len(out) - 2, ch):
            px.append((out[k], out[k + 1], out[k + 2]))
    elif ch <= 2:
        step = ch
        for k in range(0, len(out), step):
            v = out[k]; px.append((v, v, v))
    return px or None


def _representative(px):
    """Pick a vivid, cloth-like colour: favour saturated mid-tones, drop the
    paper-white and ink-black that dominate most covers."""
    good = []
    for (r, g, b) in px:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if v < 0.14:            # near-black (text, borders)
            continue
        if s < 0.12 and v > 0.86:  # near-white (paper)
            continue
        good.append((s, r, g, b))
    if not good:
        n = len(px)
        return (sum(p[0] for p in px) // n, sum(p[1] for p in px) // n,
                sum(p[2] for p in px) // n)
    good.sort(reverse=True)  # most saturated first
    top = good[:max(3, len(good) // 2)]
    return (sum(p[1] for p in top) // len(top),
            sum(p[2] for p in top) // len(top),
            sum(p[3] for p in top) // len(top))


def cover_thumb(dest, slug):
    """Make a small cover thumbnail used as the (abstracted) spine background,
    so the page isn't loading full-size covers for every spine."""
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    out = THUMBS_DIR / f"{slug}.jpg"
    if out.exists() and out.stat().st_size > 800:
        return f"covers_thumb/{slug}.jpg"
    try:
        subprocess.run(["sips", "-Z", "240", "-s", "format", "jpeg",
                        str(dest), "--out", str(out)],
                       capture_output=True, timeout=20)
    except Exception:
        return None
    return f"covers_thumb/{slug}.jpg" if out.exists() else None


def cover_color(dest, slug, cache):
    if slug in cache:
        return cache[slug]
    try:
        subprocess.run(["sips", "-z", "10", "10", "-s", "format", "png",
                        str(dest), "--out", str(_TMP_PNG)],
                       capture_output=True, timeout=20)
        px = _decode_png(_TMP_PNG.read_bytes())
    except Exception:
        px = None
    if not px:
        return None
    r, g, b = _representative(px)
    hexc = "#%02x%02x%02x" % (r, g, b)
    cache[slug] = hexc
    return hexc


def curl_download(url, dest):
    try:
        r = subprocess.run(["curl", "-sL", "--max-time", "30", "-A", UA, "-o", str(dest), url],
                           capture_output=True, timeout=40)
        if r.returncode == 0 and dest.exists() and dest.stat().st_size > 2000:
            return True
        if dest.exists():
            dest.unlink()
    except Exception:
        if dest.exists():
            dest.unlink()
    return False


# ---------------------------------------------------------------- main build
def build(download_covers=True):
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    color_cache = {}
    if COLOR_CACHE.exists():
        try:
            color_cache = json.loads(COLOR_CACHE.read_text())
        except ValueError:
            color_cache = {}
    books, gaps_cover, gaps_summary, skipped_no_sub = [], [], [], []

    for f in sorted(VAULT.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        fm, body = split_frontmatter(text)
        cats = [c.lower() for c in as_list(fm.get("categories"))]
        if "book" not in cats:
            continue
        if not is_read(fm):
            continue

        title = re.sub(r'\.md$', '', f.name)
        genre_raw = " ".join(as_list(fm.get("genre"))).lower()
        subgenre = (as_list(fm.get("subgenre")) or [None])[0]
        subgenre = subgenre.lower() if subgenre else None

        # Decide genre: explicit field wins, else infer from subgenre.
        if "fiction" in genre_raw and "non" not in genre_raw:
            genre = "fiction"
        elif "non-fiction" in genre_raw or "nonfiction" in genre_raw:
            genre = "non-fiction"
        else:
            genre = "fiction" if subgenre in FICTION_SUBS else "non-fiction"

        if genre in EXCLUDE_GENRES:
            continue

        authors = [a for a in as_list(fm.get("author")) if a]
        region = (as_list(fm.get("region")) or [None])[0]
        region = region.lower() if region else None
        summary = extract_summary(body)
        if not summary:
            gaps_summary.append(title)

        slug = slugify(f.name)
        cover_remote = fm.get("cover")
        cover_remote = cover_remote.strip() if isinstance(cover_remote, str) else None
        if cover_remote and cover_remote.startswith("http://"):
            cover_remote = "https://" + cover_remote[len("http://"):]
        cover_local, cover_thumb_local, spine_color = None, None, None
        if cover_remote and cover_remote.startswith("http"):
            dest = COVERS_DIR / f"{slug}.jpg"
            if dest.exists() and dest.stat().st_size > 2000:
                cover_local = f"covers/{slug}.jpg"
            elif download_covers and curl_download(cover_remote, dest):
                cover_local = f"covers/{slug}.jpg"
            if cover_local:
                spine_color = cover_color(dest, slug, color_cache)
                cover_thumb_local = cover_thumb(dest, slug)
        if not cover_local:
            gaps_cover.append(title)

        # Canonical shelf/zone from subgenre (non-fiction only).
        shelf_num = SHELF_ORDER.get(subgenre)
        zone = SHELF_ZONE.get(subgenre) if genre == "non-fiction" else None
        if genre == "non-fiction" and subgenre not in SHELF_ORDER:
            skipped_no_sub.append(f"{title} (subgenre={subgenre})")

        books.append({
            "id": slug,
            "title": title,
            "authors": authors,
            "genre": genre,
            "subgenre": subgenre,
            "subgenreLabel": SUB_LABEL.get(subgenre, (subgenre or "Other").title()),
            "region": region,
            "shelfNum": shelf_num,
            "zone": zone,
            "completed": norm_date(fm.get("completed")),
            "cover": cover_local,
            "coverThumb": cover_thumb_local,
            "spineColor": spine_color,
            "coverRemote": cover_remote,
            "summary": summary,
        })

    COLOR_CACHE.write_text(json.dumps(color_cache), encoding="utf-8")
    if _TMP_PNG.exists():
        _TMP_PNG.unlink()

    rooms = assemble_rooms(books)
    # NOTE: deliberately no build timestamp — keeping the JSON stable when nothing
    # changed lets the auto-update job detect "no change" and skip a needless deploy.
    payload = {
        "count": len(books),
        "books": books,
        "rooms": rooms,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    report(books, rooms, gaps_cover, gaps_summary, skipped_no_sub)


def assemble_rooms(books):
    """Group books into rooms -> shelves in physical walk order."""
    by_sub = {}
    for b in books:
        by_sub.setdefault(b["subgenre"], []).append(b)

    def sort_shelf(items):
        # Recently read first within a shelf; unrated/undated sink to the end.
        return sorted(items, key=lambda b: (b["completed"] or "0000", b["title"]),
                      reverse=True)

    rooms = []
    for zone in ZONE_ORDER:
        subs = sorted([s for s in SHELF_ORDER if SHELF_ZONE.get(s) == zone],
                      key=lambda s: SHELF_ORDER[s])
        shelves = []
        for s in subs:
            items = by_sub.get(s, [])
            if not items:
                continue
            shelves.append({
                "key": s,
                "label": f"{SHELF_ORDER[s]:02d} · {SUB_LABEL[s]}",
                "bookIds": [b["id"] for b in sort_shelf(items)],
            })
        if shelves:
            rooms.append({"id": slugify(zone), "zone": zone,
                          "genre": "non-fiction", "shelves": shelves})

    # Fiction room
    fic_shelves = []
    for s in FICTION_SUBS:
        items = by_sub.get(s, [])
        if not items:
            continue
        fic_shelves.append({
            "key": s,
            "label": SUB_LABEL[s],
            "bookIds": [b["id"] for b in sort_shelf(items)],
        })
    # Any fiction-genre book with an unexpected subgenre lands in an "Other" shelf.
    seen = {bid for sh in fic_shelves for bid in sh["bookIds"]}
    leftover = [b for b in books
                if b["genre"] == "fiction" and b["id"] not in seen]
    if leftover:
        fic_shelves.append({"key": "other-fiction", "label": "More Fiction",
                            "bookIds": [b["id"] for b in leftover]})
    if fic_shelves:
        rooms.append({"id": "fiction", "zone": "Fiction",
                      "genre": "fiction", "shelves": fic_shelves})
    return rooms


def report(books, rooms, gaps_cover, gaps_summary, skipped_no_sub):
    print(f"\n  Living Bookshelf — build report")
    print(f"  {'='*44}")
    print(f"  Read books:          {len(books)}")
    print(f"  Covers cached:       {len(books) - len(gaps_cover)}  (missing {len(gaps_cover)})")
    print(f"  Summaries present:   {len(books) - len(gaps_summary)}  (missing {len(gaps_summary)})")
    print(f"\n  Rooms / shelves:")
    for r in rooms:
        n = sum(len(sh["bookIds"]) for sh in r["shelves"])
        print(f"    {r['zone']:<20} {n:>3} books  ·  {len(r['shelves'])} shelves")
    if skipped_no_sub:
        print(f"\n  ⚠ non-fiction without a known subgenre ({len(skipped_no_sub)}):")
        for x in skipped_no_sub[:12]:
            print(f"      - {x}")
    if gaps_cover:
        print(f"\n  ⚠ no cover ({len(gaps_cover)}): " + ", ".join(gaps_cover[:8])
              + (" …" if len(gaps_cover) > 8 else ""))
    if gaps_summary:
        print(f"  ⚠ no summary ({len(gaps_summary)}): " + ", ".join(gaps_summary[:8])
              + (" …" if len(gaps_summary) > 8 else ""))
    print(f"\n  Wrote {OUT_JSON.relative_to(HERE)}\n")


if __name__ == "__main__":
    if not VAULT.exists():
        sys.exit(f"Vault not found: {VAULT}")
    build(download_covers="--no-covers" not in sys.argv)
