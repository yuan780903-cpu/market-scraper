"""
LINE Flex Message 生成器 — Carousel 版（多卡片左右滑）
每個區段（違規 / 上架 / 活動 / 新聞）獨立成 1+ 張卡片，超量自動分頁。
LINE 限制：
- Carousel 最多 12 張 bubble
- 單則訊息 JSON 上限 50KB
- 單張 bubble 元件數約 100 上限
"""

import re
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from config import REPORT_RECENT_DAYS, REPORT_FALLBACK_MIN
import solar_term
import agri_kb

# 每張卡片最多顯示的項目數（控制單卡高度與 component 數）
ITEMS_PER_PAGE = 12
MAX_BUBBLES = 12  # LINE Carousel 硬上限


# ---------- 小工具 ----------

def _text(text: str, **kw) -> Dict:
    base = {"type": "text", "text": text or " ", "wrap": True}
    base.update(kw)
    return base


def _separator(margin: str = "md") -> Dict:
    return {"type": "separator", "margin": margin}


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")


def _header(title: str, subtitle: str = "", color: str = "#2d6a4f") -> Dict:
    contents = [_text(title, color="#ffffff", weight="bold", size="md")]
    if subtitle:
        contents.append(_text(subtitle, color="#ffffff", size="xs"))
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": color,
        "paddingAll": "14px",
        "contents": contents,
    }


def _bubble(header: Dict, body_contents: List[Dict],
            footer: Optional[Dict] = None) -> Dict:
    bubble = {
        "type": "bubble",
        "size": "giga",
        "header": header,
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": body_contents,
        },
    }
    if footer:
        bubble["footer"] = footer
    return bubble


# ---------- 各項目 render ----------

def _render_violation(v: Dict) -> Dict:
    cat = v.get("原品目", "?")
    brand = _truncate(v.get("廠牌商品名稱", ""), 30)
    company = _truncate(v.get("業者名稱", ""), 24)
    reason = _truncate(v.get("違規原因", ""), 60)
    date = v.get("下網日", "")
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "paddingBottom": "6px",
        "contents": [
            _text(f"[{cat}] {brand}", size="sm", weight="bold"),
            _text(f"{date}  ·  {company}", size="xs", color="#888888"),
            _text(reason, size="xs", color="#b54b00"),
        ],
    }


def _render_listing(a: Dict) -> Dict:
    cat = a.get("品目", "?")
    brand = _truncate(a.get("廠牌商品名稱", ""), 32)
    company = _truncate(a.get("業者名稱", ""), 24)
    date = a.get("上架日", "")
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "paddingBottom": "4px",
        "contents": [
            _text(f"[{cat}] {brand}", size="sm", weight="bold"),
            _text(f"{date}  ·  {company}", size="xs", color="#888888"),
        ],
    }


def _render_news(r: Dict, link_color: str) -> Dict:
    title = _truncate(r.get("標題", ""), 56)
    sources = r.get("_media_sources") or [r.get("來源網站", "")]
    main_source = _truncate(sources[0].replace("Google News - ", ""), 16)
    extra = f"  +{len(sources)-1} 家報導" if len(sources) > 1 else ""
    date = (r.get("發布日期", "") or "")[:10]
    link = r.get("連結", "")
    title_node = _text(title, size="sm", weight="bold", color=link_color)
    if link:
        title_node["action"] = {"type": "uri", "uri": link}
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "paddingBottom": "4px",
        "contents": [
            title_node,
            _text(f"{main_source}{extra}  ·  {date}", size="xs", color="#888888"),
        ],
    }


# ---------- 分頁建 bubble ----------

def _paginated_bubbles(
    items: List[Dict],
    title: str,
    color: str,
    item_renderer,
    items_per_page: int = ITEMS_PER_PAGE,
) -> List[Dict]:
    if not items:
        return []
    total = len(items)
    pages = (total + items_per_page - 1) // items_per_page
    bubbles = []
    for page in range(pages):
        chunk = items[page * items_per_page : (page + 1) * items_per_page]
        subtitle = f"共 {total} 筆"
        if pages > 1:
            subtitle += f"  ·  {page + 1}/{pages}"
        body = []
        for it in chunk:
            body.append(item_renderer(it))
        header = _header(title, subtitle, color)
        bubbles.append(_bubble(header, body))
    return bubbles


