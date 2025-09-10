#!/usr/bin/env python3
"""
Fetch RSS/Atom feeds and write a dated markdown page (with Jekyll front matter)
containing Feedly-style preview cards. Handles HTML-y summaries (e.g., CISA),
adds image fallbacks (OG -> first <img> -> favicon), and cleans descriptions.
Runs in GitHub Actions.
"""
import os, re, sys, yaml, time, html, datetime as dt, urllib.parse
import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREHOSE = os.path.join(ROOT, "firehose")
FEEDS_YAML = os.path.join(ROOT, "feeds.yaml")

# Limit how many links we "deep fetch" for OG metadata to keep Action fast.
OG_SCRAPE_LIMIT = 60  # total across all feeds

USER_AGENT = "Mozilla/5.0 (CTI Hub Bot)"

def load_config():
    with open(FEEDS_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    feeds = cfg.get("feeds", []) or []
    keywords = [k.strip() for k in (cfg.get("keywords") or []) if str(k).strip()]
    return feeds, keywords

def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

def strip_html_to_text(s):
    if not s:
        return ""
    try:
        soup = BeautifulSoup(s, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception:
        # best-effort fallback: remove tags crudely
        return re.sub(r"<[^>]+>", " ", s)

def first_img_src_from_html(s):
    if not s:
        return ""
    try:
        soup = BeautifulSoup(s, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img.get("src").strip()
    except Exception:
        pass
    return ""

def match_kw(text, kws):
    if not kws:
        return True
    t = text.lower()
    return any(k.lower() in t for k in kws)

def domain_from_url(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""

def favicon_for(url):
    host = domain_from_url(url)
    if not host:
        return ""
    # Google favicon service is reliable for a visual fallback
    return f"https://www.google.com/s2/favicons?domain={host}&sz=128"

def fetch_url_html(url, timeout=8):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
        return r.text
    return ""

def fetch_og(url, timeout=8):
    """Fetch OG info (image, description, site_name) and first <img> fallback."""
    out = {"image": "", "desc": "", "site": "", "first_img": ""}
    if not url:
        return out
    try:
        html_text = fetch_url_html(url, timeout=timeout)
        if not html_text:
            return out
        soup = BeautifulSoup(html_text, "html.parser")

        def content(prop):
            tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
            return tag.get("content", "").strip() if tag else ""

        out["image"] = content("og:image")
        out["desc"]  = content("og:description")
        out["site"]  = content("og:site_name") or content("twitter:site") or ""
        # first <img> in page as a fallback if no og:image
        img = soup.find("img")
        if img and img.get("src"):
            out["first_img"] = img.get("src").strip()
        return out
    except Exception:
        return out

def entry_summary_and_html(e):
    """
    Returns (summary_text, summary_html) for an entry.
    - Prefer entry.content[0].value if present (often richer than summary)
    - Fall back to summary/detail fields
    """
    raw_html = ""
    if isinstance(e.get("content"), list) and e["content"]:
        raw_html = e["content"][0].get("value", "") or ""
    if not raw_html:
        raw_html = e.get("summary", "") or e.get("description", "") or ""
    text = strip_html_to_text(raw_html)
    return text, raw_html

def entry_to_card(feed_name, e, og=None):
    link  = e.get("link", "")
    title = norm(e.get("title", "")) or "(untitled)"
    pub   = e.get("published", e.get("updated", ""))

    # derive description (OG desc -> text summary)
    summary_text, summary_html = entry_summary_and_html(e)
    desc = (og.get("desc") if og else "") or summary_text
    if len(desc) > 240:
        desc = desc[:237] + "..."

    # site/source label
    site = (og.get("site") if og else "") or feed_name
    if not site:
        site = domain_from_url(link)

    # image priority: og:image -> first <img> in page -> first <img> in summary HTML -> favicon
    image = (og.get("image") if og else "") or ""
    if not image:
        # if we scraped the page, consider first_img from the page
        if og and og.get("first_img"):
            image = og["first_img"]
    if not image:
        # try the feed-provided media arrays
        thumbs = e.get("media_thumbnail") or e.get("media_content") or []
        if thumbs and isinstance(thumbs, list) and thumbs[0].get("url"):
            image = thumbs[0]["url"]
    if not image:
        # try first <img> inside the summary HTML itself
        image = first_img_src_from_html(summary_html)
    if not image:
        # last resort: favicon
        image = favicon_for(link)

    # Build HTML card (works inside Markdown)
    img_html = f'<img src="{html.escape(image)}" alt="preview">' if image else ""
    safe_title = html.escape(title)
    safe_link  = html.escape(link)
    safe_site  = html.escape(site)
    safe_pub   = html.escape(pub)
    safe_desc  = html.escape(desc)

    return f"""<li class="card">
  {img_html}
  <div>
    <h3><a href="{safe_link}" target="_blank" rel="noopener">{safe_title}</a></h3>
    <div class="meta">{safe_site} · {safe_pub}</div>
    <p>{safe_desc}</p>
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
            # Build a blob for keyword filtering that includes plain-text summary
            sum_text, sum_html = entry_summary_and_html(e)
            blob = " ".join([
                e.get("title",""),
                sum_text,
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
            try:
                og = fetch_og(e.get("link"))
            except Exception:
                og = {}
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
