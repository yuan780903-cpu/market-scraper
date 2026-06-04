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
import motivation_picker

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

    # 避免「最後一張只有 1-2 筆」變成孤兒卡（浪費 LINE 50KB 額度）：
    # 若最後一頁 chunk 太短，併回前一頁，少出一張卡
    if pages > 1:
        last_chunk_size = total - (pages - 1) * items_per_page
        if last_chunk_size <= 2:
            pages -= 1  # 只用 pages-1 張卡，最後一張裝多於 items_per_page 筆
    bubbles = []
    for page in range(pages):
        if page == pages - 1:
            # 最後一張裝完所有剩餘
            chunk = items[page * items_per_page :]
        else:
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


# ---------- 節氣施肥重點 Flex bubble ----------

REGION_CHIP_COLORS = {
    "北部": ("#dfeefc", "#1864ab"),
    "中部": ("#e6f4d7", "#3b6e0e"),
    "南部": ("#fde0d0", "#a3370b"),
    "東部": ("#f0e0fa", "#5e2c8f"),
}


def _build_solar_term_bubble(today: Optional[date] = None) -> Dict:
    if today is None:
        today = date.today()
    term, term_start, next_term, next_start = solar_term.current_and_next(today)
    g = agri_kb.guide_for(term)
    days_in = (today - term_start).days
    days_to_next = (next_start - today).days

    body = [
        _text(f"{today.isoformat()}　·　{term}已過 {days_in} 天　·　距「{next_term}」{days_to_next} 天",
              size="xs", color="#888888"),
    ]
    # 氣候特徵
    if g.get("climate"):
        body.append(_separator(margin="md"))
        body.append(_text("氣候特徵", weight="bold", size="sm", color="#6b3300"))
        body.append(_text(g["climate"], size="sm", color="#1f2933", wrap=True))

    # 各區當期作物（用 horizontal 而非 baseline，wrap 才會生效）
    if g.get("regions"):
        body.append(_separator(margin="md"))
        body.append(_text("各區當期作物", weight="bold", size="sm", color="#2d6a4f"))
        for region, crops in g["regions"].items():
            bg, fg = REGION_CHIP_COLORS.get(region, ("#eeeeee", "#333333"))
            row = {
                "type": "box",
                "layout": "horizontal",
                "spacing": "sm",
                "margin": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": bg,
                        "cornerRadius": "8px",
                        "paddingAll": "4px",
                        "width": "60px",
                        "contents": [_text(region, size="xs", weight="bold",
                                           color=fg, align="center")],
                    },
                    _text(crops, size="sm", color="#1f2933", wrap=True, flex=5),
                ],
            }
            body.append(row)

    # 施肥重點
    if g.get("focus"):
        body.append(_separator(margin="md"))
        body.append(_text("施肥重點", weight="bold", size="sm", color="#6b3300"))
        body.append(_text(g["focus"], size="sm", color="#1f2933", wrap=True))

    # 業務建議
    if g.get("sales"):
        body.append(_separator(margin="md"))
        body.append(_text("業務建議 · 本期主推", weight="bold", size="sm", color="#c92a2a"))
        body.append(_text(g["sales"], size="sm", color="#1f2933", wrap=True))

    body.append(_separator(margin="lg"))
    body.append(_text("※ 業界常識參考，非即時銷售數據",
                       size="xxs", color="#aaaaaa", margin="sm"))

    header = _header(f"節氣施肥重點 · {term}", today.isoformat(), "#8a5a00")
    return _bubble(header, body)


# ---------- 各區作物 / 基肥對照 Flex bubble ----------

