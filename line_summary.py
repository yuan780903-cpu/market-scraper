"""
LINE 純文字週報摘要 — 限 5000 字內，分段易讀
- PDF 變動（新上架前 N、新違規全部）
- 活動最新 5 則
- 新聞最新 5 則
- 附完整報表 URL
"""

from datetime import datetime
from typing import Dict, List

MAX_LISTING = 5
MAX_NEWS = 5
MAX_ACTIVITY = 5


def _safe(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")


def _section_pdf(pdf_result: Dict) -> str:
    if not pdf_result:
        return ""

    added = pdf_result.get("recent_added", [])
    violations = pdf_result.get("recent_violations", [])
    days = pdf_result.get("change_days", 30)

    lines = [f"【推薦名單監控（近 {days} 天）】"]
    lines.append(f"新上架 {len(added)} 件 ｜ 新違規 {len(violations)} 件")
    lines.append("")

    if violations:
        lines.append("▶ 新違規")
        for v in violations:
            cat = v.get("原品目", "?")
            brand = _safe(v.get("廠牌商品名稱", ""), 30)
            company = _safe(v.get("業者名稱", ""), 20)
            reason = _safe(v.get("違規原因", ""), 50)
            date = v.get("下網日", "")
            lines.append(f"・[{cat}] {brand} ({company})")
            lines.append(f"  {date} - {reason}")
        lines.append("")

    if added:
        lines.append(f"▶ 新上架（顯示前 {min(len(added), MAX_LISTING)} 件）")
        for a in added[:MAX_LISTING]:
            cat = a.get("品目", "?")
            brand = _safe(a.get("廠牌商品名稱", ""), 30)
            company = _safe(a.get("業者名稱", ""), 20)
            date = a.get("上架日", "")
            lines.append(f"・[{cat}] {date} {brand} ({company})")
        if len(added) > MAX_LISTING:
            lines.append(f"  …其餘 {len(added) - MAX_LISTING} 件請見完整報表")
        lines.append("")

    return "\n".join(lines)


def _section_news(rows: List[Dict], category: str, label: str, limit: int) -> str:
    items = [r for r in rows if r.get("來源類型") == category]
    items.sort(key=lambda x: x.get("發布日期", ""), reverse=True)
    items = items[:limit]
    if not items:
        return ""

    lines = [f"【{label}（最新 {len(items)} 則）】"]
    for r in items:
        title = _safe(r.get("標題", ""), 60)
        source = _safe(r.get("來源網站", "").replace("Google News - ", ""), 15)
        date = (r.get("發布日期", "") or "")[:10]
        lines.append(f"・{title}")
        lines.append(f"  ({source} · {date})")
    lines.append("")
    return "\n".join(lines)


def build_summary(rows: List[Dict], pdf_result: Dict, report_url: str = "") -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    parts = [f"有機肥料市場週報 {today}", ""]

    pdf_block = _section_pdf(pdf_result)
    if pdf_block:
        parts.append(pdf_block)

    activity_block = _section_news(rows, "活動", "觀摩會 / 推廣活動", MAX_ACTIVITY)
    if activity_block:
        parts.append(activity_block)

    news_block = _section_news(rows, "新聞", "其他新聞", MAX_NEWS)
    if news_block:
        parts.append(news_block)

    if report_url:
        parts.append(f"完整報表（72h ~ 永久）：\n{report_url}")

    text = "\n".join(parts)
    # LINE 文字訊息上限 5000 字
    if len(text) > 4900:
        text = text[:4900] + "\n\n…(超過上限，請點報表連結看完整)"
    return text


if __name__ == "__main__":
    sample_pdf = {
        "change_days": 30,
        "recent_added": [
            {"品目": "5-08", "廠牌商品名稱": "嶺先333", "業者名稱": "嶺先興業", "上架日": "2026-05-26"}
        ],
        "recent_violations": [
            {"原品目": "5-13", "廠牌商品名稱": "金大牌有機質肥料", "業者名稱": "金大堆肥",
             "下網日": "2026-05-18", "違規原因": "全磷酐5.8%不符規定"}
        ],
    }
    sample_news = [
        {"來源類型": "活動", "來源網站": "Google News - 觀摩會", "標題": "臺南農改場機械觀摩會", "發布日期": "2026-05-28"},
        {"來源類型": "新聞", "來源網站": "Google News - 有機肥料", "標題": "有機肥技術升級", "發布日期": "2026-05-17"},
    ]
    print(build_summary(sample_news, sample_pdf, "https://files.catbox.moe/test.html"))
