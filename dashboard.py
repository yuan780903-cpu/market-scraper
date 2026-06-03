"""
一頁式 Dashboard HTML 生成器
- Hero（標題 + 統計摘要）
- Taiwan 雨量泡泡圖（Leaflet + CWA 測站座標）
- 4 區雨量數據
- PDF 監控（新違規 / 新上架）
- 節氣施肥重點 + 各區作物
- 新聞 / 活動 / 政府公告 / FB
- 業務充電站

技術：Leaflet (map) + 純 HTML/CSS，無框架
資料：catbox 上傳後永久公開
"""

import html
import json
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import agri_kb
import motivation_picker
import solar_term


def _escape(s) -> str:
    return html.escape(str(s) if s is not None else "")


def _normalize_title(t: str) -> str:
    t = t or ""
    if " - " in t:
        t = t.rsplit(" - ", 1)[0]
    if "｜" in t:
        t = t.rsplit("｜", 1)[0]
    return re.sub(r"[\s\-\|｜:：「」『』《》【】（）()，,。．]", "", t).lower()


def _dedupe_and_sort(items: List[Dict]) -> List[Dict]:
    """去重 + 按標題長度短到長"""
    groups: Dict[str, List[Dict]] = {}
    for r in items:
        k = _normalize_title(r.get("標題", ""))
        if not k:
            continue
        groups.setdefault(k, []).append(r)
    deduped = []
    for grp in groups.values():
        grp.sort(key=lambda x: x.get("發布日期", ""), reverse=True)
        rep = dict(grp[0])
        sources = []
        for r in grp:
            src = r.get("來源網站", "")
            if src and src not in sources:
                sources.append(src)
        rep["_media_sources"] = sources
        deduped.append(rep)
    deduped.sort(key=lambda x: len(x.get("標題", "")))
    return deduped


def _filter_recent(items: List[Dict], days: int = 14) -> List[Dict]:
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
    if len(kept) < 5:
        items_sorted = sorted(items, key=lambda x: x.get("發布日期", ""), reverse=True)
        return items_sorted[:max(5, len(kept))]
    return kept


def _render_news_section(rows: List[Dict], category: str, title: str,
                           accent: str, limit: int = 15) -> str:
    items = [r for r in rows if r.get("來源類型") == category]
    items = _filter_recent(items)
    items = _dedupe_and_sort(items)[:limit]
    if not items:
        return ""

    lis = []
    for r in items:
        t = _escape(r.get("標題", ""))
        link = _escape(r.get("連結", ""))
        sources = r.get("_media_sources") or [r.get("來源網站", "")]
        main = _escape(sources[0].replace("Google News - ", ""))
        extra = f' <span class="media-extra">+{len(sources)-1} 家報導</span>' if len(sources) > 1 else ""
        d = _escape((r.get("發布日期", "") or "")[:10])
        lis.append(f'<li><a href="{link}" target="_blank">{t}</a>'
                   f'<div class="meta">{main}{extra} · {d}</div></li>')
    return f"""
    <section class="card" style="border-left:4px solid {accent}">
      <h2 style="color:{accent}">{_escape(title)}　<span class="count">{len(items)}</span></h2>
      <ul class="news-list">{''.join(lis)}</ul>
    </section>
    """


def _rainfall_level_for_map(past24h: float, past3d: float) -> tuple:
    """回傳 (颜色, 等級文字) 為地圖泡泡用"""
    # 取較嚴重者
    if past3d >= 150 or past24h >= 80:
        return ("#c92a2a", "重災")
    if past3d >= 100 or past24h >= 50:
        return ("#e96b1f", "警戒")
    if past3d >= 50 or past24h >= 30:
        return ("#f0b400", "留意")
    if past24h >= 10 or past3d >= 10:
        return ("#52b788", "輕雨")
    return ("#90c2e7", "微量")