def _build_regional_crops_bubble(today: Optional[date] = None) -> Dict:
    if today is None:
        today = date.today()
    focus = agri_kb.monthly_focus(today.month)

    body = []

    # 本月焦點區 highlight
    if focus:
        focus_box = {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#fff6db",
            "cornerRadius": "8px",
            "paddingAll": "12px",
            "spacing": "xs",
            "contents": [
                _text("★ 本月基肥焦點區", size="xs", weight="bold",
                      color="#c92a2a"),
                _text(focus.get("region", "—"), size="xl",
                      weight="bold", color="#6b4800", margin="sm"),
                _text(focus.get("crop", ""), size="sm",
                      color="#1f2933", wrap=True),
            ],
        }
        if focus.get("scale"):
            focus_box["contents"].append(
                _text(f"規模：{focus['scale']}", size="xs",
                      color="#52616b", wrap=True)
            )
        if focus.get("products"):
            focus_box["contents"].append(
                _text(f"主推：{focus['products']}", size="xs",
                      color="#52616b", wrap=True)
            )
        body.append(focus_box)
        if focus.get("reason"):
            body.append(_text(f"※ {focus['reason']}",
                              size="xxs", color="#888888", wrap=True, margin="sm"))

    # 四區
    body.append(_separator(margin="lg"))
    body.append(_text("四區作物面積與基肥對照",
                       weight="bold", size="sm", color="#1864ab"))

    for r in agri_kb.REGIONAL_CROPS:
        short = r["region"].split(" ")[0]
        bg, fg = REGION_CHIP_COLORS.get(short, ("#eeeeee", "#333333"))
        region_block = {
            "type": "box",
            "layout": "vertical",
            "margin": "md",
            "spacing": "xs",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "vertical",
                            "backgroundColor": bg,
                            "cornerRadius": "8px",
                            "paddingAll": "4px",
                            "width": "60px",
                            "contents": [_text(short, size="xs", weight="bold",
                                               color=fg, align="center")],
                        },
                        _text(r["region"].split(" ", 1)[1] if " " in r["region"] else "",
                              size="xs", color="#888888", flex=5, margin="sm",
                              gravity="center"),
                    ],
                },
            ],
        }
        for crop in r["crops"]:
            region_block["contents"].append(
                _text(f"· {crop}", size="xs", color="#1f2933", wrap=True)
            )
        region_block["contents"].append(
            _text(f"常用基肥：{r['common_fertilizer']}",
                  size="xs", color="#6b3300", wrap=True, margin="xs")
        )
        body.append(region_block)

    body.append(_separator(margin="lg"))
    body.append(_text("※ 面積為農業統計年報概略值",
                       size="xxs", color="#aaaaaa", margin="sm"))

    header = _header("各區作物 / 基肥對照",
                      f"{today.year} 年 {today.month} 月　·　業務區域戰情",
                      "#1864ab")
    return _bubble(header, body)


# ---------- 業務充電站 Flex bubble ----------

def _build_motivation_bubble(today: Optional[date] = None,
                              mark_used: bool = True,
                              picked: Optional[Dict] = None) -> Dict:
    if today is None:
        today = date.today()
    if picked is None:
        picked = motivation_picker.pick_quote_and_tactic(mark_used=mark_used)
    quote = picked["quote"]
    tactic = picked["tactic"]

    body = []

    # 金句區（金黃 panel）
    quote_box = {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": "#fff9ec",
        "cornerRadius": "8px",
        "paddingAll": "14px",
        "spacing": "sm",
        "contents": [
            _text(f"本週金句　·　{quote['id']}",
                  size="xxs", weight="bold", color="#a07a00"),
            _text(f"「{quote['text']}」",
                  size="md", weight="bold", color="#3d2800", wrap=True),
            _text(f"— {quote['author']}",
                  size="xs", color="#8a6500", align="end"),
        ],
    }
    body.append(quote_box)

    # 銷售手段區
    body.append(_separator(margin="lg"))
    body.append(_text(f"本週銷售手段　·　{tactic['id']}",
                       size="xxs", weight="bold", color="#1864ab"))
    body.append(_text(tactic["title"],
                       size="md", weight="bold", color="#0e3a6b", margin="xs"))
    body.append(_text(tactic["body"],
                       size="sm", color="#1f2933", wrap=True, margin="sm"))

    body.append(_separator(margin="lg"))
    body.append(_text(
        f"※ 金句池 {len(motivation_picker.motivation_kb.QUOTES)} 條／手段池 "
        f"{len(motivation_picker.motivation_kb.TACTICS)} 條　·　自動輪播不重複",
        size="xxs", color="#aaaaaa", margin="sm"))

    header = _header("業務充電站", f"{today.isoformat()}　·　本週金句 + 銷售手段",
                      "#7c4dcc")
    return _bubble(header, body)


