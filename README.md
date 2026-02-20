# CTI Hub

A low/zero-code Cyber Threat Intelligence hub that lives entirely in GitHub.

- **Firehose**: automated RSS pulls into `/firehose/` via GitHub Actions
- **Curated**: human-written highlights in `/curated/` (monthly/quarterly)
- **Indicators**: optional STIX/CSV/JSON IoCs in `/indicators/`
- **Tools**: helper scripts and docs

## Quick Start

1. **Create a new GitHub repository** (private or public).
2. **Upload the contents** of this template (or import it).
3. Review and edit `feeds.yaml` to match the sources you want.
4. Enable Actions (if disabled) and let the **Daily Firehose** run.
5. (Optional) Turn on **GitHub Pages** (Settings → Pages) to make a browsable portal.
   
## Curation Workflow

- The Action writes a dated markdown file in `/firehose/` each day.
- You skim the latest entries and assemble human-curated notes in `/curated/`.
- For major periods, create `/curated/2025-Q3-highlights.md` with summaries and links.
- Share the curated doc link in your Webex SecOps space.

## Repo Layout

```
/firehose/               # Daily raw feed snapshots (auto)
/curated/                # Human-curated monthly/quarterly notes
/indicators/             # IoCs in STIX/CSV/JSON (optional)
/scripts/                # Python helper scripts
/tools/                  # Docs and helper notes
.github/workflows/       # GitHub Actions
feeds.yaml               # List of RSS feeds and optional keyword filters
README.md
```

## License

- If this repo is **internal-only**, you can leave it unlicensed (default “all rights reserved”).
- If you plan to share curated content publicly, consider **CC BY 4.0** for content and **MIT** for scripts. See `LICENSE-CHOICES.md`.