def _render_rainfall_map(rainfall_result: Optional[Dict]) -> str:
    """Leaflet Taiwan 雨量泡泡圖"""
    if not rainfall_result or rainfall_result.get("skipped"):
        return ""
    map_data = rainfall_result.get("map_data", [])
    if not map_data:
        return '<section class="card"><h2>雨量分布</h2><p>無資料</p></section>'

    # 準備泡泡資料（JS 用）
    bubbles = []
    for d in map_data:
        color, level = _rainfall_level_for_map(d["past24h"], d["past3d"])
        bubbles.append({
            "lat": d["lat"], "lon": d["lon"],
            "county": d["county"], "town": d["town"],
            "station": d["station"],
            "past24h": d["past24h"], "past3d": d["past3d"],
            "color": color, "level": level,
        })
    bubbles_json = json.dumps(bubbles, ensure_ascii=False)
    today = rainfall_result.get("today", date.today().isoformat())

    return f"""
    <section class="card card-map">
      <h2 style="color:#1864ab">雨量分布 · 全台即時泡泡圖</h2>
      <div class="map-legend">
        <span class="legend-dot" style="background:#90c2e7"></span> 微量
        <span class="legend-dot" style="background:#52b788"></span> 輕雨
        <span class="legend-dot" style="background:#f0b400"></span> 留意 30+
        <span class="legend-dot" style="background:#e96b1f"></span> 警戒 50+
        <span class="legend-dot" style="background:#c92a2a"></span> 重災 80+
        <span class="legend-note">　·　泡泡大小依 24h 累積雨量</span>
      </div>
      <div id="rainfall-map"></div>
      <p class="meta">資料：中央氣象署 OpenData ({today})　·　{len(bubbles)} 個有雨測站</p>
    </section>
    <script>
      const stations = {bubbles_json};
      const map = L.map('rainfall-map').setView([23.7, 121.0], 7);
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '© OpenStreetMap'
      }}).addTo(map);
      stations.forEach(s => {{
        const radius = Math.max(4, Math.min(30, Math.sqrt(s.past24h + 1) * 2.5));
        L.circleMarker([s.lat, s.lon], {{
          radius: radius,
          color: s.color,
          fillColor: s.color,
          fillOpacity: 0.5,
          weight: 1
        }})
        .bindPopup(`<b>${{s.county}} ${{s.town}}</b><br>` +
                    `站名：${{s.station}}<br>` +
                    `24h：${{s.past24h}} mm<br>` +
                    `3 日：${{s.past3d}} mm<br>` +
                    `<span style="color:${{s.color}};font-weight:bold">${{s.level}}</span>`)
        .addTo(map);
      }});
    </script>
    """


def _render_rainfall_regions(rainfall_result: Optional[Dict]) -> str:
    if not rainfall_result or rainfall_result.get("skipped"):
        return ""
    regions = rainfall_result.get("regions", [])
    if not regions:
        return ""
    rows = []
    for r in regions:
        rows.append(f"""
        <tr>
          <td><strong>{_escape(r['region'])}</strong>（{_escape(r['station'])}）</td>
          <td>{r.get('recent_3days_mm', 0):g} mm</td>
          <td>{r.get('monthly_mm', 0):g} mm</td>
          <td>{r.get('quarterly_mm', 0):g} mm</td>
          <td style="color:{r['monthly_color']};font-weight:bold">{_escape(r['monthly_level'])}</td>
          <td>{_escape(r['monthly_note'])}</td>
        </tr>
        """)
    return f"""
    <section class="card">
      <h2 style="color:#1864ab">4 區雨量數據</h2>
      <table class="data-table">
        <thead><tr><th>區域</th><th>近 3 日</th><th>本月</th><th>本季</th><th>狀態</th><th>業務建議</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
      <p class="meta">月統計期間：{_escape(rainfall_result.get('month_period', ''))}
        · 季統計期間：Q{rainfall_result.get('quarter','')} {_escape(rainfall_result.get('quarter_period', ''))}</p>
    </section>
    """