# ---------- 雨量警示 Flex bubble ----------

def _build_rainfall_bubble(rainfall_result: Dict) -> Optional[Dict]:
    """雨量警示卡：4 區月/季累積 + 業務判讀"""
    if not rainfall_result or rainfall_result.get("skipped"):
        return None
    regions = rainfall_result.get("regions", [])
    if not regions:
        return None

    today = rainfall_result.get("today", date.today().isoformat())
    q = rainfall_result.get("quarter", 1)

    body = [
        _text(f"{today}　·　Q{q} 至今累積",
              size="xs", color="#888888"),
        _separator(margin="md"),
    ]

    # 表頭
    body.append({
        "type": "box",
        "layout": "horizontal",
        "spacing": "sm",
        "contents": [
            _text("區域", size="xs", color="#888888", weight="bold", flex=2),
            _text("近3日", size="xs", color="#888888", weight="bold", flex=2, align="end"),
            _text("本月", size="xs", color="#888888", weight="bold", flex=2, align="end"),
            _text("本季", size="xs", color="#888888", weight="bold", flex=2, align="end"),
        ],
    })

    # 每區一列
    for r in regions:
        r3 = r.get("recent_3days_mm", 0)
        r3_color = "#c92a2a" if r3 > 100 else ("#a05c00" if r3 > 50 else "#52616b")
        body.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "margin": "sm",
            "contents": [
                _text(r["region"], size="sm", weight="bold", color="#1f2933", flex=2),
                _text(f"{r3:g} mm", size="sm",
                      color=r3_color, flex=2, align="end"),
                _text(f"{r['monthly_mm']:g} mm", size="sm",
                      color=r["monthly_color"], flex=2, align="end"),
                _text(f"{r['quarterly_mm']:g} mm", size="sm",
                      color="#c92a2a" if r["quarterly_alert"] else "#52616b",
                      flex=2, align="end"),
            ],
        })

    body.append(_separator(margin="md"))

    # 業務判讀（針對警戒區）
    warnings = [r for r in regions if r["monthly_level"] in ("留意", "警戒")]
    if warnings:
        body.append(_text("業務影響判讀", weight="bold", size="sm", color="#c92a2a"))
        for r in warnings:
            body.append(_text(
                f"・{r['region']}（{r['station']}）月累積 {r['monthly_mm']:g} mm — {r['monthly_note']}",
                size="xs", color="#1f2933", wrap=True, margin="sm"))
    else:
        body.append(_text("各區雨量正常，施肥/出貨皆可順行。",
                          size="sm", color="#2d6a4f"))

    # 影響閾值對照表（壓縮版）
    body.append(_separator(margin="md"))
    body.append(_text("雨量對肥料銷量影響", weight="bold", size="xs", color="#1864ab"))

    # 精簡閾值表（每段最關鍵 3 條，總共 9 條控制 JSON 大小）
    threshold_table = [
        ("短期單日", [
            ("<30 mm", "可施肥", "#2d6a4f"),
            ("30-80", "養分流失，當日施肥白費", "#a05c00"),
            (">80 mm", "禁施，農路積水", "#c92a2a"),
        ]),
        ("連續 3-5 天", [
            ("<50 mm", "田面 OK，正常出貨", "#2d6a4f"),
            ("50-150", "泥濘，影響出貨", "#a05c00"),
            (">150 mm", "田面積水", "#c92a2a"),
        ]),
        ("月累積（銷量）", [
            ("<150 mm", "施肥黃金期，銷量旺", "#2d6a4f"),
            ("150-300", "普通，看空檔", "#52616b"),
            ("300-500", "銷量下滑 20-30%", "#a05c00"),
            (">500 mm", "銷量低谷", "#c92a2a"),
        ]),
    ]
    for section_title, rows in threshold_table:
        body.append(_text(section_title, size="xxs", weight="bold",
                          color="#52616b", margin="sm"))
        for rng, note, c in rows:
            body.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    _text(rng, size="xxs", color=c, weight="bold", flex=3),
                    _text(note, size="xxs", color="#1f2933", flex=5, wrap=True),
                ],
            })

    # 資料來源 + 統計期間
    body.append(_separator(margin="md"))
    month_period = rainfall_result.get("month_period", "")
    quarter_period = rainfall_result.get("quarter_period", "")
    body.append(_text(f"月統計期間：{month_period}",
                       size="xxs", color="#888888"))
    body.append(_text(f"季統計期間：Q{q}　{quarter_period}",
                       size="xxs", color="#888888"))
    body.append(_text("資料來源：中央氣象署 OpenData",
                       size="xxs", color="#888888"))
    body.append(_text("※ 月/季累積為本程式逐日累積，依執行頻率而定",
                       size="xxs", color="#aaaaaa"))

    header = _header("雨量警示 · 區域出貨判讀",
                      f"{today}　·　4 區代表站",
                      "#1864ab")
    return _bubble(header, body)


