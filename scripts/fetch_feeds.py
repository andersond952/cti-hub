#!/usr/bin/env python3
"""
Fetch RSS/Atom feeds and write a dated markdown page (with Jekyll front matter)
containing Feedly-style preview cards. Runs in GitHub Actions.
"""
import os, re, sys, yaml, time, html, datetime as dt
import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREHOSE = os.path.join(ROOT, "firehose")
FEEDS_YAML = os.path.join(ROOT, "feeds.yaml")

# Limit how many links we "deep fetch" for OG metadata to keep Action fast.
OG_SCRAPE_LIMIT = 60  # total across all feeds

def load_config():
    with open(FEEDS_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    feeds = cfg.get("feeds", []) or []
    keywords = [k.strip() for k in (cfg.get("keywords") or []) if str(k).strip()]
    return feeds, keywords

def norm(s): 
    return re.sub(r"\s+"," ", (s or "")).strip()

def match_kw(text, kws):
    if not kws: 
        return True
    t = text.lower()
    return any(k.lower() in t for k in kws)

def fetch_og(url, timeout=6):
    """Fetch Open Graph info (image, description, site_name). Fail quietly."""
    out = {"image": "", "desc": "", "site": ""}
    if not url:
        return out
    try:
        r = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (CTI Hub Bot)"}
        )
        if r.status_code != 200 or "text/html" not in r.headers.get("Content-Type", ""):
            return out
        soup = BeautifulSoup(r.text, "html.parser")
        def content(prop):
            tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            return tag.get("content", "").strip() if tag else ""
        out["image"] = content("og:image")
        out["desc"]  = content("og:description")
        out["site"]  = content("og:site_name") or content("twitter:site") or ""
        return out
    except Exception:
        return out

def entry_to_card(feed_name, e, og=None):
    title = norm(e.get("title","")) or "(untitled)"
    link  = e.get("link","")
    pub   = e.get("published", e.get("updated",""))
    summary = norm(html.unescape(e.get("summary",""))) or ""
    # use OG desc if present, else summary (trim)
    desc = (og.get("desc") if og else "") or summary
    if len(desc) > 240:
        desc = desc[:237] + "..."
    # derive site/source label
    site = (og.get("site") if og else "") or feed_name
    # try feed image fields if no OG image
    image = (og.get("image") if og else "") or ""
    if not image:
        thumbs = e.get("media_thumbnail") or e.get("media_content") or []
        if thumbs and isinstance(thumbs, list) and thumbs[0].get("url"):
            image = thumbs[0]["url"]

    img_html = f'<img src="{html.escape(image)}" alt="preview">' if image else ""
    return f"""<li class="card">
  {img_html}
  <div>
    <h3><a href="{html.escape(link)}" target="_blank" rel="noopener">{html.escape(title)}</a></h3>
    <div class="meta">{html.escape(site)} · {html.escape(pub)}</div>
    <p>{html.escape(desc)}</p>
  </div>
</li>"""

def main():
    feeds, keywords = load_config()
    os.makedirs(FIREHOSE, exist_ok=True)
    today_iso = dt.datetime.utcnow().date().isoformat()
    outpath = os.path.join(FIREHOSE, f"{today_iso}.md")

    # Collect entries
    entries = []
    for f in feeds:
        name = f.get("name") or f.get("url")
        url = f.get("url")
        if not url:
            continue
        d = feedparser.parse(url)
        for e in d.entries:
            blob = " ".join([
                e.get("title",""),
                e.get("summary",""),
                e.get("description",""),
                e.get("link",""),
                " ".join([t.get("term","") for t in e.get("tags", [])])
            ])
            if match_kw(blob, keywords):
                entries.append((name, e))

    # Sort newest first (best-effort)
    def ts(e):
        for k in ("published_parsed","updated_parsed"):
            v = getattr(e, k, None)
            if v:
                return time.mktime(v)
        return 0
    entries.sort(key=lambda pair: ts(pair[1]), reverse=True)

    # Enrich top N with Open Graph
    enriched = []
    scrape_budget = OG_SCRAPE_LIMIT
    for name, e in entries:
        og = {}
        if scrape_budget > 0 and e.get("link"):
            og = fetch_og(e.get("link"))
            scrape_budget -= 1
        enriched.append((name, e, og))

    # Build page with front matter + card list
    today_human = dt.datetime.utcnow().strftime('%B %d, %Y')
    header = [
        "---",
        "layout: default",
        f"title: Firehose — {today_human}",
        "---",
        "",
        '<link rel="stylesheet" href="{{ \'/assets/css/cards.css\' | relative_url }}">',
        "",
        f"# Daily CTI Firehose — {today_iso}",
        "",
        f"_Feeds: {len(feeds)} | Items: {len(enriched)} | Keyword filter: {', '.join(keywords) if keywords else 'none'}_",
        "",
        '<ul class="cards">'
    ]

    cards = [entry_to_card(name, e, og) for (name, e, og) in enriched]
    footer = ["</ul>", ""]

    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(header + cards + footer))

    print(f"Wrote {outpath} with {len(enriched)} items (OG scraped up to {OG_SCRAPE_LIMIT}).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
