#!/usr/bin/env python3
"""Populate missing book summaries in the Eden/Alexandria vault.

Read books whose `> [!note] Summary` callout is empty get an AI-drafted summary
that Rahul reviews before it's written back into the note.

Workflow:
  1.  python3 summaries.py list
        -> writes summaries_review.md : one editable block per book.
           (Claude fills the draft summaries into this file.)
  2.  Rahul opens summaries_review.md, edits/deletes freely, saves.
  3.  python3 summaries.py apply
        -> writes each non-empty summary into its note's Summary callout,
           matching Rahul's `> _italic_` style. Skips blanks; never
           overwrites a summary that already has text; re-verifies each write.

The vault is only touched by `apply`, and only for the notes listed.
"""
import sys, re
from pathlib import Path

VAULT = Path.home() / "Vaults" / "Eden" / "Alexandria"
# Review file lives in the Eden vault root so it can be read/edited in Obsidian.
REVIEW = VAULT.parent / "summaries_review.md"

SUMMARY_HDR = re.compile(r'^>\s*\[!note\]\s*Summary', re.I)
BLOCK_SEP = "\n\n" + ("-" * 60) + "\n\n"


def split_frontmatter(text):
    if not text.startswith("---"):
        return {}, text, 0
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, text, 0
    fm = {}
    for ln in lines[1:end]:
        m = re.match(r'^([A-Za-z0-9_ -]+):\s*(.*)$', ln)
        if m and m.group(2).strip():
            fm[m.group(1).strip()] = m.group(2).strip()
    return fm, "\n".join(lines[end + 1:]), end


def authors_of(text):
    return re.findall(r'\[\[([^\]]+)\]\]', _author_block(text))


def _author_block(text):
    m = re.search(r'^author:\s*\n((?:\s*-\s*.*\n)+)', text, re.M)
    if m:
        return m.group(1)
    m = re.search(r'^author:\s*(.+)$', text, re.M)
    return m.group(1) if m else ""


def is_read(text):
    m = re.search(r'^readingStatus:\s*(.*)$', text, re.M)
    if m and m.group(1).strip().lower() == "read":
        return True
    m = re.search(r'^readingStatus:\s*\n\s*-\s*(.+)$', text, re.M)
    return bool(m and m.group(1).strip().lower() == "read")


def summary_text(body):
    lines = body.splitlines()
    start = next((i for i, ln in enumerate(lines) if SUMMARY_HDR.match(ln)), None)
    if start is None:
        return None  # no callout at all
    out = []
    for ln in lines[start + 1:]:
        if ln.startswith(">"):
            out.append(re.sub(r'^>\s?', '', ln))
        else:
            break
    return re.sub(r'[_*\s]+', '', "".join(out))  # stripped -> "" if empty


def has_summary_content(text):
    """True if the note already carries a summary in ANY form: a non-empty
    `> [!note] Summary` callout, a `## Summary` heading with text under it, or a
    substantial block of free-form prose. Used to avoid clobbering / duplicating."""
    _, body, _ = split_frontmatter(text)
    if summary_text(body):
        return True
    m = re.search(r'^#+\s*Summary\s*$', body, re.M | re.I)
    if m:
        seg = re.split(r'^#+\s', body[m.end():], flags=re.M)[0]
        if re.sub(r'[\s>_*]', '', seg):
            return True
    # A summary written as free-form prose sits directly under the frontmatter,
    # BEFORE the first heading. Prose under `## Notes` / `## Extracts` is reading
    # notes, not a summary, so we stop counting at the first heading.
    c = 0
    for ln in body.splitlines():
        s = ln.strip()
        if s.startswith("#"):
            break
        if (not s or s.startswith(">") or re.match(r'^\[\[.*\]\]$', s)):
            continue
        c += len(s)
    return c > 60


