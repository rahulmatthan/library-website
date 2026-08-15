# The Living Bookshelf

A public, interactive website of every book Rahul has read — browsed the way the
books actually sit on his shelves. Non-fiction is laid out in physical
walk-order (STEM → Past & Lives → Power & Society → Craft); fiction is its own
room. Click a spine and the book slides out to show its cover and summary.
Search by title or author, filter by genre/region, and re-sort each shelf.

Built with **Hugo** (static) + a small vanilla-JS front end, deployed to
**GitHub Pages**. Data comes from the Eden/Alexandria Obsidian vault.

## How it works

- `build_library.py` reads `~/Vaults/Eden/Alexandria/*.md`, keeps the notes
  marked **Read**, parses the frontmatter + the `> [!note] Summary` callout,
  caches every cover locally, and writes:
  - `static/library.json` — the single data file the site loads
  - `static/covers/*.jpg` — the cached cover art (committed to the repo)
- `layouts/index.html` + `static/js/shelf.js` + `static/css/shelf.css` render
  the bookshelf from that JSON. No build step beyond Hugo.

## Keeping it up to date (automatic)

When you flip a book's `readingStatus` to **Read** in the vault, the site picks it
up on its own — no manual steps.

- `update.sh` rebuilds from the vault and, **only if something changed**, commits
  and pushes; the push auto-deploys via GitHub Pages (live in ~1 min).
- A launchd agent (`~/Library/LaunchAgents/com.rahul.library-update.plist`) runs
  `update.sh` every 30 minutes, so newly-Read books appear within half an hour.
- Want it instantly? Run it yourself any time: `~/Coding/library-website/update.sh`
- Change the cadence: edit `StartInterval` (seconds) in the plist, then
  `launchctl unload` + `launchctl load -w` it. Disable it entirely with
  `launchctl unload -w ~/Library/LaunchAgents/com.rahul.library-update.plist`.
- Logs: `update.log` in this folder.

## Rebuild the data (run whenever you shelf new books)

```bash
python3 build_library.py            # re-parse vault + download any new covers
python3 build_library.py --no-covers  # faster: reuse cached covers, only refresh data
```

The build prints a report: books per shelf, and any missing covers/summaries.
The vault is **never modified**.

## Fill in missing summaries

Some Read books have an empty Summary callout in the vault. `summaries.py`
drafts and applies them with your confirmation:

```bash
python3 summaries.py list     # -> ~/Vaults/Eden/summaries_review.md (editable in Obsidian)
# ...edit the review file: fix text, or blank a summary to skip that book...
python3 summaries.py apply    # writes confirmed summaries into each vault note
python3 build_library.py --no-covers   # refresh the site
```

The review file lives in the **Eden vault root** (`~/Vaults/Eden/summaries_review.md`)
so you can read and edit it directly in Obsidian.

`apply` writes into each note's `> [!note] Summary` callout in your `_italic_`
style, never overwrites an existing summary, and re-verifies each write.
`<!-- ... -->` notes in the review file are stripped and never reach the vault.

## Preview locally

```bash
hugo server
# → http://localhost:1313/library-website/
```

## Deploy

Push to `main` — `.github/workflows/hugo.yml` builds and publishes to GitHub
Pages automatically.

**Before go-live:** set the final URL in `hugo.toml` (`baseURL`) and, for a
custom domain, add a `static/CNAME` file with the domain (e.g.
`library.rahulmatthan.com`).

## Notes

- **Scope:** only books with `readingStatus: Read` (currently ~348).
- **Ratings** in the vault use an inconsistent scale (values 2–7); shown as a
  plain `★ N` badge only when present, not as a 5-star meter.
- **Covers** are hotlinked Amazon/Google URLs in the vault; they're downloaded
  and served locally so the public site never hotlinks or breaks.