# ---------- 去重 + 短到長排序 ----------

def _normalize_title(t: str) -> str:
    """正規化標題用於去重：移除媒體後綴、空白、標點"""
    t = t or ""
    # 切掉「 - 媒體名」尾巴
    if " - " in t:
        t = t.rsplit(" - ", 1)[0]
    # 切掉「｜ 來源」尾巴
    if "｜" in t:
        t = t.rsplit("｜", 1)[0]
    # 去除所有空白與常見標點
    t = re.sub(r"[\s\-\|｜:：「」『』《》【】（）()，,。．]", "", t)
    return t.lower()


def _dedupe_by_title(items: List[Dict]) -> List[Dict]:
    """同標題不同媒體合併成 1 筆，記錄所有媒體來源到 _media_sources"""
    groups: Dict[str, List[Dict]] = {}
    for r in items:
        key = _normalize_title(r.get("標題", ""))
        if not key:
            continue
        groups.setdefault(key, []).append(r)

    deduped = []
    for items_in_group in groups.values():
        # 用最新發布日期那則當代表
        items_in_group.sort(key=lambda x: x.get("發布日期", ""), reverse=True)
        rep = dict(items_in_group[0])
        # 蒐集所有不重複的媒體來源
        sources_seen = []
        for r in items_in_group:
            src = r.get("來源網站", "")
            if src and src not in sources_seen:
                sources_seen.append(src)
        rep["_media_sources"] = sources_seen
        deduped.append(rep)
    return deduped


def _sort_short_to_long(items: List[Dict]) -> List[Dict]:
    return sorted(items, key=lambda x: len(x.get("標題", "")))


# ---------- 過濾近 N 天 ----------

