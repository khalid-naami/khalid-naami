#!/usr/bin/env python3
"""
Fetches the latest articles from https://khalidnaami.com/blog/rss.xml
(with /blog HTML date fallback) and updates the table inside README.md
between <!-- BLOG-POST-LIST:START --> and <!-- BLOG-POST-LIST:END -->.
Uses Python standard library only.
"""

from __future__ import annotations

import datetime
import email.utils
import html
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET


RSS_URL = "https://khalidnaami.com/blog/rss.xml"
BLOG_URL = "https://khalidnaami.com/blog"
START_MARKER = "<!-- BLOG-POST-LIST:START -->"
END_MARKER = "<!-- BLOG-POST-LIST:END -->"
MAX_POSTS = 4


def fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; khalid-naami-readme-bot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def format_pub_date(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.strip()
    try:
        dt = email.utils.parsedate_to_datetime(text)
        return dt.strftime("%b %d, %Y").replace(" 0", " ")
    except (TypeError, ValueError):
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        try:
            dt = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return dt.strftime("%b %d, %Y").replace(" 0", " ")
        except ValueError:
            pass
    return text[:20]


def pick_emoji(title: str) -> str:
    low = title.lower()
    if "dashboard options" in low:
        return "🚀"
    if any(k in low for k in ("gamma", "gex", "options", "volatility", "delta", "vega", "vix")):
        return "📊"
    if any(k in low for k in ("market", "bank", "credit", "fed", "ecb", "oil", "yield", "trading", "bond")):
        return "📈"
    if any(k in low for k in ("python", "rust", "ai", "pandas", "numpy", "c++", "react", "streamlit")):
        return "🤖"
    if any(k in low for k in ("strike", "missile", "radar", "drone", "iran", "israel", "nato", "china", "us ", "gulf")):
        return "🌍"
    return "📄"


def extract_dates_from_blog_html() -> dict[str, str]:
    """Optional fallback: maps /blog/<slug> -> 'Mon DD, YYYY' from /blog HTML."""
    try:
        page = fetch_text(BLOG_URL, timeout=15)
    except Exception:
        return {}
    date_map: dict[str, str] = {}
    # Look for a date string near a /blog/<slug> href
    pattern = re.compile(
        r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4}).{0,600}?href=[\"'](?:https://khalidnaami\.com)?(/blog/[a-z0-9-]+)[\"']",
        re.DOTALL,
    )
    for m in pattern.finditer(page):
        raw_date, path = m.group(1), m.group(2)
        try:
            dt = datetime.datetime.strptime(raw_date.strip(), "%B %d, %Y")
            date_map[path] = dt.strftime("%b %d, %Y").replace(" 0", " ")
        except ValueError:
            try:
                dt = datetime.datetime.strptime(raw_date.strip(), "%b %d, %Y")
                date_map[path] = dt.strftime("%b %d, %Y").replace(" 0", " ")
            except ValueError:
                pass
    return date_map


def parse_rss_posts(xml_text: str, limit: int = MAX_POSTS) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    posts: list[dict[str, str]] = []

    items = root.findall(".//item")
    if items:
        for item in items[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (
                item.findtext("pubDate")
                or item.findtext("{http://purl.org/dc/elements/1.1/}date")
                or ""
            )
            if title and link:
                posts.append({"title": title, "link": link, "date": format_pub_date(pub)})
    else:
        # Atom fallback
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns)[:limit]:
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.attrib.get("href", "").strip() if link_el is not None else ""
            pub = (
                entry.findtext("atom:updated", default="", namespaces=ns)
                or entry.findtext("atom:published", default="", namespaces=ns)
            )
            if title and link:
                posts.append({"title": title, "link": link, "date": format_pub_date(pub)})

    # If any item lacks a publication date, try enriching from /blog HTML
    if posts and any(not p["date"] for p in posts):
        date_map = extract_dates_from_blog_html()
        for p in posts:
            if not p["date"]:
                slug_match = re.search(r"(/blog/[^/?#]+)", p["link"])
                if slug_match and slug_match.group(1) in date_map:
                    p["date"] = date_map[slug_match.group(1)]
                else:
                    p["date"] = "Latest"

    return posts


def build_table_html(posts: list[dict[str, str]]) -> str:
    rows = [
        '<table align="center">',
        "  <tr>",
        "    <th>📄 Article</th>",
        "    <th>📅 Published</th>",
        "  </tr>",
    ]
    for p in posts:
        emoji = pick_emoji(p["title"])
        safe_url = html.escape(p["link"], quote=True)
        safe_title = html.escape(p["title"])
        safe_date = html.escape(p["date"] or "Latest")
        rows.extend(
            [
                "  <tr>",
                "    <td>",
                f'      <a href="{safe_url}">',
                f"        {emoji} {safe_title}",
                "      </a>",
                "    </td>",
                f"    <td>{safe_date}</td>",
                "  </tr>",
            ]
        )
    rows.append("</table>")
    return "\n".join(rows)


def update_readme(readme_path: str = "README.md") -> bool:
    if not os.path.exists(readme_path):
        print(f"{readme_path} not found.", file=sys.stderr)
        return False

    try:
        rss_xml = fetch_text(RSS_URL)
        posts = parse_rss_posts(rss_xml, MAX_POSTS)
    except Exception as exc:
        print(f"Skipping blog sync (fetch/parse failed): {exc}", file=sys.stderr)
        return False

    if not posts:
        print("No posts parsed from RSS; keeping existing README table.", file=sys.stderr)
        return False

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    if START_MARKER not in content or END_MARKER not in content:
        print("Blog markers missing in README.md; skipping update.", file=sys.stderr)
        return False

    new_block = f"{START_MARKER}\n{build_table_html(posts)}\n{END_MARKER}"
    updated = re.sub(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        lambda _: new_block,
        content,
        count=1,
        flags=re.DOTALL,
    )

    if updated != content:
        with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        print(f"Updated {readme_path} with {len(posts)} latest blog posts.")
        return True

    print("README.md blog table already up to date.")
    return False


if __name__ == "__main__":
    update_readme()
