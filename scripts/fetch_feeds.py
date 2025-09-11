#!/usr/bin/env python3
"""
Fetch RSS/Atom feeds and write a dated markdown page (with Jekyll front matter)
containing card-style previews.

Features:
- ALWAYS strips HTML tags for descriptions (no raw <p>…</p>)
- Image priority:
  OG image -> first <img> in article -> feed media ->
  first <img> in summary -> per-domain override (e.g., CISA logo) ->
  DuckDuckGo favicon -> inline SVG placeholder
- Resolves relative image URLs against the article URL
- Jekyll front matter so GitHub Pages applies your theme
"""

import os, re, sys, yaml, time, html, datetime as dt, urllib.parse
import feedparser
import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREHOSE = os.path.join(ROOT, "firehose")
FEEDS_YAML = os.path.join(ROOT, "feeds.yaml")

OG_SCRAPE_LIMIT = 60
USER_AGENT = "Mozilla/5.0 (CTI Hub Bot)"

# Per-domain image overrides (used when no meaningful preview image is found)
DOMAIN_IMAGE_OVERRIDES = {
    "cisa.gov": "https://www.cisa.gov/themes/custom/cisa/images/cisa-logo.svg",
    "www.cisa.gov": "https://www.cisa.gov/themes/custom/cisa/images/cisa-logo.svg",
}

SVG_PLACEHOLDER_DATAURI = (
    "data:image/svg+xml;utf8,"
    + urllib.parse.quote(
        """<svg xmlns='http://www.w3.org/2000/svg' width='280' height='180'>
<rect width='100%' height='100%' fill='#e5e7eb'/>
<text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle'
      font-family='Arial, Helvetica, sans-serif' font-size='16' fill='#6b7280'>
No preview
</text>
</svg>"""
    )
)

def load_config():
    with open(FEEDS_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    feeds = cfg.get("feeds", []) or []
    keywords = [k.strip() for k in (cfg.get("keywords") or []) if str(k).strip()]
    return feeds, keywords

def norm(s): return re.sub(r"\s+"," ", (s or "")).strip()

def strip_html(text):
    if not text:
        return ""
    try:
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(" ", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", " ", text)

def first_img_src(html_text):
    if not html_text:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        tag = soup.find("img")
        return (tag.get("src") or "").strip() if tag else ""
    except Exception:
        return ""

def resolve_url(base, src):
    if not src:
        return ""
    try:
        return urllib.parse.urljoin(base, src)
    except Exception:
        return src

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

def entry_summary_pair(e):
    # Prefer content[].value if present; else summary/description
    raw_html = ""
    if isinstance(e.get("content"), list) and e["content"]:
        raw_html = e["content"][0].get("value", "") or ""
    if not raw_html:
        raw_html = e.get("summary", "") or e.get("description", "") or ""
    text = strip_html(raw_html)
    return text, raw_html

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
    # 5) Per-domain override (e.g., CISA logo)
    if not image:
        host = domain_from_url(link)
        if host in DOMAIN_IMAGE_OVERRIDES:
            image = DOMAIN_IMAGE_OVERRIDES[host]
    # 6) Favicon (always something)
    if not image:
        image = ddg_favicon_for(link)
    # 7) Final fallback: inline SVG placeholder (always works)
    if not image:
        image = SVG_PLACEHOLDER_DATAURI
    return image

def entry_to_card(feed_name, e, og):
    link  = e.get("link", "") or ""
    title = norm(e.get("title", "")) or "(untitled)"
    pub   = e.get("published", e.get("updated", "")) or ""

    # Plain-text description: prefer OG desc, else summary HTML → strip
    sum_text, sum_html = entry_summary_pair(e)
    desc_source = og.get("desc") or sum_html or sum_text
    desc = strip_html(desc_source)
    if len(desc) > 240:
        desc = desc[:237] + "..."

    # Site label
    site = og.get("site") or feed_name or domain_from_url(link)

    # Image with robust fallbacks (incl. CISA override)
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
    feeds, keywords = load_config()
    os.makedirs(FIREHOSE, exist_ok=True)
    today_iso = dt.datetime.utcnow().date().isoformat()
    outpath = os.path.join(FIREHOSE, f"{today_iso}.md")

    # Gather entries
    entries = []
    for f in feeds:
        name = f.get("name") or f.get("url")
        url  = f.get("url")
        if not url:
            continue
        d = feedparser.parse(url)
        for e in d.entries:
            plain_sum, _ = entry_summary_pair(e)
            blob = " ".join([
                e.get("title",""),
                plain_sum,
                e.get("link",""),
                " ".join([t.get("term","") for t in e.get("tags", [])])
            ])
            if match_kw(blob, keywords):
                entries.append((name, e))

    # Newest first
    def ts(entry):
        for k in ("published_parsed","updated_parsed"):
            v = getattr(entry, k, None)
            if v: return time.mktime(v)
        return 0
    entries.sort(key=lambda pair: ts(pair[1]), reverse=True)

    # Enrich with OG (budgeted)
    enriched, budget = [], OG_SCRAPE_LIMIT
    for name, e in entries:
        og = {}
        if budget > 0 and e.get("link"):
            try:
                og = fetch_og(e.get("link"))
            except Exception:
                og = {}
            budget -= 1
        enriched.append((name, e, og))

    # Build page
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