def _filter_recent_news(items: List[Dict], days: int = REPORT_RECENT_DAYS) -> List[Dict]:
    cutoff = datetime.now() - timedelta(days=days)
    kept = []
    for r in items:
        d = r.get("發布日期", "")
        if not d:
            continue
        try:
            dt = datetime.strptime(d[:16], "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                dt = datetime.strptime(d[:10], "%Y-%m-%d")
            except ValueError:
                continue
        if dt >= cutoff:
            kept.append(r)
    # fallback: 若太少，回退到最新 N 則不分日期
    if len(kept) < REPORT_FALLBACK_MIN:
        sorted_items = sorted(items, key=lambda x: x.get("發布日期", ""), reverse=True)
        return sorted_items[:max(REPORT_FALLBACK_MIN, len(kept))]
    return kept


# ---------- 節氣施肥重點卡 ----------

def _build_solar_term_bubble() -> Dict:
    today = date.today()
    term, term_start, next_term, next_start = solar_term.current_and_next(today)
    g = agri_kb.guide_for(term)
    days_in = (today - term_start).days
    days_to_next = (next_start - today).days

    body = [
        _text(f"今日 {today.isoformat()}（{term}已過 {days_in} 天｜距「{next_term}」{days_to_next} 天）",
              size="xs", color="#888888"),
        _text(g.get("climate", ""), size="sm", color="#555555", margin="sm"),
        _separator(),
        _text("各區當期作物", weight="bold", size="sm", color="#2d6a4f", margin="md"),
    ]
    for region, crops in g.get("regions", {}).items():
        body.append({
            "type": "box",
            "layout": "baseline",
            "spacing": "sm",
            "contents": [
                _text(region, flex=2, size="xs", color="#1864ab", weight="bold"),
                _text(crops, flex=5, size="xs", color="#333333", wrap=True),
            ],
        })

    body.append(_separator(margin="md"))
    if g.get("focus"):
        body.append(_text("施肥重點", weight="bold", size="sm", color="#6b3300", margin="md"))
        body.append(_text(g["focus"], size="sm", color="#333333"))
    if g.get("sales"):
        body.append(_text("業務建議", weight="bold", size="sm", color="#c92a2a", margin="md"))
        body.append(_text(g["sales"], size="sm", color="#333333"))

    body.append(_separator(margin="md"))
    body.append(_text("※ 業界常識參考，非即時銷售數據", size="xs", color="#aaaaaa", margin="sm"))

    header = _header(f"節氣施肥重點 · {term}", today.isoformat(), "#6b3300")
    return _bubble(header, body)


# ---------- 區域作物 / 基肥對照卡 ----------

def _build_regional_crops_bubble() -> Dict:
    body = [_text("全台主要作物面積與常用基肥對照", size="xs", color="#888888")]

    for r in agri_kb.REGIONAL_CROPS:
        body.append(_separator(margin="md"))
        body.append(_text(r["region"], weight="bold", size="sm", color="#2d6a4f", margin="md"))
        for crop in r["crops"]:
            body.append(_text(f"  · {crop}", size="xs", color="#333333"))
        body.append(_text(f"常用基肥：{r['common_fertilizer']}",
                          size="xs", color="#6b3300", wrap=True, margin="sm"))

    body.append(_separator(margin="md"))
    body.append(_text("※ 面積為農業統計年報概略值，年度更新",
                      size="xs", color="#aaaaaa", margin="sm"))

    header = _header("各區作物面積 / 基肥對照", "業務區域參考", "#1864ab")
    return _bubble(header, body)


# ---------- 主入口 ----------

def build_flex(rows: List[Dict], pdf_result: Dict, report_url: str = "") -> Dict:
    today = datetime.now().strftime("%Y-%m-%d")
    bubbles: List[Dict] = []

    # 1. 封面摘要卡
    cover_body = [_text(f"產出時間：{today}", size="sm", color="#555555")]
    if pdf_result:
        days = pdf_result.get("change_days", 30)
        cover_body.append(_separator())
        cover_body.append(_text("推薦名單監控", weight="bold", size="md", color="#6b3300"))
        cover_body.append(_text(
            f"近 {days} 天：新上架 {len(pdf_result.get('recent_added', []))} 件 "
            f"｜ 新違規 {len(pdf_result.get('recent_violations', []))} 件",
            size="sm", color="#333333"))
        pdf_metas = pdf_result.get("pdf_results", [])
        if pdf_metas:
            cover_body.append(_separator())
            cover_body.append(_text("各品目資料更新日", weight="bold", size="sm"))
            for m in pdf_metas:
                meta = m.get("meta", {})
                d = meta.get("資料更新日期")
                d_str = d.isoformat() if hasattr(d, "isoformat") else (d or "未知")
                count = len(m.get("products", []))
                cover_body.append(_text(
                    f"・{meta.get('品目', '?')}  {d_str}  ({count} 件)",
                    size="xs", color="#555555"))

    cover_header = _header("有機肥料市場週報", today, "#2d6a4f")
    bubbles.append(_bubble(cover_header, cover_body))

    # 註：節氣施肥重點 + 區域作物 改用圖片訊息推送（見 weekly_line_push）

    # 2. 新違規卡（紅色 header）
    if pdf_result:
        viols = pdf_result.get("recent_violations", [])
        bubbles.extend(_paginated_bubbles(
            viols, "新違規案件", "#c92a2a", _render_violation,
        ))

    # 3. 新上架卡（綠色 header）
    if pdf_result:
        added = pdf_result.get("recent_added", [])
        bubbles.extend(_paginated_bubbles(
            added, "新上架", "#2d6a4f", _render_listing,
        ))

    # 4. 活動卡（藍色 header）— 去重 + 短到長排序
    activities = [r for r in rows if r.get("來源類型") == "活動"]
    activities = _filter_recent_news(activities)
    activities = _dedupe_by_title(activities)
    activities = _sort_short_to_long(activities)
    bubbles.extend(_paginated_bubbles(
        activities, "觀摩會 / 推廣活動", "#1864ab",
        lambda x: _render_news(x, "#1864ab"),
    ))

    # 4.5 FB 粉專貼文卡（FB 藍）— 限制最多 24 筆（2 張卡），其餘看完整報表
    fb_items = [r for r in rows if r.get("來源類型") == "FB"]
    fb_items = _filter_recent_news(fb_items)
    fb_items.sort(key=lambda x: x.get("發布日期", ""), reverse=True)
    fb_capped = fb_items[:24]
    bubbles.extend(_paginated_bubbles(
        fb_capped, "FB 粉專動態", "#1877f2",
        lambda x: _render_news(x, "#1877f2"),
    ))

    # 5. 新聞卡（深藍 header）— 去重 + 短到長排序
    news = [r for r in rows if r.get("來源類型") == "新聞"]
    news = _filter_recent_news(news)
    news = _dedupe_by_title(news)
    news = _sort_short_to_long(news)
    bubbles.extend(_paginated_bubbles(
        news, "其他新聞", "#1a5490",
        lambda x: _render_news(x, "#1a5490"),
    ))

    # 6. 政府公告卡（若有）
    gov = [r for r in rows if r.get("來源類型") == "政府公告"]
    gov = _filter_recent_news(gov)
    gov.sort(key=lambda x: x.get("發布日期", ""), reverse=True)
    bubbles.extend(_paginated_bubbles(
        gov, "政府公告", "#5c4a00",
        lambda x: _render_news(x, "#5c4a00"),
    ))

    # 硬上限 12
    if len(bubbles) > MAX_BUBBLES:
        bubbles = bubbles[:MAX_BUBBLES]
        bubbles[-1]["body"]["contents"].append(_text(
            "…後續內容請見完整報表", size="xs", color="#888888", margin="md",
        ))

    # 把 footer 按鈕加到「最後一張卡」
    if bubbles and report_url:
        bubbles[-1]["footer"] = {
            "type": "box",
            "layout": "vertical",
            "contents": [{
                "type": "button",
                "style": "primary",
                "color": "#2d6a4f",
                "height": "sm",
                "action": {"type": "uri", "label": "看完整報表", "uri": report_url},
            }],
        }

    return {
        "type": "flex",
        "altText": f"有機肥料市場週報 {today}",
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }


if __name__ == "__main__":
    import json
    sample_pdf = {
        "change_days": 30,
        "recent_added": [
            {"品目": "5-08", "廠牌商品名稱": "嶺先 333", "業者名稱": "嶺先興業", "上架日": "2026-05-26"},
            {"品目": "5-09", "廠牌商品名稱": "春成牌省閣勇", "業者名稱": "成友", "上架日": "2026-04-29"},
        ],
        "recent_violations": [
            {"原品目": "5-13", "廠牌商品名稱": "金大牌有機質肥料", "業者名稱": "金大堆肥共同處理場",
             "下網日": "2026-05-18", "違規原因": "全磷酐 5.8% 不符規定"}
        ],
        "pdf_results": [
            {"meta": {"品目": "5-08", "資料更新日期": "2026-05-26"}, "products": [{}] * 27},
            {"meta": {"品目": "5-09", "資料更新日期": "2026-05-26"}, "products": [{}] * 127},
        ],
    }
    sample_rows = [
        {"來源類型": "活動", "來源網站": "Google News - 觀摩會", "標題": "臺南農改場機械觀摩會",
         "發布日期": "2026-05-28", "連結": "https://example.com/1"},
        {"來源類型": "新聞", "來源網站": "Google News - 有機肥料", "標題": "屏東農科有機肥廠動土",
         "發布日期": "2026-05-17", "連結": "https://example.com/2"},
    ]
    msg = build_flex(sample_rows, sample_pdf, "https://files.catbox.moe/test.html")
    print(json.dumps(msg, ensure_ascii=False, indent=2)[:3000])
    print("...")
    j = json.dumps(msg, ensure_ascii=False)
    print(f"\n總 bubble 數: {len(msg['contents']['contents'])}")
    print(f"JSON 大小: {len(j)} bytes (上限 50KB)")
