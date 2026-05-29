"""
新聞爬蟲 — 透過 RSS 蒐集，不打到網站 HTML，最穩定
"""

import time
from datetime import datetime
from typing import Optional

import feedparser

from config import KEYWORDS, REQUEST_DELAY, RSS_FEEDS


def _match_keyword(text: str) -> Optional[str]:
    for kw in KEYWORDS:
        if kw in text:
            return kw
    return None


def _format_date(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6]).strftime("%Y-%m-%d %H:%M")
            except (TypeError, ValueError):
                pass
    return entry.get("published", "") or entry.get("updated", "")


def fetch_feed(feed: dict) -> list:
    parsed = feedparser.parse(feed["url"])
    if parsed.bozo and not parsed.entries:
        print(f"  [!] 無法解析 {feed['name']}: {parsed.bozo_exception}")
        return []

    # 活動類 feed 已用 Google News 精準查詢，不再做關鍵字二次過濾
    requires_keyword = feed.get("category", "新聞") == "新聞"

    results = []
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        summary = entry.get("summary", "").strip()
        full_text = f"{title} {summary}"

        matched = _match_keyword(full_text) if requires_keyword else None
        if requires_keyword and not matched:
            continue
        if not matched:
            matched = feed.get("name", "").replace("Google News - ", "")

        results.append({
            "來源類型": feed.get("category", "新聞"),
            "來源網站": feed["name"],
            "標題": title,
            "連結": entry.get("link", ""),
            "命中關鍵字": matched,
            "發布日期": _format_date(entry),
            "摘要": summary[:200],
        })

    return results


def scrape_all() -> list:
    all_results = []
    for feed in RSS_FEEDS:
        print(f"[新聞] 抓取 {feed['name']} ...")
        items = fetch_feed(feed)
        print(f"  → 找到 {len(items)} 則符合關鍵字的新聞")
        all_results.extend(items)
        time.sleep(REQUEST_DELAY)
    return all_results


if __name__ == "__main__":
    rows = scrape_all()
    for r in rows[:10]:
        print(r)
