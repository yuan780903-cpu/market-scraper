"""
HTML 報表生成
- 篩近 N 日（config 設定）
- 資料太少時自動 fallback 顯示最新 N 則
- 按來源類型分區（政府/新聞），區內按關鍵字分組
- 內嵌 CSS，可直接當 email 內文
"""

import html
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from config import REPORT_RECENT_DAYS, REPORT_FALLBACK_MIN, REPORT_FALLBACK_TOP


def _parse_date(s: str):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _filter_recent(rows: List[Dict], days: int):
    cutoff = datetime.now() - timedelta(days=days)
    kept = []
    for r in rows:
        d = _parse_date(r.get("發布日期", ""))
        if d is None or d >= cutoff:
            kept.append(r)
    return kept


def _sort_by_date_desc(rows: List[Dict]) -> List[Dict]:
    def key(r):
        d = _parse_date(r.get("發布日期", ""))
        return d or datetime.min
    return sorted(rows, key=key, reverse=True)


def _render_item(r: Dict) -> str:
    title = html.escape(r.get("標題", ""))
    link = html.escape(r.get("連結", ""))
    date = html.escape(r.get("發布日期", "") or "—")
    source = html.escape(r.get("來源網站", ""))

    return f"""
    <div class="item">
      <a href="{link}" class="title" target="_blank">{title}</a>
      <div class="meta">{source} · {date}</div>
    </div>
    """


def _render_grouped(rows: List[Dict]) -> str:
    grouped = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[r.get("來源類型", "其他")][r.get("命中關鍵字", "其他")].append(r)

    sections_html = []
    for source_type in ("活動", "政府公告", "新聞", "其他"):
        if source_type not in grouped:
            continue
        kw_blocks = []
        for kw, items in sorted(grouped[source_type].items(), key=lambda x: -len(x[1])):
            items_sorted = _sort_by_date_desc(items)
            items_html = "".join(_render_item(r) for r in items_sorted)
            kw_blocks.append(f"""
            <div class="kw-block">
              <h3>{html.escape(kw)} <span class="count">{len(items)}</span></h3>
              {items_html}
            </div>
            """)
        sections_html.append(f"""
        <section>
          <h2>{html.escape(source_type)}</h2>
          {''.join(kw_blocks)}
        </section>
        """)
    return "".join(sections_html)


def _render_pdf_meta_header(pdf_results: List[Dict]) -> str:
    """顯示每個 PDF 的品目 + 資料更新日期 + 筆數"""
    rows = []
    for r in pdf_results:
        meta = r.get("meta", {})
        cat = meta.get("品目", "")
        d = meta.get("資料更新日期")
        d_str = d.isoformat() if hasattr(d, "isoformat") else (d or "未知")
        count = len(r.get("products", []))
        rows.append(f"""
          <tr>
            <td class="cat">{html.escape(cat)}</td>
            <td>{html.escape(d_str)}</td>
            <td class="num">{count}</td>
          </tr>
        """)
    return f"""
    <table class="meta-table">
      <thead><tr><th>品目</th><th>資料更新日期</th><th>產品數</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


def _group_by_category(items: List[Dict]) -> Dict[str, List[Dict]]:
    groups: Dict[str, List[Dict]] = {}
    for p in items:
        groups.setdefault(p.get("品目", "其他"), []).append(p)
    return groups


def _render_listing_table(items: List[Dict], date_field: str, date_label: str,
                          show_reason: bool = False, show_category: bool = False) -> str:
    if not items:
        return ""

    sorted_items = sorted(items, key=lambda x: x.get(date_field, ""), reverse=True)
    rows = []
    for p in sorted_items:
        cat_td = (
            f"<td class='cat-cell'>{html.escape(p.get('原品目', '未知'))}</td>"
            if show_category else ""
        )
        reason_td = (
            f"<td class='reason'>{html.escape(p.get('違規原因', ''))}</td>"
            if show_reason else ""
        )
        rows.append(f"""
        <tr>
          <td class="date">{html.escape(p.get(date_field, ''))}</td>
          {cat_td}
          <td class="lic">{html.escape(p.get('登記證字號', ''))}</td>
          <td>{html.escape(p.get('廠牌商品名稱', ''))}</td>
          <td>{html.escape(p.get('業者名稱', ''))}</td>
          {reason_td}
        </tr>
        """)
    cat_th = "<th>肥料品目</th>" if show_category else ""
    reason_th = "<th>違規原因</th>" if show_reason else ""
    return f"""
    <table class="pdf-table">
      <thead><tr><th>{date_label}</th>{cat_th}<th>登記證字號</th><th>廠牌/商品</th><th>業者</th>{reason_th}</tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


