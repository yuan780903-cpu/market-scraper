"""
政府公告爬蟲
支援兩種結構：
  - afa_card: 農糧署卡片 (<a class="agricultural-news" title="..."> 含日期 span)
  - generic:  通用，從所有 <a> 找含關鍵字的標題
依 config.GOV_SOURCES 的 structure 欄位決定。
"""

import re
import time
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import GOV_SOURCES, KEYWORDS, REQUEST_DELAY, REQUEST_TIMEOUT, USER_AGENT

ROC_DATE_RE = re.compile(r"(\d{3})-(\d{2})-(\d{2})")


def _match_keyword(text: str) -> Optional[str]:
    for kw in KEYWORDS:
        if kw in text:
            return kw
    return None


def _roc_to_iso(s: str) -> str:
    m = ROC_DATE_RE.search(s or "")
    if not m:
        return ""
    try:
        d = date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))
        return d.strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _http_get(url: str) -> requests.Response:
    return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)


def _fetch_afa_card(source: Dict) -> List[Dict]:
    """農糧署卡片結構：<a class='agricultural-news' title='...' href='...'>"""
    try:
        r = _http_get(source["url"])
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
    except requests.RequestException as e:
        print(f"  [!] 無法存取 {source['name']}: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    results = []
    seen = set()
    requires_keyword = source.get("requires_keyword", True)

    # 同時抓 .agricultural-news (卡片版) 和 a[href*=article_id] (列表版)
    candidates = soup.select("a.agricultural-news") or soup.select('a[href*="article_id"]')

    for a in candidates:
        title = (a.get("title") or "").strip()
        if not title:
            h3 = a.select_one("h3")
            title = h3.get_text(strip=True) if h3 else ""
        if not title:
            continue

        matched = _match_keyword(title)
        if requires_keyword and not matched:
            continue
        if not matched:
            matched = "—"

        href = urljoin(source["url"], a.get("href", ""))
        if href in seen:
            continue
        seen.add(href)

        # 日期：先找卡片版 ribbon span，否則找 parent 內任何 ROC 日期文字
        date_iso = ""
        date_span = a.select_one(".agricultural-news-ribbon span")
        if date_span:
            date_iso = _roc_to_iso(date_span.get_text(" ", strip=True))
        if not date_iso:
            parent = a.find_parent(["tr", "li", "div"])
            if parent:
                date_iso = _roc_to_iso(parent.get_text(" ", strip=True))

        results.append({
            "來源類型": "政府公告",
            "來源網站": source["name"],
            "標題": title,
            "連結": href,
            "命中關鍵字": matched,
            "發布日期": date_iso,
            "摘要": "",
        })
    return results


def _fetch_generic(source: Dict) -> List[Dict]:
    """通用 fallback：找所有 <a>，篩標題含關鍵字"""
    try:
        r = _http_get(source["url"])
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
    except requests.RequestException as e:
        print(f"  [!] 無法存取 {source['name']}: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")
    results = []
    seen = set()

    for link in soup.select("a"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or not href or href.startswith(("#", "javascript")):
            continue
        matched = _match_keyword(title)
        if not matched:
            continue
        full_url = urljoin(source.get("base_url") or source["url"], href)
        if full_url in seen:
            continue
        seen.add(full_url)
        results.append({
            "來源類型": "政府公告",
            "來源網站": source["name"],
            "標題": title,
            "連結": full_url,
            "命中關鍵字": matched,
            "發布日期": "",
            "摘要": "",
        })
    return results


def fetch_source(source: Dict) -> List[Dict]:
    structure = source.get("structure", "generic")
    if structure == "afa_card":
        return _fetch_afa_card(source)
    return _fetch_generic(source)


def scrape_all() -> List[Dict]:
    all_results = []
    for source in GOV_SOURCES:
        print(f"[政府] 爬取 {source['name']} ...")
        items = fetch_source(source)
        print(f"  → 找到 {len(items)} 則符合關鍵字的項目")
        all_results.extend(items)
        time.sleep(REQUEST_DELAY)
    return all_results


if __name__ == "__main__":
    rows = scrape_all()
    print(f"\n總共 {len(rows)} 筆")
    for r in rows[:10]:
        print(f"  [{r['發布日期'] or '—'}] {r['標題'][:60]}")