def _render_pdf_section(pdf_result: Optional[Dict]) -> str:
    if not pdf_result:
        return ""
    added = pdf_result.get("recent_added", [])
    viols = pdf_result.get("recent_violations", [])
    days = pdf_result.get("change_days", 30)

    sections = []
    if viols:
        rows = []
        for v in viols:
            rows.append(f"""
            <tr><td>{_escape(v.get('原品目','?'))}</td>
                <td>{_escape(v.get('登記證字號',''))}</td>
                <td>{_escape(v.get('廠牌商品名稱',''))}</td>
                <td>{_escape(v.get('業者名稱',''))}</td>
                <td>{_escape(v.get('下網日',''))}</td>
                <td>{_escape(v.get('違規原因',''))}</td>
            </tr>""")
        sections.append(f"""
        <h3 style="color:#c92a2a">新違規（共 {len(viols)} 件）</h3>
        <table class="data-table">
          <thead><tr><th>品目</th><th>登記證</th><th>廠牌</th><th>業者</th><th>下網日</th><th>原因</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        """)
    if added:
        rows = []
        for a in added:
            rows.append(f"""
            <tr><td>{_escape(a.get('品目','?'))}</td>
                <td>{_escape(a.get('登記證字號',''))}</td>
                <td>{_escape(a.get('廠牌商品名稱',''))}</td>
                <td>{_escape(a.get('業者名稱',''))}</td>
                <td>{_escape(a.get('上架日',''))}</td>
            </tr>""")
        sections.append(f"""
        <h3 style="color:#2d6a4f">新上架（共 {len(added)} 件）</h3>
        <table class="data-table">
          <thead><tr><th>品目</th><th>登記證</th><th>廠牌</th><th>業者</th><th>上架日</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        """)
    if not sections:
        return ""
    return f"""
    <section class="card">
      <h2 style="color:#6b3300">推薦名單監控（近 {days} 天）</h2>
      {''.join(sections)}
    </section>
    """


def _render_solar_section() -> str:
    today = date.today()
    term, term_start, next_term, next_start = solar_term.current_and_next(today)
    g = agri_kb.guide_for(term)
    days_in = (today - term_start).days
    days_to_next = (next_start - today).days
    regions = "".join(
        f'<li><b style="color:#1864ab">{_escape(r)}</b>　{_escape(c)}</li>'
        for r, c in g.get("regions", {}).items()
    )
    return f"""
    <section class="card">
      <h2 style="color:#6b3300">節氣施肥重點 · {_escape(term)}</h2>
      <p class="meta">{today.isoformat()} · {_escape(term)}已過 {days_in} 天 · 距「{_escape(next_term)}」{days_to_next} 天</p>
      <p><strong>氣候特徵：</strong>{_escape(g.get('climate',''))}</p>
      <h3 style="margin:14px 0 6px;color:#2d6a4f">各區當期作物</h3>
      <ul class="region-list">{regions}</ul>
      <p><strong style="color:#6b3300">施肥重點：</strong>{_escape(g.get('focus',''))}</p>
      <p><strong style="color:#c92a2a">業務建議：</strong>{_escape(g.get('sales',''))}</p>
    </section>
    """


def _render_motivation_section(motivation_picked: Optional[Dict] = None) -> str:
    """業務充電站區塊（金句 + 銷售手段）"""
    if motivation_picked is None:
        return ""
    q = motivation_picked.get("quote", {})
    t = motivation_picked.get("tactic", {})
    if not q or not t:
        return ""
    return f"""
    <section class="card card-motivation">
      <h2 style="color:#7c4dcc">業務充電站</h2>
      <div class="quote-box">
        <div class="quote-tag">本週金句 · {_escape(q.get('id',''))}</div>
        <p class="quote-text">「{_escape(q.get('text',''))}」</p>
        <p class="quote-author">— {_escape(q.get('author',''))}</p>
      </div>
      <div class="tactic-box">
        <div class="tactic-tag">本週銷售手段 · {_escape(t.get('id',''))}</div>
        <h3 class="tactic-title">{_escape(t.get('title',''))}</h3>
        <p class="tactic-body">{_escape(t.get('body',''))}</p>
      </div>
      <p class="meta">金句池 {len(motivation_picker.motivation_kb.QUOTES)} 條／手段池 {len(motivation_picker.motivation_kb.TACTICS)} 條　·　自動輪播不重複</p>
    </section>
    """


def _render_regional_crops_section() -> str:
    today = date.today()
    focus = agri_kb.monthly_focus(today.month)
    focus_html = ""
    if focus:
        focus_html = f"""
        <div class="focus-box">
          <div class="focus-tag">★ 本月基肥焦點區</div>
          <div class="focus-region">{_escape(focus.get('region',''))}</div>
          <div class="focus-crop">{_escape(focus.get('crop',''))}</div>
          <div class="focus-meta">規模：{_escape(focus.get('scale',''))}</div>
          <div class="focus-meta">主推：{_escape(focus.get('products',''))}</div>
          <div class="focus-reason">※ {_escape(focus.get('reason',''))}</div>
        </div>
        """
    blocks = []
    for r in agri_kb.REGIONAL_CROPS:
        crops = "".join(f"<li>{_escape(c)}</li>" for c in r["crops"])
        blocks.append(f"""
        <div class="region-block">
          <h3>{_escape(r['region'])}</h3>
          <ul>{crops}</ul>
          <p class="fert">常用基肥：{_escape(r['common_fertilizer'])}</p>
        </div>
        """)
    return f"""
    <section class="card">
      <h2 style="color:#1864ab">各區作物 / 基肥對照</h2>
      {focus_html}
      <div class="region-grid">{''.join(blocks)}</div>
    </section>
    """