def _render_change_block(title: str, items: List[Dict], date_field: str,
                          date_label: str, show_reason: bool = False,
                          show_category: bool = False, group_key: str = "品目") -> str:
    if not items:
        return f"<h3>{html.escape(title)}（0 筆）</h3><p class='empty'>無</p>"

    groups: Dict[str, List[Dict]] = {}
    for p in items:
        groups.setdefault(p.get(group_key, "其他"), []).append(p)

    blocks = []
    for cat in sorted(groups.keys()):
        cat_items = groups[cat]
        blocks.append(f"""
        <h4>{html.escape(cat)} <span class="count">{len(cat_items)}</span></h4>
        {_render_listing_table(cat_items, date_field, date_label, show_reason, show_category)}
        """)
    return f"<h3>{html.escape(title)}（共 {len(items)} 筆）</h3>{''.join(blocks)}"


def _render_pdf_changes(pdf_result: Dict) -> str:
    if pdf_result is None:
        return ""

    pdf_results = pdf_result.get("pdf_results", [])
    products = pdf_result.get("products", [])
    recent_added = pdf_result.get("recent_added", [])
    recent_removed = pdf_result.get("recent_removed", [])
    recent_violations = pdf_result.get("recent_violations", [])
    change_days = pdf_result.get("change_days", 30)
    is_first = pdf_result.get("is_first_run", False)

    meta_html = _render_pdf_meta_header(pdf_results)

    first_run_banner = (
        f'<div class="banner">首次執行，已建立 {len(products)} 筆基準快照。'
        f'「下架」需與下次比對才會顯示，「新上架」與「新違規」依 PDF 日期欄已可顯示。</div>'
        if is_first else ""
    )

    added_html = _render_change_block(
        f"新上架（近 {change_days} 天，依上網日）",
        recent_added, "上架日", "上架日",
    )
    # 違規依「原品目」分組並顯示品目欄
    violation_html = _render_change_block(
        f"新違規案件（近 {change_days} 天，依下網日）",
        recent_violations, "下網日", "下網日",
        show_reason=True, show_category=True, group_key="原品目",
    )

    return f"""
    <section class="pdf-section">
      <h2>推薦名單監控</h2>
      {meta_html}
      <div class="pdf-summary">
        近 <strong>{change_days}</strong> 天變動：
        <span class="up">新上架 {len(recent_added)}</span> ｜
        <span class="warn">新違規 {len(recent_violations)}</span>
      </div>
      {first_run_banner}
      {added_html}
      {violation_html}
    </section>
    """