# ---------- 全台縣市重災排名 Flex bubble ----------

def _build_rainfall_ranking_bubble(rainfall_result: Dict) -> Optional[Dict]:
    """全台雨量排名：縣市 + 鄉鎮 兩層"""
    if not rainfall_result or rainfall_result.get("skipped"):
        return None
    top_24h = rainfall_result.get("top_24h", []) or []
    top_3days = rainfall_result.get("top_3days", []) or []
    top_24h_town = rainfall_result.get("top_24h_town", []) or []
    top_3days_town = rainfall_result.get("top_3days_town", []) or []
    if not (top_24h or top_24h_town):
        return None

    today = rainfall_result.get("today", date.today().isoformat())

    def _level_label(mm, is_3days=False):
        if is_3days:
            if mm >= 150: return ("田面積水", "#c92a2a")
            if mm >= 100: return ("全面影響", "#c25400")
            if mm >= 50: return ("黏土泥濘", "#a05c00")
            return ("正常", "#2d6a4f")
        else:
            if mm >= 80: return ("豪雨警戒", "#c92a2a")
            if mm >= 50: return ("不宜施肥", "#c25400")
            if mm >= 30: return ("養分流失", "#a05c00")
            if mm >= 10: return ("輕雨", "#52616b")
            return ("正常", "#2d6a4f")

    def _county_row(i, r, is_3days):
        level, color = _level_label(r["mm"], is_3days)
        return {
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                _text(f"{i}", size="sm", color="#1f2933", weight="bold", flex=1),
                _text(r["county"], size="sm", color="#1f2933", flex=4, wrap=True),
                _text(f"{r['mm']:g} mm", size="sm", color=color, flex=3, align="end", weight="bold"),
                _text(level, size="xxs", color=color, flex=3, align="center"),
            ],
        }

    def _town_row(i, r, is_3days):
        level, color = _level_label(r["mm"], is_3days)
        location = f"{r['county']} {r['town']}"
        return {
            "type": "box", "layout": "horizontal", "margin": "xs",
            "contents": [
                _text(f"{i}", size="sm", color="#1f2933", weight="bold", flex=1),
                _text(location, size="xs", color="#1f2933", flex=5, wrap=True),
                _text(f"{r['mm']:g} mm", size="sm", color=color, flex=3, align="end", weight="bold"),
                _text(level, size="xxs", color=color, flex=3, align="center"),
            ],
        }

    body = [
        _text(f"{today}　·　即時排名（鄉鎮級，含縣市）",
              size="xs", color="#888888"),
    ]

    # ===== 過去 24 小時 鄉鎮 TOP 5 =====
    body.append(_separator(margin="md"))
    body.append(_text("過去 24 小時　鄉鎮 TOP 5",
                       weight="bold", size="sm", color="#c92a2a"))
    body.append({
        "type": "box", "layout": "horizontal",
        "contents": [
            _text("#", size="xxs", color="#888888", weight="bold", flex=1),
            _text("縣市 / 鄉鎮", size="xxs", color="#888888", weight="bold", flex=5),
            _text("雨量", size="xxs", color="#888888", weight="bold", flex=3, align="end"),
            _text("狀態", size="xxs", color="#888888", weight="bold", flex=3, align="center"),
        ],
    })
    for i, r in enumerate(top_24h_town, 1):
        body.append(_town_row(i, r, False))

    # ===== 過去 3 日 鄉鎮 TOP 5 =====
    body.append(_separator(margin="md"))
    body.append(_text("過去 3 日累積　鄉鎮 TOP 5",
                       weight="bold", size="sm", color="#c92a2a"))
    body.append({
        "type": "box", "layout": "horizontal",
        "contents": [
            _text("#", size="xxs", color="#888888", weight="bold", flex=1),
            _text("縣市 / 鄉鎮", size="xxs", color="#888888", weight="bold", flex=5),
            _text("雨量", size="xxs", color="#888888", weight="bold", flex=3, align="end"),
            _text("狀態", size="xxs", color="#888888", weight="bold", flex=3, align="center"),
        ],
    })
    for i, r in enumerate(top_3days_town, 1):
        body.append(_town_row(i, r, True))

    body.append(_separator(margin="md"))
    body.append(_text("資料來源：中央氣象署 OpenData（全國雨量站）",
                       size="xxs", color="#888888"))
    body.append(_text("※ 月/季鄉鎮累積排名需逐日資料，後續擴充",
                       size="xxs", color="#aaaaaa"))

    header = _header("全台鄉鎮重災排名",
                      f"{today}　·　即時雨量熱區",
                      "#c92a2a")
    return _bubble(header, body)


