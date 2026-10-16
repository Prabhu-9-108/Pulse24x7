#!/usr/bin/env python3
"""
Pulse24×7 Autonomous Scraper & SEO Publisher
--------------------------------------------
Fetches official Current Affairs (PIB, RBI) and Job Notifications,
formats them into high-SEO structured articles (with optional Gemini AI enrichment),
and writes directly to `feeds.json` and `sitemap.xml` for GitHub Pages deployment.
"""

import json
import os
import re
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://your-username.github.io/pulse24x7")
FEEDS_JSON_PATH = "feeds.json"
SITEMAP_XML_PATH = "sitemap.xml"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

RSS_SOURCES = [
    {
        "name": "PIB Official Releases",
        "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
        "category": "current-affairs",
        "categoryLabel": "Current Affairs",
        "author": "Pulse24×7 PIB Syndicate"
    },
    {
        "name": "RBI Monetary & Banking Notifications",
        "url": "https://rbi.org.in/notifications_rss.xml",
        "category": "data-news",
        "categoryLabel": "Data Report",
        "author": "Pulse24×7 RBI Policy Desk"
    },
    {
        "name": "Remote & Tech Engineering Jobs",
        "url": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "category": "private-jobs",
        "categoryLabel": "Tech Careers",
        "author": "Pulse24×7 Tech Hiring Network"
    }
]


def strip_html_tags(text: str) -> str:
    """Removes raw HTML tags and normalizes whitespace."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def make_article_id(prefix: str, title: str) -> str:
    """Creates a deterministic, SEO-friendly ID from the headline."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:45]
    return f"{prefix}-{slug}"


def extract_keywords(title: str, category: str) -> list:
    """Extracts high-value SEO keywords from the headline."""
    stop_words = {
        "the", "and", "for", "with", "from", "that", "this", "under", "into",
        "over", "more", "than", "will", "have", "been", "india", "announces"
    }
    words = re.findall(r"[A-Za-z0-9]{4,}", title)
    keywords = []
    for w in words:
        if w.lower() not in stop_words and w.lower() not in [k.lower() for k in keywords]:
            keywords.append(w)
        if len(keywords) >= 4:
            break

    if category == "gov-jobs":
        keywords.append("Sarkari Job 2026")
    elif category == "private-jobs":
        keywords.append("Tech Careers 2026")
    else:
        keywords.append("Current Affairs 2026")

    return keywords[:5]


