"""
Facebook 粉專貼文爬蟲 — 透過 Apify 第三方服務（合法、零風險）
- 使用 apify/facebook-posts-scraper actor
- 每個粉專抓最近 N 篇貼文
- 用 KEYWORDS 過濾
- 沒設 APIFY_API_TOKEN 時整個流程跳過

Apify 定價：每月 $5 免費額度，超過約 $0.30 / 1000 posts
"""

import os
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests

from email_sender import _load_env
from config import APIFY_MIN_REMAINING_USD, FB_PAGES, FB_POSTS_PER_PAGE, KEYWORDS

ACTOR_ID = "apify~facebook-posts-scraper"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"
USER_INFO_URL = "https://api.apify.com/v2/users/me"


def _check_remaining_budget(token: str) -> float:
    """查 Apify 帳號當月剩餘額度，回傳 USD（無法取得時回 0.0）"""
    try:
        r = requests.get(USER_INFO_URL, params={"token": token}, timeout=15)
        if r.status_code != 200:
            return 0.0
        data = r.json().get("data", {})
        plan = data.get("plan", {})
        max_usd = float(plan.get("maxMonthlyUsageUsd", 0) or 0)
        usage = data.get("usageCycle", {})
        used_usd = float(usage.get("usageUsd", 0) or 0)
        return max(0.0, max_usd - used_usd)
    except (requests.RequestException, ValueError, KeyError):
        return 0.0


def _match_keyword(text: str) -> Optional[str]:
    for kw in KEYWORDS:
        if kw in text:
            return kw
    return None


def _format_date(s: str) -> str:
    """Apify 回傳的時間像 '2026-05-28T10:30:00.000Z'，轉成 'YYYY-MM-DD HH:MM'"""
    if not s:
        return ""
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return s[:16]


def _page_name(url: str) -> str:
    """從 FB URL 抽粉專 id：https://www.facebook.com/888HS888/ → 888HS888"""
    return url.rstrip("/").split("/")[-1].split("?")[0]


def fetch_pages(pages: List[str], posts_per_page: int) -> List[Dict]:
    """呼叫 Apify actor 抓貼文，回傳精簡 dict list"""
    _load_env()
    token = os.environ.get("APIFY_API_TOKEN", "").strip()
    if not token:
        print("[FB] 沒設 APIFY_API_TOKEN，跳過 FB 抓取")
        return []
    if not pages:
        print("[FB] config.FB_PAGES 為空，跳過")
        return []

    # 預檢查 Apify 餘額，避免 402 失敗
    remaining = _check_remaining_budget(token)
    if remaining > 0 and remaining < APIFY_MIN_REMAINING_USD:
        print(f"[FB] Apify 剩餘額度 ${remaining:.4f} < ${APIFY_MIN_REMAINING_USD}，跳過 FB 避免失敗")
        return []
    if remaining > 0:
        print(f"[FB] Apify 剩餘額度 ${remaining:.2f}")

    print(f"[FB] 透過 Apify 抓 {len(pages)} 個粉專，每個最多 {posts_per_page} 篇...")

    payload = {
        "startUrls": [{"url": u} for u in pages],
        "resultsLimit": posts_per_page,
    }

    try:
        r = requests.post(
            RUN_SYNC_URL,
            params={"token": token, "timeout": 180},
            json=payload,
            timeout=240,
        )
    except requests.RequestException as e:
        print(f"[FB] Apify 呼叫失敗：{e}")
        return []

    # Apify run-sync 成功時可能回 200 或 201
    if r.status_code not in (200, 201):
        print(f"[FB] Apify 回應異常 {r.status_code}: {r.text[:300]}")
        return []

    try:
        items = r.json()
    except ValueError:
        print(f"[FB] Apify 回傳非 JSON: {r.text[:300]}")
        return []

    print(f"[FB] Apify 回傳 {len(items)} 篇貼文，篩選關鍵字...")

    results = []
    for it in items:
        text = (it.get("text") or "").strip()
        url = it.get("url") or it.get("postUrl") or ""
        page_url = it.get("pageUrl") or it.get("facebookUrl") or ""
        published = it.get("time") or it.get("publishedTime") or ""

        matched = _match_keyword(text)
        if not matched:
            continue

        # 取貼文前 80 字當「標題」
        title_text = text.split("\n")[0][:80]
        if len(text) > len(title_text):
            title_text += "…"

        results.append({
            "來源類型": "FB",
            "來源網站": f"FB - {_page_name(page_url or url)}",
            "標題": title_text,
            "連結": url,
            "命中關鍵字": matched,
            "發布日期": _format_date(published),
            "摘要": text[:200],
        })

    print(f"[FB] 篩出 {len(results)} 篇含關鍵字的貼文")
    return results


def scrape_all() -> List[Dict]:
    return fetch_pages(FB_PAGES, FB_POSTS_PER_PAGE)


if __name__ == "__main__":
    rows = scrape_all()
    print(f"\n總共 {len(rows)} 筆")
    for r in rows[:5]:
        print(f"  [{r['發布日期']}] {r['來源網站']} - {r['標題'][:50]}")
