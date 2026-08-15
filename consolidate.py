#!/usr/bin/env python3
"""Consolidate book notes that ended up with duplicate Summary + Extracts blocks.

The shelf-books template (`> [!note] Summary` + `## Extracts from the Book`) was
prepended above notes that already had their own summary, and a later apply run
filled that empty top callout with an AI summary. Result: two Summary callouts
and two Extracts sections.

This keeps ONE summary — preferring the note's own summary (which starts with the
book's title) over the generic AI one — removes the duplicate Summary callout,
and drops an empty duplicate `## Extracts` heading. All other content (the real
extracts, trailing links) is preserved untouched.

    python3 consolidate.py          # dry run: show keeper vs removed per note
    python3 consolidate.py --apply  # write the changes
"""
import re, sys
from pathlib import Path
import summaries  # reuse the review-file parser to identify AI-written text

VAULT = Path.home() / "Vaults" / "Eden" / "Alexandria"
CALLOUT = re.compile(r'^>\s*\[!note\]\s*Summary', re.I)
EXTRACTS = re.compile(r'^#+\s*Extracts', re.I)

# The AI summaries I applied (from summaries_review.md) — used to positively
# identify which callout is mine so the note's OWN summary is always preferred.
try:
    AI = {t: summaries.norm_key(s) if hasattr(summaries, "norm_key") else s
          for t, s in summaries.parse_review().items()}
except Exception:
    AI = {}


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def is_ai(title, body):
    ai = AI.get(title)
    if not ai:
        return False
    a, b = norm(ai), norm(body)
    return bool(a) and (b.startswith(a[:70]) or a.startswith(b[:70]))


def callout_blocks(lines):
    """List of (start, end, summary_text) for each Summary callout."""
    out = []
    i = 0
    while i < len(lines):
        if CALLOUT.match(lines[i]):
            j = i + 1
            body = []
            while j < len(lines) and lines[j].startswith(">"):
                c = re.sub(r'^>\s?', '', lines[j]).strip()
                if c:
                    body.append(c)
                j += 1
            out.append((i, j, " ".join(body).strip()))
            i = j
        else:
            i += 1
    return out


def extracts_sections(lines):
    """List of (start, end, has_content) for each Extracts heading."""
    out = []
    for i, ln in enumerate(lines):
        if EXTRACTS.match(ln):
            j = i + 1
            while j < len(lines) and not (re.match(r'^#+\s', lines[j])
                                          or CALLOUT.match(lines[j])):
                j += 1
            content = "".join(x for x in lines[i + 1:j]
                              if x.strip() and not re.match(r'^\[\[.*\]\]$', x.strip()))
            out.append((i, j, bool(content.strip())))
    return out


def plan(lines, title):
    """Return (keep_idx, drop_ranges, note) describing the consolidation, or None."""
    cos = callout_blocks(lines)
    if len(cos) < 2:
        return None
    tnorm = norm(title)

    def score(k):
        txt = cos[k][2]
        body = re.sub(r'^[_*\s]+', '', txt)
        has = bool(re.sub(r'[_*\s]', '', body))
        mine = is_ai(title, txt)                      # my AI callout ranks lowest
        starts_title = tnorm and norm(body[:len(title) + 4]).startswith(tnorm[:max(4, len(tnorm) - 2)])
        # prefer: your non-AI content > AI content > empty
        return (1 if (has and not mine) else 0,
                1 if has else 0,
                1 if starts_title else 0,
                len(body))
    keep = max(range(len(cos)), key=score)
    drops = []
    for k, (s, e, txt) in enumerate(cos):
        if k == keep:
            continue
        # extend drop range to swallow the blank line(s) after the callout
        e2 = e
        while e2 < len(lines) and lines[e2].strip() == "":
            e2 += 1
        drops.append((s, e2, txt))
    return keep, cos, drops


def consolidate(lines, title):
    p = plan(lines, title)
    if not p:
        return None
    keep, cos, drops = p
    keep_txt = cos[keep][2]
    # delete dropped callout ranges bottom-to-top
    for s, e, _txt in sorted(drops, key=lambda d: -d[0]):
        del lines[s:e]
    # now remove empty duplicate Extracts headings, if a non-empty one remains
    secs = extracts_sections(lines)
    if any(c for _s, _e, c in secs) and len(secs) > 1:
        for s, e, has in sorted(secs, key=lambda d: -d[0]):
            if not has:
                e2 = e
                while e2 < len(lines) and lines[e2].strip() == "":
                    e2 += 1
                del lines[s:e2]
                break  # remove just one empty duplicate
    # tidy: collapse 3+ blank lines to 2
    out = re.sub(r'\n{3,}', '\n\n', "\n".join(lines))
    return keep_txt, [d[2] for d in drops], out


def main(apply):
    changed = []
    for f in sorted(VAULT.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if "[[book]]" not in text:
            continue
        lines = text.split("\n")
        res = consolidate(lines, f.stem)
        if not res:
            continue
        keep_txt, dropped, out = res
        if out.rstrip("\n") == text.rstrip("\n"):
            continue
        changed.append((f.stem, keep_txt, dropped))
        if apply:
            f.write_text(out if out.endswith("\n") else out + "\n", encoding="utf-8")
    print(f"\n  {len(changed)} notes — {'consolidated' if apply else 'would consolidate'}\n")
    for name, keep, dropped in changed:
        print(f"  • {name}")
        print(f"      KEEP : {keep[:110]}")
        for d in dropped:
            print(f"      DROP : {(d or '(empty)')[:110]}")
    if not apply:
        print("\n  (dry run — re-run with --apply to write)\n")


if __name__ == "__main__":
    main("--apply" in sys.argv)
