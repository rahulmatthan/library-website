#!/bin/bash
# Rebuild Rahul's Library from the Eden/Alexandria vault and deploy it — but only
# if something actually changed (a book flipped to Read, a new cover, etc.).
#
# Run it by hand any time for an instant update:   ~/Coding/library-website/update.sh
# It also runs automatically on a schedule via the launchd agent
# com.rahul.library-update (see README).

export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
REPO="/Users/rahul/Coding/library-website"
LOG="$REPO/update.log"
cd "$REPO" || exit 1

{
  echo "----- $(date '+%Y-%m-%d %H:%M:%S') -----"

  # Rebuild data + fetch covers/thumbnails for any newly-Read books.
  if ! python3 build_library.py; then
    echo "build failed"; exit 1
  fi

  # Nothing changed? Don't commit or deploy.
  if [ -z "$(git status --porcelain)" ]; then
    echo "no changes — nothing to deploy"; exit 0
  fi

  git add -A
  git commit -m "Update library ($(date '+%Y-%m-%d %H:%M'))" || { echo "commit skipped"; exit 0; }

  if git push origin main; then
    echo "pushed — GitHub Pages is deploying (live in ~1 min)"
  else
    echo "push failed (check network / auth); changes are committed locally"
    exit 1
  fi
} >> "$LOG" 2>&1
