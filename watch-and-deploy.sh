#!/bin/bash
# Watch the Eden/Alexandria vault and auto-deploy Rahul's Library when a book
# changes (e.g. readingStatus flipped to Read). Same approach as photo-website's
# watch-and-deploy.sh: poll the source, and on a *settled* change run update.sh
# (which rebuilds and pushes only if the site data actually changed).
#
# Runs continuously via launchd (com.rahulmatthan.library, KeepAlive+RunAtLoad).

export PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
WATCH_DIR="/Users/rahul/Vaults/Eden/Alexandria"
REPO_DIR="/Users/rahul/Coding/library-website"
CHECK_INTERVAL=10   # seconds between checks
SETTLE=8            # wait for a burst of edits to stop before deploying

# snapshot: mtime + size + name of every note, so content edits are detected
get_state() {
    find "$WATCH_DIR" -type f -name '*.md' -exec stat -f "%m %z %N" {} \; 2>/dev/null | sort
}

echo "$(date '+%Y-%m-%d %H:%M:%S') - watching $WATCH_DIR"
last_state=$(get_state)

while true; do
    sleep "$CHECK_INTERVAL"
    current_state=$(get_state)

    if [ "$current_state" != "$last_state" ]; then
        # let a burst of edits settle: wait until the vault stops changing
        while true; do
            sleep "$SETTLE"
            s=$(get_state)
            [ "$s" = "$current_state" ] && break
            current_state=$s
        done

        echo "$(date '+%Y-%m-%d %H:%M:%S') - vault changed, rebuilding + deploying"
        "$REPO_DIR/update.sh"   # rebuild + commit + push, only if something changed

        last_state=$(get_state)
    fi
done