def generate_html(rows: List[Dict], pdf_result: Optional[Dict] = None) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    recent_rows = _filter_recent(rows, REPORT_RECENT_DAYS)

    used_fallback = False
    if len(recent_rows) < REPORT_FALLBACK_MIN:
        recent_rows = _sort_by_date_desc(rows)[:REPORT_FALLBACK_TOP]
        used_fallback = True

    body_html = _render_grouped(recent_rows) or "<section><p>無資料</p></section>"

    if used_fallback:
        banner = (
            f'<div class="banner">'
            f'近 {REPORT_RECENT_DAYS} 日新增不足 {REPORT_FALLBACK_MIN} 則，'
            f'自動顯示最新 {len(recent_rows)} 則'
            f'</div>'
        )
        period_text = f"最新 {len(recent_rows)} 則"
    else:
        banner = ""
        period_text = f"近 {REPORT_RECENT_DAYS} 日新增 <strong>{len(recent_rows)}</strong> 則"

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>有機肥料市場日報 {today}</title>
<style>
  body {{
    font-family: -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif;
    line-height: 1.6;
    color: #222;
    max-width: 780px;
    margin: 0 auto;
    padding: 24px;
    background: #f7f7f5;
  }}
  .header {{
    background: linear-gradient(135deg, #2d6a4f, #52b788);
    color: white;
    padding: 24px;
    border-radius: 12px;
    margin-bottom: 16px;
  }}
  .header h1 {{ margin: 0 0 8px; font-size: 22px; }}
  .header .stats {{ font-size: 14px; opacity: 0.95; }}
  .banner {{
    background: #fff8e1;
    border-left: 4px solid #f5b300;
    padding: 10px 14px;
    border-radius: 6px;
    font-size: 13px;
    color: #6b5500;
    margin-bottom: 16px;
  }}
  section {{
    background: white;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  }}
  h2 {{
    color: #2d6a4f;
    border-bottom: 2px solid #52b788;
    padding-bottom: 8px;
    margin-top: 0;
  }}
  .kw-block {{ margin: 16px 0 24px; }}
  h3 {{
    font-size: 15px;
    color: #555;
    margin: 16px 0 8px;
  }}
  h3 .count {{
    background: #e9f5ec;
    color: #2d6a4f;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 12px;
    margin-left: 6px;
  }}
  .item {{
    padding: 10px 0;
    border-bottom: 1px solid #eee;
  }}
  .item:last-child {{ border-bottom: none; }}
  .title {{
    color: #1a5490;
    text-decoration: none;
    font-weight: 600;
    font-size: 15px;
  }}
  .title:hover {{ text-decoration: underline; }}
  .meta {{
    font-size: 12px;
    color: #888;
    margin-top: 4px;
  }}
  .summary {{
    font-size: 13px;
    color: #555;
    margin-top: 6px;
  }}
  .footer {{
    text-align: center;
    color: #888;
    font-size: 12px;
    margin-top: 30px;
    padding-bottom: 20px;
  }}
  .pdf-section h2 {{ color: #6b3300; border-bottom-color: #f5b300; }}
  .pdf-summary {{
    background: #fff8e1; padding: 10px 14px; border-radius: 6px;
    margin: 12px 0 16px; font-size: 14px;
  }}
  .pdf-summary .up {{ color: #2d6a4f; font-weight: 600; }}
  .pdf-summary .down {{ color: #c92a2a; font-weight: 600; }}
  .pdf-summary .warn {{ color: #b54b00; font-weight: 600; }}
  .meta-table {{
    width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 12px;
  }}
  .meta-table th, .meta-table td {{
    border: 1px solid #eee; padding: 5px 10px; text-align: left;
  }}
  .meta-table th {{ background: #f4f4f0; }}
  .meta-table .cat {{ font-weight: 600; color: #2d6a4f; }}
  .meta-table .num {{ text-align: right; color: #555; }}
  .pdf-section h4 {{
    font-size: 14px; color: #555; margin: 12px 0 6px;
  }}
  .pdf-section h4 .count {{
    background: #e9f5ec; color: #2d6a4f;
    padding: 1px 7px; border-radius: 10px; font-size: 12px;
    margin-left: 6px; font-weight: 500;
  }}
  .pdf-table .date {{ font-family: ui-monospace, Menlo, monospace; color: #555; white-space: nowrap; }}
  .pdf-table .reason {{ font-size: 12px; color: #b54b00; }}
  .pdf-table {{
    width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 16px;
  }}
  .pdf-table th, .pdf-table td {{
    border: 1px solid #eee; padding: 6px 10px; text-align: left;
  }}
  .pdf-table th {{ background: #f4f4f0; color: #555; font-weight: 600; }}
  .pdf-table .lic {{ font-family: ui-monospace, Menlo, monospace; color: #1a5490; }}
  .pdf-table .pdf-name {{ color: #888; font-size: 11px; }}
  .empty {{ color: #999; font-size: 13px; font-style: italic; margin: 8px 0 16px; }}
</style>
</head>
<body>
  <div class="header">
    <h1>有機肥料市場日報</h1>
    <div class="stats">{today} ｜ {period_text} ｜ 累計 {len(rows)} 則</div>
  </div>

  {banner}
  {_render_pdf_changes(pdf_result)}
  {body_html}

  <div class="footer">自動爬蟲產出 · 完整原始資料請見附件 Excel</div>
</body>
</html>"""


if __name__ == "__main__":
    sample = [
        {"來源類型": "新聞", "來源網站": "中央社", "標題": "測試標題",
         "連結": "https://example.com", "命中關鍵字": "有機肥料",
         "發布日期": datetime.now().strftime("%Y-%m-%d %H:%M"), "摘要": "測試摘要"}
    ]
    print(generate_html(sample))
