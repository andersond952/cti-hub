#!/usr/bin/env python3
"""
Fetch RSS/Atom feeds defined in feeds.yaml and write a dated markdown snapshot
into /firehose/YYYY-MM-DD.md. Intended to run inside GitHub Actions.
"""
import os
import re
import sys
import json
import yaml
import time
import html
import hashlib
import datetime as dt

try:
    import feedparser
except ImportError:
    print("Missing dependency: feedparser", file=sys.stderr)
    sys.exit(2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREHOSE = os.path.join(ROOT, "firehose")
FEEDS_YAML = os.path.join(ROOT, "feeds.yaml")

def load_config():
    with open(FEEDS_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    feeds = cfg.get("feeds", [])
    keywords = cfg.get("keywords", []) or []
    keywords = [k.strip() for k in keywords if str(k).strip()]
    return feeds, keywords

def normalize_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def match_keywords(text, keywords):
    if not keywords:
        return True
    t = text.lower()
    for k in keywords:
        if k.lower() in t:
            return True
    return False

def render_entry_md(feed_name, e):
    title = normalize_text(e.get("title", "")) or "(untitled)"
    link = e.get("link", "")
    published = e.get("published", e.get("updated", ""))
    summary = normalize_text(html.unescape(e.get("summary", "")))
    # keep summary short
    if len(summary) > 300:
        summary = summary[:297] + "..."
    return f"- **{title}**  \n  Source: *{feed_name}* — {published}  \n  Link: {link}  \n  {summary}"

def main():
    feeds, keywords = load_config()
    os.makedirs(FIREHOSE, exist_ok=True)
    today = dt.datetime.utcnow().date().isoformat()
    outpath = os.path.join(FIREHOSE, f"{today}.md")

    entries = []
    for f in feeds:
        name = f.get("name") or f.get("url")
        url = f.get("url")
        if not url:
            continue
        try:
            d = feedparser.parse(url)
        except Exception as ex:
            print(f"[WARN] Failed to parse {url}: {ex}", file=sys.stderr)
            continue
        for e in d.entries:
            blob = " ".join([
                e.get("title",""),
                e.get("summary",""),
                e.get("description",""),
                e.get("link",""),
                " ".join([t.get("term","") for t in e.get("tags", [])])
            ])
            if match_keywords(blob, keywords):
                entries.append((name, e))

    # sort by published/updated (best-effort)
    def entry_ts(e):
        for key in ("published_parsed","updated_parsed"):
            if getattr(e, key, None):
                return time.mktime(getattr(e, key))
        return 0
    entries.sort(key=lambda pair: entry_ts(pair[1]), reverse=True)

    lines = [f"# Daily CTI Firehose — {today}", "", f"_Feeds: {len(feeds)} | Items: {len(entries)} | Keyword filter: {', '.join(keywords) if keywords else 'none'}_", ""]
    for name, e in entries:
        lines.append(render_entry_md(name, e))
        lines.append("")

    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {outpath} with {len(entries)} items.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
