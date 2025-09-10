#!/usr/bin/env python3
"""
Build a vendor-focused page (e.g., Fortinet) with Feedly-style preview cards.
It filters items from:
  1) All feeds listed in feeds.yaml
  2) Any EXTRA_FEEDS provided via env var (comma-separated URLs, e.g. Reddit RSS)

Filtering rules (any-match):
  - KEYWORDS: match on title/summary (case-insensitive)
  - SOURCE_MATCH: include entries whose FEED NAME contains any of these substrings

Env vars (all optional):
  PAGE_TITLE      -> title for the page (default: "Vendor Watch")
  KEYWORDS        -> "Fortinet, FortiOS, FortiClient, ..." (any-match)
  SOURCE_MATCH    -> "Fortinet, FortiGuard" (feed name contains)
  EXTRA_FEEDS     -> extra RSS/Atom URLs (comma-separated)
  OUTPUT_PATH     -> output file path (default: curated/vendor-watch.md)
  OG_SCRAPE_LIMIT -> int, how many links to fetch for OpenGraph (default: 40)

Requires: feedparser, pyyaml, requests, beautifulsoup4
"""

import os, re, sys, time, html, datetime as dt, urllib.parse
import yaml
import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREHOSE = os.path.join(ROOT, "firehose")
FEEDS_YAML = os.path.join(ROOT, "feeds.yaml")

USER_AGENT = "Mozilla/5.0 (CTI Hub Bot)"

def getenv(name, default=""):
    v = os.environ.get(name, "")
    return v if v is not None else default

def parse_list_env(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]

PAGE_TITLE      = getenv("PAGE_TITLE", "Vendor Watch").strip() or "Vendor Watch"
OUTPUT_PATH     = os.path.join(ROOT, (getenv("OUTPUT_PATH", "curated/vendor-watch.md").strip() or "curated/vendor-watch.md"))
OG_SCRAPE_LIMIT = int(getenv("OG_SCRAPE_LIMIT", "40") or "40")

KEYWORDS     = [s.lower() for s in parse_list_env(getenv("KEYWORDS", ""))]
SOURCE_MATCH = [s.lower() for s in parse_list_env(getenv("SOURCE_MATCH", ""))]
EXTRA_FEEDS  = parse_list_env(getenv("EXTRA_FEEDS", ""))