def _render_hero(today: str, pdf_result: Optional[Dict],
                  rainfall_result: Optional[Dict], rows: List[Dict]) -> str:
    pdf_summary = ""
    if pdf_result:
        a = len(pdf_result.get("recent_added", []))
        v = len(pdf_result.get("recent_violations", []))
        pdf_summary = f'<div class="stat"><span class="num">{a}</span><span class="label">新上架</span></div>' \
                      f'<div class="stat"><span class="num">{v}</span><span class="label">新違規</span></div>'
    rain_summary = ""
    if rainfall_result and not rainfall_result.get("skipped"):
        n = len(rainfall_result.get("map_data", []))
        rain_summary = f'<div class="stat"><span class="num">{n}</span><span class="label">有雨測站</span></div>'
    news = len([r for r in rows if r.get("來源類型") == "新聞"])
    act = len([r for r in rows if r.get("來源類型") == "活動"])
    return f"""
    <header class="hero">
      <h1>有機肥料市場週報</h1>
      <p class="hero-date">{_escape(today)}</p>
      <div class="hero-stats">
        {pdf_summary}
        {rain_summary}
        <div class="stat"><span class="num">{act}</span><span class="label">活動</span></div>
        <div class="stat"><span class="num">{news}</span><span class="label">新聞</span></div>
      </div>
    </header>
    """


def generate_email_summary(report_url: str,
                            rows: List[Dict],
                            pdf_result: Optional[Dict] = None,
                            rainfall_result: Optional[Dict] = None) -> str:
    """寄到 Gmail 用的精簡 HTML：重點摘要 + 大按鈕連 dashboard"""
    today = datetime.now().strftime("%Y-%m-%d")

    # 統計
    added = len(pdf_result.get("recent_added", [])) if pdf_result else 0
    viols = len(pdf_result.get("recent_violations", [])) if pdf_result else 0
    news_n = len([r for r in rows if r.get("來源類型") == "新聞"])
    act_n = len([r for r in rows if r.get("來源類型") == "活動"])
    gov_n = len([r for r in rows if r.get("來源類型") == "政府公告"])
    fb_n = len([r for r in rows if r.get("來源類型") == "FB"])

    # 雨量重點
    rain_html = ""
    if rainfall_result and not rainfall_result.get("skipped"):
        warns = [r for r in rainfall_result.get("regions", [])
                 if r.get("monthly_level") in ("留意", "警戒")]
        top_24h = (rainfall_result.get("top_24h_town", []) or
                   rainfall_result.get("top_24h", []))[:1]
        if warns or top_24h:
            warn_lis = "".join(
                f"<li>{_escape(r['region'])} 月累積 {r['monthly_mm']:g} mm — "
                f"<span style='color:{r['monthly_color']}'>{_escape(r['monthly_level'])}</span></li>"
                for r in warns
            )
            top_text = ""
            if top_24h:
                t = top_24h[0]
                loc = f"{t.get('county','')} {t.get('town','')}".strip()
                top_text = f"<p>過去 24 小時最大雨量：<b>{_escape(loc)} {t['mm']:g} mm</b></p>"
            rain_html = f"""
            <h3 style="color:#1864ab;margin:18px 0 6px">雨量警示</h3>
            {top_text}
            <ul>{warn_lis or "<li>各區雨量正常</li>"}</ul>
            """

    # 違規重點（業務最關心）
    viol_html = ""
    if pdf_result and pdf_result.get("recent_violations"):
        rows_html = "".join(
            f"<li>[{_escape(v.get('原品目','?'))}] <b>{_escape(v.get('廠牌商品名稱',''))}</b>"
            f"（{_escape(v.get('業者名稱',''))}）— {_escape(v.get('違規原因',''))}</li>"
            for v in pdf_result["recent_violations"][:5]
        )
        viol_html = f"""
        <h3 style="color:#c92a2a;margin:18px 0 6px">新違規案件（{viols} 件）</h3>
        <ul>{rows_html}</ul>
        """

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;
              color:#1f2933;line-height:1.6;max-width:640px;margin:0 auto;padding:20px;
              background:#f5f6f3">
