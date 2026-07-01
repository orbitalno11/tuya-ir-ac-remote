# Releasing

This project ships to users exclusively through HACS as a **custom
repository**. HACS detects new versions by watching this repo's GitHub
Releases/tags -- once a release is published, every user who added this
repo sees an update badge (and, if they've enabled it, a persistent
notification) in their own Home Assistant. No release-notification code
lives in the integration itself; publishing the release *is* the
notification mechanism.

Releases are created manually. For every new version:

1. Bump `"version"` in
   [`custom_components/tuya_ir_ac/manifest.json`](custom_components/tuya_ir_ac/manifest.json)
   to the new `X.Y.Z`.
2. Add a new `## [X.Y.Z]` entry at the top of [`CHANGELOG.md`](CHANGELOG.md)
   describing what changed.
3. Commit both to `main`, e.g.:
   ```bash
   git commit -am "Bump version to X.Y.Z"
   ```
4. Tag the commit and push it:
   ```bash
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```
5. Publish a GitHub Release from that tag, using the matching
   `CHANGELOG.md` entry as the release notes:
   ```bash
   gh release create vX.Y.Z --title vX.Y.Z --notes-file <(sed -n '/^## \[X.Y.Z\]/,/^## \[/p' CHANGELOG.md | sed '1d;$d')
   ```
   (or fill in the same title/notes through the GitHub web UI).

That's it -- no further action is needed for users to be notified; HACS
picks up the new tag/release on its own on its next check.
