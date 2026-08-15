#!/usr/bin/env python3
"""Remove the redundant bold-italic "TL;DR" line some summaries carry at the end.

Many older summaries end with a one-sentence takeaway wrapped in **_…_** (bold
AND italic) after the main paragraph, e.g.:

    > _<the actual summary>_
    >
    > **_A single-sentence restatement of the summary._**

This strips that trailing line (and the blank separator before it). The main
summary — which is only single-`_italic_` — is never touched, and a summary that
is ONLY the wrapped line (nothing else) is left alone so nothing is emptied.

Handles all three summary forms: `> [!note] Summary` callout, `## Summary`
heading, and free-form prose before the first heading.

    python3 strip_tldr.py          # dry run: report what WOULD be removed
    python3 strip_tldr.py --apply  # actually edit the notes
"""
import re, sys
from pathlib import Path

VAULT = Path.home() / "Vaults" / "Eden" / "Alexandria"
CALLOUT = re.compile(r'^>\s*\[!note\]\s*Summary', re.I)
HEADING = re.compile(r'^#+\s*Summary\s*$', re.I)
# a whole line wrapped in bold+italic (both markers at both ends)
WRAP = re.compile(r'^(\*\*_.+_\*\*|_\*\*.+\*\*_)$')


def frontmatter_end(lines):
    if not lines or lines[0].strip() != "---":
        return -1
    return next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), -1)


def summary_ranges(lines):
    """Return every summary block as (kind, start, end). Handles notes with
    more than one `Summary` callout / heading; falls back to free-form prose."""
    fm = frontmatter_end(lines)
    body_start = fm + 1 if fm >= 0 else 0
    blocks = []
    i = body_start
    while i < len(lines):
        if CALLOUT.match(lines[i]):
            j = i + 1
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            blocks.append(("callout", i, j)); i = j; continue
        if HEADING.match(lines[i]):
            j = i + 1
            while j < len(lines) and not re.match(r'^#+\s', lines[j]):
                j += 1
            blocks.append(("heading", i, j)); i = j; continue
        i += 1
    if not blocks:
        j = body_start
        while j < len(lines) and not lines[j].lstrip().startswith("#"):
            j += 1
        if j > body_start:
            blocks.append(("freeform", body_start, j))
    return blocks


def content_lines(lines, kind, start, end):
    """(index, stripped_text) for each non-empty line inside the block."""
    first = start + 1 if kind in ("callout", "heading") else start
    out = []
    for k in range(first, end):
        txt = re.sub(r'^>\s?', '', lines[k]).strip() if kind == "callout" else lines[k].strip()
        if txt:
            out.append((k, txt))
    return out


def strip_note(lines):
    """Mutate `lines` in place; return list of removed TL;DR texts."""
    removed = []
    # process blocks bottom-to-top so earlier indices stay valid
    for kind, start, end in sorted(summary_ranges(lines), key=lambda b: -b[1]):
        items = content_lines(lines, kind, start, end)
        if len(items) < 2:            # need a main summary AND a trailing line
            continue
        last_k, last_txt = items[-1]
        if last_txt.startswith("-") or not WRAP.match(last_txt):
            continue
        prev_k = items[-2][0]
        del lines[prev_k + 1:last_k + 1]   # drop blank separator(s) + the TL;DR
        removed.append(last_txt)
    return removed


def main(apply):
    changed = []
    for f in sorted(VAULT.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if "[[book]]" not in text:
            continue
        lines = text.split("\n")
        removed = strip_note(lines)
        if removed:
            changed.append((f.stem, removed))
            if apply:
                f.write_text("\n".join(lines), encoding="utf-8")
    total = sum(len(r) for _n, r in changed)
    mode = "REMOVED" if apply else "would remove"
    print(f"\n  {len(changed)} notes — {mode} {total} trailing bold-italic TL;DR line(s)\n")
    for name, rlist in changed:
        print(f"  • {name}")
        for line in rlist:
            print(f"      {line[:140]}{'…' if len(line) > 140 else ''}")
    if not apply:
        print("\n  (dry run — re-run with --apply to write these changes)\n")
    else:
        print("\n  Done. Re-run  python3 build_library.py --no-covers  to refresh the site.\n")


if __name__ == "__main__":
    main("--apply" in sys.argv)