<div style="background:white;padding:28px;border-radius:14px">
  <h1 style="margin:0;color:#1f3a2e;font-size:24px">有機肥料市場週報</h1>
  <p style="color:#888;margin:4px 0 20px">{_escape(today)}</p>

  <div style="background:#f4f6f8;border-radius:10px;padding:16px;margin:16px 0">
    <strong>本週重點</strong>
    <ul style="margin:8px 0 0;padding-left:22px">
      <li>推薦名單：新上架 <b>{added}</b> 件 ｜ 新違規 <b style="color:#c92a2a">{viols}</b> 件</li>
      <li>觀摩會 / 推廣活動 {act_n} 則</li>
      <li>新聞 {news_n} 則 ｜ 政府公告 {gov_n} 則 ｜ FB {fb_n} 則</li>
    </ul>
  </div>

  {rain_html}
  {viol_html}

  <div style="text-align:center;margin:28px 0">
    <a href="{_escape(report_url)}"
       style="display:inline-block;background:#2d6a4f;color:white;
              padding:14px 32px;border-radius:10px;text-decoration:none;
              font-weight:600;font-size:16px">
      查看完整 Dashboard
    </a>
    <p style="color:#888;font-size:12px;margin:10px 0 0">
      含 Taiwan 雨量泡泡圖、互動表格、節氣施肥、業務充電站等完整資料
    </p>
  </div>

  <p style="color:#aaa;font-size:11px;text-align:center;margin-top:30px;
            border-top:1px solid #eee;padding-top:14px">
    自動爬蟲產出　·　{_escape(today)}
  </p>