def enrich_with_ai_or_fallback(title: str, raw_summary: str, category: str) -> dict:
    """
    Uses Gemini API if GEMINI_API_KEY is configured in GitHub Secrets.
    Otherwise falls back to deterministic structured formatting so the pipeline
    runs 100% free without failing.
    """
    clean_desc = strip_html_tags(raw_summary)
    if len(clean_desc) < 40:
        clean_desc = (
            f"Official Pulse24×7 update regarding {title}. Review key highlights, "
            f"important dates, eligibility criteria, and examination takeaways."
        )

    if GEMINI_API_KEY:
        try:
            prompt = (
                f"Write a concise, fact-checked HTML summary (using <p> and <ul><li> tags) "
                f"for competitive exam aspirants and job seekers based on this headline: '{title}' "
                f"and details: '{clean_desc[:500]}'. Keep it under 140 words."
            )
            payload = json.dumps({
                "contents": [{"parts": [{"text": prompt}]}]
            }).encode("utf-8")
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                ai_html = (
                    result.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                if ai_html:
                    return {
                        "summary": clean_desc[:155],
                        "content": ai_html
                    }
        except Exception as exc:
            print(f"[Info] AI enrichment skipped, using structured template: {exc}")

    formatted_html = (
        f"<p>{clean_desc}</p>"
        f"<h3 class='text-base font-bold text-slate-900 dark:text-white mt-3'>"
        f"Pulse24×7 Key Exam & Career Takeaways:</h3>"
        f"<ul class='list-disc pl-5 space-y-1'>"
        f"<li><strong>Headline Focus:</strong> {title}</li>"
        f"<li><strong>Category:</strong> Verified {category.replace('-', ' ').title()} Release</li>"
        f"<li><strong>Action Point:</strong> Cross-check official portal notifications for annexures and PDF circulars.</li>"
        f"</ul>"
    )
    return {
        "summary": clean_desc[:152] + ("..." if len(clean_desc) > 152 else ""),
        "content": formatted_html
    }


def fetch_rss_items(source: dict, max_items: int = 4) -> list:
    """Fetches and parses an RSS XML feed into Pulse24×7 article objects."""
    articles = []
    headers = {
        "User-Agent": "Pulse24x7Bot/2.0 (+https://github.com/pulse24x7; SEO News Aggregator)"
    }
    try:
        req = urllib.request.Request(source["url"], headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_bytes = response.read()

        root = ET.fromstring(xml_bytes)
        items = root.findall(".//item")[:max_items]
        today_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

        for item in items:
            title_el = item.find("title")
            desc_el = item.find("description")
            title = strip_html_tags(title_el.text if title_el is not None else "")
            raw_desc = desc_el.text if desc_el is not None else ""

            if not title or len(title) < 10:
                continue

            cat = source["category"]
            cat_label = source["categoryLabel"]
            job_meta = None

            if any(w in title.lower() for w in ["recruitment", "vacancy", "upsc", "ssc", "exam", "posts"]):
                cat = "gov-jobs"
                cat_label = "Govt Job"
                job_meta = {
                    "vacancies": "Check Official PDF",
                    "salary": "As per 7th/8th CPC Matrix",
                    "eligibility": "Graduate / Post-Graduate",
                    "deadline": "Refer Notification"
                }
            elif cat == "private-jobs":
                job_meta = {
                    "vacancies": "Multiple Openings",
                    "salary": "Competitive Tech Package",
                    "eligibility": "B.Tech / CS or Equivalent Experience",
                    "deadline": "Rolling Recruitment"
                }

            enriched = enrich_with_ai_or_fallback(title, raw_desc, cat)
            art_id = make_article_id("auto", title)

            articles.append({
                "id": art_id,
                "title": title,
                "category": cat,
                "categoryLabel": cat_label,
                "date": today_str,
                "readTime": "3 min read",
                "author": source["author"],
                "keywords": extract_keywords(title, cat),
                "summary": enriched["summary"],
                "content": enriched["content"],
                "jobMeta": job_meta
            })

    except Exception as err:
        print(f"[Warning] Could not fetch {source['name']} ({source['url']}): {err}")

    return articles


def load_existing_feeds() -> list:
    """Loads existing articles from feeds.json if present."""
    if os.path.exists(FEEDS_JSON_PATH):
        try:
            with open(FEEDS_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as err:
            print(f"[Warning] Failed to read {FEEDS_JSON_PATH}: {err}")
    return []


def write_sitemap_xml(articles: list) -> None:
    """Generates a fresh sitemap.xml for Google Search Console indexing."""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '  <url>',
        f'    <loc>{SITE_BASE_URL}/</loc>',
        f'    <lastmod>{today_iso}</lastmod>',
        '    <changefreq>hourly</changefreq>',
        '    <priority>1.0</priority>',
        '  </url>'
    ]

    for art in articles[:100]:
        priority = "0.9" if art.get("category") in ("gov-jobs", "current-affairs") else "0.8"
        lines.extend([
            '  <url>',
            f'    <loc>{SITE_BASE_URL}/?article={art.get("id", "post")}</loc>',
            f'    <lastmod>{today_iso}</lastmod>',
            '    <changefreq>daily</changefreq>',
            f'    <priority>{priority}</priority>',
            '  </url>'
        ])

    lines.append('</urlset>')
    with open(SITEMAP_XML_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[Success] Updated {SITEMAP_XML_PATH} with {min(len(articles), 100)} URLs.")


def main():
    print("=== Starting Pulse24×7 Autonomous Scraper ===")
    existing_articles = load_existing_feeds()
    existing_ids = {item.get("id") for item in existing_articles if isinstance(item, dict)}

    newly_added = 0
    for source in RSS_SOURCES:
        print(f"Fetching: {source['name']}...")
        fetched_items = fetch_rss_items(source, max_items=4)
        for item in fetched_items:
            if item["id"] not in existing_ids:
                existing_articles.insert(0, item)
                existing_ids.add(item["id"])
                newly_added += 1

    existing_articles = existing_articles[:60]

    with open(FEEDS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(existing_articles, f, indent=2, ensure_ascii=False)

    print(f"[Success] Added {newly_added} new articles. Total stored: {len(existing_articles)}")
    write_sitemap_xml(existing_articles)


if __name__ == "__main__":
    main()