# ---------- 主入口 ----------

def build_flex(rows: List[Dict], pdf_result: Dict, report_url: str = "",
                mark_motivation_used: bool = True,
                rainfall_result: Optional[Dict] = None,
                motivation_picked: Optional[Dict] = None) -> Dict:
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

    # 1.2 節氣施肥重點 Flex 卡（取代之前的圖片）
    bubbles.append(_build_solar_term_bubble())

    # 1.4 各區作物 / 基肥對照 Flex 卡
    bubbles.append(_build_regional_crops_bubble())

    # 1.5 雨量警示卡（4 區）
    rb = _build_rainfall_bubble(rainfall_result)
    if rb:
        bubbles.append(rb)

    # 1.6 全台縣市重災排名卡
    rrb = _build_rainfall_ranking_bubble(rainfall_result)
    if rrb:
        bubbles.append(rrb)

    # 1.6 業務充電站 Flex 卡（金句 + 銷售手段，自動輪播不重複）
    bubbles.append(_build_motivation_bubble(mark_used=mark_motivation_used,
                                              picked=motivation_picked))

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
    def _attach_footer(bubble_list):
        if bubble_list and report_url:
            bubble_list[-1]["footer"] = {
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

    _attach_footer(bubbles)

    payload = {
        "type": "flex",
        "altText": f"有機肥料市場週報 {today}",
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }

    # === Size guard：LINE Flex carousel JSON 上限 50 KB ===
    # 預留 buffer（49000 bytes）。若超過，從尾端砍 bubbles 並把 footer 移到新的最後一張
    import json as _json
    MAX_BYTES = 49000

    def _size():
        return len(_json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    if _size() > MAX_BYTES:
        # 先記下 footer 要保留
        had_footer = bubbles and "footer" in bubbles[-1]
        if had_footer:
            bubbles[-1].pop("footer", None)

        # 從尾端砍 bubbles（保留至少 3 張：封面 + 節氣 + 區域作物）
        while len(bubbles) > 3 and _size() > MAX_BYTES:
            bubbles.pop()

        # 如果還是超：從最後一張砍 body items（保留 header + 至少 3 行）
        while bubbles and _size() > MAX_BYTES:
            last_body = bubbles[-1].get("body", {}).get("contents", [])
            if len(last_body) > 3:
                last_body.pop()
            else:
                bubbles.pop()
                if len(bubbles) <= 3:
                    break

        if had_footer:
            _attach_footer(bubbles)

        print(f"[Flex] 已自動瘦身：carousel 縮到 {len(bubbles)} 張卡、{_size()} bytes")

    return payload


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
