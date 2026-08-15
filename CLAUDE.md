# Rahul's Library — project manual

Read this first when resuming. It captures what the project is, how it's built,
every decision made, and how to run/update/deploy it.

**Live:** https://library.rahulmatthan.com/ · **Repo:** github.com/rahulmatthan/library-website (public)

## What it is

A public, interactive website of every book Rahul has **read**, laid out the way
they sit on his physical shelves. Built for his team, who kept asking for a way
to browse his reading. Skeuomorphic "living bookshelf": cover-art spines on
wooden shelves, click a spine to pull the book and see its cover + summary,
search by title/author, filter by region, sort several ways.

Data comes from the **Eden/Alexandria Obsidian vault** (`~/Vaults/Eden/Alexandria/*.md`),
the same notes the `shelf-books` skill maintains. **315 read books** currently.

## Stack & layout

Hugo (static) + vanilla JS + GitHub Pages. No framework, no build step beyond Hugo.

```
build_library.py       # vault -> static/library.json (+ covers, thumbs, colours)
summaries.py           # draft/apply missing summaries via the review file
strip_tldr.py          # remove trailing bold-italic "TL;DR" lines from summaries
consolidate.py         # merge duplicate Summary/Extracts blocks in notes
update.sh              # rebuild + commit + push (only if data changed)
watch-and-deploy.sh    # vault watcher -> update.sh (run by launchd)
hugo.toml              # baseURL = https://library.rahulmatthan.com/
layouts/index.html     # page shell (title "Rahul's Library")
static/js/shelf.js     # all rendering + interaction
static/css/shelf.css   # wood/spine/label styling
static/library.json    # GENERATED data (no timestamp — see gotcha)
static/covers/*.jpg     + _colors.json   # cached full covers + per-spine colour cache
static/covers_thumb/*.jpg                # small covers used as spine backgrounds
static/CNAME           # library.rahulmatthan.com
.github/workflows/hugo.yml               # Pages deploy on push to main
```

## Data model (per book, in library.json)

`id` (slug), `title` (= note filename), `authors[]`, `genre` (fiction/non-fiction),
`subgenre` + `subgenreLabel`, `region` (india/world/null), `zone`, `shelfNum`,
`completed` (date), `cover`, `coverThumb`, `spineColor` (sampled from cover),
`summary`. Plus a `rooms[]` structure grouping books into walk-order shelves.

Rooms (zones), in walk order: **1 STEM, 2 History, 3 Society, 4 Craft**. Each
holds ordered sub-genre shelves (science, technology, history, biography,
politics, law-policy, economics, society, self_help, arts, food).

## How updating works (self-updating)

Flip a book's `readingStatus` to **Read** in Obsidian → it's live in ~30s. Chain:
launchd `com.rahulmatthan.library` (KeepAlive+RunAtLoad) → `watch-and-deploy.sh`
(polls the vault every 10s, waits for edits to settle) → `update.sh` (rebuilds,
commits + pushes **only if the site data changed**) → GitHub Actions deploys.

- Instant manual update: `~/Coding/library-website/update.sh`
- Watcher status/stop/start: `launchctl list|unload -w|load -w` on
  `~/Library/LaunchAgents/com.rahulmatthan.library.plist`
- Logs: `update.log` (deploys), `/tmp/library-watcher.log` (watcher)

## Deploy (already done; for reference)

Repo is public; Pages source = GitHub Actions; custom domain via `static/CNAME`;
DNS is a CNAME record `library` → `rahulmatthan.github.io`; HTTPS enforced.
Mirrors the photo-website setup.

## Decisions & gotchas (important)

- **build_library.py never writes the vault.** `summaries.py`, `strip_tldr.py`,
  `consolidate.py` DO edit vault notes — they're careful (guard/verify) but
  the vault is git-backed daily (`eden-backup`) if you need to revert.
- **Ratings dropped.** The vault's `rating` values are an inconsistent scale
  (2–7), so ratings were removed from the site entirely. If you ever want them,
  first decide the intended scale.
- **Fiction is hidden** (incl. science fiction) via `EXCLUDE_GENRES = {"fiction"}`
  in build_library.py, at Rahul's request "until I update the library". Set it
  back to `set()` and rebuild to bring the Fiction room back.
- **Summaries live in 3 forms** and the site reads all: a `> [!note] Summary`
  callout, a `## Summary` heading, or free-form prose before the first heading.
  Rahul's own summaries (start with the book title) are always preferred over the
  AI-drafted ones.
- **library.json has no build timestamp** — deliberate, so an unchanged rebuild
  is byte-identical and the watcher treats it as "no change" (no needless deploy).
- **Covers** are hotlinked URLs in the vault; always cache locally (never hotlink
  on the site). Thumbnails (240px) back the spines; full covers back the drawer.
- **Spine design:** cover thumb at 25% opacity over the cover-sampled dominant
  colour, with a radial centre-darkening so titles stay legible (tunable in
  `.spine-art` / `.spine.has-art::after`). Titles wrap to a 2nd column (no
  ellipsis); short titles use a larger font.
- **Shelves are continuous** and wrap to a new plank on overflow. Sub-genres are
  separated by a one-book gap; the category name is a **brass nameplate embossed
  into the shelf plank**, sitting under the first book of the section (a bookend
  design was tried and rejected).

## History of this build (what was done)

Design chosen: "Living Bookshelf" → renamed "Rahul's Library". Built the pipeline;
generated summaries for 121 missing books via 4 web-grounded agents into
`~/Vaults/Eden/summaries_review.md`, reviewed by Rahul, applied via summaries.py
(with careful handling of notes that already had summaries elsewhere). Stripped
159 redundant TL;DR lines (strip_tldr.py). Consolidated 62 notes with duplicate
Summary/Extracts blocks (consolidate.py), keeping Rahul's own summaries. Rahul
deleted 5 duplicate book notes. Cover-art spines, cover-sampled colours, continuous
wrapping shelves, embossed category labels. Deployed to library.rahulmatthan.com.
Added the self-updating vault watcher.

## Open / possible future items

- **~4 books still have no cover**: The Afterlife of Data, Tiananmen Square, War,
  Why Fish Don't Exist (no cover URL in the vault, or the URL failed). Add a
  `cover:` URL to those notes to fix.
- **Re-enable fiction** when Rahul's ready (`EXCLUDE_GENRES`).
- **Per-book deep-link pages / author pages** — a possible v2 (not built; site is
  a single interactive page).
- **`~/Vaults/Eden/summaries_review.md`** is a leftover from the summary workflow
  (already applied). Safe to delete; Rahul was asked and hadn't decided.
- Ratings — dropped; revisit only if Rahul wants them with a defined scale.