</div>
</body></html>"""


def generate_dashboard(rows: List[Dict],
                        pdf_result: Optional[Dict] = None,
                        rainfall_result: Optional[Dict] = None,
                        motivation_picked: Optional[Dict] = None) -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>有機肥料市場週報 · {today[:10]}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif;
    margin: 0; padding: 0; background: #f5f6f3; color: #1f2933;
    line-height: 1.6;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}
  .hero {{
    background: linear-gradient(135deg, #1f3a2e, #4caf73);
    color: white; padding: 36px 28px; border-radius: 14px; margin-bottom: 24px;
  }}
  .hero h1 {{ margin: 0; font-size: 28px; }}
  .hero-date {{ margin: 6px 0 20px; color: #d8efde; }}
  .hero-stats {{ display: flex; flex-wrap: wrap; gap: 16px; }}
  .stat {{
    background: rgba(255,255,255,0.18); padding: 12px 20px;
    border-radius: 10px; min-width: 90px; text-align: center;
  }}
  .stat .num {{ display: block; font-size: 28px; font-weight: 700; }}
  .stat .label {{ display: block; font-size: 12px; color: #cce5d6; }}
  .card {{
    background: white; border-radius: 14px; padding: 24px;
    margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  }}
  .card h2 {{ margin: 0 0 12px; font-size: 20px; }}
  .card h3 {{ margin: 16px 0 8px; font-size: 16px; }}
  .meta {{ font-size: 12px; color: #888; margin-top: 6px; }}
  .count {{
    display: inline-block; background: #e9f5ec; color: #2d6a4f;
    padding: 2px 10px; border-radius: 12px; font-size: 13px; margin-left: 6px;
  }}
  .data-table {{ width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 14px; }}
  .data-table th, .data-table td {{
    border: 1px solid #eee; padding: 8px 10px; text-align: left;
  }}
  .data-table th {{ background: #f4f6f8; color: #555; font-weight: 600; }}
  .data-table tr:nth-child(even) td {{ background: #fafafa; }}
  .news-list {{ list-style: none; padding: 0; margin: 0; }}
  .news-list li {{
    padding: 12px 0; border-bottom: 1px solid #eee;
  }}
  .news-list li:last-child {{ border-bottom: none; }}
  .news-list a {{
    color: #1a5490; text-decoration: none; font-weight: 600; font-size: 15px;
  }}
  .news-list a:hover {{ text-decoration: underline; }}
  .media-extra {{ color: #c92a2a; font-weight: 600; font-size: 12px; }}
  /* Leaflet map */
  #rainfall-map {{ height: 560px; border-radius: 10px; margin-top: 10px; }}
  .map-legend {{
    display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
    font-size: 13px; color: #555; margin-bottom: 10px;
  }}
  .legend-dot {{
    display: inline-block; width: 14px; height: 14px; border-radius: 50%;
    margin-right: 4px; vertical-align: middle;
  }}
  .legend-note {{ color: #888; font-size: 12px; }}
  /* 焦點區 */
  .focus-box {{
    background: #fff6db; border-left: 6px solid #c92a2a;
    padding: 18px; border-radius: 8px; margin: 12px 0;
  }}
  .focus-tag {{
    display: inline-block; background: #c92a2a; color: white;
    padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;
  }}
  .focus-region {{ font-size: 28px; font-weight: 700; color: #6b4800; margin-top: 8px; }}
  .focus-crop {{ font-size: 16px; margin: 4px 0; }}
  .focus-meta {{ font-size: 13px; color: #555; }}
  .focus-reason {{ font-size: 12px; color: #888; margin-top: 8px; }}
  .region-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 14px; margin-top: 12px;
  }}
  .region-block {{
    background: #fafafa; padding: 14px; border-radius: 8px;
  }}
  .region-block h3 {{ margin: 0 0 8px; color: #2d6a4f; }}
  .region-block ul {{ padding-left: 20px; margin: 0; font-size: 13px; }}
  .region-block .fert {{
    font-size: 13px; color: #6b3300; margin-top: 10px;
    border-top: 1px dashed #ddd; padding-top: 8px;
  }}
  .region-list {{ list-style: none; padding: 0; }}
  .region-list li {{ padding: 6px 0; font-size: 14px; }}
  /* 業務充電站 */
  .quote-box {{
    background: #fff9ec; border-left: 4px solid #f0b400;
    padding: 18px 20px; border-radius: 8px; margin: 12px 0;
  }}
  .quote-tag {{
    display: inline-block; background: #f0b400; color: white;
    padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;
  }}
  .quote-text {{
    font-size: 20px; font-weight: 600; color: #3d2800;
    line-height: 1.5; margin: 12px 0;
  }}
  .quote-author {{ text-align: right; color: #8a6500; margin: 0; font-size: 14px; }}
  .tactic-box {{
    background: #eff6ff; border-left: 4px solid #1864ab;
    padding: 18px 20px; border-radius: 8px; margin: 12px 0;
  }}
  .tactic-tag {{
    display: inline-block; background: #1864ab; color: white;
    padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600;
  }}
  .tactic-title {{ font-size: 18px; color: #0e3a6b; margin: 12px 0 8px; }}
  .tactic-body {{ color: #1f2933; line-height: 1.7; }}
  .footer {{
    text-align: center; padding: 24px; color: #888; font-size: 12px;
  }}
  @media (max-width: 640px) {{
    .container {{ padding: 12px 8px; }}
    .card {{ padding: 16px; }}
    .hero {{ padding: 24px 18px; }}
    .hero h1 {{ font-size: 22px; }}
    .data-table {{ font-size: 12px; }}
    .data-table th, .data-table td {{ padding: 6px; }}
    #rainfall-map {{ height: 420px; }}
  }}
</style>
</head>
<body>
<div class="container">
  {_render_hero(today, pdf_result, rainfall_result, rows)}
  {_render_rainfall_map(rainfall_result)}
  {_render_rainfall_regions(rainfall_result)}
  {_render_pdf_section(pdf_result)}
  {_render_solar_section()}
  {_render_regional_crops_section()}
  {_render_motivation_section(motivation_picked)}
  {_render_news_section(rows, "活動", "觀摩會 / 推廣活動", "#1864ab", limit=20)}
  {_render_news_section(rows, "FB", "FB 粉專動態", "#1877f2", limit=20)}
  {_render_news_section(rows, "新聞", "其他新聞", "#1a5490", limit=20)}
  {_render_news_section(rows, "政府公告", "政府公告", "#5b4a00", limit=20)}
  <div class="footer">
    有機肥料市場週報　·　自動爬蟲產出於 {today}
  </div>
</div>
</body>
</html>"""
