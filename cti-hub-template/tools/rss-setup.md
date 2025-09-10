# RSS Setup Notes

- Feeds are configured in `feeds.yaml`.
- Add/remove feeds by editing the YAML.
- Optional: add keywords to filter items (any-match, case-insensitive). Leave empty to ingest everything.
- Daily run uses GitHub Actions in `.github/workflows/firehose.yml`.
- If you enable GitHub Pages, your repo becomes a lightweight browsable portal.
