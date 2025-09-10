#!/usr/bin/env python3
"""
Create or update a monthly curated template using the last N days of firehose files.
This is optional helper for analysts; run locally or via workflow_dispatch.
"""
import os, sys, glob, datetime as dt, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIREHOSE = os.path.join(ROOT, "firehose")
CURATED = os.path.join(ROOT, "curated")

def month_slug(d):
    return d.strftime("%Y-%m")

def main(days=7):
    days = int(os.environ.get("DAYS", str(days)))
    today = dt.date.today()
    month_path = os.path.join(CURATED, f"{month_slug(today)}-curated.md")

    files = []
    for p in glob.glob(os.path.join(FIREHOSE, "*.md")):
        # pick files within window
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.md$", p)
        if not m: continue
        d = dt.datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if (today - d).days <= days:
            files.append(p)
    files.sort(reverse=True)

    section = [
        f"# Curated Highlights — {today.strftime('%B %Y')}",
        "",
        f"_Seeded from last {days} days of firehose entries. Replace bullets with analysis and org-relevant context._",
        "",
        "## Top Incidents / Advisories",
        "- ",
        "",
        "## Vendor Patches / Product-Specific",
        "- ",
        "",
        "## Vulnerabilities / Exploits",
        "- ",
        "",
        "## Ransomware / Threat Actor Activity",
        "- ",
        "",
        "## Detection & Hardening Notes",
        "- ",
        "",
        "## Sources Considered (last {days} days)".format(days=days),
    ]

    for p in files:
        name = os.path.basename(p)
        section.append(f"- {name}")

    os.makedirs(CURATED, exist_ok=True)
    if not os.path.exists(month_path):
        with open(month_path, "w", encoding="utf-8") as f:
            f.write("\n".join(section) + "\n")
        print(f"Created {month_path}")
    else:
        with open(month_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + "\n".join(section) + "\n")
        print(f"Appended to {month_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