def load_config_feeds():
    feeds = []
    if os.path.exists(FEEDS_YAML):
        with open(FEEDS_YAML, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        for f in (cfg.get("feeds") or []):
            name = f.get("name") or f.get("url") or ""
            url  = f.get("url") or ""
            if url:
                feeds.append({"name": name, "url": url})
    return feeds

def add_extra_feeds(feeds):
    """Append extra feeds from env; names derived from hostname/path."""
    for url in EXTRA_FEEDS:
        try:
            u = urllib.parse.urlparse(url)
            host = u.hostname or "extra"
            # Make a readable name like "reddit: /r/fortinet/top (day)"
            path = (u.path or "").strip("/")
            q = urllib.parse.parse_qs(u.query)
            t = q.get("t", [""])[0]
            name = f"{host}: /{path}" + (f" (t={t})" if t else "")
            feeds.append({"name": name, "url": url})
        except Exception:
            feeds.append({"name": "extra", "url": url})
    return feeds

def norm(s): 
    return re.sub(r"\s+"," ", (s or "")).strip()

def strip_html(text):
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", text)

def entry_summary_pair(e):
    # Prefer content[].value if present; else summary/description
    raw_html = ""
    if isinstance(e.get("content"), list) and e["content"]:
        raw_html = e["content"][0].get("value", "") or ""
    if not raw_html:
        raw_html = e.get("summary", "") or e.get("description", "") or ""
    text = strip_html(raw_html)
    return text, raw_html

def match_keywords(text):
    if not KEYWORDS:
        return True
    t = text.lower()
    return any(k in t for k in KEYWORDS)

def match_source(feed_name):
    if not SOURCE_MATCH:
        return True
    name = (feed_name or "").lower()
    return any(s in name for s in SOURCE_MATCH)

def resolve_url(base, src):
    if not src:
        return ""
    try:
        return urllib.parse.urljoin(base, src)
    except Exception:
        return src

def domain_from_url(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:
        return ""

def ddg_favicon_for(url):
    host = domain_from_url(url)
    return f"https://icons.duckduckgo.com/ip3/{host}.ico" if host else ""

def fetch_url_html(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200 and "text/html" in r.headers.get("Content-Type", ""):
            return r.text
    except Exception:
        pass
    return ""

def fetch_og(url, timeout=8):
    out = {"image": "", "desc": "", "site": "", "first_img": ""}
    if not url:
        return out
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
    img = soup.find("img")
    if img and img.get("src"):
        out["first_img"] = img.get("src").strip()
    return out

def first_img_src(html_text):
    if not html_text:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        tag = soup.find("img")
        return (tag.get("src") or "").strip() if tag else ""
    except Exception:
        return ""

def pick_image(link, e, og, summary_html):
    # 1) OG image
    image = og.get("image") or ""
    # 2) First <img> in fetched page
    if not image and og.get("first_img"):
        image = resolve_url(link, og["first_img"])
    # 3) Feed media arrays
    if not image:
        thumbs = e.get("media_thumbnail") or e.get("media_content") or []
        if thumbs and isinstance(thumbs, list) and thumbs[0].get("url"):
            image = resolve_url(link, thumbs[0]["url"])
    # 4) First <img> in summary HTML
    if not image:
        img_in_summary = first_img_src(summary_html)
        image = resolve_url(link, img_in_summary) if img_in_summary else ""
    # 5) Favicon (always something)
    if not image:
        image = ddg_favicon_for(link)
    return image

def entry_to_card(feed_name, e, og):
    link  = e.get("link", "") or ""
    title = norm(e.get("title", "")) or "(untitled)"
    pub   = e.get("published", e.get("updated", "")) or ""

    sum_text, sum_html = entry_summary_pair(e)
    desc_source = og.get("desc") or sum_html or sum_text
    desc = strip_html(desc_source)
    if len(desc) > 240:
        desc = desc[:237] + "..."

    site = og.get("site") or feed_name or domain_from_url(link)
    image = pick_image(link, e, og, sum_html)

    img_html = f'<img src="{html.escape(image)}" alt="preview">'
    return f"""<li class="card">
  {img_html}
  <div>
    <h3><a href="{html.escape(link)}" target="_blank" rel="noopener">{html.escape(title)}</a></h3>
    <div class="meta">{html.escape(site)} · {html.escape(pub)}</div>
    <p>{html.escape(desc)}</p>
  </div>
</li>"""

def main():
    # Load feeds from feeds.yaml and append EXTRA_FEEDS
    feeds = load_config_feeds()
    add_extra_feeds(feeds)

    # Gather matches from all feeds
    items = []
    for f in feeds:
        name = f.get("name") or f.get("url")
        url  = f.get("url")
        if not url:
            continue
        # If SOURCE_MATCH provided, keep only feeds whose names match
        if not match_source(name):
            # Still allow in if keywords match later? We filter after parsing, so we
            # skip here only when filtering strictly by source names.
            pass
        d = feedparser.parse(url)
        for e in d.entries:
            plain_sum, _ = entry_summary_pair(e)
            blob = " ".join([
                e.get("title",""),
                plain_sum,
                e.get("link",""),
                " ".join([t.get("term","") for t in e.get("tags", [])])
            ])
            # Keep entry if either source name matches OR keywords match the content
            if match_source(name) or match_keywords(blob):
                items.append((name, e))

    # Sort newest first
    def ts(entry):
        for k in ("published_parsed","updated_parsed"):
            v = getattr(entry, k, None)
            if v: return time.mktime(v)
        return 0
    items.sort(key=lambda pair: ts(pair[1]), reverse=True)

    # Enrich with OG for top N
    enriched, budget = [], OG_SCRAPE_LIMIT
    for name, e in items:
        og = {}
        if budget > 0 and e.get("link"):
            try:
                og = fetch_og(e.get("link"))
            except Exception:
                og = {}
            budget -= 1
        enriched.append((name, e, og))

    # Ensure output dir
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    # Build page
    today_human = dt.datetime.utcnow().strftime('%B %d, %Y')
    header = [
        "---",
        "layout: default",
        f"title: {PAGE_TITLE}",
        "---",
        "",
        '<link rel="stylesheet" href="{{ \'/assets/css/cards.css\' | relative_url }}">',
        "",
        f"# {PAGE_TITLE}",
        "",
        f"_Updated: {today_human} • Sources filter: "
        f"{', '.join(SOURCE_MATCH) if SOURCE_MATCH else 'none'} • "
        f"Keywords: {', '.join([k for k in KEYWORDS]) if KEYWORDS else 'none'}_",
        "",
        '<ul class="cards">'
    ]
    cards = [entry_to_card(name, e, og) for (name, e, og) in enriched]
    footer = ["</ul>", ""]

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(header + cards + footer))

    print(f"Wrote {OUTPUT_PATH} with {len(enriched)} items.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
