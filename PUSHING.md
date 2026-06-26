# Push Notes

This is the running checklist for publishing different Pixora changes.

## Card Source Changes

Use this path for changes under `cards/`, including addon card fixes.

1. Make the source change in `cards/addons/`.
2. If card metadata or options changed, update `cards/registry.json`.
3. Run a focused render/import check from the `cards/` directory when possible.
4. Review the diff with `git diff -- cards/...`.
5. Commit the card source and any matching registry or preview updates.
6. Push to `https://github.com/bptworld/pixora`.

Current source of truth for public cards is:

```text
pixora-src/cards
```

## Cloud Renderer Changes

Cloud deployment is separate from the public card source.

Use the `pixora-cloud` repository or the configured cloud remote when changing hosted Render behavior. Do not assume files under this repo's cloud snapshots deploy automatically.