def missing_books():
    out = []
    for f in sorted(VAULT.glob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if "[[book]]" not in text or not is_read(text):
            continue
        if has_summary_content(text):  # already has a summary somewhere
            continue
        out.append((f, re.sub(r'\.md$', '', f.name), authors_of(text)))
    return out


# ---------------------------------------------------------------- list
def cmd_list():
    books = missing_books()
    parts = [
        "<!-- Review file for missing book summaries.",
        "     Edit any draft below. DELETE a block's summary (leave it blank) to skip that book.",
        "     Keep the `## Title :: Author` header line intact — apply matches on it.",
        "     When done, run:  python3 summaries.py apply -->",
        "",
    ]
    for f, title, authors in books:
        a = ", ".join(authors) if authors else "Unknown"
        parts.append("## %s :: %s" % (title, a))
        parts.append("")           # <- summary goes here
        parts.append("")
    REVIEW.write_text("\n".join(parts), encoding="utf-8")
    print("%d books need summaries -> %s" % (len(books), REVIEW.name))
    for _, t, _a in books:
        print("  -", t)


# ---------------------------------------------------------------- apply
def parse_review():
    if not REVIEW.exists():
        sys.exit("No %s — run `summaries.py list` first." % REVIEW.name)
    text = REVIEW.read_text(encoding="utf-8")
    text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    entries = {}
    cur = None
    buf = []
    for ln in text.splitlines():
        m = re.match(r'^##\s+(.+?)\s+::\s+(.+?)\s*$', ln)
        if m:
            if cur:
                entries[cur] = "\n".join(buf).strip()
            cur = m.group(1).strip()
            buf = []
        elif cur is not None:
            buf.append(ln)
    if cur:
        entries[cur] = "\n".join(buf).strip()
    return entries


def write_summary(path, summary):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    clean = re.sub(r'\s+', ' ', summary).strip().strip('_*').strip()
    start = next((i for i, ln in enumerate(lines) if SUMMARY_HDR.match(ln)), None)

    if start is None:
        # No Summary callout. Protect notes that already have content elsewhere
        # (their own summary/notes); otherwise create a callout after the
        # frontmatter for a genuinely empty note.
        if has_summary_content(text):
            return "has-content"
        fm_end = 0
        if lines and lines[0].strip() == "---":
            fm_end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), 0)
        insert = ["", "> [!note] Summary", "> _%s_" % clean]
        if fm_end + 1 >= len(lines) or lines[fm_end + 1].strip() != "":
            insert.append("")
        rebuilt = lines[:fm_end + 1] + insert + lines[fm_end + 1:]
        path.write_text("\n".join(rebuilt) + "\n", encoding="utf-8")
        return "ok-created" if summary_text(split_frontmatter(path.read_text(encoding="utf-8"))[1]) else "verify-failed"

    # find end of the existing callout block
    j = start + 1
    while j < len(lines) and lines[j].startswith(">"):
        j += 1
    # guard: refuse if the callout already holds real text
    existing = re.sub(r'[_*\s>]+', '', "".join(lines[start + 1:j]).replace(">", ""))
    if existing:
        return "already-has-summary"
    rebuilt = lines[:start] + [lines[start], "> _%s_" % clean] + lines[j:]
    out = "\n".join(rebuilt)
    if text.endswith("\n") and not out.endswith("\n"):
        out += "\n"
    path.write_text(out, encoding="utf-8")
    check = summary_text(split_frontmatter(path.read_text(encoding="utf-8"))[1])
    return "ok" if check else "verify-failed"


def cmd_apply():
    entries = parse_review()
    by_title = {re.sub(r'\.md$', '', f.name): f for f, _t, _a in missing_books()}
    wrote, protected, blank, errors = [], [], [], []
    for title, summary in entries.items():
        if not summary.strip():
            blank.append(title); continue
        path = by_title.get(title)
        if not path:
            # note isn't in the missing list — it already has a summary somewhere
            protected.append(title); continue
        r = write_summary(path, summary)
        if r in ("ok", "ok-created"):
            wrote.append(title)
        elif r in ("already-has-summary", "has-content"):
            protected.append(title)
        else:
            errors.append("%s (%s)" % (title, r))
    print("\n  Summaries applied")
    print("  " + "=" * 40)
    print("  Written:  %d" % len(wrote))
    for t in wrote:
        print("     ✓", t)
    if blank:
        print("  Left blank (skipped): %d" % len(blank))
    if protected:
        print("  Already had a summary — left untouched: %d" % len(protected))
        for t in protected:
            print("     ·", t)
    if errors:
        print("  ⚠ Errors: %d" % len(errors))
        for e in errors:
            print("     -", e)
    print("\n  Re-run  python3 build_library.py --no-covers  to refresh the site.\n")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "list":
        cmd_list()
    elif cmd == "apply":
        cmd_apply()
    else:
        sys.exit("usage: summaries.py list | apply")
