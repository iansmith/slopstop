# doc-sync: GitHub wiki backend

## system = "github"

1. **Pre-flight:** `gh auth status` must succeed. If not, stop with auth instructions.

2. **Clone the wiki repo. If the wiki has not been initialized upstream, stop with instructions.**

   GitHub requires the first wiki page to be created via the web UI before `git push` to the wiki repo will work. A fresh wiki (feature enabled but no pages) returns "Repository not found" on clone — detect this and stop with a clear message instead of attempting init+push (which also fails).

   ```bash
   TMP=$(mktemp -d)
   if ! git clone git@github.com:$KEY.wiki.git $TMP 2>/dev/null; then
       rm -rf $TMP
       cat <<EOF
The wiki for $KEY has not been initialized yet.
GitHub requires the first wiki page to be created via the web UI
before git push will accept new content — this is a GitHub-specific
quirk, not something the skill can work around.

To unblock:
  1. Visit https://github.com/$KEY/wiki
  2. Click "Create the first page" and save anything — the content
     does not matter; it will be overwritten on the next sync.
  3. Re-run /slopstop:doc-sync.
EOF
       exit 0
   fi
   ```

3. **For each `design/*.md` source file** (excluding subdirectories):

   - Parse frontmatter → `$TITLE`, `$SLUG`.
   - Strip frontmatter from the body.
   - Write the body to `$TMP/$SLUG.md`.

4. **Orphan prune:** for each `*.md` in `$TMP/` that doesn't correspond to a current `design/` source slug:

   ```bash
   rm $TMP/$ORPHAN.md
   ```

5. **Commit and push:**

   ```bash
   cd $TMP
   git add -A
   if git diff --cached --quiet; then
       echo "No changes to push."
   else
       SHA=$(cd $ORIG_CWD && git rev-parse HEAD)
       git commit -m "doc-sync from $SHA"
       git push origin master
   fi
   ```

6. **Cleanup:** `rm -rf $TMP`.

7. **Confirm:** `"Synced N design docs to $KEY wiki."`
