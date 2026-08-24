"""
互動式全台累積雨量地圖
- 用 Open-Meteo Forecast API（past_days=92）一次拿 22 縣市的過去 92 天日雨量
- 產獨立 HTML，上方 3 個 toggle 按鈕（今日 / 本月 / 本季）切換顯示
- Leaflet 縣市泡泡圖：泡泡大小 + 顏色依雨量級距
- 上傳 catbox 取永久 URL

用法：python3 rainfall_taiwan_map.py
"""

import json
import os
import subprocess
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

OUTPUT_DIR = Path("output")
DOCS_DIR = Path("docs")          # GitHub Pages 來源資料夾
GITHUB_PAGES_BASE = "https://yuan780903-cpu.github.io/market-scraper"

# 全台 22 縣市（座標 = 縣市政府所在地或中心點）
# 用「最會下雨那個鄉鎮」更準，但 22 縣市先夠用
COUNTIES = [
    # 北部
    ("臺北市", 25.04, 121.51),
    ("新北市", 25.01, 121.46),
    ("基隆市", 25.13, 121.74),
    ("桃園市", 24.99, 121.31),
    ("新竹市", 24.81, 120.97),
    ("新竹縣", 24.84, 121.01),
    ("宜蘭縣", 24.70, 121.74),
    # 中部
    ("苗栗縣", 24.56, 120.82),
    ("臺中市", 24.15, 120.68),
    ("彰化縣", 24.07, 120.54),
    ("南投縣", 23.91, 120.69),
    ("雲林縣", 23.71, 120.43),
    # 南部
    ("嘉義市", 23.48, 120.45),
    ("嘉義縣", 23.45, 120.45),
    ("臺南市", 22.99, 120.21),
    ("高雄市", 22.62, 120.31),
    ("屏東縣", 22.55, 120.55),
    # 東部
    ("花蓮縣", 23.99, 121.60),
    ("臺東縣", 22.75, 121.15),
    # 離島
    ("澎湖縣", 23.57, 119.58),
    ("金門縣", 24.43, 118.32),
    ("連江縣", 26.16, 119.95),
]

# 顏色級距（mm）— 仿中央氣象署降雨色階（白→綠→黃→橙→紅→紫）
# 給「本月累積」用；今日/本季會自動 scale
COLOR_BANDS = [
    (0, 30, "#f5f6f3", "極少"),
    (30, 80, "#a3e0a3", "少雨"),
    (80, 150, "#5cb85c", "普通"),
    (150, 300, "#f0c040", "略多"),
    (300, 500, "#f08040", "多雨"),
    (500, 800, "#d63838", "豪雨"),
    (800, 99999, "#8b1d8b", "暴雨"),
]

# GeoJSON 縣市名 → 我們資料的縣市名（處理 「臺/台」差異和 2014 桃園升格）
COUNTY_NAME_MAP = {
    "台北市": "臺北市", "台中市": "臺中市", "台南市": "臺南市", "台東縣": "臺東縣",
    "桃園縣": "桃園市",  # GeoJSON 是 2010 版本
}

# g0v 台灣縣市 GeoJSON (2010 版，22 縣市齊)
GEOJSON_URL = "https://raw.githubusercontent.com/g0v/twgeojson/master/json/twCounty2010.geo.json"


def fetch_rainfall(lat: float, lon: float, past_days: int = 92,
                    forecast_days: int = 1) -> dict:
    """回傳 {YYYY-MM-DD: precipitation_mm}（含今日 + 可選未來 N 天預測）"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "timezone": "Asia/Taipei",
        "past_days": past_days,
        "forecast_days": forecast_days,
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    return {t: round(float(p or 0), 1) for t, p in zip(
        data["daily"]["time"], data["daily"]["precipitation_sum"]
    )}


def aggregate(daily: dict, today: date) -> dict:
    """計算 今日 / 本月累積 / 本季累積 (只算到 today, 不含未來 forecast)"""
    today_str = today.isoformat()
    today_val = daily.get(today_str, 0)

    # 本月:所有 today.year-today.month 的日值 (不含 today 之後的預測)
    month_prefix = f"{today.year}-{today.month:02d}-"
    month_total = sum(v for d, v in daily.items()
                     if d.startswith(month_prefix) and d <= today_str)

    # 本季:同月+同季但不含未來
    q = (today.month - 1) // 3 + 1
    q_months = {(q - 1) * 3 + i + 1 for i in range(3)}
    q_total = sum(
        v for d, v in daily.items()
        if d.startswith(f"{today.year}-") and d <= today_str
        and int(d.split("-")[1]) in q_months
    )

    return {
        "today": round(today_val, 1),
        "month": round(month_total, 1),
        "quarter": round(q_total, 1),
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>全台累積雨量地圖 · {today}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  /* ===== CWA 風格設計系統 ===== */
  :root{{
    --cwa-primary:#0c4a8c;      /* 主藍 */
    --cwa-dark:#003d7a;         /* 深藍 */
    --cwa-light:#e8f0f8;        /* 淡藍底 */
    --cwa-accent:#1976d2;       /* 資訊藍 */
    --cwa-warning:#ef6c00;      /* 警示橙 */
    --cwa-danger:#c62828;       /* 嚴重紅 */
    --cwa-success:#2e7d32;      /* 綠色 */
    --cwa-bg:#f4f6f9;           /* 頁面背景 */
    --cwa-card:#ffffff;         /* 卡片底 */
    --cwa-border:#dfe4ea;       /* 淺灰邊 */
    --cwa-text:#1f2933;         /* 主文字 */
    --cwa-text-muted:#6b7280;   /* 次文字 */
    --cwa-text-light:#9aa5b1;   /* 淡文字 */
    --cwa-hover:#f5f7fa;        /* hover 底 */
  }}
  *{{box-sizing:border-box;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}}
  html,body{{margin:0}}
  body{{font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",-apple-system,sans-serif;background:var(--cwa-bg);color:var(--cwa-text);line-height:1.6;font-size:15px}}

  /* ===== 頂部品牌條 (大成 · 碩成) ===== */
  .brand-bar{{background:linear-gradient(90deg,#003c8f 0%,#002171 100%);color:#fff;padding:10px 22px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;border-bottom:3px solid #ffd54f;box-shadow:0 2px 6px rgba(0,0,0,.15)}}
  .brand-left{{display:flex;align-items:center;gap:14px}}
  .brand-logos{{display:flex;align-items:center;gap:10px;background:#fff;padding:6px 12px;border-radius:8px;box-shadow:inset 0 0 0 1px rgba(0,0,0,.05),0 2px 6px rgba(0,0,0,.2)}}
  .brand-dachan-img{{height:44px;width:auto;display:block;object-fit:contain}}
  .brand-shuocheng-img{{height:44px;width:auto;display:block;object-fit:contain}}
  @media (max-width:640px){{
    .brand-logos{{padding:4px 8px;gap:6px}}
    .brand-dachan-img,.brand-shuocheng-img{{height:32px}}
  }}
  .brand-name{{display:flex;flex-direction:column;line-height:1.2}}
  .brand-name .co{{font-size:13px;font-weight:700;color:#fff;letter-spacing:.5px}}
  .brand-name .dept{{font-size:11px;color:#c8e6c9;letter-spacing:.3px;margin-top:2px}}
  .brand-right{{display:flex;align-items:center;gap:12px;font-size:12px;color:#c8e6c9}}
  .brand-right .stock{{padding:3px 10px;background:rgba(0,0,0,.2);border-radius:12px;font-family:ui-monospace,Menlo,monospace;color:#fff;font-weight:600}}

  /* ===== 主 Header (業務戰情室) ===== */
  .header{{background:linear-gradient(180deg,var(--cwa-dark) 0%,var(--cwa-primary) 100%);color:#fff;padding:22px 22px 18px;border-bottom:3px solid #d4a017;position:relative}}
  .header::before{{content:"";position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,#d4a017 50%,transparent)}}
  .header h1{{margin:0;font-size:24px;font-weight:900;letter-spacing:1.5px}}
  .header h1 .icon{{margin-right:8px}}
  .header .sub{{margin:8px 0 0;color:#cfe0f0;font-size:13px;letter-spacing:.5px}}
  .header .sub .divider{{margin:0 8px;color:#5a7ba8}}
  .header .badge{{display:inline-block;padding:2px 8px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);border-radius:10px;font-size:11px;color:#fff;margin-left:6px;letter-spacing:.5px}}

  /* ===== 工具列 refresh-bar ===== */
  .refresh-bar{{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 16px;background:var(--cwa-card);border-bottom:1px solid var(--cwa-border);font-size:13px}}
  .refresh-bar > *{{margin:2px 0}}
  .refresh-bar button{{padding:8px 18px;background:var(--cwa-primary);color:#fff;border:none;border-radius:3px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:all .15s;letter-spacing:.5px}}
  .refresh-bar button:hover:not(:disabled){{background:var(--cwa-dark)}}
  .refresh-bar button:disabled{{background:#8ba9c9;cursor:wait}}
  .refresh-bar .refresh-time{{color:var(--cwa-text-muted);font-size:12px;font-family:ui-monospace,Menlo,monospace}}
  .refresh-bar .cwa-link{{color:var(--cwa-primary);text-decoration:none;font-weight:600;font-size:12px;padding:6px 12px;border:1.5px solid var(--cwa-primary);border-radius:3px;transition:all .15s}}
  .refresh-bar .cwa-link:hover{{background:var(--cwa-primary);color:#fff}}

  /* ===== 警示條 (CWA 黃色警示條) ===== */
  .accuracy-note{{padding:10px 16px;background:#fff8e1;border-left:4px solid var(--cwa-warning);border-bottom:1px solid #f0d878;font-size:12px;color:#7a5a00;line-height:1.6}}
  .accuracy-note a{{color:var(--cwa-danger);text-decoration:none;font-weight:600}}
  .accuracy-note strong{{color:var(--cwa-danger)}}

  /* ===== 主 toggle (層級 tab) ===== */
  .toggle{{display:flex;justify-content:flex-start;gap:0;padding:0;background:var(--cwa-card);border-bottom:2px solid var(--cwa-primary);overflow-x:auto}}
  .toggle button{{padding:12px 22px;border:none;background:transparent;color:var(--cwa-text-muted);font-size:14px;font-weight:600;cursor:pointer;transition:all .15s;border-bottom:3px solid transparent;margin-bottom:-2px;font-family:inherit;white-space:nowrap;flex-shrink:0}}
  .toggle button:hover{{background:var(--cwa-hover);color:var(--cwa-primary)}}
  .toggle button.active{{color:var(--cwa-primary);border-bottom-color:var(--cwa-primary);background:var(--cwa-light)}}

  /* ===== 統計期間橫幅 ===== */
  .period{{padding:10px 16px;background:var(--cwa-light);border-bottom:1px solid var(--cwa-border);text-align:center;font-size:13px;color:var(--cwa-text)}}
  .period strong{{color:var(--cwa-primary);font-weight:700;font-family:ui-monospace,Menlo,monospace}}

  /* ===== 自訂區間 ===== */
  .custom-range{{display:none;padding:12px 16px;background:var(--cwa-hover);border-bottom:1px solid var(--cwa-border);text-align:center;font-size:13px}}
  .custom-range.show{{display:block}}
  .custom-range label{{margin:0 6px;font-weight:600;color:var(--cwa-text)}}
  .custom-range input[type=date]{{padding:6px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-size:13px;font-family:inherit;background:#fff}}
  .custom-range button{{padding:6px 16px;background:var(--cwa-primary);color:#fff;border:none;border-radius:3px;font-size:13px;font-weight:600;cursor:pointer;margin-left:6px;font-family:inherit}}
  .custom-range .hint{{font-size:11px;color:var(--cwa-text-muted);margin-top:6px}}

  /* ===== 主地圖 ===== */
  #map{{width:100%;height:60vh;background:#cfe9ff}}
  .county-label{{background:rgba(255,255,255,0.92);border:1px solid rgba(0,0,0,0.2);border-radius:2px;padding:2px 6px;font-size:11px;font-weight:600;color:var(--cwa-text);white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,0.12)}}
  .county-label .mm{{color:var(--cwa-danger);margin-left:3px;font-family:ui-monospace,Menlo,monospace}}

  /* ===== 通用區塊卡片樣式 ===== */
  .legend,.ranking,.impact,.source,.rainy-block,.forecast-block,.analysis-block,.news-block{{
    padding:16px 20px;background:var(--cwa-card);margin-top:1px;
  }}
  .legend{{border-top:1px solid var(--cwa-border)}}
  .legend-title,
  .impact h3,.ranking h3,.rainy-block h3,.forecast-block h3,.analysis-block h3,.news-block h3,.source h3{{
    margin:0 0 12px;font-size:15px;font-weight:700;color:var(--cwa-text);
    padding:6px 0 6px 12px;border-left:4px solid var(--cwa-primary);
    background:linear-gradient(90deg,var(--cwa-light) 0%,transparent 60%);
  }}

  /* ===== 色階圖例 ===== */
  .legend-row{{display:flex;align-items:center;gap:8px;font-size:13px;margin:5px 0}}
  .legend-swatch{{width:28px;height:16px;border-radius:2px;flex-shrink:0;border:1px solid #ccc}}

  /* ===== 排名表 (CWA 表格風) ===== */
  .ranking table{{width:100%;border-collapse:collapse;font-size:13px;border:1px solid var(--cwa-border)}}
  .ranking thead{{display:none}}   /* 已用 h3 標題 */
  .ranking td{{padding:8px 10px;border-bottom:1px solid var(--cwa-border)}}
  .ranking tr:nth-child(odd){{background:var(--cwa-hover)}}
  .ranking tr:hover{{background:var(--cwa-light)}}
  .ranking td.rank{{width:40px;color:var(--cwa-text-muted);font-weight:700;text-align:center;font-family:ui-monospace,Menlo,monospace}}
  .ranking td.county{{width:100px;font-weight:600;color:var(--cwa-text)}}
  .ranking td.mm{{text-align:right;font-family:ui-monospace,Menlo,monospace;font-weight:700}}

  /* ===== 影響級距表 (fab 浮動 icon 展開) ===== */
  .impact-fab-panel .group-title{{margin:10px 0 4px;font-size:12px;font-weight:700;color:var(--cwa-primary);background:var(--cwa-hover);padding:3px 8px;border-left:3px solid var(--cwa-primary)}}
  .impact-fab-panel .row{{display:flex;gap:10px;font-size:11.5px;margin:2px 0;align-items:baseline;padding:3px 8px;line-height:1.4}}
  .impact-fab-panel .row:nth-child(even){{background:var(--cwa-hover)}}
  .impact-fab-panel .rng{{width:82px;font-weight:700;font-family:ui-monospace,Menlo,monospace;flex-shrink:0;font-size:11px}}
  .impact-fab-panel .note{{color:var(--cwa-text);flex:1}}
  .impact-fab-panel .green{{color:var(--cwa-success)}}
  .impact-fab-panel .amber{{color:var(--cwa-warning)}}
  .impact-fab-panel .red{{color:var(--cwa-danger)}}
  .impact-fab-panel .gray{{color:var(--cwa-text-muted)}}
  .impact-fab-panel .info-note{{margin-top:10px;padding:8px 10px;background:var(--cwa-light);border-left:4px solid var(--cwa-primary);border-radius:2px;font-size:11px;color:var(--cwa-text);line-height:1.6}}
  .impact-fab-panel .info-note strong{{color:var(--cwa-primary)}}

  /* fab 容器 */
  .impact-fab{{position:fixed;right:16px;bottom:16px;z-index:998}}
  .impact-fab-btn{{background:linear-gradient(135deg,#1976d2,#0d47a1);color:#fff;border:none;border-radius:26px;padding:10px 16px 10px 14px;font-size:14px;font-weight:700;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.3);display:flex;align-items:center;gap:6px;transition:transform .15s;font-family:inherit}}
  .impact-fab-btn:hover{{transform:translateY(-2px);box-shadow:0 6px 16px rgba(0,0,0,.4)}}
  .impact-fab-btn span{{font-size:13px;letter-spacing:.5px}}
  .impact-fab-panel{{position:absolute;right:0;bottom:52px;width:400px;max-width:calc(100vw - 32px);max-height:70vh;overflow-y:auto;background:#fff;border:1px solid var(--cwa-border);border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,.25);padding:12px 14px;opacity:0;visibility:hidden;transform:translateY(8px);transition:opacity .15s,transform .15s,visibility .15s}}
  .impact-fab:hover .impact-fab-panel,.impact-fab.open .impact-fab-panel{{opacity:1;visibility:visible;transform:translateY(0)}}
  .impact-fab-head{{font-size:14px;font-weight:900;color:var(--cwa-primary);padding-bottom:6px;border-bottom:2px solid var(--cwa-primary);margin-bottom:8px}}
  @media (max-width:640px){{
    .impact-fab{{right:8px;bottom:8px}}
    .impact-fab-btn{{padding:8px 12px 8px 10px;font-size:12px}}
    .impact-fab-btn span{{font-size:11px}}
    .impact-fab-panel{{width:calc(100vw - 16px);max-height:60vh}}
  }}

  /* ===== 資料來源 ===== */
  .source{{border-top:2px solid var(--cwa-border);background:var(--cwa-hover)}}
  .source h3{{background:transparent;border-left-color:var(--cwa-text-muted);color:var(--cwa-text-muted)}}
  .source ul{{margin:0;padding-left:20px;font-size:12px;color:var(--cwa-text-muted);line-height:1.8}}
  .source li{{margin:4px 0}}
  .source a{{color:var(--cwa-accent);text-decoration:none;word-break:break-all}}
  .source a:hover{{text-decoration:underline}}

  /* ===== 精美頁尾 (corporate 級) ===== */
  .footer{{background:linear-gradient(180deg,#1b5e20 0%,#0d3f10 100%);color:#c8e6c9;padding:24px 22px 18px;border-top:3px solid #d4a017;box-shadow:0 -2px 8px rgba(0,0,0,.1)}}
  .footer-grid{{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;font-size:12px;line-height:1.7}}
  .footer-col h5{{margin:0 0 8px;font-size:13px;color:#d4a017;font-weight:700;letter-spacing:1px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,.15)}}
  .footer-col .row{{margin:4px 0}}
  .footer-col .lbl{{color:#a5d6a7;margin-right:6px;font-weight:600}}
  .footer-col .val{{color:#fff;font-family:ui-monospace,Menlo,monospace}}
  .footer-copy{{max-width:1200px;margin:16px auto 0;padding-top:14px;border-top:1px solid rgba(255,255,255,.15);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;font-size:11px;color:#a5d6a7}}
  .footer-copy .sig{{display:inline-flex;align-items:center;gap:8px}}
  .footer-copy .sig .stamp{{padding:4px 10px;background:#d4a017;color:#1b5e20;border-radius:3px;font-weight:900;letter-spacing:1px}}
  .footer-copy a{{color:#fff;text-decoration:none;border-bottom:1px dashed rgba(255,255,255,.3)}}
  @media (max-width:640px){{
    .footer-grid{{grid-template-columns:1fr;gap:14px}}
    .footer-copy{{flex-direction:column;text-align:center}}
  }}

  /* ===== 精美卡片陰影 (corporate) ===== */
  .legend,.ranking,.impact,.source,.rainy-block,.forecast-block,.analysis-block,.news-block,
  .crops-block,.towns-block,.history-block,.adv-block,.term-detail-block{{
    box-shadow:0 1px 3px rgba(0,0,0,.04),0 0 0 1px rgba(0,0,0,.04);
  }}

  /* ===== Popup ===== */
  .popup-content{{font-size:14px}}
  .popup-content strong{{color:var(--cwa-primary)}}

  /* ===== 本月降雨日曆 ===== */
  .rainy-filters{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px;align-items:center;font-size:13px;padding:10px;background:var(--cwa-hover);border-radius:3px;border:1px solid var(--cwa-border)}}
  .rainy-filters label{{font-weight:600;color:var(--cwa-text)}}
  .rainy-filters select{{padding:6px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-size:13px;font-family:inherit;background:#fff;color:var(--cwa-text)}}
  .rainy-summary{{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:center;padding:14px 18px;background:var(--cwa-light);color:var(--cwa-text);border-left:4px solid var(--cwa-primary);border-radius:3px;margin-bottom:12px;font-size:13px}}
  .rainy-summary .loc{{color:var(--cwa-primary);font-weight:700;font-size:15px;display:inline-flex;align-items:center;gap:4px}}
  .rainy-summary .date{{color:var(--cwa-text-muted);font-family:ui-monospace,Menlo,monospace;font-size:13px}}
  .rainy-summary .stat{{color:var(--cwa-text);display:inline-flex;align-items:baseline;gap:5px;white-space:nowrap}}
  .rainy-summary .stat strong{{color:var(--cwa-danger);font-size:22px;font-family:ui-monospace,Menlo,monospace;margin:0 2px;font-weight:900;line-height:1}}
  .rainy-summary .stat .unit{{color:var(--cwa-text-muted);font-size:12px}}
  .cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;font-size:12px;margin:0 auto 12px;background:var(--cwa-border);padding:2px;border-radius:3px;max-width:640px}}
  .cal-head{{padding:5px 4px;text-align:center;font-weight:700;background:var(--cwa-primary);color:#fff;font-size:11px}}
  .cal-head:first-child{{color:#ffd54f}}
  .cal-head:last-child{{color:#ffcccc}}
  .cal-cell{{min-height:52px;padding:4px 5px;display:flex;flex-direction:column;justify-content:space-between;text-align:center;background:#fff;color:var(--cwa-text);cursor:pointer;transition:transform .1s;position:relative}}
  .cal-cell:hover:not(.empty){{transform:scale(1.05);z-index:2;box-shadow:0 2px 6px rgba(0,0,0,.15)}}
  .cal-cell.empty{{background:transparent;cursor:default}}
  .cal-cell.dry{{background:#fafafa;color:var(--cwa-text-light)}}
  .cal-cell.rain-1{{background:#e3f2fd;color:#0d47a1}}
  .cal-cell.rain-2{{background:#64b5f6;color:#fff}}
  .cal-cell.rain-3{{background:#1976d2;color:#fff}}
  .cal-cell.rain-4{{background:#ef6c00;color:#fff}}
  .cal-cell.rain-5{{background:#c62828;color:#fff}}
  .cal-cell.today{{outline:3px solid #ffd54f;outline-offset:-3px;font-weight:900}}
  .cal-cell .d{{font-size:13px;font-weight:700;line-height:1.1;display:flex;justify-content:space-between;align-items:baseline}}
  .cal-cell .wk{{font-size:9px;opacity:.65;font-weight:600;margin-left:2px}}
  .cal-cell .mm{{font-size:11px;font-weight:700;font-family:ui-monospace,Menlo,monospace}}
  @media (max-width:640px){{
    .cal-cell{{min-height:44px;padding:3px}}
    .cal-cell .d{{font-size:12px}}
    .cal-cell .wk{{font-size:8px}}
    .cal-cell .mm{{font-size:10px}}
  }}
  /* 雨量視覺化 modal */
  .rain-modal{{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.55);z-index:2000;align-items:center;justify-content:center;padding:16px}}
  .rain-modal.show{{display:flex;animation:modal-fade .2s ease-out}}
  @keyframes modal-fade{{from{{opacity:0}}to{{opacity:1}}}}
  .rm-content{{background:#fff;border-radius:6px;max-width:480px;width:100%;max-height:90vh;overflow-y:auto;box-shadow:0 10px 40px rgba(0,0,0,.3);position:relative}}
  .rm-head{{padding:14px 18px;background:var(--cwa-primary);color:#fff;border-radius:6px 6px 0 0;display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:15px}}
  .rm-head .close{{background:transparent;border:none;color:#fff;font-size:24px;cursor:pointer;padding:0 4px;line-height:1;font-weight:normal}}
  .rm-body{{padding:20px}}
  .rm-viz{{position:relative;height:220px;display:flex;align-items:flex-end;justify-content:center;gap:20px;background:linear-gradient(to bottom,#87ceeb 0%,#b3e5fc 100%);border-radius:4px;overflow:hidden;margin-bottom:14px}}
  .rm-drops{{position:absolute;top:0;left:0;right:0;bottom:0;pointer-events:none;overflow:hidden}}
  .rm-drop{{position:absolute;font-size:20px;animation:rm-fall linear infinite;opacity:.8}}
  @keyframes rm-fall{{0%{{transform:translateY(-20px);opacity:0}}10%{{opacity:1}}90%{{opacity:1}}100%{{transform:translateY(240px);opacity:0}}}}
  .rm-cup{{position:relative;width:90px;height:180px;background:linear-gradient(to right,rgba(255,255,255,.5),rgba(255,255,255,.75),rgba(255,255,255,.5));border:3px solid #fff;border-top:none;border-radius:0 0 12px 12px;z-index:2;box-shadow:0 4px 10px rgba(0,0,0,.2)}}
  .rm-cup .water{{position:absolute;bottom:0;left:0;right:0;background:linear-gradient(180deg,#2196f3,#0d47a1);transition:height 1s ease-out;border-radius:0 0 8px 8px}}
  .rm-cup .water::before{{content:"";position:absolute;top:-6px;left:0;right:0;height:8px;background:radial-gradient(ellipse at center,rgba(255,255,255,.6) 0%,transparent 60%)}}
  .rm-cup .scale{{position:absolute;top:0;bottom:0;right:-42px;width:38px;display:flex;flex-direction:column;justify-content:space-between;padding:4px 0;color:#fff;font-size:10px;font-family:ui-monospace,Menlo,monospace;text-shadow:0 1px 2px rgba(0,0,0,.5)}}
  .rm-cup .scale span{{display:block}}
  .rm-value{{position:absolute;top:16px;left:16px;background:rgba(255,255,255,.95);padding:8px 12px;border-radius:4px;box-shadow:0 2px 6px rgba(0,0,0,.15)}}
  .rm-value .num{{font-size:28px;font-weight:900;color:var(--cwa-danger);font-family:ui-monospace,Menlo,monospace;line-height:1}}
  .rm-value .unit{{font-size:12px;color:var(--cwa-text-muted);margin-left:2px}}
  .rm-value .lvl{{font-size:12px;color:var(--cwa-primary);font-weight:700;margin-top:3px}}
  .rm-cmps{{list-style:none;padding:0;margin:0}}
  .rm-cmps li{{padding:10px 12px;border-bottom:1px solid var(--cwa-border);font-size:13px;color:var(--cwa-text);line-height:1.5}}
  .rm-cmps li:last-child{{border-bottom:none}}
  .rm-cmps li strong{{color:var(--cwa-primary);font-weight:700}}
  .rm-impact{{margin-top:14px;padding:12px 14px;background:var(--cwa-light);border-left:4px solid var(--cwa-primary);border-radius:3px;font-size:13px;color:var(--cwa-text);line-height:1.7}}
  .rm-impact .label{{font-weight:700;color:var(--cwa-primary);display:block;margin-bottom:4px}}
  .rainy-list{{max-height:180px;overflow-y:auto;background:var(--cwa-hover);padding:10px 12px;border-radius:3px;font-size:12px;line-height:1.8;border:1px solid var(--cwa-border)}}
  .rainy-list .day{{display:inline-block;padding:3px 10px;margin:3px;background:#fff;border-radius:2px;border:1px solid var(--cwa-border);font-family:ui-monospace,Menlo,monospace}}
  .rainy-list .day b{{color:var(--cwa-danger)}}

  /* ===== 未來 7 天預測地圖 ===== */
  .fcst-mode-bar{{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}}
  .fcst-mode-bar button{{padding:6px 14px;border:1.5px solid var(--cwa-border);background:#fff;color:var(--cwa-text-muted);font-size:12px;font-weight:600;border-radius:3px;cursor:pointer;font-family:inherit;transition:all .15s}}
  .fcst-mode-bar button:hover{{background:var(--cwa-hover);color:var(--cwa-primary);border-color:var(--cwa-primary)}}
  .fcst-mode-bar button.active{{background:var(--cwa-primary);color:#fff;border-color:var(--cwa-primary)}}
  .fcst-checkboxes{{display:none;flex-wrap:wrap;gap:8px;padding:10px 12px;background:var(--cwa-hover);border-radius:3px;border:1px solid var(--cwa-border);margin-bottom:10px}}
  .fcst-checkboxes.show{{display:flex}}
  .fcst-checkboxes label{{display:inline-flex;align-items:center;gap:5px;font-size:12px;cursor:pointer;padding:4px 10px;background:#fff;border:1px solid var(--cwa-border);border-radius:3px;font-family:inherit}}
  .fcst-checkboxes label:hover{{background:var(--cwa-light)}}
  .fcst-checkboxes input[type=checkbox]{{margin:0;accent-color:var(--cwa-primary)}}
  .fcst-checkboxes label.checked{{background:var(--cwa-light);border-color:var(--cwa-primary);color:var(--cwa-primary);font-weight:700}}
  .fcst-info{{padding:8px 12px;background:var(--cwa-light);border-left:3px solid var(--cwa-primary);border-radius:2px;margin-bottom:10px;font-size:12px;color:var(--cwa-text);line-height:1.6}}
  .fcst-info strong{{color:var(--cwa-primary);font-family:ui-monospace,Menlo,monospace}}
  .fcst-day-tabs{{display:flex;gap:0;margin-bottom:12px;overflow-x:auto;border-bottom:1px solid var(--cwa-border)}}
  .fcst-day-tabs button{{flex-shrink:0;padding:10px 16px;border:none;background:transparent;color:var(--cwa-text-muted);font-size:13px;font-weight:600;cursor:pointer;line-height:1.2;font-family:inherit;border-bottom:3px solid transparent;margin-bottom:-1px;transition:all .15s}}
  .fcst-day-tabs button:hover{{background:var(--cwa-hover);color:var(--cwa-primary)}}
  .fcst-day-tabs button.active{{color:var(--cwa-primary);border-bottom-color:var(--cwa-primary);background:var(--cwa-light)}}
  .fcst-wrap{{display:flex;gap:14px;align-items:flex-start;flex-wrap:wrap}}
  #fcstMap{{flex:1 1 320px;min-width:280px;height:420px;background:#cfe9ff;border:1px solid var(--cwa-border);border-radius:3px}}
  .fcst-legend{{flex:0 0 150px;padding:12px;background:var(--cwa-hover);border-radius:3px;border:1px solid var(--cwa-border)}}
  .fcst-legend-title{{font-size:12px;font-weight:700;color:var(--cwa-primary);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--cwa-border)}}
  .fcst-bar{{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:11px}}
  .fcst-bar-color{{width:26px;height:14px;border-radius:2px;flex-shrink:0;border:1px solid rgba(0,0,0,.1)}}
  .fcst-bar-label{{color:var(--cwa-text);font-weight:600;width:42px}}
  .fcst-bar-range{{color:var(--cwa-text-muted);font-size:10px;font-family:ui-monospace,Menlo,monospace}}
  .fcst-legend-hint{{margin-top:12px;padding-top:8px;border-top:1px solid var(--cwa-border);font-size:10px;color:var(--cwa-text-muted);line-height:1.6}}
  /* 預測縣市排名 */
  .fcst-ranking{{margin-top:16px;padding-top:12px;border-top:1px dashed var(--cwa-border)}}
  .fcst-ranking-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
  .fcst-ranking-head h4{{margin:0;font-size:14px;font-weight:700;color:var(--cwa-primary)}}
  .fcst-ranking-head button{{padding:5px 12px;border:1.5px solid var(--cwa-primary);background:#fff;color:var(--cwa-primary);font-size:12px;font-weight:600;border-radius:3px;cursor:pointer;font-family:inherit}}
  .fcst-ranking-head button:hover{{background:var(--cwa-primary);color:#fff}}
  .fcst-ranking table{{width:100%;border-collapse:collapse;font-size:13px;border:1px solid var(--cwa-border)}}
  .fcst-ranking th{{padding:8px 10px;background:var(--cwa-primary);color:#fff;text-align:left;font-weight:600;font-size:12px}}
  .fcst-ranking th.n{{text-align:right}}
  .fcst-ranking td{{padding:7px 10px;border-bottom:1px solid var(--cwa-border)}}
  .fcst-ranking tr:nth-child(odd) td{{background:var(--cwa-hover)}}
  .fcst-ranking tr:hover td{{background:var(--cwa-light)}}
  .fcst-ranking td.rank{{width:44px;color:var(--cwa-text-muted);font-weight:700;text-align:center;font-family:ui-monospace,Menlo,monospace}}
  .fcst-ranking td.county{{font-weight:600}}
  .fcst-ranking td.mm{{text-align:right;font-family:ui-monospace,Menlo,monospace;font-weight:700;white-space:nowrap}}
  .fcst-ranking td.lvl{{width:70px;text-align:center;font-size:11px;font-weight:700}}
  .fcst-ranking .swatch{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:middle;border:1px solid rgba(0,0,0,.1)}}

  /* ===== 基肥作物篩選 ===== */
  .crops-block{{padding:16px 20px;background:var(--cwa-card);margin-top:1px;border-left:4px solid var(--cwa-success)}}
  .crops-block h3{{margin:0 0 12px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid var(--cwa-success);background:linear-gradient(90deg,#e8f5e9 0%,transparent 60%)}}
  .crops-filters{{padding:12px;background:var(--cwa-hover);border:1px solid var(--cwa-border);border-radius:3px;margin-bottom:12px}}
  .crops-f-row{{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;font-size:13px}}
  .crops-f-row label{{font-weight:600;color:var(--cwa-text);white-space:nowrap}}
  .crops-f-row select{{padding:6px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-size:13px;font-family:inherit;background:#fff;color:var(--cwa-text)}}
  .crops-summary{{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:center;padding:14px 18px;background:var(--cwa-light);color:var(--cwa-text);border-left:4px solid var(--cwa-success);border-radius:3px;margin-bottom:12px;font-size:13px}}
  .crops-summary .stat{{color:var(--cwa-text);display:inline-flex;align-items:baseline;gap:5px;white-space:nowrap}}
  .crops-summary .stat strong{{color:var(--cwa-success);font-size:22px;font-family:ui-monospace,Menlo,monospace;margin:0 2px;font-weight:900;line-height:1}}
  .crops-summary .stat .unit{{color:var(--cwa-text-muted);font-size:12px}}
  .crops-summary .this-month{{color:var(--cwa-warning);font-weight:700;font-size:13px}}
  .crops-table-wrap{{overflow-x:auto;border:1px solid var(--cwa-border);border-radius:3px}}
  .crops-table{{width:100%;border-collapse:collapse;font-size:13px;min-width:720px}}
  .crops-table th{{padding:9px 10px;background:var(--cwa-primary);color:#fff;text-align:left;font-weight:600;font-size:12px;white-space:nowrap}}
  .crops-table td{{padding:8px 10px;border-bottom:1px solid var(--cwa-border);vertical-align:middle}}
  .crops-table tr:nth-child(odd) td{{background:var(--cwa-hover)}}
  .crops-table tr:hover td{{background:var(--cwa-light)}}
  .crops-table tr.match-month td{{background:#fff9c4 !important;border-left:3px solid var(--cwa-warning)}}
  .crops-table td.cat{{font-size:20px;text-align:center;line-height:1}}
  .crops-table td.name{{font-weight:600;color:var(--cwa-text)}}
  .crops-table td.months{{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--cwa-text-muted)}}
  .crops-table td.months .m{{display:inline-block;padding:1px 5px;background:#e8f0f8;color:var(--cwa-primary);border-radius:2px;margin:1px 2px;font-weight:600}}
  .crops-table td.months .m.now{{background:var(--cwa-warning);color:#fff}}
  .crops-table td.regions{{color:var(--cwa-text-muted);font-size:12px}}
  .crops-table td.kg{{text-align:right;font-family:ui-monospace,Menlo,monospace;font-weight:700;color:var(--cwa-primary)}}
  .crops-table td.prob{{text-align:center;font-weight:700}}
  .crops-table td.prob.h{{color:var(--cwa-danger)}}
  .crops-table td.prob.m{{color:var(--cwa-warning)}}
  .crops-table td.prob.l{{color:var(--cwa-text-muted)}}
  .crops-table td.note{{font-size:11px;color:var(--cwa-text-muted)}}
  .crops-foot{{margin-top:12px;padding:10px 12px;background:var(--cwa-hover);border-radius:3px;font-size:11px;color:var(--cwa-text-muted);line-height:1.8}}
  .crops-foot strong{{color:var(--cwa-primary)}}

  /* ===== 鄉鎮農產分布地圖 ===== */
  .towns-block{{padding:16px 20px;background:var(--cwa-card);margin-top:1px;border-left:4px solid #c2185b}}
  .towns-block h3{{margin:0 0 12px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid #c2185b;background:linear-gradient(90deg,#fce4ec 0%,transparent 60%)}}
  .towns-filters{{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;padding:10px 12px;background:var(--cwa-hover);border:1px solid var(--cwa-border);border-radius:3px;margin-bottom:10px;font-size:13px}}
  .towns-filters label{{font-weight:600;color:var(--cwa-text)}}
  .towns-filters select{{padding:6px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-size:13px;font-family:inherit;background:#fff}}
  .towns-count{{margin-left:auto;color:#c2185b;font-weight:700;font-size:13px}}
  #townsMap{{width:100%;height:520px;background:#cfe9ff;border:1px solid var(--cwa-border);border-radius:3px}}
  .towns-legend{{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:8px;padding:8px 12px;background:var(--cwa-hover);border-radius:3px;font-size:11px;color:var(--cwa-text-muted)}}
  .towns-legend .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}}
  .town-popup{{font-size:13px;line-height:1.6;min-width:180px}}
  .town-popup .head{{font-weight:700;color:var(--cwa-primary);font-size:14px;border-bottom:1px solid #eee;padding-bottom:4px;margin-bottom:4px}}
  .town-popup .crops{{margin:6px 0}}
  .town-popup .crop-tag{{display:inline-block;padding:2px 8px;background:var(--cwa-light);color:var(--cwa-primary);border-radius:10px;font-size:11px;font-weight:600;margin:2px}}
  .town-popup .note{{color:var(--cwa-text-muted);font-size:11px;font-style:italic}}
  .town-marker{{background:#fff;border:2px solid;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:900;box-shadow:0 2px 4px rgba(0,0,0,.25);cursor:pointer;transition:transform .1s}}
  .town-marker:hover{{transform:scale(1.2);z-index:1000 !important}}
  .town-marker.fruit{{border-color:#c62828;color:#c62828}}
  .town-marker.veg{{border-color:#2e7d32;color:#2e7d32}}
  .town-marker.tea{{border-color:#00695c;color:#00695c}}
  .town-marker.flower{{border-color:#c2185b;color:#c2185b}}
  .town-marker.grain{{border-color:#5d4037;color:#5d4037}}

  /* ===== 歷史雨量比較 ===== */
  .history-block{{padding:16px 20px;background:var(--cwa-card);margin-top:1px;border-left:4px solid #7b1fa2}}
  .history-block h3{{margin:0 0 12px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid #7b1fa2;background:linear-gradient(90deg,#f3e5f5 0%,transparent 60%)}}
  .history-filters{{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;padding:10px 12px;background:var(--cwa-hover);border:1px solid var(--cwa-border);border-radius:3px;margin-bottom:12px;font-size:13px}}
  .history-filters label{{font-weight:600;color:var(--cwa-text)}}
  .history-filters select{{padding:6px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-size:13px;font-family:inherit;background:#fff}}
  .history-filters button{{padding:7px 16px;background:#7b1fa2;color:#fff;border:none;border-radius:3px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit}}
  .history-filters button:hover:not(:disabled){{background:#4a148c}}
  .history-filters button:disabled{{background:#b39ddb;cursor:wait}}
  .history-status{{padding:10px 12px;background:var(--cwa-light);border-left:3px solid #7b1fa2;border-radius:2px;margin-bottom:12px;font-size:13px;color:var(--cwa-text);display:none}}
  .history-status.show{{display:block}}
  .history-chart{{padding:14px;background:#fafafa;border:1px solid var(--cwa-border);border-radius:3px;margin-bottom:12px;min-height:200px}}
  .history-chart svg{{width:100%;height:auto;display:block}}
  .history-table-wrap{{overflow-x:auto;border:1px solid var(--cwa-border);border-radius:3px;margin-bottom:12px}}
  .history-table{{width:100%;border-collapse:collapse;font-size:13px}}
  .history-table th{{padding:9px 10px;background:#7b1fa2;color:#fff;text-align:center;font-weight:600;font-size:12px;white-space:nowrap}}
  .history-table td{{padding:8px 10px;text-align:center;border-bottom:1px solid var(--cwa-border);font-family:ui-monospace,Menlo,monospace}}
  .history-table tr:nth-child(odd) td{{background:var(--cwa-hover)}}
  .history-table tr:hover td{{background:var(--cwa-light)}}
  .history-table td.yr{{font-weight:700;color:var(--cwa-primary)}}
  .history-table td.mm{{font-weight:700;color:var(--cwa-text)}}
  .history-table td.diff.up{{color:var(--cwa-danger);font-weight:700}}
  .history-table td.diff.down{{color:var(--cwa-success);font-weight:700}}
  .history-table tr.avg-row td{{background:#fff3e0 !important;font-weight:700}}
  .history-table tr.current-row td{{background:#e8f5e9 !important;font-weight:700;color:#1b5e20}}
  .history-report{{padding:14px 16px;background:var(--cwa-light);border-left:4px solid #7b1fa2;border-radius:3px;font-size:13px;color:var(--cwa-text);line-height:1.8}}
  .history-report .label{{font-weight:700;color:#7b1fa2;display:block;margin-bottom:6px}}
  .history-report .biz{{margin-top:8px;padding:10px 12px;background:#fff;border-radius:3px}}

  /* ===== 進階歷史比較 ===== */
  .adv-block{{padding:16px 20px;background:var(--cwa-card);margin-top:1px;border-left:4px solid #d84315}}
  .adv-block h3{{margin:0 0 12px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid #d84315;background:linear-gradient(90deg,#ffe0b2 0%,transparent 60%)}}
  .adv-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:14px}}
  .adv-group{{padding:12px 14px;background:linear-gradient(180deg,#fff 0%,#fafafa 100%);border:1px solid var(--cwa-border);border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
  .adv-group-head{{display:flex;justify-content:space-between;align-items:center;font-size:13px;font-weight:900;color:var(--cwa-primary);margin-bottom:10px;padding-bottom:8px;border-bottom:2px solid var(--cwa-primary)}}
  .adv-group-head .quick{{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}}
  .adv-group-head .quick a{{background:var(--cwa-hover);color:var(--cwa-primary);font-size:11px;cursor:pointer;font-weight:700;padding:2px 8px;border-radius:10px;border:1px solid transparent;transition:all .1s}}
  .adv-group-head .quick a:hover{{background:var(--cwa-primary);color:#fff}}
  .adv-cbs{{display:flex;flex-wrap:wrap;gap:6px}}
  .adv-cbs label{{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;background:#fff;border:1.5px solid var(--cwa-border);border-radius:16px;font-size:12px;cursor:pointer;font-family:inherit;transition:all .12s;user-select:none;white-space:nowrap}}
  .adv-cbs label:hover{{background:var(--cwa-light);border-color:var(--cwa-primary);transform:translateY(-1px)}}
  .adv-cbs label.on{{background:linear-gradient(135deg,#d84315,#bf360c);color:#fff;border-color:#bf360c;font-weight:700;box-shadow:0 2px 4px rgba(216,67,21,.35)}}
  .adv-cbs input[type=checkbox]{{margin:0;accent-color:#d84315;pointer-events:none}}
  /* 指標分色: 雨量藍系, 氣溫紅系 */
  .adv-chip.metric-rain{{border-color:#1976d2;color:#1976d2}}
  .adv-chip.metric-rain.on,.adv-chip.metric-rain input:checked ~ *{{}}
  #advMetrics .metric-rain.on{{background:linear-gradient(135deg,#1976d2,#0d47a1) !important;border-color:#0d47a1 !important;box-shadow:0 2px 4px rgba(25,118,210,.35) !important;color:#fff !important}}
  .adv-chip.metric-temp{{border-color:#c62828;color:#c62828}}
  #advMetrics .metric-temp.on{{background:linear-gradient(135deg,#c62828,#8b0000) !important;border-color:#8b0000 !important;box-shadow:0 2px 4px rgba(198,40,40,.35) !important;color:#fff !important}}
  .adv-chip.metric-sales{{border-color:#f57c00;color:#f57c00}}
  #advMetrics .metric-sales.on{{background:linear-gradient(135deg,#f57c00,#e65100) !important;border-color:#e65100 !important;box-shadow:0 2px 4px rgba(245,124,0,.35) !important;color:#fff !important}}
  .adv-summary{{margin-left:auto;font-size:12px;color:var(--cwa-text-muted);font-weight:700}}
  .adv-actions{{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap;font-size:13px}}
  .adv-actions button{{padding:8px 16px;background:#d84315;color:#fff;border:none;border-radius:3px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit}}
  .adv-actions button:hover:not(:disabled){{background:#bf360c}}
  .adv-actions button:disabled{{background:#ffab91;cursor:wait}}
  .adv-actions .est{{color:var(--cwa-text-muted);font-size:12px}}
  .adv-actions .est strong{{color:#d84315;font-weight:700}}
  .adv-status{{padding:10px 12px;background:var(--cwa-light);border-left:3px solid #d84315;border-radius:2px;margin-bottom:10px;font-size:13px;color:var(--cwa-text);display:none}}
  .adv-status.show{{display:block}}
  .adv-view-tabs{{display:flex;gap:0;margin-bottom:10px;border-bottom:1px solid var(--cwa-border)}}
  .adv-view-tabs button{{padding:8px 16px;border:none;background:transparent;color:var(--cwa-text-muted);font-size:12px;font-weight:600;cursor:pointer;border-bottom:3px solid transparent;margin-bottom:-1px;font-family:inherit}}
  .adv-view-tabs button.active{{color:#d84315;border-bottom-color:#d84315;background:#ffe0b2}}
  .adv-table-wrap{{overflow-x:auto;border:1px solid var(--cwa-border);border-radius:3px;margin-bottom:12px}}
  .adv-table{{width:100%;border-collapse:collapse;font-size:12px;min-width:520px}}
  .adv-table th{{padding:8px;background:#d84315;color:#fff;text-align:center;font-weight:600;font-size:11px;white-space:nowrap;cursor:pointer;user-select:none}}
  .adv-table th:hover{{background:#bf360c}}
  .adv-table th .sort{{opacity:.6;font-size:10px;margin-left:2px}}
  .adv-table td{{padding:7px 8px;text-align:center;border-bottom:1px solid var(--cwa-border);font-family:ui-monospace,Menlo,monospace}}
  .adv-table tr:nth-child(odd) td{{background:var(--cwa-hover)}}
  .adv-table tr:hover td{{background:#ffe0b2}}
  .adv-table td.year,.adv-table td.region{{font-weight:700;color:var(--cwa-primary)}}
  .adv-table td.mm{{font-weight:700}}
  .adv-table td.high{{background:#ffcdd2 !important;color:#b71c1c;font-weight:900}}
  .adv-table td.low{{background:#c8e6c9 !important;color:#1b5e20;font-weight:900}}
  /* 矩陣視圖 */
  .adv-matrix{{width:100%;border-collapse:collapse;font-size:11.5px}}
  .adv-matrix th,.adv-matrix td{{padding:5px 4px;text-align:center;border:1px solid var(--cwa-border);font-family:ui-monospace,Menlo,monospace;min-width:44px}}
  .adv-matrix thead th{{background:linear-gradient(180deg,#d84315,#bf360c);color:#fff;font-weight:700;font-size:11px;white-space:nowrap;position:sticky;top:0}}
  .adv-matrix tbody th{{background:#f5f5f5;color:#333;text-align:left;padding-left:8px;font-weight:900;white-space:nowrap;position:sticky;left:0;z-index:1}}
  .adv-chart-legend{{display:flex;flex-wrap:wrap;gap:8px 14px;padding:10px 12px;background:#fafafa;border-top:1px solid var(--cwa-border);font-size:11px}}
  .adv-chart-legend .leg{{display:inline-flex;align-items:center;gap:5px;color:#333;font-weight:600}}
  .adv-chart-legend .ln{{display:inline-block;width:20px;height:3px;border-radius:2px}}
  .adv-matrix tbody th{{background:var(--cwa-primary);color:#fff;font-weight:700;text-align:left;padding:6px 10px;white-space:nowrap}}
  .adv-matrix td{{background:#fff;color:var(--cwa-text)}}
  .adv-matrix td.mx-0{{background:#fafafa;color:#aaa}}
  .adv-matrix td.mx-1{{background:#e3f2fd;color:#0d47a1}}
  .adv-matrix td.mx-2{{background:#64b5f6;color:#fff}}
  .adv-matrix td.mx-3{{background:#1976d2;color:#fff}}
  .adv-matrix td.mx-4{{background:#f0c040;color:#5a3800}}
  .adv-matrix td.mx-5{{background:#ef6c00;color:#fff}}
  .adv-matrix td.mx-6{{background:#c62828;color:#fff}}
  .adv-matrix td.mx-7{{background:#7b1fa2;color:#fff}}
  .adv-matrix td .d{{font-size:9px;opacity:.7;margin-top:1px;display:block}}
  /* 分析評語 */
  .adv-analysis{{padding:16px 18px;background:linear-gradient(180deg,#fff3e0,#fff8e1);border-left:5px solid #d84315;border-radius:6px;font-size:13.5px;color:var(--cwa-text);line-height:1.75}}
  .adv-analysis h4{{margin:14px 0 8px;font-size:14px;color:#d84315;font-weight:900;padding:5px 10px;background:#fff;border-left:3px solid #d84315;border-radius:0 4px 4px 0}}
  .adv-analysis h4:first-child{{margin-top:0}}
  .adv-analysis ul{{margin:6px 0;padding-left:22px}}
  .adv-analysis li{{margin:4px 0}}
  .adv-analysis p{{margin:6px 0}}
  .adv-analysis strong{{color:#c62828;font-weight:900}}
  .adv-analysis .growth{{color:#2e7d32;font-weight:900}}
  .adv-analysis .drop{{color:#c62828;font-weight:900}}
  .adv-analysis .biz{{margin-top:14px;padding:12px 14px;background:#fff;border-radius:4px;border:1px solid var(--cwa-border);border-left:4px solid #d84315}}
  .adv-kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:12px 0}}
  .adv-kpi{{background:#fff;border:1px solid var(--cwa-border);border-left:4px solid #90a4ae;border-radius:4px;padding:8px 10px;text-align:center}}
  .adv-kpi.hi{{border-left-color:#c62828;background:#ffebee}}
  .adv-kpi.lo{{border-left-color:#2e7d32;background:#e8f5e9}}
  .adv-kpi .lbl{{font-size:11px;color:var(--cwa-text-muted);font-weight:700}}
  .adv-kpi .val{{font-size:22px;font-weight:900;color:#c62828;line-height:1.1;margin-top:2px;font-family:ui-monospace,Menlo,monospace}}
  .adv-kpi .val span{{font-size:11px;color:#888;font-weight:600}}
  .adv-kpi .who{{font-size:10px;color:#666;margin-top:2px}}

  /* ===== 節氣 × 基肥影響區塊 ===== */
  .term-detail-block{{padding:16px 20px;background:var(--cwa-card);margin-top:1px;border-left:4px solid #f9a825}}
  .term-detail-block h3{{margin:0 0 10px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid #f9a825;background:linear-gradient(90deg,#fff8e1 0%,transparent 60%)}}
  .term-detail-block .term-hi{{color:#e65100;font-weight:900}}
  .term-detail-lead{{padding:10px 14px;background:#fff8e1;color:#7a5a00;font-size:13px;font-weight:600;border-radius:3px;margin-bottom:10px;line-height:1.6}}
  .term-detail-list{{margin:0;padding:0;list-style:none}}
  .term-detail-list li{{padding:8px 12px;border-bottom:1px dashed var(--cwa-border);font-size:13px;line-height:1.6;color:var(--cwa-text)}}
  .term-detail-list li:last-child{{border-bottom:none}}
  .term-detail-list li:hover{{background:var(--cwa-hover)}}
  .term-detail-foot{{margin-top:12px;padding:10px 12px;background:var(--cwa-hover);border-radius:3px;font-size:11px;color:var(--cwa-text-muted);line-height:1.7}}
  .term-detail-foot strong{{color:var(--cwa-primary)}}

  /* ===== 天氣分析 ===== */
  .analysis-block{{border-left:4px solid var(--cwa-success)}}
  .analysis-block h3{{border-left-color:var(--cwa-success)}}
  .analysis-text{{margin:0;font-size:14px;line-height:1.9;color:var(--cwa-text);padding:8px 12px;background:var(--cwa-hover);border-radius:3px}}

  /* ===== 新聞列表 ===== */
  .news-list{{margin:0;padding:0;list-style:none;border:1px solid var(--cwa-border);border-radius:3px}}
  .news-list li{{padding:10px 14px;border-bottom:1px solid var(--cwa-border);font-size:13px;line-height:1.5;background:#fff;transition:background .1s}}
  .news-list li:last-child{{border-bottom:none}}
  .news-list li:hover{{background:var(--cwa-hover)}}
  .news-list a{{color:var(--cwa-primary);text-decoration:none;font-weight:500}}
  .news-list a:hover{{text-decoration:underline;color:var(--cwa-dark)}}
  .news-list .meta{{display:block;margin-top:4px;font-size:11px;color:var(--cwa-text-muted);font-family:ui-monospace,Menlo,monospace}}

  /* ===== 節氣提示條（Header 內） ===== */
  .term-strip{{margin-top:10px;padding:6px 12px;background:rgba(255,255,255,0.15);border-radius:20px;display:inline-block;font-size:13px;color:#fff;letter-spacing:.5px}}
  .term-emoji{{font-size:16px;margin-right:4px}}
  .term-name{{font-weight:700;color:#ffd54f;margin-right:6px}}
  .term-hint{{color:#e3f2fd;font-size:12px}}

  /* ===== 颱風警戒模式 ===== */
  body.typhoon-alert .header{{background:linear-gradient(180deg,#8b0000 0%,#c62828 100%);animation:typhoon-pulse 2s ease-in-out infinite;border-bottom-color:#fff59d}}
  .typhoon-strip{{background:#c62828;color:#fff;padding:8px;text-align:center;font-size:14px;font-weight:700;letter-spacing:1px;animation:typhoon-slide 8s linear infinite;box-shadow:0 2px 8px rgba(198,40,40,.4);position:sticky;top:0;z-index:900}}
  @keyframes typhoon-pulse{{0%,100%{{box-shadow:0 0 0 0 rgba(255,213,79,.6)}}50%{{box-shadow:0 0 20px 4px rgba(255,213,79,.4)}}}}
  @keyframes typhoon-slide{{0%,100%{{background:#c62828}}50%{{background:#e53935}}}}

  /* ===== 天氣吉祥物 ===== */
  .mascot{{position:fixed;right:16px;bottom:20px;width:66px;height:66px;background:#fff;border-radius:50%;border:3px solid var(--cwa-primary);box-shadow:0 4px 12px rgba(0,0,0,.2);display:flex;align-items:center;justify-content:center;z-index:1000;cursor:pointer;transition:transform .15s;animation:mascot-bounce 3s ease-in-out infinite}}
  .mascot:hover{{transform:scale(1.1)}}
  .mascot-face{{font-size:36px;line-height:1}}
  .mascot-sunny{{border-color:#f9a825;animation-duration:2s}}
  .mascot-mild{{border-color:#4caf50}}
  .mascot-rainy{{border-color:#1976d2}}
  .mascot-storm{{border-color:#c62828;animation:mascot-shake .3s ease-in-out infinite}}
  @keyframes mascot-bounce{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-6px)}}}}
  @keyframes mascot-shake{{0%,100%{{transform:translate(0,0) rotate(0)}}25%{{transform:translate(-2px,-2px) rotate(-4deg)}}50%{{transform:translate(2px,0) rotate(4deg)}}75%{{transform:translate(-2px,2px) rotate(-2deg)}}}}
  .mascot-bubble{{position:absolute;right:74px;bottom:8px;background:#fff;border:2px solid var(--cwa-primary);border-radius:14px;padding:8px 12px;font-size:12px;color:var(--cwa-text);white-space:nowrap;max-width:240px;min-width:140px;box-shadow:0 3px 10px rgba(0,0,0,.15);opacity:0;transform:translateX(10px);transition:all .3s;font-weight:600;text-align:right;line-height:1.4}}
  .mascot-bubble.show{{opacity:1;transform:translateX(0)}}
  .mascot-bubble::after{{content:"";position:absolute;right:-8px;top:16px;width:0;height:0;border-left:8px solid var(--cwa-primary);border-top:6px solid transparent;border-bottom:6px solid transparent}}
  @media (max-width:640px){{
    .mascot{{width:54px;height:54px;right:10px;bottom:14px}}
    .mascot-face{{font-size:28px}}
    .mascot-bubble{{right:60px;font-size:11px;padding:6px 10px;max-width:180px;min-width:110px}}
  }}

  /* ===== 地圖豪雨粒子動畫 ===== */
  .rain-particle{{pointer-events:none;font-size:16px;line-height:1;opacity:0;animation:raindrop 1.4s linear infinite}}
  .rain-particle span{{display:inline-block;animation-name:raindrop;animation-timing-function:linear;animation-iteration-count:infinite}}
  @keyframes raindrop{{0%{{transform:translateY(-24px);opacity:0}}20%{{opacity:.9}}80%{{opacity:.9}}100%{{transform:translateY(38px);opacity:0}}}}
  .county-label.storm-lvl{{animation:storm-pulse 1.6s ease-in-out infinite}}
  @keyframes storm-pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.08);filter:brightness(1.1)}}}}

  /* ===== 📽 投影模式：字體/圖示/按鈕全站放大 (適合會議室投影) ===== */
  body.projector{{font-size:18px}}
  body.projector .header{{padding:26px 22px 22px}}
  body.projector .header h1{{font-size:30px;letter-spacing:1px}}
  body.projector .header p{{font-size:15px}}
  body.projector .term-strip{{font-size:16px;padding:8px 16px}}
  body.projector .term-emoji{{font-size:20px}}
  body.projector .term-name{{font-size:18px}}
  body.projector .term-hint{{font-size:15px}}
  body.projector .refresh-bar{{padding:14px 18px;font-size:15px}}
  body.projector .refresh-bar button{{padding:11px 22px;font-size:15px}}
  body.projector .refresh-bar .refresh-time{{font-size:14px}}
  body.projector .refresh-bar .cwa-link{{font-size:14px;padding:9px 16px}}
  body.projector .accuracy-note{{font-size:14px;padding:12px 18px;line-height:1.7}}
  body.projector .toggle button{{padding:15px 28px;font-size:17px}}
  body.projector .period{{font-size:15px;padding:14px 18px}}
  body.projector .custom-range{{font-size:15px;padding:14px 18px}}
  body.projector .custom-range input[type=date]{{padding:8px 12px;font-size:15px}}
  body.projector .custom-range button{{padding:8px 20px;font-size:15px}}
  body.projector .legend-title{{font-size:17px}}
  body.projector .legend-row{{font-size:15px;margin:6px 0}}
  body.projector .legend-swatch{{width:34px;height:20px}}
  body.projector .county-label{{font-size:14px;padding:3px 8px}}
  body.projector .county-label .mm{{font-size:14px}}
  body.projector h3,body.projector .legend-title,body.projector .adv-block h3,body.projector .history-block h3,body.projector .term-detail-block h3,body.projector .crops-block h3,body.projector .towns-block h3,body.projector .rainy-block h3,body.projector .forecast-block h3,body.projector .analysis-block h3,body.projector .news-block h3,body.projector .impact h3,body.projector .ranking h3,body.projector .source h3{{font-size:20px;padding:8px 0 8px 14px}}
  body.projector .ranking table{{font-size:16px}}
  body.projector .ranking td{{padding:10px 12px}}
  body.projector .impact .rng{{font-size:15px;width:120px}}
  body.projector .impact .note{{font-size:15px}}
  body.projector .impact .group-title{{font-size:15px;padding:6px 12px}}
  body.projector .impact .info-note{{font-size:14px;padding:14px 16px;line-height:1.9}}
  body.projector .term-detail-lead{{font-size:15px;padding:12px 16px}}
  body.projector .term-detail-list li{{font-size:15px;padding:10px 14px}}
  body.projector .term-detail-foot{{font-size:13px;padding:12px 14px}}
  body.projector .crops-filters{{padding:14px}}
  body.projector .crops-f-row{{font-size:15px;gap:10px 18px}}
  body.projector .crops-f-row select{{padding:8px 12px;font-size:15px}}
  body.projector .crops-summary{{font-size:16px;padding:16px 20px}}
  body.projector .crops-summary .stat strong{{font-size:28px}}
  body.projector .crops-table{{font-size:15px}}
  body.projector .crops-table th{{font-size:14px;padding:11px 12px}}
  body.projector .crops-table td{{padding:10px 12px}}
  body.projector .crops-table td.cat{{font-size:26px}}
  body.projector .crops-table td.months .m{{font-size:13px;padding:2px 8px}}
  body.projector .towns-filters{{font-size:15px}}
  body.projector .towns-filters select{{padding:8px 12px;font-size:15px}}
  body.projector .towns-filters input[type=text]{{padding:8px 12px;font-size:15px}}
  body.projector .towns-legend{{font-size:13px}}
  body.projector .town-marker{{width:34px;height:34px;font-size:16px}}
  body.projector .rainy-filters{{font-size:15px}}
  body.projector .rainy-filters select{{padding:8px 12px;font-size:15px}}
  body.projector .rainy-summary{{font-size:16px;padding:16px 20px}}
  body.projector .rainy-summary .loc{{font-size:18px}}
  body.projector .rainy-summary .stat strong{{font-size:28px}}
  body.projector .rainy-list{{font-size:14px}}
  body.projector .rainy-list .day{{font-size:14px;padding:5px 12px}}
  body.projector .cal-cell{{min-height:64px}}
  body.projector .cal-cell .d{{font-size:16px}}
  body.projector .cal-cell .wk{{font-size:11px}}
  body.projector .cal-cell .mm{{font-size:13px}}
  body.projector .cal-head{{font-size:13px;padding:8px 4px}}
  body.projector .fcst-mode-bar button{{font-size:14px;padding:9px 18px}}
  body.projector .fcst-checkboxes label{{font-size:14px;padding:6px 14px}}
  body.projector .fcst-info{{font-size:14px;padding:12px 16px}}
  body.projector .fcst-day-tabs button{{font-size:15px;padding:12px 20px}}
  body.projector .fcst-legend-title{{font-size:14px}}
  body.projector .fcst-bar{{font-size:14px;margin:5px 0}}
  body.projector .fcst-bar-color{{width:32px;height:18px}}
  body.projector .fcst-bar-label{{font-size:13px;width:56px}}
  body.projector .fcst-bar-range{{font-size:13px}}
  body.projector .fcst-legend-hint{{font-size:12px}}
  body.projector .fcst-ranking-head h4{{font-size:16px}}
  body.projector .fcst-ranking-head button{{font-size:14px;padding:7px 14px}}
  body.projector .fcst-ranking table{{font-size:15px}}
  body.projector .fcst-ranking th{{font-size:14px;padding:11px 12px}}
  body.projector .fcst-ranking td{{padding:10px 12px}}
  body.projector .fcst-ranking td.lvl{{font-size:13px}}
  body.projector .analysis-text{{font-size:16px;padding:14px 18px;line-height:2}}
  body.projector .news-list li{{font-size:15px;padding:12px 16px}}
  body.projector .news-list .meta{{font-size:12px}}
  body.projector .source ul{{font-size:14px;line-height:2}}
  body.projector .footer{{font-size:13px;padding:20px}}
  body.projector .history-filters{{font-size:15px}}
  body.projector .history-filters select{{padding:8px 12px;font-size:15px}}
  body.projector .history-filters button{{padding:9px 20px;font-size:15px}}
  body.projector .history-status{{font-size:15px;padding:12px 16px}}
  body.projector .history-table{{font-size:15px}}
  body.projector .history-table th{{font-size:14px;padding:11px 12px}}
  body.projector .history-table td{{padding:10px 12px;font-size:15px}}
  body.projector .history-report{{font-size:15px;padding:16px 20px;line-height:2}}
  body.projector .adv-cbs label{{font-size:14px;padding:6px 14px}}
  body.projector .adv-actions{{font-size:15px}}
  body.projector .adv-actions button{{padding:10px 20px;font-size:15px}}
  body.projector .adv-actions .est{{font-size:14px}}
  body.projector .adv-status{{font-size:15px;padding:12px 16px}}
  body.projector .adv-view-tabs button{{font-size:14px;padding:10px 18px}}
  body.projector .adv-table{{font-size:14px}}
  body.projector .adv-table th{{font-size:13px;padding:10px}}
  body.projector .adv-table td{{padding:9px 10px}}
  body.projector .adv-matrix th,body.projector .adv-matrix td{{font-size:14px;padding:9px;min-width:72px}}
  body.projector .adv-matrix td .d{{font-size:11px}}
  body.projector .adv-analysis{{font-size:15px;padding:16px 20px;line-height:2}}
  body.projector .adv-analysis h4{{font-size:17px}}
  body.projector .adv-analysis li{{margin:6px 0}}
  body.projector .mascot{{width:82px;height:82px;right:20px;bottom:24px}}
  body.projector .mascot-face{{font-size:46px}}
  body.projector .mascot-bubble{{font-size:14px;max-width:300px;padding:10px 14px}}
  body.projector .rm-content{{max-width:600px}}
  body.projector .rm-head{{font-size:17px;padding:16px 20px}}
  body.projector .rm-value .num{{font-size:34px}}
  body.projector .rm-cmps li{{font-size:15px;padding:12px 14px}}
  body.projector .rm-impact{{font-size:15px}}

  /* ===== 浮動版權水印 (農業配色 · 咖啡+深綠+稻穗紋) ===== */
  .copyright-badge{{position:fixed;left:190px;bottom:16px;z-index:999;background:linear-gradient(135deg,#6d4c1f 0%,#5d4037 40%,#1b5e20 100%);color:#fff;padding:8px 18px 8px 8px;border-radius:40px;box-shadow:0 6px 20px rgba(93,64,55,.55),0 2px 6px rgba(0,0,0,.3);display:flex;align-items:center;gap:12px;border:3px solid #d4a017;user-select:none;transition:transform .15s;position:fixed;overflow:hidden}}
  /* 稻穗/作物花紋層 */
  .copyright-badge::before{{content:"";position:absolute;inset:0;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='60' height='60' viewBox='0 0 60 60'><g fill='%23ffd54f' opacity='0.15'><text x='4' y='18' font-size='16'>🌾</text><text x='30' y='42' font-size='14'>🌱</text><text x='4' y='56' font-size='12'>🍃</text></g></svg>");background-size:60px 60px;pointer-events:none;opacity:.7}}
  .copyright-badge:hover{{transform:translateY(-2px) scale(1.03)}}
  .copyright-badge > *{{position:relative;z-index:1}}
  .copyright-badge .cb-avatar{{width:56px;height:56px;border-radius:50%;object-fit:cover;border:3px solid #d4a017;background:#fff;flex-shrink:0;box-shadow:0 2px 4px rgba(0,0,0,.4),0 0 0 1px rgba(255,255,255,.4) inset}}
  .copyright-badge .cb-text{{display:flex;flex-direction:column;gap:2px;line-height:1.2}}
  .copyright-badge .cb-line1{{font-size:12px;font-weight:700;color:#fff8b3;letter-spacing:1.5px;text-shadow:0 1px 2px rgba(0,0,0,.4)}}
  .copyright-badge .cb-line1::before{{content:"🌾 ";font-size:11px;filter:drop-shadow(0 1px 1px rgba(0,0,0,.3))}}
  .copyright-badge .cb-seal{{background:linear-gradient(180deg,#f4d03f,#d4a017);color:#3e2723;font-weight:900;padding:4px 14px;border-radius:14px;font-family:"STKaiti","BiauKai","STHeiti",serif;letter-spacing:4px;font-size:18px;box-shadow:inset 0 -2px 3px rgba(0,0,0,.25),inset 0 1px 2px rgba(255,255,255,.5),0 1px 3px rgba(0,0,0,.3);border:1.5px solid #b8860b;text-shadow:0 1px 1px rgba(255,255,255,.3)}}
  body:has(.cwa-sidebar.collapsed) .copyright-badge{{left:68px}}
  @media (max-width:768px){{
    .copyright-badge{{left:60px;bottom:10px;padding:6px 14px 6px 6px;gap:8px;border-width:2px}}
    .copyright-badge .cb-avatar{{width:44px;height:44px;border-width:2px}}
    .copyright-badge .cb-line1{{font-size:10px;letter-spacing:1px}}
    .copyright-badge .cb-seal{{font-size:14px;padding:3px 8px;letter-spacing:3px}}
  }}
  @media (max-width:480px){{
    .copyright-badge{{padding:5px 10px 5px 5px}}
    .copyright-badge .cb-avatar{{width:36px;height:36px}}
    .copyright-badge .cb-line1{{display:none}}
    .copyright-badge .cb-seal{{font-size:13px;padding:3px 8px}}
  }}

  /* ===== 銷售分析區塊 (第 4 tab) ===== */
  .sales-block{{padding:16px 20px;background:var(--cwa-card);border-left:4px solid #f57c00}}
  .sales-block h3{{margin:0 0 14px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid #f57c00;background:linear-gradient(90deg,#fff3e0 0%,transparent 60%);display:flex;align-items:center;gap:10px}}
  .sales-warn{{background:#c62828;color:#fff;font-size:11px;padding:3px 8px;border-radius:4px;font-weight:700;letter-spacing:1px}}
  .sales-kpi-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:12px 0 16px}}
  .sales-kpi{{background:#fff;border:1.5px solid var(--cwa-border);border-left:4px solid #90a4ae;padding:10px 12px;border-radius:4px;text-align:center}}
  .sales-kpi.hi{{border-left-color:#f57c00;background:#fff8e1}}
  .sales-kpi.hi2{{border-left-color:#2e7d32;background:#e8f5e9}}
  .sales-kpi .lbl{{font-size:12px;color:var(--cwa-text-muted);font-weight:600}}
  .sales-kpi .val{{font-size:26px;font-weight:900;color:#c62828;line-height:1.1;margin-top:3px;font-family:ui-monospace,Menlo,monospace}}
  .sales-kpi .unit{{font-size:11px;color:var(--cwa-text-muted)}}
  .sales-controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--cwa-hover);padding:10px 12px;border-radius:4px;margin-bottom:10px;font-size:13px}}
  .sales-controls select{{padding:5px 8px;border:1px solid var(--cwa-border);border-radius:3px;font-family:inherit;font-size:13px}}
  .sales-controls label{{font-weight:700;color:var(--cwa-primary)}}
  .sales-hint{{margin-left:auto;font-size:12px;color:var(--cwa-text-muted)}}
  .sales-chart-wrap{{background:#fff;border:1px solid var(--cwa-border);border-radius:4px;padding:10px;overflow-x:auto}}
  #salesChart{{min-width:640px;width:100%}}
  #salesChart svg{{width:100%;height:auto;display:block}}
  .sales-table-wrap{{margin-top:14px;overflow-x:auto}}
  .sales-table{{width:100%;border-collapse:collapse;font-size:12.5px;min-width:800px}}
  .sales-table th,.sales-table td{{padding:6px 5px;border:1px solid var(--cwa-border);text-align:center;font-family:ui-monospace,Menlo,monospace}}
  .sales-table th{{background:linear-gradient(180deg,#fff3e0,#ffe0b2);color:#e65100;font-weight:900;font-size:12px}}
  .sales-table th.total{{background:linear-gradient(180deg,#ffcdd2,#ef9a9a);color:#b71c1c}}
  .sales-table td:first-child{{font-weight:900;background:#f5f5f5;color:#333;font-size:13px}}
  .sales-table td.total{{font-weight:900;background:#ffebee;color:#c62828;font-size:14px}}
  .sales-table td.hi{{background:#c62828;color:#fff;font-weight:900}}
  .sales-table td.mid{{background:#f57c00;color:#fff}}
  .sales-table td.low{{background:#e0e0e0;color:#666}}
  .sales-table td.empty{{background:#fafafa;color:#ccc}}
  .sales-edit-bar{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:14px;padding:10px 12px;background:#f5f5f5;border-radius:4px;font-size:12px}}
  .sales-edit-bar .btn-edit,.sales-edit-bar .btn-reset,.sales-edit-bar .btn-export{{padding:7px 14px;background:linear-gradient(135deg,#0d47a1,#003c8f);color:#fff;border:none;border-radius:4px;font-weight:700;cursor:pointer;font-size:13px;font-family:inherit;letter-spacing:.5px;box-shadow:0 2px 4px rgba(13,71,161,.3);transition:transform .1s}}
  .sales-edit-bar .btn-edit:hover,.sales-edit-bar .btn-reset:hover,.sales-edit-bar .btn-export:hover{{transform:translateY(-1px);box-shadow:0 3px 6px rgba(13,71,161,.4)}}
  .sales-edit-bar .btn-reset{{background:linear-gradient(135deg,#c62828,#8b0000);box-shadow:0 2px 4px rgba(198,40,40,.3)}}
  .sales-edit-bar .btn-export{{background:linear-gradient(135deg,#2e7d32,#1b5e20);box-shadow:0 2px 4px rgba(46,125,50,.3)}}
  .sales-edit-bar .edit-hint{{color:#666;font-size:11px;margin-right:auto}}
  .sales-edit-panel{{margin-top:10px;padding:14px;background:#fff8e1;border:2px dashed #f57c00;border-radius:6px}}
  .sales-edit-head{{font-weight:900;color:#e65100;margin-bottom:10px;font-size:13px;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center}}
  .sales-edit-status{{font-size:11px;color:#2e7d32;font-weight:700}}
  .sales-edit-tablewrap{{overflow-x:auto;background:#fff;border:1px solid var(--cwa-border);border-radius:4px}}
  .sales-edit-table{{width:100%;border-collapse:collapse;font-size:12px;min-width:850px}}
  .sales-edit-table th,.sales-edit-table td{{padding:4px;border:1px solid var(--cwa-border);text-align:center}}
  .sales-edit-table th{{background:linear-gradient(180deg,#fff3e0,#ffe0b2);color:#e65100;font-weight:900;font-size:11px}}
  .sales-edit-table td.year-cell{{background:#f5f5f5;font-weight:900;color:#333}}
  .sales-edit-table input.month-cell{{width:100%;padding:5px 3px;text-align:center;border:1px solid transparent;border-radius:3px;background:transparent;font-family:ui-monospace,Menlo,monospace;font-size:12px;transition:all .1s}}
  .sales-edit-table input.month-cell:hover{{border-color:#ffb74d;background:#fff3e0}}
  .sales-edit-table input.month-cell:focus{{outline:none;border-color:#f57c00;background:#fff;box-shadow:inset 0 0 0 1px #f57c00}}
  .sales-edit-table input.month-cell.changed{{background:#fff8e1;color:#e65100;font-weight:900}}
  .sales-edit-table .del-btn{{background:#c62828;color:#fff;border:none;border-radius:3px;padding:3px 8px;font-size:11px;cursor:pointer}}
  .sales-add-row{{margin-top:12px;display:flex;gap:8px;align-items:center;font-size:13px}}
  .sales-add-row input{{padding:5px 8px;border:1px solid var(--cwa-border);border-radius:3px}}
  .sales-add-row button{{padding:6px 14px;background:#2e7d32;color:#fff;border:none;border-radius:3px;font-weight:700;cursor:pointer;font-family:inherit}}
  .sales-add-row button:hover{{background:#1b5e20}}
  .sales-analysis{{margin-top:14px;font-size:13px;line-height:1.7;color:var(--cwa-text)}}
  .sales-exec{{background:linear-gradient(135deg,#c62828 0%,#8b0000 50%,#4a0000 100%);color:#fff;padding:16px 20px;border-radius:8px;margin-bottom:14px;box-shadow:0 4px 12px rgba(198,40,40,.3)}}
  .sales-exec .es-title{{font-size:15px;font-weight:900;margin-bottom:12px;letter-spacing:1px;border-bottom:2px solid rgba(255,255,255,.3);padding-bottom:6px}}
  .sales-exec .es-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}}
  .sales-exec .es-item{{background:rgba(255,255,255,.12);padding:10px 12px;border-radius:6px;border:1px solid rgba(255,255,255,.15)}}
  .sales-exec .es-item.up{{border-left:4px solid #4caf50}}
  .sales-exec .es-item.dn{{border-left:4px solid #ffab91}}
  .sales-exec .es-item.hi{{background:rgba(255,213,79,.2);border-left:4px solid #ffd54f}}
  .sales-exec .es-item .lbl{{font-size:11px;color:rgba(255,255,255,.8);font-weight:600;letter-spacing:.5px}}
  .sales-exec .es-item .val{{font-size:24px;font-weight:900;color:#ffd54f;font-family:ui-monospace,Menlo,monospace;line-height:1.1;margin-top:4px}}
  .sales-exec .es-item .val span{{font-size:13px;color:rgba(255,213,79,.8)}}
  .sales-exec .es-item .unit{{font-size:10px;color:rgba(255,255,255,.6);margin-top:2px}}

  .sales-dashboard{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-bottom:14px}}
  .sales-dashboard .db-card{{background:#fff;border:1px solid var(--cwa-border);border-radius:6px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
  .sales-dashboard .db-head{{font-size:13px;font-weight:900;color:#c62828;padding-bottom:8px;border-bottom:2px solid #c62828;margin-bottom:10px}}
  .sales-dashboard .db-body svg{{width:100%;height:auto;display:block}}
  .sales-dashboard .db-insight{{margin-top:10px;padding:8px 10px;background:#ffebee;border-left:3px solid #c62828;border-radius:0 4px 4px 0;font-size:11.5px;color:#333;line-height:1.5}}

  .sales-swot{{background:#fff;border:1px solid var(--cwa-border);border-radius:6px;padding:14px 16px;margin-bottom:14px}}
  .sales-swot .swot-title{{font-size:14px;font-weight:900;color:#c62828;padding-bottom:8px;border-bottom:2px solid #c62828;margin-bottom:12px}}

  .sales-actions{{background:linear-gradient(90deg,#ffebee,#fff3e0);border:1px solid #c62828;border-radius:6px;padding:14px 16px;margin-bottom:12px}}
  .sales-actions .ra-title{{font-size:14px;font-weight:900;color:#c62828;padding-bottom:8px;border-bottom:2px solid #c62828;margin-bottom:12px}}
  .sales-analysis h4{{margin:0 0 8px;font-size:14px;color:#e65100;font-weight:900}}
  .sales-analysis strong{{color:#c62828;font-weight:900}}
  .sales-analysis .growth{{color:#2e7d32;font-weight:900}}
  .sales-analysis .drop{{color:#c62828;font-weight:900}}
  .sales-analysis ul{{margin:6px 0 0;padding-left:20px}}
  .sales-analysis li{{margin:3px 0}}
  @media (max-width:640px){{
    .sales-kpi .val{{font-size:20px}}
    .sales-hint{{width:100%;margin-left:0}}
  }}

  /* ===== 左側浮動導覽 (仿 CODIS StationData sidebar) ===== */
  .cwa-sidebar{{position:fixed;top:0;left:0;bottom:0;width:170px;background:linear-gradient(180deg,#003c8f 0%,#002171 100%);color:#fff;padding:14px 0;box-shadow:2px 0 12px rgba(0,0,0,.25);z-index:950;display:flex;flex-direction:column;transition:width .2s;overflow:hidden}}
  .cwa-sidebar.collapsed{{width:48px}}
  .cwa-sidebar-toggle{{position:absolute;top:8px;right:6px;width:32px;height:32px;background:rgba(255,255,255,.15);color:#fff;border:none;border-radius:4px;font-size:16px;cursor:pointer;transition:background .1s}}
  .cwa-sidebar-toggle:hover{{background:rgba(255,255,255,.3)}}
  .cwa-sidebar-title{{padding:10px 16px 12px;font-size:11px;color:rgba(255,255,255,.65);font-weight:700;letter-spacing:2px;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:8px;margin-right:36px}}
  .cwa-sidebar.collapsed .cwa-sidebar-title,.cwa-sidebar.collapsed .cwa-sidebar-nav a span,.cwa-sidebar.collapsed .cwa-sidebar-foot{{display:none}}
  .cwa-sidebar-nav{{flex:1;overflow-y:auto;padding:0 8px}}
  .cwa-sidebar-nav a{{display:flex;align-items:center;gap:10px;padding:9px 12px;color:rgba(255,255,255,.85);text-decoration:none;font-size:13.5px;font-weight:600;border-radius:4px;margin-bottom:2px;transition:all .12s;border-left:3px solid transparent}}
  .cwa-sidebar-nav a::before{{content:attr(data-icon);font-size:16px;line-height:1}}
  .cwa-sidebar-nav a:hover{{background:rgba(255,255,255,.12);color:#fff;border-left-color:#ffd54f;padding-left:16px}}
  .cwa-sidebar-nav a.active{{background:linear-gradient(90deg,rgba(255,213,79,.2),transparent);color:#ffd54f;border-left-color:#ffd54f;font-weight:900}}
  .cwa-sidebar-foot{{padding:10px 16px;font-size:11px;color:rgba(255,255,255,.6);border-top:1px solid rgba(255,255,255,.1)}}
  .cwa-sidebar-foot .upd{{margin-bottom:6px}}
  .cwa-sidebar-foot .src-link{{color:#ffd54f;text-decoration:none;font-weight:700;display:inline-flex;align-items:center;gap:4px}}
  .cwa-sidebar-foot .src-link:hover{{text-decoration:underline}}
  /* body 讓出左側空間 */
  body{{padding-left:170px;transition:padding-left .2s}}
  body:has(.cwa-sidebar.collapsed){{padding-left:48px}}
  @media (max-width:768px){{
    .cwa-sidebar{{width:44px}}
    .cwa-sidebar-title,.cwa-sidebar-nav a span,.cwa-sidebar-foot,.cwa-sidebar-nav a::before{{}}
    .cwa-sidebar-nav a{{justify-content:center;padding:10px 4px;font-size:0}}
    .cwa-sidebar-nav a::before{{font-size:18px}}
    body{{padding-left:44px}}
    .cwa-sidebar-title,.cwa-sidebar-foot{{display:none}}
  }}

  /* ===== 浮動雨量色階條 (貼地圖右上角, 隨地圖移動) ===== */
  #map, #fcstMap{{position:relative}}
  .legend-fab{{position:absolute;right:10px;top:10px;z-index:850;background:linear-gradient(180deg,#2a2a2a,#1a1a1a);color:#fff;border-radius:8px;padding:8px 10px 10px;box-shadow:0 3px 12px rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.1);transition:transform .2s;user-select:none;font-size:11px}}
  .legend-fab.collapsed{{transform:translateX(calc(100% - 30px))}}
  .legend-fab-head{{display:flex;align-items:center;gap:6px;padding-bottom:6px;border-bottom:1px solid rgba(255,255,255,.15);margin-bottom:8px}}
  .legend-fab-head .lf-title{{font-weight:900;font-size:12px;flex:1}}
  .legend-fab-head .lf-unit{{color:#ffd54f;font-weight:700;font-size:10px}}
  .legend-fab-head .lf-toggle{{background:rgba(255,255,255,.15);color:#fff;border:none;width:20px;height:20px;border-radius:3px;cursor:pointer;font-size:10px;transition:background .1s}}
  .legend-fab-head .lf-toggle:hover{{background:rgba(255,255,255,.3)}}
  .legend-fab.collapsed .lf-toggle{{transform:rotate(180deg)}}
  .legend-fab-bar{{display:flex;flex-direction:column;gap:0;min-width:78px}}
  .legend-fab-bar .lf-row{{display:flex;align-items:center;gap:6px;font-family:ui-monospace,Menlo,monospace;font-size:10px}}
  .legend-fab-bar .lf-sw{{width:26px;height:14px;flex-shrink:0;border:1px solid rgba(255,255,255,.2)}}
  .legend-fab-bar .lf-val{{color:#fff;font-weight:700;line-height:1.6}}
  .legend-fab-bar .lf-lbl{{color:rgba(255,255,255,.6);font-size:9px;margin-left:auto}}
  .legend-fab-foot{{margin-top:8px;font-size:9px;color:rgba(255,255,255,.55);border-top:1px solid rgba(255,255,255,.1);padding-top:6px;line-height:1.4}}
  @media (max-width:768px){{
    .legend-fab{{right:8px;top:8px;font-size:10px;padding:6px 8px}}
    .legend-fab-bar .lf-sw{{width:20px;height:11px}}
    .legend-fab-bar .lf-row{{font-size:9px}}
  }}

  /* ===== 歷史地圖 tab ===== */
  .hist-map-block{{padding:16px 20px;background:var(--cwa-card);border-left:4px solid #7b1fa2}}
  .hist-map-block h3{{margin:0 0 14px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid #7b1fa2;background:linear-gradient(90deg,#f3e5f5 0%,transparent 60%);display:flex;flex-wrap:wrap;align-items:center;gap:10px}}
  .hist-map-controls{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--cwa-hover);padding:10px 12px;border-radius:4px;margin-bottom:10px;font-size:13px}}
  .hist-map-controls label{{font-weight:700;color:var(--cwa-primary)}}
  .hist-map-controls select{{padding:6px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-family:inherit;font-size:13px}}
  .hist-map-info{{padding:10px 12px;background:linear-gradient(90deg,#f3e5f5,#fff);border-left:3px solid #7b1fa2;border-radius:4px;margin-bottom:10px;font-size:13px;color:#333;line-height:1.6}}
  #histMap{{width:100%;height:520px;background:#cfe9ff;border:1px solid var(--cwa-border);border-radius:3px;position:relative}}
  .hist-map-ranking{{margin-top:14px;overflow-x:auto}}
  .hist-map-ranking h4{{margin:0 0 8px;font-size:13px;color:#7b1fa2;font-weight:900}}
  .hist-map-ranking table{{width:100%;border-collapse:collapse;font-size:12px}}
  .hist-map-ranking th{{background:linear-gradient(180deg,#7b1fa2,#4a148c);color:#fff;padding:7px 8px;font-weight:700;font-size:11px;text-align:center}}
  .hist-map-ranking th.n{{text-align:right}}
  .hist-map-ranking td{{padding:6px 8px;border-bottom:1px solid var(--cwa-border);text-align:center}}
  .hist-map-ranking td.n{{text-align:right;font-family:ui-monospace,Menlo,monospace;font-weight:700}}
  .hist-map-ranking tr:nth-child(odd) td{{background:#fafafa}}
  .hist-map-ranking td.top{{background:#c62828 !important;color:#fff;font-weight:900}}

  /* ===== 廠商排名 tab ===== */
  .rank-block{{padding:16px 20px;background:var(--cwa-card);border-left:4px solid #6a1b9a}}
  .rank-block h3{{margin:0 0 14px;font-size:15px;font-weight:700;color:var(--cwa-text);padding:6px 0 6px 12px;border-left:4px solid #6a1b9a;background:linear-gradient(90deg,#f3e5f5 0%,transparent 60%);display:flex;flex-wrap:wrap;align-items:center;gap:10px}}
  .rank-src{{font-size:11px;color:#666;font-weight:600;background:#fff;padding:3px 8px;border-radius:10px;border:1px solid var(--cwa-border)}}
  .rank-refresh-btn{{margin-left:auto;background:linear-gradient(135deg,#2e7d32,#1b5e20);color:#fff;border:none;padding:7px 14px;border-radius:20px;font-weight:900;cursor:pointer;font-size:12px;box-shadow:0 3px 8px rgba(46,125,50,.35);transition:all .15s;font-family:inherit;letter-spacing:.5px;white-space:nowrap}}
  .rank-refresh-btn:hover{{transform:translateY(-2px);box-shadow:0 5px 12px rgba(46,125,50,.5)}}
  .rank-refresh-btn:disabled{{background:#999;cursor:not-allowed;transform:none;box-shadow:none}}
  .rank-actions-link{{font-size:11px;color:#6a1b9a;text-decoration:none;padding:5px 10px;border:1px solid #6a1b9a;border-radius:14px;font-weight:700;transition:all .1s;white-space:nowrap}}
  .rank-actions-link:hover{{background:#6a1b9a;color:#fff}}
  .rank-kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:14px}}
  .rank-kpi{{background:#fff;border:1.5px solid var(--cwa-border);border-left:4px solid #90a4ae;padding:10px 12px;border-radius:4px;text-align:center}}
  .rank-kpi.hi{{border-left-color:#c62828;background:#ffebee}}
  .rank-kpi.hi2{{border-left-color:#2e7d32;background:#e8f5e9}}
  .rank-kpi.upd{{border-left-color:#6a1b9a;background:#f3e5f5}}
  .rank-kpi .lbl{{font-size:12px;color:var(--cwa-text-muted);font-weight:700}}
  .rank-kpi .val{{font-size:22px;font-weight:900;color:#6a1b9a;line-height:1.1;margin-top:3px;font-family:ui-monospace,Menlo,monospace}}
  .rank-filters{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;background:var(--cwa-hover);padding:10px 12px;border-radius:4px;margin-bottom:10px;font-size:13px}}
  .rank-filters label{{font-weight:700;color:var(--cwa-primary)}}
  .rank-filters select{{padding:5px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-family:inherit;font-size:13px}}
  .rank-count{{margin-left:auto;font-size:12px;color:#6a1b9a;font-weight:700}}
  .rank-cat-summary{{margin-bottom:12px;padding:10px 12px;background:#fff;border:1px solid var(--cwa-border);border-radius:4px;font-size:12px}}
  .rank-cat-summary .head{{font-weight:900;color:#6a1b9a;margin-bottom:6px}}
  .rank-cat-summary table{{width:100%;border-collapse:collapse}}
  .rank-cat-summary th{{padding:5px 8px;background:#f3e5f5;color:#6a1b9a;font-weight:700;font-size:11px;text-align:center;border:1px solid var(--cwa-border)}}
  .rank-cat-summary td{{padding:5px 8px;text-align:center;border:1px solid var(--cwa-border);font-family:ui-monospace,Menlo,monospace}}
  .rank-cat-summary td.name{{text-align:left;font-weight:700;color:#333;font-family:inherit}}
  .rank-cat-summary td.tier-hi{{background:#ffebee;color:#c62828;font-weight:900}}
  .rank-table-wrap{{overflow-x:auto;border:1px solid var(--cwa-border);border-radius:4px;background:#fff}}
  .rank-table{{width:100%;border-collapse:collapse;font-size:12.5px;min-width:700px}}
  .rank-table th{{background:linear-gradient(180deg,#6a1b9a,#4a148c);color:#fff;padding:9px 8px;font-weight:700;font-size:12px;text-align:center;white-space:nowrap;position:sticky;top:0;cursor:pointer}}
  .rank-table th.n{{text-align:right}}
  .rank-table td{{padding:7px 8px;border-bottom:1px solid var(--cwa-border);vertical-align:middle}}
  .rank-table td.rank{{text-align:center;font-weight:900;color:#6a1b9a;font-family:ui-monospace,Menlo,monospace}}
  .rank-table td.rank.top3{{background:linear-gradient(135deg,#ffd54f,#ffa000);color:#333}}
  .rank-table td.name{{font-weight:700}}
  .rank-table td.name.dachan{{background:linear-gradient(90deg,#ffcdd2,transparent);color:#b71c1c;font-weight:900}}
  .rank-table td.n{{text-align:right;font-family:ui-monospace,Menlo,monospace;font-weight:700}}
  .rank-table td.n.big{{color:#c62828;font-size:14px}}
  .rank-table td.cats{{font-size:11px;color:#666}}
  .rank-table td.cats .cat{{display:inline-block;background:#f3e5f5;color:#6a1b9a;padding:1px 6px;border-radius:8px;margin:1px 2px;font-family:ui-monospace,Menlo,monospace;font-size:10px;font-weight:700;cursor:pointer;transition:all .1s}}
  .rank-table td.cats .cat:hover{{background:#6a1b9a;color:#fff;transform:scale(1.1)}}
  .code-link{{color:#6a1b9a;font-weight:900;cursor:pointer;text-decoration:underline dotted;font-family:ui-monospace,Menlo,monospace}}
  .code-link:hover{{background:#6a1b9a;color:#fff;padding:1px 4px;border-radius:3px;text-decoration:none}}

  /* 品目說明 Modal */
  .code-info-modal{{position:fixed;inset:0;background:rgba(0,0,0,.5);display:none;justify-content:center;align-items:center;z-index:9999;padding:16px;backdrop-filter:blur(4px)}}
  .code-info-modal.open{{display:flex;animation:fadeIn .15s}}
  .cim-card{{background:#fff;max-width:520px;width:100%;max-height:90vh;overflow-y:auto;border-radius:12px;padding:20px 24px;box-shadow:0 20px 60px rgba(0,0,0,.4);position:relative}}
  .cim-close{{position:absolute;top:12px;right:14px;background:#f0f0f0;border:none;width:32px;height:32px;border-radius:50%;font-size:14px;cursor:pointer;font-weight:900;color:#666;transition:all .1s}}
  .cim-close:hover{{background:#c62828;color:#fff}}
  .cim-code{{display:inline-block;color:#fff;padding:6px 14px;border-radius:6px;font-family:ui-monospace,Menlo,monospace;font-weight:900;font-size:18px;margin-bottom:6px;box-shadow:0 2px 6px rgba(0,0,0,.2)}}
  .cim-name{{font-size:22px;font-weight:900;color:#333;margin-bottom:4px}}
  .cim-source{{font-size:13px;font-weight:700;margin-bottom:14px}}
  .cim-row{{display:flex;gap:12px;padding:8px 0;border-top:1px solid #eee}}
  .cim-lbl{{width:100px;font-weight:900;color:#666;font-size:13px;flex-shrink:0}}
  .cim-val{{flex:1;color:#333;font-size:13px;line-height:1.6}}
  .cim-footer{{margin-top:14px;padding-top:10px;border-top:1px solid #eee;font-size:10px;color:#888;text-align:center}}
  .rank-table tr:nth-child(odd) td{{background:#fafafa}}
  .rank-table tr:hover td{{background:#f3e5f5}}
  /* 推薦名單監控 (新違規/新上架/下架) */
  .rank-monitor{{margin:12px 0}}
  .mon-title{{font-size:14px;font-weight:900;color:#6b3300;padding:8px 12px;background:linear-gradient(90deg,#fff3e0,transparent);border-left:4px solid #6b3300;border-radius:0 4px 4px 0;margin-bottom:10px}}
  .mon-title .mon-sub{{font-size:12px;color:#555;font-weight:600;margin-left:12px}}
  .mon-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}}
  .mon-card{{background:#fff;border:1px solid var(--cwa-border);border-radius:6px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
  .mon-card .mon-h{{padding:10px 14px;color:#fff;font-weight:900;font-size:13px}}
  .mon-card.mon-viol .mon-h{{background:linear-gradient(135deg,#c92a2a,#8b0000)}}
  .mon-card.mon-add .mon-h{{background:linear-gradient(135deg,#2d6a4f,#1b4332)}}
  .mon-card.mon-rm .mon-h{{background:linear-gradient(135deg,#795548,#3e2723)}}
  .mon-card ul{{list-style:none;margin:0;padding:0;max-height:280px;overflow-y:auto}}
  .mon-card li{{padding:8px 12px;border-bottom:1px solid #f0f0f0;font-size:12px;line-height:1.5}}
  .mon-card li:last-child{{border-bottom:0}}
  .mon-card .tag{{display:inline-block;background:#e0e0e0;color:#555;padding:1px 6px;border-radius:3px;font-family:ui-monospace,Menlo,monospace;font-size:10px;font-weight:700;margin-right:4px}}
  .mon-card .who{{font-size:10px;color:#888;margin-top:2px}}
  .mon-card .reason{{margin-top:4px;padding:3px 6px;background:#ffebee;color:#c62828;font-size:10.5px;border-radius:3px}}

  .rank-analysis{{margin-top:14px;padding:0;background:transparent;font-size:13px;line-height:1.7;color:var(--cwa-text)}}
  /* Executive Summary */
  .rank-exec-summary{{background:linear-gradient(135deg,#4a148c 0%,#6a1b9a 50%,#7b1fa2 100%);color:#fff;padding:16px 20px;border-radius:8px;margin-bottom:14px;box-shadow:0 4px 12px rgba(106,27,154,.3)}}
  .rank-exec-summary .es-title{{font-size:15px;font-weight:900;margin-bottom:12px;letter-spacing:1px;border-bottom:2px solid rgba(255,255,255,.3);padding-bottom:6px}}
  .rank-exec-summary .es-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}}
  .rank-exec-summary .es-item{{background:rgba(255,255,255,.12);padding:10px 12px;border-radius:6px;backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.15)}}
  .rank-exec-summary .es-item .lbl{{font-size:11px;color:rgba(255,255,255,.8);font-weight:600;letter-spacing:.5px}}
  .rank-exec-summary .es-item .val{{font-size:26px;font-weight:900;color:#ffd54f;font-family:ui-monospace,Menlo,monospace;line-height:1.1;margin-top:4px}}
  .rank-exec-summary .es-item .val span{{font-size:14px;color:rgba(255,213,79,.8)}}
  .rank-exec-summary .es-item .unit{{font-size:10px;color:rgba(255,255,255,.6);margin-top:2px}}

  /* Dashboard 3 欄圖表區 */
  .rank-dashboard{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px;margin-bottom:16px}}
  .db-card{{background:#fff;border:1px solid var(--cwa-border);border-radius:6px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
  .db-head{{font-size:13px;font-weight:900;color:#6a1b9a;padding-bottom:8px;border-bottom:2px solid #6a1b9a;margin-bottom:10px}}
  .db-body svg{{width:100%;height:auto;display:block}}
  .db-insight{{margin-top:10px;padding:8px 10px;background:#f3e5f5;border-left:3px solid #6a1b9a;border-radius:0 4px 4px 0;font-size:11.5px;color:#333;line-height:1.5}}

  /* SWOT */
  .rank-swot{{background:#fff;border:1px solid var(--cwa-border);border-radius:6px;padding:14px 16px;margin-bottom:14px}}
  .swot-title{{font-size:14px;font-weight:900;color:#6a1b9a;padding-bottom:8px;border-bottom:2px solid #6a1b9a;margin-bottom:12px}}
  .swot-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}}
  .swot-cell{{padding:10px 12px;border-radius:5px;font-size:12px}}
  .swot-cell.strength{{background:#e8f5e9;border-left:4px solid #2e7d32}}
  .swot-cell.weakness{{background:#ffebee;border-left:4px solid #c62828}}
  .swot-cell.opportunity{{background:#e3f2fd;border-left:4px solid #1976d2}}
  .swot-cell.threat{{background:#fff3e0;border-left:4px solid #f57c00}}
  .swot-cell .h{{font-weight:900;margin-bottom:6px;font-size:13px}}
  .swot-cell.strength .h{{color:#2e7d32}}
  .swot-cell.weakness .h{{color:#c62828}}
  .swot-cell.opportunity .h{{color:#1976d2}}
  .swot-cell.threat .h{{color:#f57c00}}
  .swot-cell ul{{margin:0;padding-left:16px}}
  .swot-cell li{{margin:3px 0;line-height:1.5}}

  /* 建議行動 */
  .rank-actions{{background:linear-gradient(90deg,#fff8e1,#fff3e0);border:1px solid #f57c00;border-radius:6px;padding:14px 16px;margin-bottom:12px}}
  .ra-title{{font-size:14px;font-weight:900;color:#e65100;padding-bottom:8px;border-bottom:2px solid #e65100;margin-bottom:12px}}
  .ra-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}}
  .ra-item{{background:#fff;padding:10px 12px;border-radius:5px;border:1px solid #ffe0b2;position:relative}}
  .ra-item .p{{position:absolute;top:-8px;left:8px;background:linear-gradient(135deg,#c62828,#8b0000);color:#fff;padding:3px 10px;border-radius:10px;font-size:10px;font-weight:900;letter-spacing:1px;box-shadow:0 2px 4px rgba(198,40,40,.3)}}
  .ra-item .t{{margin-top:4px;font-size:13px;font-weight:700;color:#333;line-height:1.4}}
  .ra-item .w{{margin-top:6px;font-size:11px;color:#666;padding-top:6px;border-top:1px dashed #ffe0b2}}

  /* Footer */
  .rank-footer{{padding:10px 14px;background:#f5f5f5;border-radius:4px;font-size:11px;color:#666;line-height:1.6}}
  .rank-footer a{{color:#6a1b9a;font-weight:700;text-decoration:none}}
  .rank-footer a:hover{{text-decoration:underline}}

  /* ===== 摺疊區塊 (鄉鎮農產/作物基肥用) ===== */
  .collapsible{{position:relative}}
  .collapsible > h3{{cursor:pointer;user-select:none;padding-right:40px !important;transition:background .15s}}
  .collapsible > h3::after{{content:"▼";position:absolute;right:14px;top:50%;transform:translateY(-50%);font-size:14px;color:var(--cwa-primary);transition:transform .2s}}
  .collapsible.collapsed > h3::after{{transform:translateY(-50%) rotate(-90deg)}}
  .collapsible.collapsed > *:not(h3){{display:none}}
  .collapsible > h3:hover{{background:var(--cwa-hover) !important}}
  .collapsible.collapsed{{padding-bottom:8px !important}}

  /* ===== 統一 tab bar (三選一切換) ===== */
  .unified-tabs{{display:flex;gap:0;background:linear-gradient(180deg,#003c8f 0%,#002171 100%);padding:8px 8px 0;border-bottom:3px solid #ffd54f;position:sticky;top:0;z-index:900;box-shadow:0 3px 8px rgba(0,0,0,.2)}}
  .unified-tabs button{{flex:1;padding:12px 14px;background:rgba(255,255,255,.08);border:none;border-radius:6px 6px 0 0;color:rgba(255,255,255,.7);font-size:15px;font-weight:700;cursor:pointer;transition:all .15s;font-family:inherit;letter-spacing:1px;margin-right:2px}}
  .unified-tabs button:hover{{background:rgba(255,255,255,.15);color:#fff}}
  .unified-tabs button.active{{background:#fff;color:#0d47a1;box-shadow:0 -2px 6px rgba(0,0,0,.15)}}
  .unified-block{{display:none}}
  .unified-block.active{{display:block;animation:fadeIn .2s ease}}
  @keyframes fadeIn{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:translateY(0)}}}}
  @media (max-width:640px){{
    .unified-tabs button{{font-size:12px;padding:10px 6px;letter-spacing:0}}
  }}

  /* ===== 響應式 ===== */
  @media (max-width:640px){{
    .header{{padding:16px 14px}}
    .header h1{{font-size:18px}}
    .toggle button{{padding:10px 14px;font-size:13px}}
    .legend,.ranking,.impact,.source,.rainy-block,.forecast-block,.analysis-block,.news-block{{padding:12px 14px}}
    .fcst-wrap{{flex-direction:column}}
    .fcst-legend{{flex:1 1 auto;width:100%}}
    #map{{height:50vh}}
    #fcstMap{{height:360px}}
  }}
</style></head>
<body class="{typhoon_class}">
{typhoon_banner}

<!-- 左側浮動快速導覽 (仿 CODIS 側邊選單) -->
<aside class="cwa-sidebar" id="cwaSidebar">
  <button class="cwa-sidebar-toggle" onclick="document.getElementById('cwaSidebar').classList.toggle('collapsed')" title="收合/展開">☰</button>
  <div class="cwa-sidebar-title">章節導覽</div>
  <nav class="cwa-sidebar-nav">
    <a href="#obsBlock" data-icon="📍">雨量觀測</a>
    <a href="#fcstBlock" data-icon="🔮">未來預測</a>
    <a href="#histMapBlock" data-icon="📜">歷史地圖</a>
    <a href="#historyBlock" data-icon="📊">歷史比較</a>
    <a href="#advBlock" data-icon="📈">進階四維</a>
    <a href="#newsBlock" data-icon="📰">相關新聞</a>
    <a href="#salesBlock" data-icon="💰">銷售分析</a>
    <a href="#rankBlock" data-icon="🏭">廠商排名</a>
    <a href="#solarBlock" data-icon="🌱">節氣影響</a>
    <a href="#cropBlock" data-icon="🍎">作物基肥</a>
    <a href="#townsBlock" data-icon="🌾">鄉鎮農產</a>
  </nav>
  <div class="cwa-sidebar-foot">
    <div class="upd">🕐 {today}</div>
    <a href="https://codis.cwa.gov.tw/StationData" target="_blank" class="src-link">📡 CODIS 官網</a>
  </div>
</aside>

<!-- 頂部品牌條：大成 · 碩成 -->
<div class="brand-bar">
  <div class="brand-left">
    <div class="brand-logos">
      <img class="brand-dachan-img" src="data:image/png;base64,{dachan_logo_b64}" alt="大成長城 DaChan" title="大成長城企業股份有限公司 (1210) · dachan.com 官方 logo">
      <img class="brand-shuocheng-img" src="data:image/png;base64,{shuocheng_logo_b64}" alt="碩成" title="碩成有機質肥料 (訂貨平台官方 logo)">
    </div>
    <div class="brand-name">
      <span class="co">大成長城企業股份有限公司</span>
      <span class="dept">有機肥料部　·　碩成有機質肥料</span>
    </div>
  </div>
  <div class="brand-right">
    <span class="stock">1210 · TWSE</span>
    <span>{today}</span>
  </div>
</div>

<div class="header">
  <h1><span class="icon">🗺️</span>業務戰情室 · 全台雨量與作物出貨分析<span class="badge">內部業務決策用</span></h1>
  <p class="sub">
    資料來源 Open-Meteo (ECMWF) & 中央氣象署<span class="divider">|</span>
    覆蓋 22 縣市 91 特色農產鄉鎮<span class="divider">|</span>
    103 種常見作物基肥資料庫
  </p>
  <div class="term-strip">
    <span class="term-emoji">{term_emoji}</span>
    <span class="term-name">{term_name}</span>
    <span class="term-hint">{term_hint}</span>
  </div>
</div>

<!-- 浮動版權水印 (跟隨滾動固定左下角) -->
<div class="copyright-badge">
  <img class="cb-avatar" src="data:image/png;base64,{author_avatar_b64}" alt="莊政遠">
  <div class="cb-text">
    <div class="cb-line1">© 系統版權所有</div>
    <div class="cb-seal">莊 政 遠</div>
  </div>
</div>


<!-- 雨量視覺化 modal -->
<div class="rain-modal" id="rainModal" onclick="if(event.target===this)closeRainModal()">
  <div class="rm-content">
    <div class="rm-head">
      <span id="rmTitle">雨量視覺化</span>
      <button class="close" onclick="closeRainModal()">×</button>
    </div>
    <div class="rm-body">
      <div class="rm-viz">
        <div class="rm-drops" id="rmDrops"></div>
        <div class="rm-cup">
          <div class="water" id="rmWater" style="height:0%"></div>
          <div class="scale"><span>100</span><span>75</span><span>50</span><span>25</span><span>0</span></div>
        </div>
        <div class="rm-value">
          <span class="num" id="rmNum">0</span><span class="unit">mm</span>
          <div class="lvl" id="rmLvl"></div>
        </div>
      </div>
      <ul class="rm-cmps" id="rmCmps"></ul>
      <div class="rm-impact" id="rmImpact"></div>
    </div>
  </div>
</div>

<div class="refresh-bar">
  <button id="refreshBtn" onclick="refreshData()">🔄 立即更新雨量資料</button>
  <button id="projBtn" onclick="toggleProjector()" style="background:#7b1fa2">📽 投影模式</button>
  <span class="refresh-time" id="refreshTime">📡 資料時間：{gen_time}</span>
  <a class="cwa-link" href="https://www.cwa.gov.tw/V8/C/W/OBS_County.html" target="_blank" rel="noopener">📊 對照中央氣象署即時觀測</a>
</div>
<!-- 統一大 tab bar (三選一切換：雨量觀測/未來預測/鄉鎮農產) -->
<div class="unified-tabs" id="unifiedTabs">
  <button data-target="obsBlock" class="active">📍 雨量觀測</button>
  <button data-target="fcstBlock">🔮 未來預測</button>
  <button data-target="histMapBlock">📜 歷史地圖</button>
  <button data-target="salesBlock">💰 銷售分析</button>
  <button data-target="rankBlock">🏭 廠商排名</button>
</div>

<div id="obsBlock" class="unified-block active">

<div class="accuracy-note">
  ✅ <strong>過去+今日：中央氣象署 CODIS 官方觀測</strong>（每縣多站取 MAX,含颱風強降雨實測值）·
  <strong>未來 7 天：Open-Meteo 預測</strong>（CWA 免費 API 無未來預測）·
  警報請以 <a href="https://www.cwa.gov.tw/" target="_blank" rel="noopener"><strong>中央氣象署</strong></a> 為準。
</div>

<div class="toggle">
  <button data-mode="today">今日</button>
  <button data-mode="month" class="active">本月</button>
  <button data-mode="quarter">本季 (Q{quarter})</button>
  <button data-mode="custom">📅 自訂區間</button>
</div>

<div class="custom-range" id="customRange">
  <label>從</label><input type="date" id="dateStart" min="{data_start}" max="{today}" value="{data_start}">
  <label>到</label><input type="date" id="dateEnd" min="{data_start}" max="{today}" value="{today}">
  <button onclick="applyCustom()">套用</button>
  <div class="hint">可選範圍：{data_start} ~ {today}（資料涵蓋過去 92 天）</div>
</div>

<div class="period" id="period-info"></div>

<div id="map">
  <!-- 顏色級距 (貼地圖右上角,隨地圖) -->
  <div class="legend-fab" id="legendFab">
    <div class="legend-fab-head">
      <span class="lf-title">雨量色階</span>
      <span class="lf-unit">mm</span>
      <button class="lf-toggle" onclick="document.getElementById('legendFab').classList.toggle('collapsed')" title="收合/展開">◀</button>
    </div>
    <div class="legend-fab-bar" id="legendFabBar"></div>
    <div class="legend-fab-foot">縣市名旁的數字=累積 mm<br>今日按 1/10 縮放</div>
  </div>
</div>

<!-- 「雨量對肥料影響」摺疊為右下角浮動 icon,hover 展開節省空間 -->
<div class="impact-fab" id="impactFab">
  <button class="impact-fab-btn" aria-label="雨量對肥料影響對照表">💧<span>肥料影響</span></button>
  <div class="impact-fab-panel">
    <div class="impact-fab-head">💧 雨量對有機質肥料施用的影響程度</div>
    <div class="impact-fab-body">
      <div class="group-title">短期單日</div>
      <div class="row"><div class="rng green">&lt; 30 mm</div><div class="note">可施肥；雨水帶入水分有助於溶肥滲入</div></div>
      <div class="row"><div class="rng amber">30 – 80 mm</div><div class="note">表面顆粒被沖刷，氮素流失 10-20%，當日施肥效果打折</div></div>
      <div class="row"><div class="rng red">&gt; 80 mm</div><div class="note">禁施；農路積水、機具進不去、粒肥泡爛</div></div>

      <div class="group-title">連續 3-5 天</div>
      <div class="row"><div class="rng green">&lt; 50 mm</div><div class="note">田面 OK；正常出貨無虞</div></div>
      <div class="row"><div class="rng amber">50 – 150 mm</div><div class="note">泥濘；農路機具不易進入，出貨延後 1-2 天</div></div>
      <div class="row"><div class="rng red">&gt; 150 mm</div><div class="note">田面積水；微生物轉厭氧、根系活性降，有機質肥效大幅遞減</div></div>

      <div class="group-title">月累積（業務銷量判讀）</div>
      <div class="row"><div class="rng green">&lt; 150 mm</div><div class="note">施肥黃金期，銷量旺 — 客戶積極備肥</div></div>
      <div class="row"><div class="rng gray">150 – 300 mm</div><div class="note">普通，看空檔出貨 — 接單頻率正常</div></div>
      <div class="row"><div class="rng amber">300 – 500 mm</div><div class="note">銷量下滑 20-30% — 客戶觀望、延後備肥</div></div>
      <div class="row"><div class="rng red">&gt; 500 mm</div><div class="note">銷量低谷 — 田間無法作業，出貨幾乎停滯</div></div>

      <div class="info-note">
        <strong>📌 為什麼有機肥對雨量比化肥敏感？</strong><br>
        1. <strong>顆粒比較大</strong>，雨水浸泡 1-2 天會泡爛、養分隨水流失到溝渠<br>
        2. <strong>含微生物</strong>，連續陰雨 = 田面厭氧，菌相被破壞、肥效歸零<br>
        3. <strong>多為粒狀/粉狀</strong>，需要機具撒佈，農路積水就根本無法出貨<br>
        4. <strong>果樹/茶葉</strong>主要客戶在山區，雨季時連道路都不一定能通
      </div>
    </div>
  </div>
</div>

<div class="ranking" id="ranking">
  <h3 id="ranking-title">本月累積雨量排名</h3>
  <table id="ranking-table"><tbody></tbody></table>
</div>

<!-- ===================== 本月降雨日曆 ===================== -->
<div class="rainy-block">
  <h3>📆 本月下雨日期 · 依縣市 / 雨量閾值篩選</h3>
  <div class="rainy-filters">
    <label>地區</label>
    <select id="rainyCounty"></select>
    <label>雨量閾值</label>
    <select id="rainyThreshold">
      <option value="1">≥ 1 mm（有雨即算）</option>
      <option value="10">≥ 10 mm（小雨以上）</option>
      <option value="30" selected>≥ 30 mm（中雨以上）</option>
      <option value="50">≥ 50 mm（大雨以上）</option>
      <option value="80">≥ 80 mm（豪雨）</option>
    </select>
  </div>
  <div class="rainy-summary" id="rainySummary"></div>
  <div class="cal-grid" id="rainyCalendar"></div>
  <div class="rainy-list" id="rainyList"></div>
</div>

</div><!-- /obsBlock -->

<!-- ===================== 未來 7 天雨量預測 ===================== -->
<div class="forecast-block unified-block" id="fcstBlock">
  <h3>🔮 未來 7 天雨量預測 · 全台縣市地圖</h3>
  <div class="fcst-mode-bar">
    <button data-mode="single" class="active">📅 單日</button>
    <button data-mode="3day">📈 未來 3 天累積</button>
    <button data-mode="7day">📈 未來 7 天累積</button>
    <button data-mode="custom">✓ 自訂天數複選</button>
  </div>
  <div class="fcst-checkboxes" id="fcstCheckboxes"></div>
  <div class="fcst-day-tabs" id="fcstTabs"></div>
  <div class="fcst-info" id="fcstInfo" style="display:none"></div>
  <div class="fcst-wrap" id="fcstWrap">
    <div id="fcstMap"></div>
    <div class="fcst-legend">
      <div class="fcst-legend-title">顏色 → 日雨量 (mm)</div>
      <div id="fcstLegendBars"></div>
      <div class="fcst-legend-hint">📍 兩指縮放可看鄉鎮街道<br>👆 點縣市顯示詳細數字</div>
    </div>
  </div>
  <div class="fcst-ranking" id="fcstRanking">
    <div class="fcst-ranking-head">
      <h4 id="fcstRankingTitle">📊 22 縣市預測雨量排名（多→少）</h4>
      <button id="fcstSortToggle" onclick="toggleFcstSort()">⇅ 反轉排序</button>
    </div>
    <table><thead><tr>
      <th style="width:44px">名次</th>
      <th>縣市</th>
      <th style="width:70px">等級</th>
      <th class="n">預測雨量</th>
    </tr></thead><tbody id="fcstRankingBody"></tbody></table>
  </div>
</div>

<!-- ===================== 歷史雨量地圖 (可選年/月, CODIS 官方資料) ===================== -->
<div id="histMapBlock" class="unified-block hist-map-block">
  <h3>📜 歷史雨量地圖 · 選任意年月看全台累積 <span style="font-size:11px;color:#c62828;font-weight:700">· 資料源:中央氣象署 CODIS 觀測 (1896-)</span></h3>
  <div class="hist-map-controls">
    <label>年份</label>
    <select id="hmYear"></select>
    <label>月份</label>
    <select id="hmMonth">
      <option value="all">全年累積</option>
      <option value="1">1 月</option><option value="2">2 月</option><option value="3">3 月</option>
      <option value="4">4 月</option><option value="5">5 月</option><option value="6">6 月</option>
      <option value="7">7 月</option><option value="8">8 月</option><option value="9">9 月</option>
      <option value="10">10 月</option><option value="11">11 月</option><option value="12">12 月</option>
    </select>
    <label>指標</label>
    <select id="hmMetric">
      <option value="mm">💧 累積雨量 (mm)</option>
      <option value="rd">☔ 有雨日 (天)</option>
      <option value="sd">⛈ 豪雨日 (≥50mm)</option>
      <option value="tavg">🌡 均溫 (°C)</option>
    </select>
    <button id="hmNcdrBtn" onclick="openNcdrDailyMap()" style="margin-left:auto;padding:6px 12px;background:#0d47a1;color:#fff;border:none;border-radius:14px;font-size:12px;cursor:pointer;font-weight:700">🔗 對照 NCDR 單日圖</button>
  </div>
  <div class="hist-map-info" id="hmInfo"></div>
  <div id="histMap"></div>
  <div class="hist-map-ranking">
    <h4 id="hmRankTitle">全台縣市排名</h4>
    <table><thead><tr><th>名次</th><th>縣市</th><th>觀測站</th><th class="n">數值</th></tr></thead><tbody id="hmRankBody"></tbody></table>
  </div>
</div>

<!-- ===================== 節氣 × 有機質基肥出貨影響 ===================== -->
<div class="term-detail-block collapsible collapsed" id="solarBlock">
  <h3>{term_emoji} 本節氣 · <span class="term-hi">{term_name}</span> — 有機質肥料（基肥）出貨影響</h3>
  <div class="term-detail-lead">{term_hint}</div>
  <ul class="term-detail-list">
    {term_details_html}
  </ul>
  <div class="term-detail-foot">
    ※ 有機質肥料 = 種植前 / 收成後所施的<strong>基肥</strong>，改良土壤、緩釋供養；不同於化肥追肥。<br>
    ※ 節氣依陽曆推算，實際農時因作物品種、地區、氣候略有差異。
  </div>
</div>

<!-- ===================== 基肥施用時機 · 作物交叉篩選 ===================== -->
<div class="crops-block collapsible collapsed" id="cropBlock">
  <h3>🌱 基肥施用時機 · 作物 × 地區 × 面積 × 機率 交叉篩選</h3>
  <div class="crops-filters">
    <div class="crops-f-row">
      <label>作物類別</label>
      <select id="fltCat">
        <option value="">全部</option>
        <option value="果樹">🍎 果樹</option>
        <option value="葉菜">🥬 葉菜</option>
        <option value="瓜果類">🍅 瓜果類</option>
        <option value="根莖類">🥔 根莖類</option>
        <option value="茶葉">🍵 茶葉</option>
        <option value="花卉">🌸 花卉</option>
        <option value="雜糧">🥜 雜糧/特作</option>
        <option value="菇類">🍄 菇類</option>
      </select>
      <label>地區</label>
      <select id="fltRegion">
        <option value="">全部</option>
        <option value="北部">北部</option>
        <option value="中部">中部</option>
        <option value="南部" selected>南部（主要業務區）</option>
        <option value="東部">東部</option>
      </select>
      <label>栽培面積</label>
      <select id="fltArea">
        <option value="0">不限（每甲用量顯示）</option>
        <option value="0.5">&lt; 0.5 甲</option>
        <option value="1">0.5-1 甲</option>
        <option value="3">1-3 甲</option>
        <option value="5">3-5 甲</option>
        <option value="10">5-10 甲</option>
        <option value="20">10 甲以上</option>
      </select>
      <label>使用機率</label>
      <select id="fltProb">
        <option value="">全部</option>
        <option value="高">高（年 2-3 次基肥）</option>
        <option value="中">中（年 1-2 次基肥）</option>
      </select>
      <label>僅顯示本月適合</label>
      <input type="checkbox" id="fltThisMonth" style="width:16px;height:16px;accent-color:var(--cwa-primary);cursor:pointer">
    </div>
  </div>
  <div class="crops-summary" id="cropsSummary"></div>
  <div class="crops-table-wrap">
    <table class="crops-table">
      <thead><tr>
        <th style="width:38px">類別</th>
        <th>作物</th>
        <th style="width:220px">基肥適用月份</th>
        <th style="width:100px">主要地區</th>
        <th style="width:90px;text-align:right">量/甲 (kg)</th>
        <th style="width:60px;text-align:center">機率</th>
        <th>備註</th>
      </tr></thead>
      <tbody id="cropsTbody"></tbody>
    </table>
  </div>
  <div class="crops-foot">
    ※ 每甲用量為業界一般值；實際依土質、樹齡、產量目標調整。<br>
    ※ 使用機率：<strong>高</strong>=年 2-3 次基肥；<strong>中</strong>=年 1-2 次；<strong>低</strong>=1-2 年 1 次。<br>
    ※ 果樹採收前 30 天禁施；茶區（尤其 &gt;1000m 高山茶）禁禽畜糞、只用植物渣粕（5-13）。
  </div>
</div>

<!-- ===================== 鄉鎮特色農產地圖 (底部摺疊) ===================== -->
<div class="towns-block collapsible collapsed" id="townsBlock">
  <h3>🗺️ 全台鄉鎮特色農產分布 · 主力作物與用肥地圖</h3>
  <div class="towns-filters">
    <label>作物類別</label>
    <select id="townFltCat">
      <option value="">全部</option>
      <option value="fruit">🍎 果樹</option>
      <option value="veg">🥬 蔬菜/瓜果/根莖</option>
      <option value="tea">🍵 茶葉</option>
      <option value="flower">🌸 花卉</option>
      <option value="grain">🥜 雜糧/特作/水稻</option>
    </select>
    <label>關鍵字</label>
    <input type="text" id="townKw" placeholder="輸入作物或鄉鎮，如 芒果 / 麻豆" style="padding:6px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-size:13px;font-family:inherit;min-width:180px">
    <span class="towns-count" id="townsCount"></span>
  </div>
  <div id="townsMap"></div>
  <div class="towns-legend">
    <span><span class="dot" style="background:#c62828"></span>果樹</span>
    <span><span class="dot" style="background:#2e7d32"></span>蔬菜</span>
    <span><span class="dot" style="background:#00695c"></span>茶葉</span>
    <span><span class="dot" style="background:#c2185b"></span>花卉</span>
    <span><span class="dot" style="background:#5d4037"></span>雜糧/水稻</span>
  </div>
</div>

<!-- ===================== 有機肥料部銷售分析 (內部資料) ===================== -->
<div id="salesBlock" class="unified-block sales-block">
  <h3>💰 有機肥料部銷售分析 · 逐月噸數 + 雨量對照 <span class="sales-warn">內部業務資料</span></h3>

  <div class="sales-kpi-row">
    <div class="sales-kpi"><div class="lbl">2022 全年</div><div class="val" id="k2022">–</div><div class="unit">噸</div></div>
    <div class="sales-kpi"><div class="lbl">2023 全年</div><div class="val" id="k2023">–</div><div class="unit">噸</div></div>
    <div class="sales-kpi"><div class="lbl">2024 全年</div><div class="val" id="k2024">–</div><div class="unit">噸</div></div>
    <div class="sales-kpi hi"><div class="lbl">2025 全年 ★</div><div class="val" id="k2025">–</div><div class="unit">噸</div></div>
    <div class="sales-kpi hi2"><div class="lbl">2026 至今</div><div class="val" id="k2026">–</div><div class="unit">噸 (7 月)</div></div>
  </div>

  <div class="sales-controls">
    <label>對照雨量地區</label>
    <select id="salesRegion">
      <optgroup label="── 南部 (主業務) ──">
        <option value="臺南市" selected>臺南市 ★</option>
        <option value="高雄市">高雄市</option>
        <option value="嘉義縣">嘉義縣 ★</option>
        <option value="屏東縣">屏東縣</option>
      </optgroup>
      <optgroup label="── 其他業務區 ──">
        <option value="宜蘭縣">宜蘭縣 ★</option>
        <option value="花蓮縣">花蓮縣 ★</option>
      </optgroup>
      <optgroup label="── 其他 ──">
        <option value="臺北市">臺北市</option>
        <option value="臺中市">臺中市</option>
        <option value="臺東縣">臺東縣</option>
      </optgroup>
    </select>
    <label>比較模式</label>
    <select id="salesMode">
      <option value="both" selected>雙軸:銷售+雨量疊圖</option>
      <option value="salesOnly">只看銷售噸數</option>
      <option value="scatter">散點:雨量 vs 銷售</option>
    </select>
    <span class="sales-hint">💡 判斷雨量對銷售影響:雨量高 → 田面積水/機具不便 → 銷售延後</span>
  </div>

  <div class="sales-chart-wrap">
    <div id="salesChart"></div>
  </div>

  <div class="sales-table-wrap">
    <table class="sales-table">
      <thead><tr>
        <th>年份</th>
        <th>1月</th><th>2月</th><th>3月</th><th>4月</th><th>5月</th><th>6月</th>
        <th>7月</th><th>8月</th><th>9月</th><th>10月</th><th>11月</th><th>12月</th>
        <th class="total">合計</th>
      </tr></thead>
      <tbody id="salesTbody"></tbody>
    </table>
  </div>

  <!-- 編輯區 (本機 localStorage,不上雲端) -->
  <div class="sales-edit-bar">
    <button class="btn-edit" onclick="toggleSalesEdit()"><span id="editIcon">✏️</span> <span id="editLbl">編輯銷售資料</span></button>
    <span class="edit-hint">💡 修改僅存於本機瀏覽器 (localStorage),不會上傳。清除瀏覽器資料會還原初始值。</span>
    <button class="btn-reset" onclick="resetSalesData()" style="display:none" id="btnReset">🔄 重設為初始值</button>
    <button class="btn-export" onclick="exportSalesJson()" style="display:none" id="btnExport">📥 匯出 JSON</button>
  </div>

  <div class="sales-edit-panel" id="salesEditPanel" style="display:none">
    <div class="sales-edit-head">
      ✏️ 編輯模式 — 直接點格子輸入數字，離開格子即自動儲存到本機
      <span class="sales-edit-status" id="editStatus"></span>
    </div>
    <div class="sales-edit-tablewrap">
      <table class="sales-edit-table">
        <thead><tr>
          <th style="width:70px">年份</th>
          <th>1月</th><th>2月</th><th>3月</th><th>4月</th><th>5月</th><th>6月</th>
          <th>7月</th><th>8月</th><th>9月</th><th>10月</th><th>11月</th><th>12月</th>
          <th style="width:50px">操作</th>
        </tr></thead>
        <tbody id="salesEditTbody"></tbody>
      </table>
    </div>
    <div class="sales-add-row">
      <label>➕ 新增年份：</label>
      <input type="number" id="newYearInput" min="2000" max="2099" placeholder="例:2027" style="width:90px">
      <button onclick="addSalesYear()">新增</button>
    </div>
  </div>

  <div class="sales-analysis" id="salesAnalysis"></div>
</div>

<!-- ===================== 農糧署有機肥廠商排名 (即時抓官網) ===================== -->
<div id="rankBlock" class="unified-block rank-block">
  <h3>🏭 有機質肥料廠商排名
    <span class="rank-src" id="rankSrc">資料源:農糧署 · 115 年推薦名單</span>
    <button class="rank-refresh-btn" id="fertUpdateBtn" onclick="updateFertRankings()" title="立即從農糧署官網重抓最新推薦名單">🔄 一鍵更新</button>
    <a class="rank-actions-link" href="https://github.com/yuan780903-cpu/market-scraper/actions/workflows/refresh-rankings.yml" target="_blank" title="到 GitHub Actions 手動觸發">📋 執行紀錄</a>
  </h3>

  <div class="rank-kpi-grid">
    <div class="rank-kpi"><div class="lbl">總業者數</div><div class="val" id="rkTotSupp">–</div></div>
    <div class="rank-kpi"><div class="lbl">總產品數</div><div class="val" id="rkTotProd">–</div></div>
    <div class="rank-kpi hi"><div class="lbl">🐔 禽畜糞產品</div><div class="val" id="rkAnimal">–</div></div>
    <div class="rank-kpi hi2"><div class="lbl">🌾 植物渣粕產品</div><div class="val" id="rkPlant">–</div></div>
    <div class="rank-kpi upd"><div class="lbl">最新更新</div><div class="val" id="rkUpd">–</div></div>
  </div>

  <div class="rank-filters">
    <label>補助等級</label>
    <select id="rankTier">
      <option value="all">全部</option>
      <option value="2+2元">每公斤補助 2+2 元 (高階)</option>
      <option value="2元">每公斤補助 2 元 (一般)</option>
    </select>
    <label>品目篩選</label>
    <select id="rankCode">
      <option value="all">全部品目</option>
    </select>
    <label>關鍵字</label>
    <input id="rankKw" type="text" placeholder="輸入業者名,如「碩成」「福壽」" style="padding:5px 10px;border:1px solid var(--cwa-border);border-radius:3px;font-size:13px">
    <span class="rank-count" id="rankCount"></span>
  </div>

  <!-- 品目統計小表 -->
  <div class="rank-cat-summary" id="rankCatSummary"></div>

  <!-- 推薦名單監控 (新上架/新違規) -->
  <div class="rank-monitor" id="rankMonitor"></div>

  <!-- 廠商排名主表 -->
  <div class="rank-table-wrap">
    <table class="rank-table" id="rankTable">
      <thead><tr>
        <th style="width:50px">名次</th>
        <th>業者名稱</th>
        <th class="n">產品總數</th>
        <th class="n">2+2 元</th>
        <th class="n">2 元</th>
        <th class="n">品目數</th>
        <th>主要品目</th>
      </tr></thead>
      <tbody id="rankTbody"></tbody>
    </table>
  </div>

  <div class="rank-analysis" id="rankAnalysis"></div>
</div>

<!-- ===================== 歷史雨量比較 · 出貨影響對照 ===================== -->
<div class="history-block" id="historyBlock">
  <h3>📊 歷史雨量比較 · 近 10 年同月對照 <span style="font-size:11px;color:#c62828;font-weight:700">· 資料源：中央氣象署 CODIS 觀測站官方資料</span></h3>
  <div class="history-filters">
    <label>地區</label>
    <select id="histRegion">
      <optgroup label="── 北部 ──">
        <option value="臺北市">臺北市</option>
        <option value="新北市">新北市</option>
        <option value="基隆市">基隆市</option>
        <option value="桃園市">桃園市</option>
        <option value="新竹市">新竹市</option>
        <option value="新竹縣">新竹縣</option>
        <option value="宜蘭縣">宜蘭縣</option>
      </optgroup>
      <optgroup label="── 中部 ──">
        <option value="苗栗縣">苗栗縣</option>
        <option value="臺中市">臺中市</option>
        <option value="彰化縣">彰化縣</option>
        <option value="南投縣">南投縣</option>
        <option value="雲林縣">雲林縣</option>
      </optgroup>
      <optgroup label="── 南部（主業務區）──">
        <option value="嘉義市">嘉義市</option>
        <option value="嘉義縣" selected>嘉義縣 ★</option>
        <option value="臺南市">臺南市 ★</option>
        <option value="高雄市">高雄市</option>
        <option value="屏東縣">屏東縣</option>
      </optgroup>
      <optgroup label="── 東部 ──">
        <option value="宜蘭縣">宜蘭縣 ★</option>
        <option value="花蓮縣">花蓮縣 ★</option>
        <option value="臺東縣">臺東縣</option>
      </optgroup>
      <optgroup label="── 離島 ──">
        <option value="澎湖縣">澎湖縣</option>
        <option value="金門縣">金門縣</option>
        <option value="連江縣">連江縣</option>
      </optgroup>
    </select>
    <label>月份</label>
    <select id="histMonth">
      <option value="1">1 月</option>
      <option value="2">2 月</option>
      <option value="3">3 月</option>
      <option value="4">4 月</option>
      <option value="5">5 月</option>
      <option value="6">6 月</option>
      <option value="7">7 月</option>
      <option value="8">8 月</option>
      <option value="9">9 月</option>
      <option value="10">10 月</option>
      <option value="11">11 月</option>
      <option value="12">12 月</option>
    </select>
    <label>對照範圍</label>
    <select id="histYears">
      <option value="3">近 3 年</option>
      <option value="5" selected>近 5 年</option>
      <option value="10">近 10 年</option>
    </select>
    <button id="histRun" onclick="loadHistoryData()">🔍 撈取比較</button>
  </div>
  <div class="history-status" id="histStatus"></div>
  <div class="history-chart" id="histChart">
    <div style="text-align:center;padding:40px 20px;color:var(--cwa-text-muted)">
      👆 選好地區與月份，按「撈取比較」<br>
      <span style="font-size:11px;color:#2e7d32;font-weight:700">✓ 資料已預先打包於本頁面，瞬間查詢，任何組合皆可比對</span>
      <div style="margin-top:14px;padding:10px 14px;background:#fff3e0;border:1px solid #f57c00;border-radius:4px;font-size:12px;line-height:1.7;color:#333;text-align:left;max-width:640px;margin-left:auto;margin-right:auto">
        <strong style="color:#c62828">📖 資料源智慧切換說明</strong><br>
        • <strong>歷年 (2016–上月)</strong>：中央氣象署 CODIS 官方觀測站官方數字 (每縣多站取 MAX)<br>
        • <strong>當年當月 (進行中)</strong>：Open-Meteo Forecast (ECMWF 11km 高解析,即時)，與上方地圖同源<br>
        • <strong>自動切換</strong>：每日 GitHub Actions 重抓,月結束後當月數字自動改為 CWA 官方觀測
      </div>
    </div>
  </div>
  <div class="history-table-wrap" id="histTableWrap" style="display:none">
    <table class="history-table">
      <thead><tr>
        <th>年份</th>
        <th>該月累積雨量</th>
        <th>有雨天數 (≥1mm)</th>
        <th>豪雨日 (≥50mm)</th>
        <th>vs 均值差異</th>
        <th>vs 均值 %</th>
        <th>資料源</th>
      </tr></thead>
      <tbody id="histTbody"></tbody>
    </table>
  </div>
  <div class="history-report" id="histReport" style="display:none"></div>
</div>

<!-- ===================== 進階歷史比較 · 多維交叉分析 ===================== -->
<div class="adv-block" id="advBlock">
  <h3>📈 進階氣候比較 · 四維交叉分析 <span style="font-size:11px;color:#c62828;font-weight:700">年 × 月 × 地區 × 指標 全部可複選</span></h3>
  <div class="adv-grid">
    <div class="adv-group">
      <div class="adv-group-head">
        <span>📅 年份</span>
        <div class="quick">
          <a onclick="advQuick('year','last3')">近3年</a>
          <a onclick="advQuick('year','last5')">近5年</a>
          <a onclick="advQuick('year','last10')">近10年</a>
          <a onclick="advQuick('year','clear')">清除</a>
        </div>
      </div>
      <div class="adv-cbs" id="advYears"></div>
    </div>
    <div class="adv-group">
      <div class="adv-group-head">
        <span>📆 月份</span>
        <div class="quick">
          <a onclick="advQuick('month','all')">全選</a>
          <a onclick="advQuick('month','q1')">Q1</a>
          <a onclick="advQuick('month','q2')">Q2</a>
          <a onclick="advQuick('month','q3')">Q3</a>
          <a onclick="advQuick('month','q4')">Q4</a>
          <a onclick="advQuick('month','clear')">清除</a>
        </div>
      </div>
      <div class="adv-cbs" id="advMonths"></div>
    </div>
    <div class="adv-group">
      <div class="adv-group-head">
        <span>📍 地區</span>
        <div class="quick">
          <a onclick="advQuick('region','south')">南部</a>
          <a onclick="advQuick('region','east')">東部</a>
          <a onclick="advQuick('region','biz')">主業務區</a>
          <a onclick="advQuick('region','all')">全選</a>
          <a onclick="advQuick('region','clear')">清除</a>
        </div>
      </div>
      <div class="adv-cbs" id="advRegions"></div>
    </div>
    <div class="adv-group">
      <div class="adv-group-head">
        <span>📊 指標</span>
        <div class="quick">
          <a onclick="advQuick('metric','rain')">雨量組</a>
          <a onclick="advQuick('metric','temp')">氣溫組</a>
          <a onclick="advQuick('metric','sales')">+銷售</a>
          <a onclick="advQuick('metric','all')">全選</a>
        </div>
      </div>
      <div class="adv-cbs" id="advMetrics">
        <label class="adv-chip metric-rain"><input type="checkbox" value="mm" checked>💧 累積雨量 (mm)</label>
        <label class="adv-chip metric-rain"><input type="checkbox" value="rd">☔ 有雨日 (天)</label>
        <label class="adv-chip metric-rain"><input type="checkbox" value="sd">⛈️ 豪雨日 (≥50mm)</label>
        <label class="adv-chip metric-temp"><input type="checkbox" value="tavg">🌡️ 均溫 (°C)</label>
        <label class="adv-chip metric-temp"><input type="checkbox" value="tmax">🔥 最高溫 (°C)</label>
        <label class="adv-chip metric-temp"><input type="checkbox" value="tmin">❄️ 最低溫 (°C)</label>
        <label class="adv-chip metric-sales"><input type="checkbox" value="sales">💰 銷售噸數 (全國)</label>
      </div>
    </div>
  </div>
  <div class="adv-actions">
    <button id="advRun" onclick="runAdvancedCompare()">🔍 執行交叉比較</button>
    <span class="est">預估：<strong id="advEst">0</strong> 個組合</span>
    <span class="adv-summary" id="advSummary"></span>
  </div>
  <div class="adv-status" id="advStatus"></div>
  <div class="adv-view-tabs" id="advViewTabs" style="display:none">
    <button data-view="matrix" class="active">📋 矩陣視圖</button>
    <button data-view="flat">📊 明細表格 (可排序)</button>
    <button data-view="chart">📈 折線圖對照</button>
    <button data-view="bar">📊 長條圖對比</button>
  </div>
  <div class="adv-table-wrap" id="advTableWrap" style="display:none"></div>
  <div class="adv-analysis" id="advAnalysis" style="display:none"></div>
</div>

<!-- ===================== 天氣分析 ===================== -->
<div class="analysis-block">
  <h3>🌦️ 未來一週天氣分析</h3>
  <p class="analysis-text">{analysis_text}</p>
</div>

<!-- ===================== 相關新聞 ===================== -->
<div class="news-block" id="newsBlock">
  <h3>📰 天氣 / 豪雨 / 颱風 相關新聞</h3>
  <ul class="news-list">
    {news_html}
  </ul>
</div>

<div class="source">
  <h3>📚 資料來源 / 方法說明</h3>
  <ul>
    <li><strong>雨量數據</strong>：Open-Meteo Forecast API（基於 <a href="https://www.ecmwf.int/" target="_blank">ECMWF</a> 全球模型 + ERA5 reanalysis），分辨率約 <strong>11 km</strong>，準度 ±10%。
      <br>⚠️ 全球模型對台灣<strong>山區地形性降雨</strong>（如中央山脈迎風面）及<strong>颱風局部強對流</strong>會低估。
      官方預警請對照 <a href="https://www.cwa.gov.tw/" target="_blank" style="color:#c92a2a"><strong>中央氣象署</strong></a>（自營 WRF 模型 + 地面站校正，本地準度較高）。
      <br><a href="https://open-meteo.com/" target="_blank">https://open-meteo.com</a></li>
    <li><strong>縣市邊界</strong>：g0v 開源台灣縣市 GeoJSON（twCounty2010）。
      <br><a href="https://github.com/g0v/twgeojson" target="_blank">github.com/g0v/twgeojson</a></li>
    <li><strong>地圖底圖</strong>：OpenStreetMap 開放圖資。</li>
    <li><strong>施肥/銷量影響閾值</strong>：大成長城企業有機肥料部莊政遠業務襄理田間觀察 + 客戶回報整理（非學術研究數據，供業務內部參考）。</li>
    <li><strong>取樣點</strong>：每縣市取縣治座標作代表，未細分鄉鎮（山區實際雨量可能更高）。</li>
  </ul>
</div>

<footer class="footer">
  <div class="footer-grid">
    <div class="footer-col">
      <h5>🏢 公司資訊</h5>
      <div class="row"><span class="lbl">公司</span><span class="val">大成長城企業股份有限公司</span></div>
      <div class="row"><span class="lbl">上市編號</span><span class="val">1210 · TWSE</span></div>
      <div class="row"><span class="lbl">部門</span><span class="val">有機肥料部</span></div>
      <div class="row"><span class="lbl">品牌</span><span class="val">碩成有機質肥料</span></div>
    </div>
    <div class="footer-col">
      <h5>📊 資料來源</h5>
      <div class="row"><span class="lbl">氣象</span><span class="val">中央氣象署 · Open-Meteo (ECMWF)</span></div>
      <div class="row"><span class="lbl">歷史</span><span class="val">ERA5 Reanalysis</span></div>
      <div class="row"><span class="lbl">地理</span><span class="val">g0v 開源縣市 GeoJSON</span></div>
      <div class="row"><span class="lbl">底圖</span><span class="val">OpenStreetMap</span></div>
    </div>
    <div class="footer-col">
      <h5>👤 系統資訊</h5>
      <div class="row"><span class="lbl">版權所有人</span><span class="val">莊政遠　業務襄理</span></div>
      <div class="row"><span class="lbl">業務轄區</span><span class="val">南區 (嘉/南/宜/花)</span></div>
      <div class="row"><span class="lbl">產出時間</span><span class="val">{gen_time}</span></div>
      <div class="row"><span class="lbl">資料範圍</span><span class="val">過去 92 天 + 未來 7 天預測</span></div>
    </div>
  </div>
  <div class="footer-copy">
    <span>© 大成長城企業股份有限公司 · 有機肥料部　保留所有權利</span>
    <span class="sig">
      <span>系統設計與維護</span>
      <span class="stamp">莊 政 遠</span>
    </span>
  </div>
</footer>

<script>
// 歷史雨量資料 (最先定義, 避免 TDZ)
window.HISTORY = {history_json};
window.SALES = {sales_json};
window.FERT_RANKINGS = {fert_rankings_json};
const DATA = {data_json};
const BANDS = {bands_json};
const NAME_MAP = {name_map_json};       // GeoJSON 縣市名 → 我們資料的縣市名
const PERIODS = {periods_json};          // {{today: "2026-06-08", month: "2026-06-01 ~ 2026-06-08 (8 天)", ...}}
const GEOJSON_URL = "https://raw.githubusercontent.com/g0v/twgeojson/master/json/twCounty2010.geo.json";

// 建快速查表：name → row
const DATA_BY_NAME = {{}};
DATA.forEach(d => {{ DATA_BY_NAME[d.name] = d; }});

function pickBand(v, mode) {{
  const scale = (mode === 'today') ? 0.1 : 1.0;
  for (const [lo, hi, color, label] of BANDS) {{
    if (v >= lo * scale && v < hi * scale) return {{color, label}};
  }}
  return {{color: BANDS[0][2], label: BANDS[0][3]}};
}}

const TW_BOUNDS = L.latLngBounds([[20.5, 118.0], [26.5, 123.5]]);
const map = L.map('map', {{zoomControl: true, attributionControl: true, minZoom: 6, maxZoom: 13, maxBounds: TW_BOUNDS, maxBoundsViscosity: 1.0}}).setView([23.7, 121.0], 7);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap',
  maxZoom: 12,
  opacity: 0.4,
}}).addTo(map);

let geoLayer = null;
let labelLayer = L.layerGroup().addTo(map);

function getDataForFeature(feature) {{
  // feature.properties.COUNTYNAME 可能是「台北市」「桃園縣」，要對應到我們的 DATA 名稱
  const geoName = feature.properties.COUNTYNAME || feature.properties.name || '';
  const ourName = NAME_MAP[geoName] || geoName;
  return {{ name: ourName, row: DATA_BY_NAME[ourName] }};
}}

function render(mode) {{
  // 移除舊的
  if (geoLayer) map.removeLayer(geoLayer);
  labelLayer.clearLayers();

  // 抓 GeoJSON (cache 在第一次)
  if (window._geo) {{
    draw(window._geo, mode);
  }} else {{
    fetch(GEOJSON_URL).then(r => r.json()).then(geo => {{
      window._geo = geo;
      draw(geo, mode);
    }}).catch(e => console.error('GeoJSON 失敗', e));
  }}

  // 更新統計期間
  document.getElementById('period-info').innerHTML =
    '📅 統計期間：<strong>' + PERIODS[mode] + '</strong>';

  // 更新排名
  const sorted = [...DATA].sort((a, b) => b[mode] - a[mode]);
  const modeName = mode === 'today' ? '今日' : mode === 'month' ? '本月'
                 : mode === 'quarter' ? '本季' : '自訂區間';
  document.getElementById('ranking-title').textContent = modeName + '累積雨量排名';
  const tbody = document.querySelector('#ranking-table tbody');
  tbody.innerHTML = '';
  sorted.slice(0, 10).forEach((c, i) => {{
    const {{color}} = pickBand(c[mode], mode);
    const isSingle = (mode === 'today');
    const emj = (typeof fcstEmoji === 'function') ? fcstEmoji(c[mode], !isSingle) : '';
    const row = document.createElement('tr');
    row.innerHTML = '<td class="rank">' + (i + 1) + '</td>' +
                    '<td class="county">' + emj + ' ' + c.name + '</td>' +
                    '<td class="mm" style="color:' + color + '">' + c[mode].toFixed(1) + ' mm</td>';
    tbody.appendChild(row);
  }});
}}

function draw(geo, mode) {{
  geoLayer = L.geoJSON(geo, {{
    style: function(feature) {{
      const {{row}} = getDataForFeature(feature);
      const v = row ? row[mode] : 0;
      const {{color}} = pickBand(v, mode);
      return {{
        fillColor: color,
        weight: 1,
        color: '#fff',
        fillOpacity: 0.88,
      }};
    }},
    onEachFeature: function(feature, layer) {{
      const {{name, row}} = getDataForFeature(feature);
      const v = row ? row[mode] : 0;
      const {{color, label}} = pickBand(v, mode);
      const modeLabel = mode === 'today' ? '今日'
                       : mode === 'month' ? '本月累積'
                       : mode === 'quarter' ? '本季累積' : '區間累積';
      layer.bindPopup(
        '<div class="popup-content"><strong>' + name + '</strong><br>' +
        modeLabel + '：' +
        '<strong style="color:' + color + ';font-size:16px">' + v.toFixed(1) + ' mm</strong><br>' +
        '<span style="color:#888">（' + label + '）</span></div>'
      );
      layer.on('mouseover', function() {{ this.setStyle({{weight: 2.5, color: '#1f3a2e'}}); }});
      layer.on('mouseout', function() {{ geoLayer.resetStyle(this); }});
      // 縣市中心 label
      if (row) {{
        const center = layer.getBounds().getCenter();
        L.marker([center.lat, center.lng], {{
          icon: L.divIcon({{
            className: 'county-label',
            html: name.replace('縣','').replace('市','') + '<span class="mm">' + v.toFixed(0) + ' mm</span>',
            iconSize: null,
          }}),
        }}).addTo(labelLayer);
      }}
    }},
  }}).addTo(map);
}}

document.querySelectorAll('.toggle button').forEach(b => {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('.toggle button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    const mode = b.dataset.mode;
    // 「自訂區間」→ 顯示日期選擇 UI；其他 → 隱藏
    document.getElementById('customRange').classList.toggle('show', mode === 'custom');
    if (mode === 'custom') {{
      applyCustom();  // 用預設值先算一次
    }} else {{
      render(mode);
    }}
  }});
}});

function applyCustom() {{
  const start = document.getElementById('dateStart').value;
  const end   = document.getElementById('dateEnd').value;
  if (!start || !end || start > end) {{
    alert('請確認起訖日期（開始日不得晚於結束日）');
    return;
  }}
  // 對每縣依 daily map 加總 start ~ end 的雨量
  DATA.forEach(c => {{
    let sum = 0;
    if (c.daily) {{
      for (const [d, mm] of Object.entries(c.daily)) {{
        if (d >= start && d <= end) sum += Number(mm) || 0;
      }}
    }}
    c.custom = Math.round(sum * 10) / 10;
  }});
  // 動態更新 PERIODS.custom 顯示字串
  const days = Math.round((new Date(end) - new Date(start)) / 86400000) + 1;
  PERIODS.custom = start + ' ~ ' + end + '（共 ' + days + ' 天）';
  render('custom');
}}

render('month');

// ============ 未來 7 天預測地圖 ============
const FORECAST_DATES = {forecast_dates_json};

// 預測用色階（日雨量 mm → 顏色）— 對應「短期單日」影響級距
const FCST_BANDS = [
  [0, 1,    '#f5f6f3', '無雨',    '< 1'],
  [1, 10,   '#cfe9ff', '零星',    '1-10'],
  [10, 30,  '#7bb3eb', '小雨',    '10-30'],
  [30, 50,  '#5cb85c', '中雨',    '30-50'],
  [50, 80,  '#f0c040', '較大',    '50-80'],
  [80, 130, '#f08040', '大雨',    '80-130'],
  [130, 200,'#d63838', '豪雨',    '130-200'],
  [200, 9999,'#8b1d8b','超大豪雨','> 200'],
];

function fcstColor(mm) {{
  for (const [lo, hi, c] of FCST_BANDS) {{
    if (mm >= lo && mm < hi) return c;
  }}
  return FCST_BANDS[0][2];
}}
function fcstLabel(mm) {{
  for (const [lo, hi, c, lbl] of FCST_BANDS) {{
    if (mm >= lo && mm < hi) return lbl;
  }}
  return '無雨';
}}

// 建圖例
(function buildLegend() {{
  const box = document.getElementById('fcstLegendBars');
  FCST_BANDS.slice().reverse().forEach(([lo, hi, c, lbl, rng]) => {{
    const row = document.createElement('div');
    row.className = 'fcst-bar';
    row.innerHTML = `<div class="fcst-bar-color" style="background:${{c}}"></div>` +
                    `<div class="fcst-bar-label">${{lbl}}</div>` +
                    `<div class="fcst-bar-range">${{rng}}</div>`;
    box.appendChild(row);
  }});
}})();

// 建單日 tabs
const fcstTabs = document.getElementById('fcstTabs');
function buildDayTabs() {{
  fcstTabs.innerHTML = '';
  FORECAST_DATES.forEach((d, i) => {{
    const dt = new Date(d);
    const wk = '日一二三四五六'[dt.getDay()];
    const btn = document.createElement('button');
    btn.textContent = (dt.getMonth()+1) + '/' + dt.getDate() + '(' + wk + ')';
    btn.dataset.date = d;
    if (i === 0) btn.classList.add('active');
    btn.addEventListener('click', () => {{
      document.querySelectorAll('#fcstTabs button').forEach(x => x.classList.remove('active'));
      btn.classList.add('active');
      renderForecastMap([d]);
    }});
    fcstTabs.appendChild(btn);
  }});
}}
buildDayTabs();

// 建自訂複選 checkbox
const fcstCheckboxes = document.getElementById('fcstCheckboxes');
function buildCheckboxes() {{
  fcstCheckboxes.innerHTML = '';
  FORECAST_DATES.forEach((d, i) => {{
    const dt = new Date(d);
    const wk = '日一二三四五六'[dt.getDay()];
    const wrapper = document.createElement('label');
    wrapper.dataset.date = d;
    if (i < 3) wrapper.classList.add('checked');   // 預設勾前 3 天
    wrapper.innerHTML =
      '<input type="checkbox" ' + (i < 3 ? 'checked' : '') + '>' +
      (dt.getMonth()+1) + '/' + dt.getDate() + '(' + wk + ')';
    const cb = wrapper.querySelector('input');
    cb.addEventListener('change', () => {{
      wrapper.classList.toggle('checked', cb.checked);
      applyCustomForecast();
    }});
    fcstCheckboxes.appendChild(wrapper);
  }});
}}
buildCheckboxes();

function applyCustomForecast() {{
  const picked = [...fcstCheckboxes.querySelectorAll('input:checked')]
    .map(cb => cb.closest('label').dataset.date);
  if (picked.length === 0) {{
    document.getElementById('fcstInfo').innerHTML = '⚠ 請至少勾選 1 天';
    return;
  }}
  renderForecastMap(picked);
}}

// 模式切換 (單日 / 3天 / 7天 / 自訂)
let fcstMode = 'single';
document.querySelectorAll('.fcst-mode-bar button').forEach(b => {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('.fcst-mode-bar button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    fcstMode = b.dataset.mode;
    const tabsEl = document.getElementById('fcstTabs');
    const cbEl = document.getElementById('fcstCheckboxes');
    const infoEl = document.getElementById('fcstInfo');
    tabsEl.style.display = (fcstMode === 'single') ? 'flex' : 'none';
    cbEl.style.display = (fcstMode === 'custom') ? 'flex' : 'none';
    infoEl.style.display = (fcstMode === 'single') ? 'none' : 'block';
    if (fcstMode === 'single') {{
      const activeBtn = document.querySelector('#fcstTabs button.active') || document.querySelector('#fcstTabs button');
      if (activeBtn) renderForecastMap([activeBtn.dataset.date]);
    }} else if (fcstMode === '3day') {{
      renderForecastMap(FORECAST_DATES.slice(0, 3));
    }} else if (fcstMode === '7day') {{
      renderForecastMap(FORECAST_DATES.slice(0, 7));
    }} else if (fcstMode === 'custom') {{
      applyCustomForecast();
    }}
  }});
}});

// 預測 Leaflet 地圖
const fcstMap = L.map('fcstMap', {{zoomControl: true, attributionControl: false, minZoom: 6, maxZoom: 13, maxBounds: L.latLngBounds([[20.5, 118.0], [26.5, 123.5]]), maxBoundsViscosity: 1.0}}).setView([23.7, 121.0], 7);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 16,   // 允許縮到街道級別看鄉鎮
  opacity: 0.55,
}}).addTo(fcstMap);
L.control.attribution({{position: 'bottomright'}}).addAttribution('© OSM').addTo(fcstMap);

let fcstGeoLayer = null;
let fcstLabelLayer = L.layerGroup().addTo(fcstMap);

// 依日期陣列，回傳每縣加總 mm
function sumForecastForDates(row, dateArr) {{
  if (!row || !row.forecast) return 0;
  const set = new Set(dateArr);
  let s = 0;
  row.forecast.forEach(f => {{ if (set.has(f.d)) s += f.mm; }});
  return Math.round(s * 10) / 10;
}}

// 依累積 mm 決定色階（單日模式用「單日級距」，多日累積用主圖級距）
function fcstColorForSum(mm, isMultiDay) {{
  if (!isMultiDay) return fcstColor(mm);
  // 多日累積用主圖 COLOR_BANDS 級距（0-30, 30-80, 80-150, 150-300, 300-500, 500-800, 800+）
  for (const [lo, hi, c] of BANDS) {{
    if (mm >= lo && mm < hi) return c;
  }}
  return BANDS[0][2];
}}
function fcstLabelForSum(mm, isMultiDay) {{
  if (!isMultiDay) return fcstLabel(mm);
  for (const [lo, hi, c, lbl] of BANDS) {{
    if (mm >= lo && mm < hi) return lbl;
  }}
  return BANDS[0][3];
}}

function renderForecastMap(dateArr) {{
  if (fcstGeoLayer) fcstMap.removeLayer(fcstGeoLayer);
  fcstLabelLayer.clearLayers();

  const isMultiDay = dateArr.length > 1;
  const title = isMultiDay
    ? '📅 累積期間：<strong>' + dateArr[0] + ' ~ ' + dateArr[dateArr.length-1] + '</strong>　共 <strong>' + dateArr.length + '</strong> 天'
    : '';
  if (isMultiDay) {{
    document.getElementById('fcstInfo').innerHTML = title +
      '<br><span style="color:#666;font-size:11px">※ 累積雨量使用主圖級距（≥30 mm 略多、≥150 mm 多雨、≥300 mm 豪雨等），與單日級距不同</span>';
  }}

  const drawIt = (geo) => {{
    fcstGeoLayer = L.geoJSON(geo, {{
      style: (feature) => {{
        const {{row}} = getDataForFeature(feature);
        const mm = sumForecastForDates(row, dateArr);
        return {{fillColor: fcstColorForSum(mm, isMultiDay), weight: 0.8, color: '#fff', fillOpacity: 0.75}};
      }},
      onEachFeature: (feature, layer) => {{
        const {{name, row}} = getDataForFeature(feature);
        const mm = sumForecastForDates(row, dateArr);
        const c = fcstColorForSum(mm, isMultiDay);
        const lbl = fcstLabelForSum(mm, isMultiDay);
        const rangeLbl = isMultiDay
          ? (dateArr[0] + ' ~ ' + dateArr[dateArr.length-1] + ' 累積')
          : (dateArr[0] + ' 預測');
        layer.bindPopup(
          `<div class="popup-content"><strong>${{name}}</strong><br>` +
          `${{rangeLbl}}：<strong style="color:${{c}};font-size:16px">${{mm.toFixed(1)}} mm</strong><br>` +
          `<span style="color:#888">（${{lbl}}）</span></div>`
        );
        if (row) {{
          const center = layer.getBounds().getCenter();
          // 豪雨級縣市 → label 加脈動 class
          const isHeavy = isMultiDay ? mm >= 150 : mm >= 80;
          const isStorm = isMultiDay ? mm >= 300 : mm >= 130;
          const cls = 'county-label' + (isStorm ? ' storm-lvl' : '');
          L.marker([center.lat, center.lng], {{
            icon: L.divIcon({{
              className: cls,
              html: name.replace('縣','').replace('市','') + '<span class="mm">' + mm.toFixed(0) + '</span>',
              iconSize: null,
            }}),
          }}).addTo(fcstLabelLayer);
          // 豪雨縣市加雨滴粒子 (多滴錯開時間)
          if (isHeavy) {{
            const drops = ['💧','💧','💧'].map((_, di) =>
              '<span style="display:inline-block;animation:raindrop 1.4s linear infinite;animation-delay:' + (di * 0.4) + 's">💧</span>'
            ).join('');
            L.marker([center.lat + 0.05, center.lng], {{
              icon: L.divIcon({{
                className: 'rain-particle',
                html: drops,
                iconSize: [48, 30],
              }}),
              interactive: false,
            }}).addTo(fcstLabelLayer);
          }}
        }}
      }},
    }}).addTo(fcstMap);
  }};

  if (window._geo) {{
    drawIt(window._geo);
  }} else {{
    fetch(GEOJSON_URL).then(r => r.json()).then(g => {{ window._geo = g; drawIt(g); }});
  }}

  // 同步更新縣市排名
  renderFcstRanking(dateArr, isMultiDay);
}}

// 縣市排名：預設多→少，可反轉
let fcstSortDesc = true;
let lastFcstDateArr = null;
let lastFcstMultiDay = false;

function toggleFcstSort() {{
  fcstSortDesc = !fcstSortDesc;
  if (lastFcstDateArr) renderFcstRanking(lastFcstDateArr, lastFcstMultiDay);
}}

function renderFcstRanking(dateArr, isMultiDay) {{
  lastFcstDateArr = dateArr;
  lastFcstMultiDay = isMultiDay;
  const rows = DATA.map(c => ({{
    name: c.name,
    mm: sumForecastForDates(c, dateArr),
  }})).sort((a, b) => fcstSortDesc ? b.mm - a.mm : a.mm - b.mm);
  const rangeLbl = isMultiDay
    ? (dateArr[0] + ' ~ ' + dateArr[dateArr.length-1] + '（累積 ' + dateArr.length + ' 天）')
    : (dateArr[0] + ' 單日');
  document.getElementById('fcstRankingTitle').textContent =
    '📊 22 縣市預測雨量排名 · ' + rangeLbl + '（' + (fcstSortDesc ? '多→少' : '少→多') + '）';
  document.getElementById('fcstSortToggle').textContent =
    fcstSortDesc ? '⇅ 改為 少→多' : '⇅ 改為 多→少';
  const tbody = document.getElementById('fcstRankingBody');
  tbody.innerHTML = '';
  rows.forEach((r, i) => {{
    const c = fcstColorForSum(r.mm, isMultiDay);
    const lbl = fcstLabelForSum(r.mm, isMultiDay);
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td class="rank">' + (i + 1) + '</td>' +
      '<td class="county">' + r.name + '</td>' +
      '<td class="lvl" style="color:' + c + '">' + fcstEmoji(r.mm, isMultiDay) + ' ' + lbl + '</td>' +
      '<td class="mm" style="color:' + c + '">' + r.mm.toFixed(1) + ' mm</td>';
    tbody.appendChild(tr);
  }});
}}

// 預設載入第一天預測
if (FORECAST_DATES.length > 0) {{
  renderForecastMap([FORECAST_DATES[0]]);
}}

// ============ 📈 進階氣候比較 (年 × 月 × 地區 × 指標 四維) ============
(function initAdv() {{
  const curYear = new Date().getFullYear();
  const yearsWrap = document.getElementById('advYears');
  for (let y = curYear; y >= curYear - 9; y--) {{
    _makeAdvCb(yearsWrap, y, y + ' 年', y >= curYear - 2);
  }}
  const monthsWrap = document.getElementById('advMonths');
  for (let m = 1; m <= 12; m++) {{
    _makeAdvCb(monthsWrap, m, m + '月', m === new Date().getMonth() + 1);
  }}
  const regionsWrap = document.getElementById('advRegions');
  const allCounties = (window.HISTORY && window.HISTORY.counties) || ['臺南市','高雄市','屏東縣'];
  const bizRegions = ['臺南市', '嘉義縣', '嘉義市', '宜蘭縣', '花蓮縣'];
  allCounties.forEach(r => {{
    _makeAdvCb(regionsWrap, r, r, bizRegions.includes(r));
  }});
  // 綁定已 hardcode 的 metric chip
  document.querySelectorAll('#advMetrics input').forEach(cb => {{
    const lb = cb.closest('label');
    if (cb.checked) lb.classList.add('on');
    cb.addEventListener('change', () => {{
      lb.classList.toggle('on', cb.checked);
      updateAdvEst();
    }});
  }});
  updateAdvEst();
}})();

function _makeAdvCb(wrap, val, txt, checked) {{
  const lb = document.createElement('label');
  lb.dataset.val = val;
  if (checked) lb.classList.add('on');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.value = val;
  cb.checked = !!checked;
  cb.addEventListener('change', () => {{
    lb.classList.toggle('on', cb.checked);
    updateAdvEst();
  }});
  lb.appendChild(cb);
  lb.appendChild(document.createTextNode(' ' + txt));
  wrap.appendChild(lb);
}}

function _advPicked(id) {{
  return [...document.querySelectorAll('#' + id + ' input:checked')].map(c => c.value);
}}
function updateAdvEst() {{
  const y = _advPicked('advYears').length;
  const m = _advPicked('advMonths').length;
  const r = _advPicked('advRegions').length;
  const met = _advPicked('advMetrics').length;
  const n = y * m * r;
  document.getElementById('advEst').textContent = n + ' 組 × ' + met + ' 指標';
  const sum = document.getElementById('advSummary');
  if (sum) sum.textContent = '已選: ' + y + '年 · ' + m + '月 · ' + r + '地區 · ' + met + '指標';
}}
function advQuick(type, action) {{
  const map = {{year: 'advYears', month: 'advMonths', region: 'advRegions', metric: 'advMetrics'}};
  const wrap = document.getElementById(map[type]);
  const cbs = wrap.querySelectorAll('input');
  cbs.forEach(cb => {{
    const lb = cb.closest('label');
    let should = cb.checked;
    if (action === 'clear') should = false;
    else if (action === 'all') should = true;
    else if (type === 'year') {{
      const y = parseInt(cb.value);
      const cur = new Date().getFullYear();
      if (action === 'last3') should = (y >= cur - 2);
      else if (action === 'last5') should = (y >= cur - 4);
      else if (action === 'last10') should = true;
    }} else if (type === 'month') {{
      const m = parseInt(cb.value);
      if (action === 'q1') should = (m <= 3);
      else if (action === 'q2') should = (m >= 4 && m <= 6);
      else if (action === 'q3') should = (m >= 7 && m <= 9);
      else if (action === 'q4') should = (m >= 10);
    }} else if (type === 'region') {{
      if (action === 'south') should = ['嘉義市','嘉義縣','臺南市','高雄市','屏東縣'].includes(cb.value);
      else if (action === 'east') should = ['宜蘭縣','花蓮縣','臺東縣'].includes(cb.value);
      else if (action === 'biz') should = ['臺南市','嘉義縣','嘉義市','宜蘭縣','花蓮縣'].includes(cb.value);
    }} else if (type === 'metric') {{
      if (action === 'rain') should = ['mm','rd','sd'].includes(cb.value);
      else if (action === 'temp') should = ['tavg','tmax','tmin'].includes(cb.value);
      else if (action === 'sales') {{
        // +銷售: 保留已選+加勾 sales
        if (cb.value === 'sales') should = true;
      }}
    }}
    cb.checked = should;
    lb.classList.toggle('on', should);
  }});
  updateAdvEst();
}}

let _advResults = [];
let _advSortKey = 'mm';
let _advSortDesc = true;
let _advView = 'matrix';

let _advMetrics = ['mm'];  // 目前選的指標

function runAdvancedCompare() {{
  const years = _advPicked('advYears').map(Number).sort();
  const months = _advPicked('advMonths').map(Number).sort((a,b)=>a-b);
  const regions = _advPicked('advRegions');
  const metrics = _advPicked('advMetrics');
  if (!years.length || !months.length || !regions.length) {{
    alert('請至少選 1 個年、1 個月、1 個地區');
    return;
  }}
  if (!metrics.length) {{
    alert('請至少選 1 個指標 (雨量或氣溫)');
    return;
  }}
  _advMetrics = metrics;
  const combos = [];
  regions.forEach(r => years.forEach(y => months.forEach(m => combos.push({{r, y, m}}))));
  const btn = document.getElementById('advRun');
  const status = document.getElementById('advStatus');
  btn.disabled = true;
  status.className = 'adv-status show';
  status.innerHTML = '⚡ 即時比對 <strong>' + combos.length + '</strong> 組合 × <strong>' + metrics.length + '</strong> 指標';

  try {{
    _advResults = combos.map(({{r, y, m}}) => {{
      const regData = (HISTORY.data || {{}})[r] || {{}};
      const mData = (regData[String(y)] || {{}})[String(m)] || {{}};
      const rd = mData.rd != null ? mData.rd : 0;
      const sd = mData.sd != null ? mData.sd : 0;
      // 銷售 (全國,不隨地區) — 從 window.SALES 抓
      let sales = null;
      const salesArr = (window.SALES && window.SALES.monthly) ? window.SALES.monthly[String(y)] : null;
      if (salesArr && salesArr[m-1] != null) sales = salesArr[m-1];
      return {{
        region: r, year: y, month: m,
        mm: mData.mm != null ? mData.mm : 0,
        rd: rd, sd: sd,
        rainDays: rd, stormDays: sd,  // alias for backward compat
        tavg: mData.tavg, tmax: mData.tmax, tmin: mData.tmin,
        sales: sales,
        src: mData.src || '?',
      }};
    }});
    btn.disabled = false;
    const src = HISTORY.source || 'CWA';
    status.innerHTML = '✅ 已載入 <strong>' + _advResults.length + '</strong> 組合 × <strong>' + metrics.length + '</strong> 指標｜' + src;
    document.getElementById('advViewTabs').style.display = 'flex';
    document.getElementById('advTableWrap').style.display = '';
    renderAdvView();
    renderAdvAnalysis();
  }} catch (e) {{
    console.error(e);
    btn.disabled = false;
    status.innerHTML = '❌ 查詢失敗：' + e.message;
  }}
}}

const METRIC_META = {{
  mm: {{label: '累積雨量', unit: 'mm', color: '#1976d2', fmt: v => (v||0).toFixed(0)}},
  rd: {{label: '有雨日', unit: '天', color: '#26a69a', fmt: v => (v||0).toFixed(0)}},
  sd: {{label: '豪雨日', unit: '天', color: '#7b1fa2', fmt: v => (v||0).toFixed(0)}},
  tavg: {{label: '均溫', unit: '°C', color: '#c62828', fmt: v => v != null ? v.toFixed(1) : '–'}},
  tmax: {{label: '最高溫', unit: '°C', color: '#d32f2f', fmt: v => v != null ? v.toFixed(1) : '–'}},
  tmin: {{label: '最低溫', unit: '°C', color: '#0288d1', fmt: v => v != null ? v.toFixed(1) : '–'}},
  sales: {{label: '銷售噸數', unit: '噸', color: '#e65100', fmt: v => v != null ? v.toLocaleString() : '–'}},
}};

// 視圖切換
document.querySelectorAll('#advViewTabs button').forEach(b => {{
  b.addEventListener('click', () => {{
    document.querySelectorAll('#advViewTabs button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    _advView = b.dataset.view;
    renderAdvView();
  }});
}});

function _mxLvl(mm) {{
  if (mm < 1) return 0;
  if (mm < 30) return 1;
  if (mm < 80) return 2;
  if (mm < 150) return 3;
  if (mm < 300) return 4;
  if (mm < 500) return 5;
  if (mm < 800) return 6;
  return 7;
}}

function renderAdvView() {{
  const wrap = document.getElementById('advTableWrap');
  const metrics = _advMetrics.length ? _advMetrics : ['mm'];

  if (_advView === 'matrix') {{
    // 矩陣：row=地區+年，col=月×指標(展開)
    const regions = [...new Set(_advResults.map(r => r.region))];
    const years = [...new Set(_advResults.map(r => r.year))].sort();
    const months = [...new Set(_advResults.map(r => r.month))].sort((a,b)=>a-b);
    let html = '<table class="adv-matrix"><thead>';
    // 兩層 header: 月份 (colspan=指標數) + 各指標
    if (metrics.length > 1) {{
      html += '<tr><th rowspan="2" style="min-width:130px">地區 · 年份</th>';
      months.forEach(m => {{ html += '<th colspan="' + metrics.length + '" style="text-align:center;background:#e3f2fd">' + m + ' 月</th>'; }});
      html += '</tr><tr>';
      months.forEach(() => {{
        metrics.forEach(mk => {{
          const meta = METRIC_META[mk];
          html += '<th style="font-size:10px;background:' + meta.color + '15;color:' + meta.color + '">' + meta.label + '</th>';
        }});
      }});
      html += '</tr>';
    }} else {{
      html += '<tr><th style="min-width:130px">地區 · 年份</th>';
      months.forEach(m => {{ html += '<th>' + m + ' 月</th>'; }});
      html += '</tr>';
    }}
    html += '</thead><tbody>';
    regions.forEach(r => {{
      years.forEach(y => {{
        html += '<tr><th>' + r + ' · ' + y + '</th>';
        months.forEach(m => {{
          const item = _advResults.find(x => x.region === r && x.year === y && x.month === m);
          metrics.forEach(mk => {{
            if (!item) {{ html += '<td>–</td>'; return; }}
            const val = item[mk];
            const meta = METRIC_META[mk];
            let cls = '', style = '';
            if (mk === 'mm') {{
              cls = 'mx-' + _mxLvl(val);
            }} else if (mk === 'rd' || mk === 'sd') {{
              const bg = Math.min((val || 0) / 15, 1);
              style = 'background:rgba(38,166,154,' + bg.toFixed(2) + ');color:' + (bg > 0.5 ? '#fff' : '#333');
            }} else if (mk === 'tavg' || mk === 'tmax' || mk === 'tmin') {{
              if (val == null) {{ html += '<td>–</td>'; return; }}
              // 溫度色: 低藍 → 高紅
              const t = Math.max(0, Math.min(1, (val - 5) / 30));
              const rr = Math.round(60 + t * 195), bb = Math.round(220 - t * 200);
              style = 'background:rgb(' + rr + ',110,' + bb + ');color:#fff;font-weight:900';
            }}
            html += '<td class="' + cls + '" style="' + style + '" title="' + meta.label + ': ' + meta.fmt(val) + ' ' + meta.unit + '">' + meta.fmt(val) + '</td>';
          }});
        }});
        html += '</tr>';
      }});
    }});
    html += '</tbody></table>';
    wrap.innerHTML = html;
  }} else if (_advView === 'flat') {{
    // Flat 表格
    const sorted = [..._advResults].sort((a, b) => {{
      const av = a[_advSortKey], bv = b[_advSortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'string') return _advSortDesc ? bv.localeCompare(av) : av.localeCompare(bv);
      return _advSortDesc ? bv - av : av - bv;
    }});
    const cols = [['region', '地區'], ['year', '年份'], ['month', '月']];
    metrics.forEach(mk => cols.push([mk, METRIC_META[mk].label + ' (' + METRIC_META[mk].unit + ')']));
    let html = '<table class="adv-table"><thead><tr>';
    cols.forEach(([k, lbl]) => {{
      const isSort = _advSortKey === k;
      const arrow = isSort ? (_advSortDesc ? '▼' : '▲') : '';
      html += '<th onclick="advSortBy(\\'' + k + '\\')">' + lbl + ' <span class="sort">' + arrow + '</span></th>';
    }});
    html += '</tr></thead><tbody>';
    // 各指標 max/min for highlight
    const metricStats = {{}};
    metrics.forEach(mk => {{
      const vals = _advResults.map(r => r[mk]).filter(v => v != null);
      metricStats[mk] = {{max: Math.max(...vals), min: Math.min(...vals)}};
    }});
    sorted.forEach(r => {{
      html += '<tr><td class="region">' + r.region + '</td><td class="year">' + r.year + '</td><td>' + r.month + '月</td>';
      metrics.forEach(mk => {{
        const v = r[mk];
        const meta = METRIC_META[mk];
        const s = metricStats[mk];
        const hi = v === s.max ? ' high' : (v === s.min ? ' low' : '');
        html += '<td class="mm' + hi + '" style="color:' + meta.color + ';font-weight:700">' + meta.fmt(v) + '</td>';
      }});
      html += '</tr>';
    }});
    html += '</tbody></table>';
    wrap.innerHTML = html;
  }} else if (_advView === 'chart') {{
    // 折線圖: 智慧判定 X 軸 — 多月 → X=月份 · 單月多年 → X=年份
    const regions = [...new Set(_advResults.map(r => r.region))];
    const years = [...new Set(_advResults.map(r => r.year))].sort();
    const months = [...new Set(_advResults.map(r => r.month))].sort((a,b)=>a-b);
    if (months.length < 2 && years.length < 2) {{
      wrap.innerHTML = '<div style="padding:20px;text-align:center;color:#888">折線圖需選「2 個以上月份」或「2 個以上年份」才有意義</div>';
      return;
    }}
    // X 軸: 多月優先 (跨月趨勢),單月時改跨年
    const xMode = months.length >= 2 ? 'month' : 'year';
    const xVals = xMode === 'month' ? months : years;
    // 三軸: 左 rain, 右 temp, 銷售用「相對比例」畫在同一 chart (自己 scale)
    const rainMetrics = metrics.filter(m => ['mm','rd','sd'].includes(m));
    const tempMetrics = metrics.filter(m => ['tavg','tmax','tmin'].includes(m));
    const salesMetrics = metrics.filter(m => m === 'sales');
    const rainVals = _advResults.flatMap(r => rainMetrics.map(mk => r[mk]).filter(v => v != null));
    const tempVals = _advResults.flatMap(r => tempMetrics.map(mk => r[mk]).filter(v => v != null));
    const salesVals = _advResults.map(r => r.sales).filter(v => v != null);
    const rainMax = rainVals.length ? Math.max(...rainVals) : 100;
    const tempMax = tempVals.length ? Math.max(...tempVals) : 35;
    const tempMin = tempVals.length ? Math.min(...tempVals) : 0;
    const salesMax = salesVals.length ? Math.max(...salesVals) : 1000;

    const W = 900, HGT = 400, pl = 55, pr = tempMetrics.length ? 55 : 20, pt = 40, pb = 50;
    const cw = W - pl - pr, ch = HGT - pt - pb;
    let svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + HGT + '" preserveAspectRatio="xMidYMid meet">';
    const xLabel = xMode === 'month' ? '月份' : '年份';
    const titleDim = xMode === 'month'
      ? (regions.length + '地區×' + years.length + '年×' + metrics.length + '指標')
      : (regions.length + '地區×' + months[0] + '月×' + metrics.length + '指標');
    svg += '<text x="' + (W/2) + '" y="22" text-anchor="middle" font-size="13" font-weight="900" fill="#333">📈 逐' + xLabel + '趨勢對照 · ' + titleDim + '</text>';
    // 軸
    svg += '<line x1="' + pl + '" y1="' + (pt+ch) + '" x2="' + (W-pr) + '" y2="' + (pt+ch) + '" stroke="#666"/>';
    svg += '<line x1="' + pl + '" y1="' + pt + '" x2="' + pl + '" y2="' + (pt+ch) + '" stroke="#1976d2"/>';
    if (tempMetrics.length) svg += '<line x1="' + (W-pr) + '" y1="' + pt + '" x2="' + (W-pr) + '" y2="' + (pt+ch) + '" stroke="#c62828"/>';
    // Y ticks
    for (let i = 0; i <= 4; i++) {{
      const y = pt + ch - ch * i / 4;
      svg += '<line x1="' + pl + '" y1="' + y + '" x2="' + (W-pr) + '" y2="' + y + '" stroke="#f0f0f0"/>';
      svg += '<text x="' + (pl-6) + '" y="' + (y+4) + '" text-anchor="end" font-size="10" fill="#1976d2" font-weight="700">' + Math.round(rainMax * i / 4) + '</text>';
      if (tempMetrics.length) {{
        const tv = tempMin + (tempMax - tempMin) * i / 4;
        svg += '<text x="' + (W-pr+6) + '" y="' + (y+4) + '" text-anchor="start" font-size="10" fill="#c62828" font-weight="700">' + tv.toFixed(0) + '°</text>';
      }}
    }}
    // X ticks
    xVals.forEach((xv, i) => {{
      const x = pl + (cw / Math.max(1, xVals.length-1)) * i;
      const lbl = xMode === 'month' ? (xv + '月') : (xv + '');
      svg += '<text x="' + x + '" y="' + (pt+ch+16) + '" text-anchor="middle" font-size="11" fill="#333" font-weight="700">' + lbl + '</text>';
    }});
    // 每條線: 多月模式 → 每(地區,年,指標) 一條; 單月模式 → 每(地區,指標) 一條(X是年)
    const lines = [];
    if (xMode === 'month') {{
      regions.forEach(r => years.forEach(y => metrics.forEach(mk => lines.push({{r, y, mk}}))));
    }} else {{
      // 單月多年: 每 (r, mk) 一條,y=null 代表沿年展開
      regions.forEach(r => metrics.forEach(mk => lines.push({{r, y: null, mk}})));
    }}
    const COLORS = ['#1976d2','#c62828','#2e7d32','#f57c00','#7b1fa2','#00695c','#d84315','#0288d1','#c2185b','#5d4037','#00838f','#616161'];
    // sales 在多月模式每年一條(不隨地區), 單月模式每指標一條(不隨地區)
    const drawnSales = new Set();
    lines.forEach((L, li) => {{
      const isTemp = ['tavg','tmax','tmin'].includes(L.mk);
      const isSales = L.mk === 'sales';
      if (isSales) {{
        const k = 'sales_' + xMode + '_' + (L.y || 'x');
        if (drawnSales.has(k)) return;
        drawnSales.add(k);
      }}
      const color = isSales ? '#e65100' : COLORS[li % COLORS.length];
      const pts = [];
      xVals.forEach((xv, i) => {{
        // 尋找 item: xMode=month 時 xv=month,固定 L.y; xMode=year 時 xv=year, 固定 months[0]
        const item = xMode === 'month'
          ? _advResults.find(x => x.region === L.r && x.year === L.y && x.month === xv)
          : _advResults.find(x => x.region === L.r && x.year === xv && x.month === months[0]);
        if (!item) return;
        const v = item[L.mk];
        if (v == null) return;
        const x = pl + (cw / Math.max(1, xVals.length-1)) * i;
        let yv, tip;
        if (isTemp) {{ yv = pt + ch - ((v - tempMin) / (tempMax - tempMin)) * ch; tip = v.toFixed(1) + '°C'; }}
        else if (isSales) {{ yv = pt + ch - (v / salesMax) * ch; tip = v.toLocaleString() + ' 噸'; }}
        else {{ yv = pt + ch - (v / rainMax) * ch; tip = v.toFixed(0) + (L.mk === 'mm' ? ' mm' : (L.mk === 'rd' || L.mk === 'sd' ? ' 天' : '')); }}
        pts.push({{x, yv, v, tip}});
      }});
      if (pts.length >= 2) {{
        const dash = isTemp ? 'stroke-dasharray="5,3"' : (isSales ? 'stroke-dasharray="2,2" stroke-width="3"' : '');
        svg += '<polyline points="' + pts.map(p => p.x + ',' + p.yv).join(' ') + '" fill="none" stroke="' + color + '" stroke-width="' + (isSales ? '3' : '2') + '" ' + dash + ' opacity="' + (isSales ? '1' : '0.85') + '"/>';
      }}
      pts.forEach(p => {{
        const rSize = isSales ? 5 : 3;
        const lblYear = L.y || 'x';
        svg += '<circle cx="' + p.x + '" cy="' + p.yv + '" r="' + rSize + '" fill="' + color + '"' + (isSales ? ' stroke="#fff" stroke-width="1.5"' : '') + '><title>' + (isSales ? '💰' : L.r + ' ' + lblYear) + ' ' + METRIC_META[L.mk].label + ': ' + p.tip + '</title></circle>';
      }});
    }});
    // 圖例 (在圖下方,可換行)
    svg += '</svg>';
    let legHtml = '<div class="adv-chart-legend">';
    const seenSales = new Set();
    const uniqLines = lines.filter(L => {{
      if (L.mk === 'sales') {{
        const k = 'sales_' + L.y;
        if (seenSales.has(k)) return false;
        seenSales.add(k); return true;
      }}
      return true;
    }});
    uniqLines.slice(0, 20).forEach((L, li) => {{
      const isTemp = ['tavg','tmax','tmin'].includes(L.mk);
      const isSales = L.mk === 'sales';
      const color = isSales ? '#e65100' : COLORS[li % COLORS.length];
      const yLbl = L.y != null ? L.y : (xMode === 'year' ? '跨年' : '?');
      const label = isSales ? ('💰 ' + yLbl + ' 銷售(全國)') : (L.r + ' · ' + yLbl + ' · ' + METRIC_META[L.mk].label);
      legHtml += '<span class="leg"><span class="ln" style="background:' + color + (isSales ? ';height:5px' : '') + '"></span>' + label + '</span>';
    }});
    if (uniqLines.length > 20) legHtml += '<span style="color:#888">... 及其他 ' + (uniqLines.length - 20) + ' 條</span>';
    legHtml += '</div>';
    wrap.innerHTML = svg + legHtml;
  }} else if (_advView === 'bar') {{
    // 長條圖: 分組長條, X=年份, 每組=地區×指標
    const regions = [...new Set(_advResults.map(r => r.region))];
    const years = [...new Set(_advResults.map(r => r.year))].sort();
    const months = [...new Set(_advResults.map(r => r.month))].sort((a,b)=>a-b);
    if (years.length < 1) {{
      wrap.innerHTML = '<div style="padding:20px;text-align:center;color:#888">請至少選 1 年</div>';
      return;
    }}
    // 每個月獨立畫一個 chart (若選多月)
    let html = '';
    months.forEach(mSel => {{
      const filtered = _advResults.filter(r => r.month === mSel);
      if (!filtered.length) return;
      // 每指標分別畫
      metrics.forEach(mk => {{
        const meta = METRIC_META[mk];
        const isTemp = ['tavg','tmax','tmin'].includes(mk);
        const rows = filtered.map(r => ({{r: r.region, y: r.year, v: r[mk]}})).filter(x => x.v != null);
        if (!rows.length) return;
        const maxV = Math.max(...rows.map(x => x.v)) * 1.15;
        const minV = isTemp ? Math.min(...rows.map(x => x.v)) * 0.95 : 0;

        const W = 900, HGT = 240 + years.length * 4, pl = 60, pr = 20, pt = 44, pb = 50;
        const cw = W - pl - pr, ch = HGT - pt - pb;
        const groupCount = regions.length;
        const groupW = cw / years.length;
        const barW = Math.max(6, (groupW - 12) / groupCount);

        let svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + HGT + '" preserveAspectRatio="xMidYMid meet">';
        svg += '<text x="' + (W/2) + '" y="20" text-anchor="middle" font-size="14" font-weight="900" fill="' + meta.color + '">📊 ' + mSel + '月 · ' + meta.label + ' (' + meta.unit + ') · 逐年對比</text>';
        // Y ticks
        for (let i = 0; i <= 4; i++) {{
          const y = pt + ch - ch * i / 4;
          const v = minV + (maxV - minV) * i / 4;
          svg += '<line x1="' + pl + '" y1="' + y + '" x2="' + (W-pr) + '" y2="' + y + '" stroke="#eee"/>';
          svg += '<text x="' + (pl-6) + '" y="' + (y+4) + '" text-anchor="end" font-size="10" fill="#666">' + (isTemp ? v.toFixed(1) : Math.round(v)) + '</text>';
        }}
        svg += '<line x1="' + pl + '" y1="' + (pt+ch) + '" x2="' + (W-pr) + '" y2="' + (pt+ch) + '" stroke="#666"/>';
        // 每年群組
        years.forEach((y, yi) => {{
          const gx = pl + groupW * yi + 6;
          svg += '<text x="' + (gx + (groupW - 12) / 2) + '" y="' + (pt+ch+16) + '" text-anchor="middle" font-size="11" fill="#333" font-weight="700">' + y + '</text>';
          regions.forEach((r, ri) => {{
            const item = filtered.find(x => x.year === y && x.region === r);
            if (!item || item[mk] == null) return;
            const v = item[mk];
            const bh = ((v - minV) / (maxV - minV || 1)) * ch;
            const bx = gx + barW * ri;
            const by = pt + ch - bh;
            // 顏色: 溫度用漸層,雨量用地區色
            let color;
            if (isTemp) {{
              const t = Math.max(0, Math.min(1, (v - 5) / 30));
              const rr = Math.round(80 + t * 175), bb = Math.round(220 - t * 200);
              color = 'rgb(' + rr + ',110,' + bb + ')';
            }} else {{
              const regionColors = ['#1976d2','#c62828','#2e7d32','#f57c00','#7b1fa2','#00695c','#d84315','#0288d1','#c2185b','#5d4037','#00838f','#616161'];
              color = regionColors[regions.indexOf(r) % regionColors.length];
            }}
            svg += '<rect x="' + bx + '" y="' + by + '" width="' + (barW-1) + '" height="' + bh + '" fill="' + color + '" opacity="0.85"><title>' + r + ' ' + y + '/' + mSel + ' ' + meta.label + ': ' + meta.fmt(v) + ' ' + meta.unit + '</title></rect>';
            if (bh > 20) svg += '<text x="' + (bx + (barW-1)/2) + '" y="' + (by - 3) + '" text-anchor="middle" font-size="9" fill="' + color + '" font-weight="700">' + meta.fmt(v) + '</text>';
          }});
        }});
        svg += '</svg>';
        // 圖例 (地區色)
        let leg = '<div class="adv-chart-legend">';
        if (!isTemp) {{
          const regionColors = ['#1976d2','#c62828','#2e7d32','#f57c00','#7b1fa2','#00695c','#d84315','#0288d1','#c2185b','#5d4037','#00838f','#616161'];
          regions.forEach((r, ri) => {{
            const c = regionColors[ri % regionColors.length];
            leg += '<span class="leg"><span class="ln" style="background:' + c + ';height:12px;border-radius:2px"></span>' + r + '</span>';
          }});
        }} else {{
          leg += '<span style="color:#666">💡 溫度長條顏色: 冷=藍 · 熱=紅 (漸層自動)</span>';
        }}
        leg += '</div>';
        html += '<div style="margin-bottom:16px;background:#fff;border:1px solid var(--cwa-border);border-radius:4px;padding:6px">' + svg + leg + '</div>';
      }});
    }});
    if (!html) html = '<div style="padding:20px;text-align:center;color:#888">此組合無資料</div>';
    wrap.innerHTML = html;
  }}
}}

function advSortBy(k) {{
  if (_advSortKey === k) _advSortDesc = !_advSortDesc;
  else {{ _advSortKey = k; _advSortDesc = true; }}
  renderAdvView();
}}

function renderAdvAnalysis() {{
  const el = document.getElementById('advAnalysis');
  if (!_advResults.length) {{ el.style.display = 'none'; return; }}
  const rs = _advResults;
  const nRs = rs.length;

  // === 累積雨量統計 ===
  const mmVals = rs.map(r => r.mm).filter(v => v != null);
  const maxMm = rs.reduce((a, b) => b.mm > a.mm ? b : a);
  const minMm = rs.reduce((a, b) => b.mm < a.mm ? b : a);
  const avgMm = mmVals.reduce((s,v)=>s+v,0) / (mmVals.length || 1);
  // === 有雨天數統計 ===
  const rdVals = rs.map(r => r.rd).filter(v => v != null);
  const avgRd = rdVals.reduce((s,v)=>s+v,0) / (rdVals.length || 1);
  const maxRd = rs.reduce((a, b) => (b.rd||0) > (a.rd||0) ? b : a);
  // === 豪雨日 ===
  const totalStorm = rs.reduce((s, r) => s + (r.sd||0), 0);
  const stormCombos = rs.filter(r => (r.sd||0) > 0).length;
  // === 氣溫 ===
  const tavgs = rs.map(r => r.tavg).filter(v => v != null);
  const hasTemp = tavgs.length > 0;
  const avgTavg = hasTemp ? tavgs.reduce((s,v)=>s+v,0) / tavgs.length : null;
  const maxTmax = rs.filter(r => r.tmax != null).reduce((a, b) => (a && a.tmax > b.tmax) ? a : b, null);
  const minTmin = rs.filter(r => r.tmin != null).reduce((a, b) => (a && a.tmin < b.tmin) ? a : b, null);

  // === 年趨勢: 同地區同月比較年份序列 ===
  const trendLines = [];
  const rs_by_rm = {{}};
  rs.forEach(r => {{
    const k = r.region + '_' + r.month;
    if (!rs_by_rm[k]) rs_by_rm[k] = [];
    rs_by_rm[k].push(r);
  }});
  Object.values(rs_by_rm).forEach(arr => {{
    if (arr.length < 2) return;
    arr.sort((a, b) => a.year - b.year);
    const first = arr[0], last = arr[arr.length - 1];
    const diff = last.mm - first.mm;
    const pct = first.mm > 0 ? (diff / first.mm * 100) : 0;
    if (Math.abs(pct) < 5) return;
    const arrow = diff > 0 ? '📈 增' : '📉 減';
    trendLines.push({{
      text: first.region + ' ' + first.month + '月 (' + first.year + '→' + last.year + ')：' +
            '<strong>' + arrow + ' ' + Math.abs(pct).toFixed(0) + '%</strong> (' +
            first.mm.toFixed(0) + ' → ' + last.mm.toFixed(0) + ' mm)',
      pct: pct,
    }});
  }});

  // === 地區差異 ===
  const regionDiffLines = [];
  const rs_by_ym = {{}};
  rs.forEach(r => {{
    const k = r.year + '_' + r.month;
    if (!rs_by_ym[k]) rs_by_ym[k] = [];
    rs_by_ym[k].push(r);
  }});
  Object.values(rs_by_ym).forEach(arr => {{
    if (arr.length < 2) return;
    const hi = arr.reduce((a, b) => b.mm > a.mm ? b : a);
    const lo = arr.reduce((a, b) => b.mm < a.mm ? b : a);
    if (hi.region === lo.region) return;
    const ratio = lo.mm > 0 ? (hi.mm / lo.mm) : 999;
    if (ratio < 1.5) return;
    regionDiffLines.push(hi.year + '年' + hi.month + '月：<strong>' + hi.region + '</strong> ' + hi.mm.toFixed(0) + 'mm 為 <strong>' + lo.region + '</strong> ' + lo.mm.toFixed(0) + 'mm 的 <strong>' + ratio.toFixed(1) + ' 倍</strong>');
  }});

  // === 銷售對照 (若 SALES 有對應年月) ===
  const salesCorr = [];
  if (window.SALES && window.SALES.monthly) {{
    rs.forEach(r => {{
      const arr = window.SALES.monthly[String(r.year)];
      if (arr && arr[r.month - 1] != null) {{
        salesCorr.push({{...r, sales: arr[r.month - 1]}});
      }}
    }});
  }}
  // 分「高雨月」vs「低雨月」的銷售平均對照
  let salesInsight = '';
  if (salesCorr.length >= 4) {{
    const hi = salesCorr.filter(r => r.mm >= 300);
    const lo = salesCorr.filter(r => r.mm < 150);
    if (hi.length && lo.length) {{
      const hiSalesAvg = hi.reduce((s,r)=>s+r.sales,0) / hi.length;
      const loSalesAvg = lo.reduce((s,r)=>s+r.sales,0) / lo.length;
      const ratio = loSalesAvg / hiSalesAvg;
      if (ratio > 1.15) {{
        salesInsight = '📉 <strong>對照銷售明顯</strong>：低雨月 (&lt;150mm) 平均銷售 <strong>' + loSalesAvg.toFixed(0) + ' 噸/月</strong>，高雨月 (≥300mm) 掉到 <strong>' + hiSalesAvg.toFixed(0) + ' 噸/月</strong> (下滑 ' + ((1-1/ratio)*100).toFixed(0) + '%) → <strong>驗證雨量嚴重影響出貨</strong>';
      }} else if (ratio < 0.85) {{
        salesInsight = '🌧 反常現象：高雨月銷量反而較高，可能是<strong>颱風前搶備肥</strong>或<strong>秋季雨後補基肥</strong>行為，值得業務深入了解';
      }} else {{
        salesInsight = '⚖ 雨量與銷售關聯度普通 (差異 &lt; 15%)，銷售受其他因素 (客戶結構/促銷/新品) 影響較大';
      }}
    }}
  }}

  // === 業務綜合判斷 (雨量) ===
  const highRainCombos = rs.filter(r => r.mm >= 300).length;
  const lowRainCombos = rs.filter(r => r.mm < 150).length;
  const goldenCombos = rs.filter(r => r.mm < 150 && (r.rd || 0) < 12).length;
  let bizRain = '';
  if (lowRainCombos > highRainCombos * 1.5) {{
    bizRain = '☀ <strong>整體乾季為主</strong> — 田面可作業機會多，<span class="growth">預估銷量穩定或成長</span>，適合積極衝刺月。';
  }} else if (highRainCombos > nRs * 0.4) {{
    bizRain = '🌧 <strong>多雨月佔比高</strong> — 施肥出貨窗口有限，<span class="drop">預估銷量偏弱</span>，建議：（1）雨前 3 天提前配送 （2）雨後 2 天內快速補倉 （3）主打「速溶粒肥」耐雨規格。';
  }} else {{
    bizRain = '⛅ <strong>乾濕均衡</strong> — 出貨可按平常規劃，重點掌握「雨停放晴」窗口。';
  }}

  // === 業務判斷 (雨日) ===
  let bizRd = '';
  if (avgRd < 8) {{
    bizRd = '☀ <strong>連日晴天多</strong> (平均月有雨 ' + avgRd.toFixed(1) + '天) → 田間作業窗口寬鬆，<strong>撒佈時機容易掌握</strong>。';
  }} else if (avgRd > 20) {{
    bizRd = '🌫 <strong>連日陰雨</strong> (平均月有雨 ' + avgRd.toFixed(1) + '天) → 田面難乾、機具進不去，<strong>撒佈需卡準 24-48 小時空檔</strong>，粒肥可能泡爛，建議加強<strong>粉狀 25kg 包裝</strong>方便人工穴施。';
  }} else {{
    bizRd = '⛅ <strong>雨日普通</strong> (平均 ' + avgRd.toFixed(1) + '天) → 平常作業節奏。';
  }}

  // === 業務判斷 (氣溫) ===
  let bizTemp = '';
  if (hasTemp) {{
    if (avgTavg < 18) {{
      bizTemp = '❄ <strong>低溫時期</strong> (均溫 ' + avgTavg.toFixed(1) + '°C) → 微生物活性慢、有機肥礦化率低、<strong>基肥效期延長 2-3 週</strong>，適合冬季果樹/茶葉<strong>提早施肥</strong>養根。';
    }} else if (avgTavg > 26) {{
      bizTemp = '🔥 <strong>高溫時期</strong> (均溫 ' + avgTavg.toFixed(1) + '°C) → 微生物活躍、有機肥快速礦化、<strong>肥效發揮快也快消耗</strong>，果樹夏梢期需<strong>分次少量追施</strong>，避免一次過量造成氨氣揮發流失。';
    }} else {{
      bizTemp = '🌡 <strong>溫度適中</strong> (均溫 ' + avgTavg.toFixed(1) + '°C) → 微生物穩定發酵，肥效正常發揮，適合<strong>春秋兩季主力銷售期</strong>。';
    }}
    if (maxTmax && maxTmax.tmax >= 36) {{
      bizTemp += '<br>🚨 極端高溫紀錄：' + maxTmax.region + ' ' + maxTmax.year + '/' + maxTmax.month + ' <strong>' + maxTmax.tmax + '°C</strong> → 該時段有機肥氨氣揮發加劇，需<strong>清晨/傍晚施用+覆土</strong>。';
    }}
  }}

  // === 氣候趨勢 (年份維度 → 暖化/變濕) ===
  let bizTrend = '';
  const upTrends = trendLines.filter(t => t.pct > 10).length;
  const dnTrends = trendLines.filter(t => t.pct < -10).length;
  if (trendLines.length >= 3) {{
    if (upTrends > dnTrends * 1.5) {{
      bizTrend = '📈 <strong>近年雨量上升趨勢明顯</strong> — 全球暖化下極端降雨事件增加，長期<strong>需增備耐雨產品線</strong>並向客戶推廣<strong>提前備肥</strong>觀念。';
    }} else if (dnTrends > upTrends * 1.5) {{
      bizTrend = '📉 <strong>近年雨量下降趨勢</strong> — 乾旱化風險升高，客戶可能改用<strong>保水型有機肥+液肥追肥</strong>組合，可規劃相關產品線。';
    }} else {{
      bizTrend = '➖ 近年雨量波動大但無明顯單向趨勢，維持現有備料策略即可。';
    }}
  }}

  // === HTML 組合 ===
  let html = '<h4>📋 自動分析評語（' + nRs + ' 組合 · 雨量/雨日/氣溫/年份 四維交叉）</h4>';

  html += '<div class="adv-kpi-grid">';
  html += '  <div class="adv-kpi"><div class="lbl">💧 平均雨量</div><div class="val">' + avgMm.toFixed(0) + '<span> mm</span></div></div>';
  html += '  <div class="adv-kpi"><div class="lbl">☔ 平均雨日</div><div class="val">' + avgRd.toFixed(1) + '<span> 天</span></div></div>';
  if (hasTemp) html += '  <div class="adv-kpi"><div class="lbl">🌡 平均均溫</div><div class="val">' + avgTavg.toFixed(1) + '<span> °C</span></div></div>';
  html += '  <div class="adv-kpi"><div class="lbl">⛈ 豪雨日總計</div><div class="val">' + totalStorm + '<span> 天</span></div></div>';
  html += '  <div class="adv-kpi hi"><div class="lbl">🔴 最多雨</div><div class="val">' + maxMm.mm.toFixed(0) + '<span> mm</span></div><div class="who">' + maxMm.region + ' ' + maxMm.year + '/' + maxMm.month + '</div></div>';
  html += '  <div class="adv-kpi lo"><div class="lbl">🟢 最少雨</div><div class="val">' + minMm.mm.toFixed(0) + '<span> mm</span></div><div class="who">' + minMm.region + ' ' + minMm.year + '/' + minMm.month + '</div></div>';
  html += '</div>';

  html += '<h4 style="margin-top:14px">💧 累積雨量 → 有機肥出貨影響</h4>';
  html += '<p>' + bizRain + '</p>';
  if (stormCombos > 0) {{
    html += '<p>⛈ 共 <strong>' + stormCombos + '</strong> 個月出現豪雨日 (≥50mm)，該時段<strong>禁施+農路積水</strong>，出貨延誤 3-7 天。</p>';
  }}

  html += '<h4 style="margin-top:14px">☔ 下雨天數 → 田間作業窗口</h4>';
  html += '<p>' + bizRd + '</p>';
  html += '<p style="font-size:12px;color:#666">📌 最多雨日紀錄：' + maxRd.region + ' ' + maxRd.year + '/' + maxRd.month + ' 全月 <strong>' + maxRd.rd + '</strong> 天有雨</p>';

  if (hasTemp) {{
    html += '<h4 style="margin-top:14px">🌡 氣溫 → 有機肥礦化與施用時機</h4>';
    html += '<p>' + bizTemp + '</p>';
  }}

  if (bizTrend) {{
    html += '<h4 style="margin-top:14px">📈 年份趨勢 → 長期業務策略</h4>';
    html += '<p>' + bizTrend + '</p>';
    if (trendLines.length) {{
      html += '<ul style="font-size:12px">';
      trendLines.slice(0, 6).forEach(t => html += '<li>' + t.text + '</li>');
      html += '</ul>';
    }}
  }}

  if (regionDiffLines.length) {{
    html += '<h4 style="margin-top:14px">📍 地區差異 → 分區銷售策略</h4><ul style="font-size:12px">';
    regionDiffLines.slice(0, 5).forEach(l => html += '<li>' + l + '</li>');
    html += '</ul>';
  }}

  if (salesInsight) {{
    html += '<div class="biz" style="background:linear-gradient(90deg,#fff3e0,#fff8e1);border-left-color:#f57c00">💰 <strong>銷售數據交叉驗證</strong> (' + salesCorr.length + ' 筆對應資料)：<br>' + salesInsight + '</div>';
  }}

  html += '<div class="biz">💼 <strong>綜合業務建議</strong>：<br>';
  html += '（1）鎖定 <strong>' + minMm.region + ' 型乾季月份</strong> 為銷售衝刺期<br>';
  html += '（2）避開 <strong>' + maxMm.region + ' 型多雨月份</strong> 或改推速溶粒肥／小包裝<br>';
  html += '（3）跨年比較看氣候變遷趨勢，調整長期產品線 (耐雨/保水/低溫礦化配方)<br>';
  html += '（4）搭配「💰 銷售分析」tab 看實際銷量對照，找出「氣候相關 vs 客戶結構相關」的銷量波動</div>';

  el.innerHTML = html;
  el.style.display = '';
}}

// ============ 📊 歷史雨量比較 (Python 端預打包 · HISTORY 已於 script 頂端定義) ============

// 月份選單預設當月 (HTML 已 hardcode 12 個 option)
(function initHistMonth() {{
  const sel = document.getElementById('histMonth');
  if (!sel) return;
  sel.value = String(new Date().getMonth() + 1);
}})();

function loadHistoryData() {{
  const region = document.getElementById('histRegion').value;
  const month = parseInt(document.getElementById('histMonth').value);
  const nYears = parseInt(document.getElementById('histYears').value);
  const btn = document.getElementById('histRun');
  const status = document.getElementById('histStatus');
  const currentYear = new Date().getFullYear();
  const years = [];
  for (let i = 0; i < nYears; i++) years.push(currentYear - i);
  years.sort();

  btn.disabled = true;
  status.className = 'history-status show';

  try {{
    const regData = (HISTORY.data || {{}})[region] || {{}};
    if (Object.keys(regData).length === 0) {{
      throw new Error('查無此縣市歷史資料 (可能資料源尚未更新)');
    }}

    let results = years.map(year => {{
      const mData = (regData[year] || {{}})[month] || {{mm: 0, rd: 0, sd: 0, missing: true}};
      return {{
        year,
        mm: mData.mm || 0,
        rainDays: mData.rd || 0,
        stormDays: mData.sd || 0,
        src: mData.src || 'unknown',
        missing: !!mData.missing,
      }};
    }});
    results = results.filter(r => !(r.missing && r.mm === 0));
    if (results.length === 0) {{
      throw new Error(region + ' · ' + month + ' 月 · 近 ' + nYears + ' 年皆無資料');
    }}
    btn.disabled = false;

    // 平均
    const avgMm = results.reduce((s, r) => s + r.mm, 0) / results.length;
    const avgDays = results.reduce((s, r) => s + r.rainDays, 0) / results.length;

    // 表格
    const tbody = document.getElementById('histTbody');
    tbody.innerHTML = '';
    results.forEach(r => {{
      const diff = r.mm - avgMm;
      const diffPct = avgMm > 0 ? (diff / avgMm * 100) : 0;
      const upDown = diff >= 0 ? 'up' : 'down';
      const arrow = diff >= 0 ? '▲' : '▼';
      const tr = document.createElement('tr');
      if (r.year === currentYear) tr.className = 'current-row';
      const srcTag = r.src === 'cwa'
        ? '<span style="background:#c62828;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:900">CWA 官方</span>'
        : (r.src === 'forecast'
          ? '<span style="background:#1976d2;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px;font-weight:900" title="Open-Meteo Forecast API (即時)">即時 F/C</span>'
          : (r.src === 'openmeteo-fallback' || r.src === 'openmeteo'
            ? '<span style="background:#757575;color:#fff;padding:2px 6px;border-radius:3px;font-size:10px" title="CWA 該年無觀測 · fallback Open-Meteo">O-M 補</span>'
            : '<span style="color:#999;font-size:10px">–</span>'));
      tr.innerHTML =
        '<td class="yr">' + r.year + '</td>' +
        '<td class="mm">' + r.mm.toFixed(1) + ' mm</td>' +
        '<td>' + r.rainDays + ' 天</td>' +
        '<td>' + r.stormDays + ' 天</td>' +
        '<td class="diff ' + upDown + '">' + arrow + Math.abs(diff).toFixed(1) + ' mm</td>' +
        '<td class="diff ' + upDown + '">' + arrow + Math.abs(diffPct).toFixed(1) + '%</td>' +
        '<td>' + srcTag + '</td>';
      tbody.appendChild(tr);
    }});
    // 均值列
    const avgTr = document.createElement('tr');
    avgTr.className = 'avg-row';
    avgTr.innerHTML =
      '<td class="yr">近 ' + nYears + ' 年均</td>' +
      '<td class="mm">' + avgMm.toFixed(1) + ' mm</td>' +
      '<td>' + avgDays.toFixed(1) + ' 天</td>' +
      '<td>—</td><td>—</td><td>—</td><td>—</td>';
    tbody.appendChild(avgTr);
    document.getElementById('histTableWrap').style.display = '';

    // SVG 長條圖
    renderHistChart(results, avgMm, region, month);

    // 業務報告文字
    renderHistReport(results, avgMm, avgDays, region, month, currentYear);

    const src = HISTORY.source || '中央氣象署 CODIS';
    const upd = HISTORY.updated || '';
    const srcUrl = HISTORY.source_url || 'https://codis.cwa.gov.tw/StationData';
    const stns = ((HISTORY.stations || {{}})[region] || []).map(s => s.name + '(' + s.id + ')').join('、');
    status.innerHTML = '✅ <strong>' + region + '</strong> · ' + month + ' 月 · 共 ' + results.length + ' 年資料' +
      '<br>📍 <strong>資料源</strong>：<a href="' + srcUrl + '" target="_blank" style="color:#c62828;font-weight:900">' + src + '</a>' + (upd ? '（' + upd + ' 更新）' : '') +
      (stns ? '<br>🏛️ <strong>觀測站</strong>：' + stns + '（多站取 MAX 代表該縣市峰值降雨）' : '');
  }} catch (e) {{
    console.error(e);
    btn.disabled = false;
    status.innerHTML = '❌ 查詢失敗：' + e.message;
  }}
}}

function renderHistChart(results, avgMm, region, month) {{
  const W = 640, H = 260, pl = 46, pr = 20, pt = 30, pb = 40;
  const cw = W - pl - pr, ch = H - pt - pb;
  const maxMm = Math.max(...results.map(r => r.mm), avgMm, 50);
  const bw = cw / results.length - 12;
  let svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + H + '">';
  // 標題
  svg += '<text x="' + (W/2) + '" y="18" text-anchor="middle" font-size="13" font-weight="700" fill="#7b1fa2">' + region + ' · ' + month + '月 歷年累積雨量對照</text>';
  // Y 軸格線
  for (let i = 0; i <= 4; i++) {{
    const y = pt + ch * i / 4;
    const val = Math.round(maxMm * (4 - i) / 4);
    svg += '<line x1="' + pl + '" y1="' + y + '" x2="' + (W - pr) + '" y2="' + y + '" stroke="#e6e8eb" stroke-width="1"/>';
    svg += '<text x="' + (pl - 4) + '" y="' + (y + 4) + '" text-anchor="end" font-size="10" fill="#888">' + val + '</text>';
  }}
  // 均值虛線
  const avgY = pt + ch - (avgMm / maxMm) * ch;
  svg += '<line x1="' + pl + '" y1="' + avgY + '" x2="' + (W - pr) + '" y2="' + avgY + '" stroke="#ff9800" stroke-width="1.5" stroke-dasharray="6,4"/>';
  svg += '<text x="' + (W - pr - 4) + '" y="' + (avgY - 4) + '" text-anchor="end" font-size="10" fill="#ff9800" font-weight="700">均值 ' + avgMm.toFixed(1) + ' mm</text>';
  // Bars
  const curYear = new Date().getFullYear();
  results.forEach((r, i) => {{
    const bx = pl + i * (cw / results.length) + 6;
    const bh = (r.mm / maxMm) * ch;
    const by = pt + ch - bh;
    const isCur = r.year === curYear;
    const color = isCur ? '#7b1fa2' : (r.mm > avgMm ? '#c62828' : '#1976d2');
    svg += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="' + color + '" rx="3"/>';
    svg += '<text x="' + (bx + bw/2) + '" y="' + (by - 4) + '" text-anchor="middle" font-size="11" font-weight="700" fill="' + color + '">' + r.mm.toFixed(0) + '</text>';
    svg += '<text x="' + (bx + bw/2) + '" y="' + (H - pb + 16) + '" text-anchor="middle" font-size="11" fill="#333" font-weight="' + (isCur ? '900' : '600') + '">' + r.year + (isCur ? ' ★' : '') + '</text>';
    svg += '<text x="' + (bx + bw/2) + '" y="' + (H - pb + 30) + '" text-anchor="middle" font-size="10" fill="#666">' + r.rainDays + '天有雨</text>';
  }});
  svg += '</svg>';
  document.getElementById('histChart').innerHTML = svg;
}}

function renderHistReport(results, avgMm, avgDays, region, month, curYear) {{
  const cur = results.find(r => r.year === curYear);
  const maxYr = results.reduce((a, b) => b.mm > a.mm ? b : a);
  const minYr = results.reduce((a, b) => b.mm < a.mm ? b : a);
  const diff = cur ? (cur.mm - avgMm) : 0;
  const diffPct = avgMm > 0 && cur ? (diff / avgMm * 100) : 0;

  // 業務影響推估
  let biz = '';
  if (cur) {{
    let bizLine;
    if (cur.mm < 150 && avgMm >= 150) {{
      bizLine = '☀ 本年偏乾 → 客戶田面可作業，<strong>預估銷量比往年同期 +10~20%</strong>，建議積極洽談出貨。';
    }} else if (cur.mm < 300) {{
      bizLine = '⛅ 雨量在正常範圍 → 出貨排程可依平常規劃，<strong>銷量預期持平</strong>。';
    }} else if (cur.mm < 500) {{
      bizLine = '🌧 雨量偏多 → 出貨排程要看空檔，<strong>銷量預期下滑 10~20%</strong>，備貨可縮量。';
    }} else {{
      bizLine = '⛈ 雨量顯著偏多 → 農路積水、田面禁施，<strong>銷量預期下滑 20~40%</strong>，加強年底補撒計劃。';
    }}
    biz = '<div class="biz">💼 <strong>' + curYear + ' 年 ' + month + ' 月業務判讀：</strong><br>' + bizLine + '</div>';
  }}

  const html =
    '<span class="label">📋 分析摘要 (' + region + ' · ' + month + ' 月)</span>' +
    '本地區近 ' + results.length + ' 年 ' + month + ' 月平均降雨 <strong>' + avgMm.toFixed(1) + ' mm</strong>，' +
    '平均 <strong>' + avgDays.toFixed(1) + '</strong> 天有雨。' +
    '最多為 <strong>' + maxYr.year + ' 年 ' + maxYr.mm.toFixed(0) + ' mm</strong>，' +
    '最少為 <strong>' + minYr.year + ' 年 ' + minYr.mm.toFixed(0) + ' mm</strong>。' +
    (cur ?
      '本年 (' + curYear + ') 累積 <strong>' + cur.mm.toFixed(1) + ' mm</strong>，' +
      (diff >= 0 ? '比均值高 ' : '比均值低 ') + '<strong>' + Math.abs(diff).toFixed(1) + ' mm (' + Math.abs(diffPct).toFixed(1) + '%)</strong>。'
      : ''
    ) +
    biz;
  const rep = document.getElementById('histReport');
  rep.innerHTML = html;
  rep.style.display = '';
}}

// ============ 🗺️ 鄉鎮特色農產地圖 ============
const TOWNS = {towns_json};
// 作物→類別 對應 (依關鍵字判斷 pin 色)
const CROP_CAT_KEYWORDS = {{
  fruit: ['芒果','荔枝','龍眼','鳳梨','香蕉','木瓜','蓮霧','番石榴','酪梨','火龍果','紅龍果','釋迦','柑橘','椪柑','桶柑','柚','檸檬','金桔','橘子','水梨','梨','桃','李','蘋果','葡萄','棗','蜜棗','柿','草莓','藍莓','無花果','楊桃','枇杷','百香果','洛神','梅子','可可','橘'],
  veg: ['高麗菜','白菜','青江菜','菠菜','萵苣','地瓜葉','空心菜','小白菜','A菜','油菜','芥藍','韭菜','莧菜','山蘇','皇宮菜','西瓜','洋香瓜','美濃瓜','番茄','辣椒','彩椒','茄子','絲瓜','苦瓜','小黃瓜','南瓜','冬瓜','櫛瓜','秋葵','四季豆','毛豆','玉米','洋蔥','蒜','蔥','馬鈴薯','蘿蔔','紅蘿蔔','地瓜','薑','山藥','芋','蓮藕','菱角','竹筍','筍','蓮','蘆筍','牛蒡','蔬菜','蘿蔔','蓮花','野蓮'],
  tea: ['茶','烏龍','包種','鐵觀音','金萱','紅茶','東方美人'],
  flower: ['蘭','菊','玫瑰','百合','劍蘭','花','金針','洛神'],
  grain: ['水稻','花生','紅豆','綠豆','大豆','咖啡','檳榔','香菇','段木','木耳','蕎麥','醬油','石花','石斑','文蛤','烏魚','蜂蜜','豬腳','羊肉','瓊麻'],
}};

function _townCat(crops) {{
  // 依主力作物列表判斷類別（第一個 match 為主）
  const joined = crops.join(' ');
  for (const cat of ['fruit', 'tea', 'flower', 'grain', 'veg']) {{
    if (CROP_CAT_KEYWORDS[cat].some(k => joined.includes(k))) return cat;
  }}
  return 'grain';
}}

// Leaflet 地圖
const townsMap = L.map('townsMap', {{zoomControl: true, attributionControl: false, minZoom: 6, maxZoom: 15, maxBounds: L.latLngBounds([[20.5, 118.0], [26.5, 123.5]]), maxBoundsViscosity: 1.0}}).setView([23.7, 121.0], 7);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 15, opacity: 0.7,
}}).addTo(townsMap);
L.control.attribution({{position: 'bottomright'}}).addAttribution('© OSM').addTo(townsMap);
let townMarkerGroup = L.layerGroup().addTo(townsMap);

function renderTownsMap() {{
  const catFilter = document.getElementById('townFltCat').value;
  const kw = document.getElementById('townKw').value.trim();
  townMarkerGroup.clearLayers();
  let cnt = 0;
  TOWNS.forEach(t => {{
    const cat = _townCat(t.crops);
    if (catFilter && cat !== catFilter) return;
    if (kw && !t.town.includes(kw) && !t.county.includes(kw) &&
        !t.crops.some(c => c.includes(kw)) && !(t.note || '').includes(kw)) return;
    cnt++;
    const emoji = {{fruit:'🍎', veg:'🥬', tea:'🍵', flower:'🌸', grain:'🌾'}}[cat];
    const icon = L.divIcon({{
      className: '',
      html: '<div class="town-marker ' + cat + '" style="width:28px;height:28px">' + emoji + '</div>',
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    }});
    const marker = L.marker([t.lat, t.lon], {{icon}}).addTo(townMarkerGroup);
    const cropsHtml = t.crops.map(c => '<span class="crop-tag">' + c + '</span>').join('');
    marker.bindPopup(
      '<div class="town-popup">' +
      '<div class="head">📍 ' + t.county + ' ' + t.town + '</div>' +
      '<div class="crops">' + cropsHtml + '</div>' +
      (t.note ? '<div class="note">💡 ' + t.note + '</div>' : '') +
      '</div>'
    );
  }});
  document.getElementById('townsCount').textContent = '共 ' + cnt + ' 個特色農產鄉鎮';
}}

// ============ 💰 銷售分析 ============
const SALES_LS_KEY = 'salesMonthlyV1';
function _loadSalesFromLS() {{
  try {{
    const s = localStorage.getItem(SALES_LS_KEY);
    if (!s) return null;
    return JSON.parse(s);
  }} catch (e) {{ return null; }}
}}
function _saveSalesToLS(monthly) {{
  try {{ localStorage.setItem(SALES_LS_KEY, JSON.stringify(monthly)); return true; }}
  catch (e) {{ return false; }}
}}
// 頁面載入時: 用 LS 覆蓋 SALES.monthly
(function mergeSalesLS() {{
  const ls = _loadSalesFromLS();
  if (ls && window.SALES) {{
    window.SALES.monthly = {{...window.SALES.monthly, ...ls}};
  }}
}})();

(function initSalesBlock() {{
  const S = window.SALES || {{}};
  const monthly = S.monthly || {{}};
  const years = Object.keys(monthly).sort();
  if (!years.length) return;

  // KPI
  years.forEach(y => {{
    const vals = monthly[y].filter(v => v != null);
    const sum = vals.reduce((a,b) => a+b, 0);
    const el = document.getElementById('k' + y);
    if (el) el.textContent = sum.toLocaleString();
  }});

  // 表格
  const tbody = document.getElementById('salesTbody');
  const allVals = years.flatMap(y => monthly[y].filter(v => v != null));
  const maxVal = Math.max(...allVals);
  years.forEach(y => {{
    const arr = monthly[y];
    const total = arr.filter(v => v != null).reduce((a,b) => a+b, 0);
    const tr = document.createElement('tr');
    let html = '<td>' + y + '</td>';
    arr.forEach(v => {{
      if (v == null) {{
        html += '<td class="empty">–</td>';
      }} else {{
        const ratio = v / maxVal;
        let cls = 'low';
        if (ratio > 0.6) cls = 'hi';
        else if (ratio > 0.3) cls = 'mid';
        html += '<td class="' + cls + '">' + v.toLocaleString() + '</td>';
      }}
    }});
    html += '<td class="total">' + total.toLocaleString() + '</td>';
    tr.innerHTML = html;
    tbody.appendChild(tr);
  }});

  // 初始 chart
  renderSalesChart();

  document.getElementById('salesRegion').addEventListener('change', renderSalesChart);
  document.getElementById('salesMode').addEventListener('change', renderSalesChart);
  // 初始評語
  renderSalesAnalysis();
}})();

function renderSalesChart() {{
  const S = window.SALES;
  const H = window.HISTORY || {{}};
  const mode = document.getElementById('salesMode').value;
  const region = document.getElementById('salesRegion').value;
  const monthly = S.monthly;
  const years = Object.keys(monthly).sort();

  const W = 900, HGT = 380, pl = 60, pr = 60, pt = 30, pb = 60;
  const cw = W - pl - pr, ch = HGT - pt - pb;

  const YEAR_COLORS = {{'2022':'#1976d2','2023':'#c62828','2024':'#2e7d32','2025':'#7b1fa2','2026':'#f57c00'}};

  // 銷售最大值
  const allSales = years.flatMap(y => monthly[y].filter(v => v != null));
  const maxSales = Math.max(...allSales);

  // 抓對應地區歷年雨量 (12 個月 avg 或 該年月)
  const rainByYearMonth = {{}};
  if (mode === 'both' || mode === 'scatter') {{
    const regData = (H.data || {{}})[region] || {{}};
    years.forEach(y => {{
      const yData = regData[y] || {{}};
      rainByYearMonth[y] = [];
      for (let m = 1; m <= 12; m++) {{
        const md = yData[String(m)];
        rainByYearMonth[y].push(md ? md.mm : null);
      }}
    }});
  }}
  const allRain = Object.values(rainByYearMonth).flat().filter(v => v != null);
  const maxRain = allRain.length ? Math.max(...allRain) : 1000;

  let svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + HGT + '" preserveAspectRatio="xMidYMid meet">';

  if (mode === 'scatter') {{
    // 散點圖: X=雨量, Y=銷量
    svg += '<text x="' + (W/2) + '" y="20" text-anchor="middle" font-size="14" font-weight="900" fill="#333">' + region + ' 月雨量 (mm) vs 全國銷售 (噸) — 散點分析</text>';
    // 軸
    svg += '<line x1="' + pl + '" y1="' + (pt+ch) + '" x2="' + (W-pr) + '" y2="' + (pt+ch) + '" stroke="#666" stroke-width="1"/>';
    svg += '<line x1="' + pl + '" y1="' + pt + '" x2="' + pl + '" y2="' + (pt+ch) + '" stroke="#666" stroke-width="1"/>';
    // Y ticks
    for (let i = 0; i <= 4; i++) {{
      const y = pt + ch - ch * i / 4;
      const v = Math.round(maxSales * i / 4);
      svg += '<text x="' + (pl-8) + '" y="' + (y+4) + '" text-anchor="end" font-size="10" fill="#666">' + v + '</text>';
      svg += '<line x1="' + pl + '" y1="' + y + '" x2="' + (W-pr) + '" y2="' + y + '" stroke="#eee" stroke-width="1"/>';
    }}
    // X ticks
    for (let i = 0; i <= 5; i++) {{
      const x = pl + cw * i / 5;
      const v = Math.round(maxRain * i / 5);
      svg += '<text x="' + x + '" y="' + (pt+ch+16) + '" text-anchor="middle" font-size="10" fill="#666">' + v + '</text>';
    }}
    svg += '<text x="' + (W/2) + '" y="' + (HGT-8) + '" text-anchor="middle" font-size="12" font-weight="700" fill="#333">' + region + ' 月降雨量 (mm)</text>';
    svg += '<text x="14" y="' + (HGT/2) + '" text-anchor="middle" font-size="12" font-weight="700" fill="#333" transform="rotate(-90 14 ' + (HGT/2) + ')">全國銷售 (噸)</text>';
    // 點
    years.forEach(y => {{
      const color = YEAR_COLORS[y] || '#666';
      for (let m = 0; m < 12; m++) {{
        const rain = (rainByYearMonth[y] || [])[m];
        const sales = monthly[y][m];
        if (rain == null || sales == null) continue;
        const cx = pl + (rain / maxRain) * cw;
        const cy = pt + ch - (sales / maxSales) * ch;
        svg += '<circle cx="' + cx + '" cy="' + cy + '" r="5" fill="' + color + '" opacity="0.7" stroke="#fff" stroke-width="1"><title>' + y + '-' + (m+1) + '月: 雨' + rain.toFixed(0) + 'mm/銷' + sales + '噸</title></circle>';
      }}
    }});
    // Legend
    let lx = pl + 20, ly = pt + 15;
    years.forEach(y => {{
      svg += '<circle cx="' + lx + '" cy="' + ly + '" r="5" fill="' + (YEAR_COLORS[y] || '#666') + '"/>';
      svg += '<text x="' + (lx+9) + '" y="' + (ly+4) + '" font-size="11" fill="#333" font-weight="700">' + y + '</text>';
      lx += 55;
    }});
  }} else {{
    // 折線圖: X=1-12月, Y左=銷售, Y右=雨量(if both)
    svg += '<text x="' + (W/2) + '" y="20" text-anchor="middle" font-size="14" font-weight="900" fill="#333">📊 有機肥料部 逐月銷售趨勢' + (mode === 'both' ? ' + ' + region + ' 月雨量對照' : '') + '</text>';
    // X 軸
    svg += '<line x1="' + pl + '" y1="' + (pt+ch) + '" x2="' + (W-pr) + '" y2="' + (pt+ch) + '" stroke="#666" stroke-width="1"/>';
    // Y 左軸 (銷售)
    svg += '<line x1="' + pl + '" y1="' + pt + '" x2="' + pl + '" y2="' + (pt+ch) + '" stroke="#c62828" stroke-width="1"/>';
    for (let i = 0; i <= 4; i++) {{
      const y = pt + ch - ch * i / 4;
      const v = Math.round(maxSales * i / 4);
      svg += '<text x="' + (pl-8) + '" y="' + (y+4) + '" text-anchor="end" font-size="10" fill="#c62828" font-weight="700">' + v.toLocaleString() + '</text>';
      svg += '<line x1="' + pl + '" y1="' + y + '" x2="' + (W-pr) + '" y2="' + y + '" stroke="#f0f0f0" stroke-width="1"/>';
    }}
    svg += '<text x="14" y="' + (pt+ch/2) + '" text-anchor="middle" font-size="12" font-weight="700" fill="#c62828" transform="rotate(-90 14 ' + (pt+ch/2) + ')">銷售 (噸)</text>';

    if (mode === 'both') {{
      // Y 右軸 (雨量)
      svg += '<line x1="' + (W-pr) + '" y1="' + pt + '" x2="' + (W-pr) + '" y2="' + (pt+ch) + '" stroke="#1976d2" stroke-width="1"/>';
      for (let i = 0; i <= 4; i++) {{
        const y = pt + ch - ch * i / 4;
        const v = Math.round(maxRain * i / 4);
        svg += '<text x="' + (W-pr+8) + '" y="' + (y+4) + '" text-anchor="start" font-size="10" fill="#1976d2" font-weight="700">' + v + '</text>';
      }}
      svg += '<text x="' + (W-14) + '" y="' + (pt+ch/2) + '" text-anchor="middle" font-size="12" font-weight="700" fill="#1976d2" transform="rotate(90 ' + (W-14) + ' ' + (pt+ch/2) + ')">雨量 (mm)</text>';
    }}

    // 月份 X 標籤
    for (let m = 0; m < 12; m++) {{
      const x = pl + (cw / 11) * m;
      svg += '<text x="' + x + '" y="' + (pt+ch+16) + '" text-anchor="middle" font-size="11" fill="#333" font-weight="700">' + (m+1) + '月</text>';
    }}

    // 雨量 (先畫底層,若 both 模式) — 淡色 area
    if (mode === 'both') {{
      years.forEach(y => {{
        const color = YEAR_COLORS[y] || '#999';
        const pts = [];
        for (let m = 0; m < 12; m++) {{
          const r = (rainByYearMonth[y] || [])[m];
          if (r == null) continue;
          const x = pl + (cw / 11) * m;
          const yv = pt + ch - (r / maxRain) * ch;
          pts.push(x + ',' + yv);
        }}
        if (pts.length >= 2) {{
          svg += '<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + color + '" stroke-width="1.2" stroke-dasharray="4,3" opacity="0.4"/>';
        }}
      }});
    }}

    // 銷售折線 (主線)
    years.forEach(y => {{
      const color = YEAR_COLORS[y] || '#999';
      const arr = monthly[y];
      const pts = [];
      for (let m = 0; m < 12; m++) {{
        const v = arr[m];
        if (v == null) continue;
        const x = pl + (cw / 11) * m;
        const yv = pt + ch - (v / maxSales) * ch;
        pts.push({{x, yv, m, v}});
      }}
      if (pts.length >= 2) {{
        const pline = pts.map(p => p.x + ',' + p.yv).join(' ');
        svg += '<polyline points="' + pline + '" fill="none" stroke="' + color + '" stroke-width="2.5"/>';
      }}
      pts.forEach(p => {{
        svg += '<circle cx="' + p.x + '" cy="' + p.yv + '" r="3.5" fill="' + color + '"><title>' + y + '-' + (p.m+1) + '月: ' + p.v + '噸</title></circle>';
      }});
    }});

    // Legend
    let lx = pl + 20, ly = pt + 10;
    years.forEach(y => {{
      const color = YEAR_COLORS[y] || '#999';
      svg += '<line x1="' + lx + '" y1="' + ly + '" x2="' + (lx+18) + '" y2="' + ly + '" stroke="' + color + '" stroke-width="3"/>';
      svg += '<circle cx="' + (lx+9) + '" cy="' + ly + '" r="3" fill="' + color + '"/>';
      svg += '<text x="' + (lx+22) + '" y="' + (ly+4) + '" font-size="11" fill="#333" font-weight="700">' + y + '</text>';
      lx += 60;
    }});
    if (mode === 'both') {{
      svg += '<text x="' + (pl+20) + '" y="' + (ly+18) + '" font-size="10" fill="#666">實線=銷售(左軸)  虛線=雨量(右軸)</text>';
    }}
  }}

  svg += '</svg>';
  document.getElementById('salesChart').innerHTML = svg;
}}

function renderSalesAnalysis() {{
  const S = window.SALES;
  const monthly = S.monthly;
  const years = Object.keys(monthly).sort();
  if (years.length < 2) return;
  const target = document.getElementById('salesAnalysis');

  // === 統計核心指標 ===
  const totals = {{}};
  const monthCounts = {{}};
  years.forEach(y => {{
    const vals = monthly[y].filter(v => v != null);
    totals[y] = vals.reduce((a,b) => a+b, 0);
    monthCounts[y] = vals.length;
  }});
  const y1 = years[0], yLast = years[years.length-1], yPrev = years[years.length-2];

  // CAGR (複合年成長率)
  const yearsSpan = parseInt(yLast) - parseInt(y1);
  const cagr = yearsSpan > 0 && totals[y1] > 0
    ? (Math.pow(totals[yLast]/totals[y1], 1/yearsSpan) - 1) * 100 : 0;

  // 找最強/最弱月 (跨年綜合)
  let maxMonth = {{ y: '?', m: 0, v: 0 }};
  let minMonth = {{ y: '?', m: 0, v: Infinity }};
  years.forEach(y => monthly[y].forEach((v, i) => {{
    if (v == null) return;
    if (v > maxMonth.v) maxMonth = {{y, m: i+1, v}};
    if (v < minMonth.v && v > 0) minMonth = {{y, m: i+1, v}};
  }}));

  // 季節指數 (跨年每月平均, 用來看淡旺季)
  const monthAvgs = new Array(12).fill(0).map(() => ({{sum: 0, n: 0}}));
  years.forEach(y => monthly[y].forEach((v, i) => {{
    if (v != null) {{ monthAvgs[i].sum += v; monthAvgs[i].n++; }}
  }}));
  const seasonAvg = monthAvgs.map(m => m.n > 0 ? m.sum / m.n : 0);
  const annualAvg = seasonAvg.reduce((a,b)=>a+b,0) / 12;
  const seasonIdx = seasonAvg.map(v => annualAvg > 0 ? (v / annualAvg * 100) : 100);
  const peakMonths = seasonIdx.map((v,i) => [i+1, v]).sort((a,b) => b[1]-a[1]).slice(0, 3);
  const weakMonths = seasonIdx.map((v,i) => [i+1, v]).sort((a,b) => a[1]-b[1]).slice(0, 3);

  // 2026 全年預估 (依過去 7 月推算)
  const y2026 = monthly['2026'];
  const y2025b = monthly['2025'];
  let est2026 = 0;
  let yoyEst = 0;
  if (y2026 && y2025b) {{
    const s26 = y2026.slice(0,7).reduce((a,b) => a+(b||0), 0);
    const s25 = y2025b.slice(0,7).reduce((a,b) => a+(b||0), 0);
    yoyEst = s25 > 0 ? ((s26 - s25) / s25 * 100) : 0;
    est2026 = totals['2025'] * (1 + yoyEst/100);
  }}

  // === HTML render Power BI 樣式 ===
  let h = '';

  // Executive Summary
  h += '<div class="sales-exec">';
  h += '<div class="es-title">💼 銷售執行摘要 (Executive Summary · KPI)</div>';
  h += '<div class="es-grid">';
  h += '  <div class="es-item"><div class="lbl">' + yLast + ' YTD 銷量</div><div class="val">' + totals[yLast].toLocaleString() + '<span> 噸</span></div><div class="unit">(' + monthCounts[yLast] + ' 個月)</div></div>';
  if (yoyEst !== 0) {{
    const cls = yoyEst > 0 ? 'up' : 'dn';
    h += '  <div class="es-item ' + cls + '"><div class="lbl">2026 vs 2025 同期</div><div class="val">' + (yoyEst>0?'+':'') + yoyEst.toFixed(1) + '<span>%</span></div><div class="unit">1-7 月 YoY</div></div>';
  }}
  if (cagr > 0) {{
    h += '  <div class="es-item up"><div class="lbl">' + y1 + '→' + yLast + ' CAGR</div><div class="val">+' + cagr.toFixed(1) + '<span>%</span></div><div class="unit">年複合成長率</div></div>';
  }}
  if (est2026 > 0) {{
    h += '  <div class="es-item hi"><div class="lbl">🎯 2026 全年推估</div><div class="val">' + Math.round(est2026).toLocaleString() + '<span> 噸</span></div><div class="unit">按 YoY 外推</div></div>';
  }}
  h += '  <div class="es-item"><div class="lbl">🔥 歷史單月峰值</div><div class="val">' + maxMonth.v.toLocaleString() + '<span> 噸</span></div><div class="unit">' + maxMonth.y + '/' + maxMonth.m + ' 月</div></div>';
  h += '  <div class="es-item"><div class="lbl">📉 歷史單月低谷</div><div class="val">' + minMonth.v.toLocaleString() + '<span> 噸</span></div><div class="unit">' + minMonth.y + '/' + minMonth.m + ' 月</div></div>';
  h += '</div></div>';

  // === Dashboard 卡片區 ===
  h += '<div class="sales-dashboard">';

  // Card 1: 年成長 bar
  const maxYT = Math.max(...Object.values(totals));
  let ybar = '<svg viewBox="0 0 320 200" xmlns="http://www.w3.org/2000/svg">';
  years.forEach((y, i) => {{
    const t = totals[y];
    const bh = (t / maxYT) * 130;
    const bx = 30 + i * (250 / years.length);
    const bw = (250 / years.length) - 8;
    const by = 160 - bh;
    const isCur = y === yLast;
    const color = isCur ? '#c62828' : '#1976d2';
    ybar += '<rect x="' + bx + '" y="' + by + '" width="' + bw + '" height="' + bh + '" fill="' + color + '" rx="3"/>';
    ybar += '<text x="' + (bx + bw/2) + '" y="' + (by - 4) + '" text-anchor="middle" font-size="11" font-weight="900" fill="' + color + '">' + t.toLocaleString() + '</text>';
    ybar += '<text x="' + (bx + bw/2) + '" y="180" text-anchor="middle" font-size="12" font-weight="700" fill="#333">' + y + (isCur ? '★' : '') + '</text>';
    ybar += '<text x="' + (bx + bw/2) + '" y="194" text-anchor="middle" font-size="9" fill="#666">' + monthCounts[y] + '月</text>';
  }});
  ybar += '</svg>';
  h += '<div class="db-card"><div class="db-head">📈 年度銷量成長 (' + y1 + '-' + yLast + ')</div><div class="db-body">' + ybar;
  h += '<div class="db-insight">CAGR = <strong>+' + cagr.toFixed(1) + '%</strong>/年 → 屬<strong>高速成長業務</strong>,遠超台灣有機肥產業平均 (估 3-8%/年)。</div></div></div>';

  // Card 2: 季節性熱力
  let seas = '<svg viewBox="0 0 340 90" xmlns="http://www.w3.org/2000/svg">';
  seasonIdx.forEach((idx, i) => {{
    const w = 340/12 - 2;
    const x = i * (340/12) + 1;
    let color = '#e0e0e0';
    if (idx > 130) color = '#c62828';
    else if (idx > 110) color = '#f57c00';
    else if (idx > 90) color = '#fbc02d';
    else if (idx > 70) color = '#9ccc65';
    else color = '#1976d2';
    seas += '<rect x="' + x + '" y="15" width="' + w + '" height="50" fill="' + color + '" rx="2"/>';
    seas += '<text x="' + (x + w/2) + '" y="42" text-anchor="middle" font-size="10" font-weight="900" fill="#fff">' + Math.round(idx) + '</text>';
    seas += '<text x="' + (x + w/2) + '" y="80" text-anchor="middle" font-size="10" fill="#333" font-weight="600">' + (i+1) + '月</text>';
  }});
  seas += '<text x="170" y="10" text-anchor="middle" font-size="9" fill="#666">季節指數 (跨年月均 vs 全年均, 100=平均)</text>';
  seas += '</svg>';
  h += '<div class="db-card"><div class="db-head">🌊 季節性熱力圖</div><div class="db-body">' + seas;
  h += '<div class="db-insight">旺季 Top 3: <strong>' + peakMonths.map(m => m[0] + '月(' + Math.round(m[1]) + ')').join(' · ') + '</strong> · 淡季: <strong>' + weakMonths.map(m => m[0] + '月').join('/') + '</strong>。備料/促銷時程可對齊。</div></div></div>';

  // Card 3: 銷售 vs 雨量對照 (依用戶選定 region)
  const region = document.getElementById('salesRegion') ? document.getElementById('salesRegion').value : '臺南市';
  const H = window.HISTORY;
  const corr = [];
  if (H && H.data && H.data[region]) {{
    years.forEach(y => {{
      monthly[y].forEach((v, i) => {{
        if (v == null) return;
        const rd = (H.data[region][y] || {{}})[String(i+1)];
        if (rd && rd.mm != null) corr.push({{y, m: i+1, sales: v, rain: rd.mm}});
      }});
    }});
  }}
  if (corr.length >= 4) {{
    // 相關係數
    const n = corr.length;
    const sx = corr.reduce((s,r)=>s+r.rain,0), sy = corr.reduce((s,r)=>s+r.sales,0);
    const sxy = corr.reduce((s,r)=>s+r.rain*r.sales,0);
    const sxx = corr.reduce((s,r)=>s+r.rain*r.rain,0), syy = corr.reduce((s,r)=>s+r.sales*r.sales,0);
    const r = (n*sxy - sx*sy) / (Math.sqrt(n*sxx - sx*sx) * Math.sqrt(n*syy - sy*sy) || 1);
    const rColor = Math.abs(r) > 0.5 ? '#c62828' : (Math.abs(r) > 0.3 ? '#f57c00' : '#666');
    let interp = '';
    if (r < -0.5) interp = '強負相關 → <strong>雨量高時銷售明顯下滑</strong>,建議提前配送';
    else if (r < -0.3) interp = '中度負相關 → 雨量會影響銷售,可監控';
    else if (r > 0.3) interp = '正相關 → <strong>反常</strong>,可能是雨後補基肥或颱風前搶備肥';
    else interp = '低相關 → 銷售受其他因素 (季節/客戶/促銷) 影響較大';

    h += '<div class="db-card"><div class="db-head">🌧 雨量 × 銷售相關性 (' + region + ')</div><div class="db-body">';
    h += '<div style="text-align:center;padding:14px 8px">';
    h += '<div style="font-size:36px;font-weight:900;color:' + rColor + ';font-family:ui-monospace,Menlo,monospace">r = ' + r.toFixed(3) + '</div>';
    h += '<div style="font-size:11px;color:#666;margin-top:4px">Pearson 相關係數 · n = ' + n + '</div>';
    h += '</div>';
    h += '<div class="db-insight">' + interp + '。<br>切「散點圖」模式看實際分布。</div></div></div>';
  }}

  h += '</div>';  // /sales-dashboard

  // SWOT 卡
  h += '<div class="sales-swot">';
  h += '<div class="swot-title">🎯 銷售定位 SWOT 分析</div><div class="swot-grid">';
  h += '<div class="swot-cell strength"><div class="h">💪 Strength 優勢</div><ul>';
  h += '<li>' + y1 + '→' + yLast + ' 年 CAGR <strong>+' + cagr.toFixed(0) + '%</strong> · 高速成長</li>';
  h += '<li>單月峰值 <strong>' + maxMonth.v.toLocaleString() + '</strong> 噸 (' + maxMonth.y + '/' + maxMonth.m + ') · 產能已達千噸級</li>';
  h += '<li>母公司大成集團 (1210) · 品牌背書強</li></ul></div>';
  h += '<div class="swot-cell weakness"><div class="h">⚠️ Weakness 劣勢</div><ul>';
  h += '<li>淡旺季差距大 (旺季指數 ' + Math.round(peakMonths[0][1]) + ' vs 淡季 ' + Math.round(weakMonths[0][1]) + ')</li>';
  h += '<li>' + minMonth.y + '/' + minMonth.m + ' 月僅 ' + minMonth.v + ' 噸 · 淡季產能空置</li>';
  h += '<li>全國市佔約 1.8% · 距 Top 10 廠商仍有距離</li></ul></div>';
  h += '<div class="swot-cell opportunity"><div class="h">🚀 Opportunity 機會</div><ul>';
  h += '<li>依 CAGR 推估 2028 可達 <strong>' + Math.round(totals[yLast] * Math.pow(1+cagr/100, 3)).toLocaleString() + ' 噸</strong></li>';
  h += '<li>淡季 (' + weakMonths[0][0] + '/' + weakMonths[1][0] + '月) 促銷方案可平滑產能</li>';
  h += '<li>雨量對銷售有負影響 → 可推「速溶粒肥」耐雨規格增加雨季銷量</li></ul></div>';
  h += '<div class="swot-cell threat"><div class="h">🌪 Threat 威脅</div><ul>';
  h += '<li>2026 前 7 月 YoY ' + (yoyEst>0?'+':'') + yoyEst.toFixed(1) + '% → 成長趨緩需觀察 (2025 有基期效應)</li>';
  h += '<li>禽畜糞細分市場競爭 46 家搶 244 產品</li>';
  h += '<li>環保法規對禽畜糞來源趨嚴 (氨氣/重金屬)</li></ul></div>';
  h += '</div></div>';

  // 建議行動
  h += '<div class="sales-actions">';
  h += '<div class="ra-title">🎬 銷售策略建議</div><div class="ra-grid">';
  h += '<div class="ra-item"><div class="p">P1 短期</div><div class="t">淡季 ' + weakMonths[0][0] + '/' + weakMonths[1][0] + '月推早鳥備肥優惠</div><div class="w">預期:淡季拉近 30-50% 差距</div></div>';
  h += '<div class="ra-item"><div class="p">P2 中期</div><div class="t">推速溶粒肥/耐雨包裝主打雨季客戶</div><div class="w">預期:高雨月銷量回升 10-20%</div></div>';
  h += '<div class="ra-item"><div class="p">P3 長期</div><div class="t">目標 2028 破 20,000 噸 · 躋身全國 Top 15</div><div class="w">預期:市佔從 1.8% → 3%+</div></div>';
  h += '</div></div>';

  h += '<div class="rank-footer">📊 分析方法: CAGR 年複合成長率 · 季節指數 · Pearson 相關係數 · SWOT 定位 · YoY 同期比較</div>';

  target.innerHTML = h;
}}

// === 銷售資料編輯 (本機 localStorage) ===
function toggleSalesEdit() {{
  const panel = document.getElementById('salesEditPanel');
  const isOpen = panel.style.display !== 'none';
  panel.style.display = isOpen ? 'none' : '';
  document.getElementById('editIcon').textContent = isOpen ? '✏️' : '💾';
  document.getElementById('editLbl').textContent = isOpen ? '編輯銷售資料' : '關閉編輯 (已即時儲存)';
  document.getElementById('btnReset').style.display = isOpen ? 'none' : '';
  document.getElementById('btnExport').style.display = isOpen ? 'none' : '';
  if (!isOpen) renderSalesEditTable();
}}

function renderSalesEditTable() {{
  const monthly = window.SALES.monthly;
  const years = Object.keys(monthly).sort();
  const tbody = document.getElementById('salesEditTbody');
  tbody.innerHTML = '';
  years.forEach(y => {{
    const arr = monthly[y];
    const tr = document.createElement('tr');
    let html = '<td class="year-cell">' + y + '</td>';
    for (let m = 0; m < 12; m++) {{
      const v = arr[m];
      html += '<td><input class="month-cell" type="number" min="0" step="1" data-year="' + y + '" data-month="' + m + '" value="' + (v != null ? v : '') + '" placeholder="–"></td>';
    }}
    html += '<td><button class="del-btn" onclick="deleteSalesYear(\\'' + y + '\\')">刪除</button></td>';
    tr.innerHTML = html;
    tbody.appendChild(tr);
  }});
  // 綁定 input change
  tbody.querySelectorAll('input.month-cell').forEach(inp => {{
    inp.addEventListener('change', () => {{
      const y = inp.dataset.year, m = parseInt(inp.dataset.month);
      const raw = inp.value.trim();
      const v = raw === '' ? null : parseFloat(raw);
      window.SALES.monthly[y][m] = v;
      inp.classList.add('changed');
      _saveSalesToLS(window.SALES.monthly);
      _rerenderSales();
      const st = document.getElementById('editStatus');
      st.textContent = '✓ ' + y + '年' + (m+1) + '月 已儲存 (' + (v == null ? '清空' : v + ' 噸') + ')';
      setTimeout(() => {{ st.textContent = ''; inp.classList.remove('changed'); }}, 2500);
    }});
  }});
}}

function addSalesYear() {{
  const inp = document.getElementById('newYearInput');
  const y = inp.value.trim();
  if (!y || !/^\\d{{4}}$/.test(y)) {{
    alert('請輸入 4 位數年份 (例:2027)');
    return;
  }}
  if (window.SALES.monthly[y]) {{
    alert(y + ' 年已存在,請直接編輯該列');
    return;
  }}
  window.SALES.monthly[y] = new Array(12).fill(null);
  _saveSalesToLS(window.SALES.monthly);
  inp.value = '';
  renderSalesEditTable();
  _rerenderSales();
  document.getElementById('editStatus').textContent = '✓ 已新增 ' + y + ' 年 (請填入月份數字)';
}}

function deleteSalesYear(y) {{
  if (!confirm('確定刪除 ' + y + ' 年全部資料?')) return;
  delete window.SALES.monthly[y];
  _saveSalesToLS(window.SALES.monthly);
  renderSalesEditTable();
  _rerenderSales();
}}

function resetSalesData() {{
  if (!confirm('確定清除本機所有修改,還原為程式內建的初始資料?')) return;
  try {{ localStorage.removeItem(SALES_LS_KEY); }} catch (e) {{}}
  location.reload();
}}

function exportSalesJson() {{
  const data = JSON.stringify(window.SALES.monthly, null, 2);
  const blob = new Blob([data], {{type: 'application/json'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'sales_monthly_' + new Date().toISOString().slice(0,10) + '.json';
  a.click();
  URL.revokeObjectURL(url);
}}

function _rerenderSales() {{
  // 重繪 KPI+表格+圖表+評語
  const monthly = window.SALES.monthly;
  Object.keys(monthly).sort().forEach(y => {{
    const vals = monthly[y].filter(v => v != null);
    const sum = vals.reduce((a,b) => a+b, 0);
    let el = document.getElementById('k' + y);
    if (!el) return;  // 新加的年沒 KPI 卡,忽略
    el.textContent = sum.toLocaleString();
  }});
  // 重繪表格
  const tbody = document.getElementById('salesTbody');
  const allVals = Object.values(monthly).flatMap(a => a.filter(v => v != null));
  const maxVal = Math.max(...allVals, 1);
  tbody.innerHTML = '';
  Object.keys(monthly).sort().forEach(y => {{
    const arr = monthly[y];
    const total = arr.filter(v => v != null).reduce((a,b) => a+b, 0);
    const tr = document.createElement('tr');
    let html = '<td>' + y + '</td>';
    arr.forEach(v => {{
      if (v == null) {{
        html += '<td class="empty">–</td>';
      }} else {{
        const ratio = v / maxVal;
        let cls = 'low';
        if (ratio > 0.6) cls = 'hi';
        else if (ratio > 0.3) cls = 'mid';
        html += '<td class="' + cls + '">' + v.toLocaleString() + '</td>';
      }}
    }});
    html += '<td class="total">' + total.toLocaleString() + '</td>';
    tr.innerHTML = html;
    tbody.appendChild(tr);
  }});
  renderSalesChart();
  renderSalesAnalysis();
}}

// 浮動色階條 (參考 CODIS 官方 vertical bar) — 從 BANDS 動態生成
(function initLegendFab() {{
  const bar = document.getElementById('legendFabBar');
  if (!bar) return;
  // BANDS 由淺到深, 顯示時反過來 (深上淺下, 貼近 CODIS)
  const sorted = [...BANDS].reverse();
  bar.innerHTML = sorted.map(([lo, hi, color, lbl]) => {{
    const val = hi < 9999 ? hi : lo + '+';
    return '<div class="lf-row"><div class="lf-sw" style="background:' + color + '"></div>' +
           '<span class="lf-val">' + val + '</span><span class="lf-lbl">' + lbl + '</span></div>';
  }}).join('');
}})();

// 一鍵更新: 觸發 GitHub Actions daily-rainfall workflow (內含 fert_rankings 抓取)
async function updateFertRankings() {{
  const btn = document.getElementById('fertUpdateBtn');
  const origTxt = '🔄 一鍵更新';
  const REPO = 'yuan780903-cpu/market-scraper';
  const WF = 'refresh-rankings.yml';
  const PAT_KEY = 'gh_pat_v1';

  let pat = localStorage.getItem(PAT_KEY);
  if (!pat) {{
    pat = prompt('請貼 GitHub Personal Access Token (PAT)\\n\\n只存本機瀏覽器,不上傳雲端。\\n\\n取得方式:\\n1. 前往 https://github.com/settings/tokens\\n2. Generate new token (classic)\\n3. 勾選「workflow」scope\\n4. Generate → 複製貼上\\n\\n(下次按更新按鈕就不用再輸入了)');
    if (!pat) return;
    pat = pat.trim();
    localStorage.setItem(PAT_KEY, pat);
  }}

  btn.disabled = true;
  btn.textContent = '⏳ 觸發 GitHub Actions...';
  try {{
    const r = await fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/' + WF + '/dispatches', {{
      method: 'POST',
      headers: {{
        'Accept': 'application/vnd.github+json',
        'Authorization': 'Bearer ' + pat,
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
      }},
      body: JSON.stringify({{ ref: 'main' }}),
    }});
    if (r.status === 204) {{
      btn.textContent = '✅ 已觸發,約 3-8 分鐘完成';
      // 5 秒後啟動輪詢 workflow 狀態
      setTimeout(() => pollFertUpdate(pat, btn, origTxt), 5000);
    }} else if (r.status === 401 || r.status === 403) {{
      localStorage.removeItem(PAT_KEY);
      btn.textContent = '❌ PAT 無效 (再按重試)';
      btn.disabled = false;
      alert('PAT 驗證失敗\\n請確認:\\n1. Token 有「workflow」scope\\n2. Token 未過期');
    }} else {{
      const txt = await r.text();
      btn.textContent = '❌ HTTP ' + r.status;
      btn.disabled = false;
      console.error('trigger failed:', txt);
    }}
  }} catch (e) {{
    btn.textContent = '❌ ' + e.message;
    btn.disabled = false;
  }}
}}

async function pollFertUpdate(pat, btn, origTxt) {{
  const REPO = 'yuan780903-cpu/market-scraper';
  const start = new Date().toISOString();
  let attempts = 0;
  const timer = setInterval(async () => {{
    attempts++;
    try {{
      const r = await fetch('https://api.github.com/repos/' + REPO + '/actions/runs?per_page=5&event=workflow_dispatch', {{
        headers: {{'Authorization': 'Bearer ' + pat, 'Accept': 'application/vnd.github+json'}}
      }});
      if (!r.ok) return;
      const j = await r.json();
      const recent = (j.workflow_runs || [])[0];
      if (!recent) return;
      const status = recent.status;  // queued/in_progress/completed
      const concl = recent.conclusion;  // success/failure/null
      if (status === 'completed') {{
        clearInterval(timer);
        if (concl === 'success') {{
          btn.textContent = '✅ 完成!重整頁面看新資料';
          btn.style.background = 'linear-gradient(135deg,#1976d2,#0d47a1)';
          btn.onclick = () => location.reload();
          btn.disabled = false;
        }} else {{
          btn.textContent = '❌ Workflow 失敗:' + (concl||'?');
          btn.disabled = false;
        }}
      }} else if (status === 'queued') {{
        btn.textContent = '⏳ 排隊中... (' + attempts + ')';
      }} else if (status === 'in_progress') {{
        btn.textContent = '⚙️ 執行中... (' + attempts + ')';
      }}
    }} catch (e) {{}}
    if (attempts > 60) {{ clearInterval(timer); btn.textContent = '⌛ 超時,重整看看'; btn.disabled = false; }}
  }}, 8000);
}}

// 品目界定字典 (依農糧署 1090424 肥料種類品目及規格修正規定)
const CODE_INFO = {{
  '5-01': {{name:'植物渣粕肥料', source:'🌾 植物來源', src_color:'#2e7d32',
    criteria:'榨油後副產品 (大豆粕/花生粕/菜籽粕/棉籽粕/椰纖)', spec:'有機質 ≥40% · N ≥4%',
    examples:'大豆粕、花生粕、菜籽粕', uses:'有機認證農場、精緻蔬菜、有機茶園', tier:'2 元 (一般)'}},
  '5-02': {{name:'副產植物質肥料', source:'🌾 植物來源', src_color:'#2e7d32',
    criteria:'農食品加工植物副產品 (穀糠/樹皮/菇渣/酒糟)', spec:'有機質 ≥40%',
    examples:'米糠、菇太空包、酒糟', uses:'土壤改良、綠肥', tier:'2 元 (一般)'}},
  '5-03': {{name:'魚廢渣肥料', source:'🐟 動物來源', src_color:'#0288d1',
    criteria:'魚類加工副產品 (魚粉/骨粉)', spec:'有機質 ≥40% · N ≥5%',
    examples:'魚精肥、魚骨粉', uses:'高單價蔬菜/花卉', tier:'2 元'}},
  '5-04': {{name:'動物廢渣肥料', source:'🐄 動物來源', src_color:'#c62828',
    criteria:'屠宰副產品 (骨粉/血粉/羽毛粉)', spec:'有機質 ≥40%',
    examples:'血粉肥、羽毛肥', uses:'有機蔬菜、觀葉植物', tier:'2 元'}},
  '5-08': {{name:'雞糞加工肥料', source:'🐔 禽畜糞系', src_color:'#c62828',
    criteria:'100% 雞糞高溫乾燥或造粒 (未經堆肥發酵)', spec:'有機質 ≥45% · N ≥1.5%',
    examples:'雞糞粒、雞糞粉', uses:'果樹、大田作物、水稻', tier:'💰 2+2 元 (高階補助)'}},
  '5-09': {{name:'禽畜糞堆肥', source:'🐔 禽畜糞系', src_color:'#c62828',
    criteria:'禽畜糞 (雞/豬/牛/鴨/羊) + 好氣性堆肥發酵', spec:'有機質 ≥40% · C/N ≤20 (完熟指標)',
    examples:'豬糞堆肥、牛糞堆肥、禽糞堆肥', uses:'★大成/碩成主戰場★ 果樹基肥、蔬果', tier:'💰 2+2 元 (高階補助)'}},
  '5-10': {{name:'一般堆肥', source:'🔀 混合系', src_color:'#f57c00',
    criteria:'植物+動物混合堆肥發酵', spec:'有機質 ≥30%',
    examples:'綜合堆肥、農家堆肥', uses:'廣泛使用、土壤改良', tier:'2 元'}},
  '5-11': {{name:'雜項堆肥', source:'🔀 混合系', src_color:'#f57c00',
    criteria:'不屬 5-09/5-10 的其他堆肥 (菇渣/都市/菜市場廢棄物)', spec:'有機質 ≥30%',
    examples:'菇類堆肥、都市有機堆肥', uses:'環保回收再利用型', tier:'2 元'}},
  '5-12': {{name:'混合有機質肥料', source:'⚗️ 混合+化肥', src_color:'#7b1fa2',
    criteria:'有機肥+化學肥料 N/P/K 添加', spec:'有機質 ≥30% + 無機成分',
    examples:'有機化學複合肥', uses:'速效+長效兼顧、慣行農法', tier:'2 元'}},
  '5-13': {{name:'雜項有機質肥料', source:'🧪 特殊/雜項', src_color:'#6a1b9a',
    criteria:'5-01~5-12 都不算的其他 (含微生物/生物炭/特殊酵素)', spec:'因產品而異',
    examples:'微生物肥、生物炭肥、酵素肥', uses:'特殊功能訴求、藍海市場', tier:'💰 2+2 元 (高階補助)'}},
  '5-14': {{name:'液態雜項有機質肥料', source:'💧 液態', src_color:'#0288d1',
    criteria:'液態版 5-13', spec:'液態、含微生物',
    examples:'EM 菌液肥、發酵液肥', uses:'滴灌、葉面噴施', tier:'2 元'}},
  '5-15': {{name:'液態有機質肥料', source:'💧 液態', src_color:'#0288d1',
    criteria:'純有機質液態肥料', spec:'液態',
    examples:'液態豆餅肥、魚精液肥', uses:'滴灌系統、水耕', tier:'2 元'}},
  '7-02': {{name:'雜項有機質栽培介質', source:'🌱 栽培介質', src_color:'#5d4037',
    criteria:'兩種以上有機質介質混合', spec:'介質類、非肥料',
    examples:'椰纖+泥炭+珍珠石', uses:'育苗、盆栽', tier:'2 元'}},
  '7-03': {{name:'有機質栽培介質', source:'🌱 栽培介質', src_color:'#5d4037',
    criteria:'純單一有機質介質', spec:'介質類、非肥料',
    examples:'100% 泥炭、100% 椰纖', uses:'育苗、精緻盆栽', tier:'2 元'}},
}};

function showCodeInfo(code) {{
  const info = CODE_INFO[code];
  if (!info) return;
  let modal = document.getElementById('codeInfoModal');
  if (!modal) {{
    modal = document.createElement('div');
    modal.id = 'codeInfoModal';
    modal.className = 'code-info-modal';
    modal.onclick = (e) => {{ if (e.target === modal) modal.classList.remove('open'); }};
    document.body.appendChild(modal);
  }}
  modal.innerHTML =
    '<div class="cim-card">' +
    '<button class="cim-close" onclick="document.getElementById(\\'codeInfoModal\\').classList.remove(\\'open\\')">✕</button>' +
    '<div class="cim-code" style="background:' + info.src_color + '">' + code + '</div>' +
    '<div class="cim-name">' + info.name + '</div>' +
    '<div class="cim-source" style="color:' + info.src_color + '">' + info.source + '</div>' +
    '<div class="cim-row"><div class="cim-lbl">📖 界定原料</div><div class="cim-val">' + info.criteria + '</div></div>' +
    '<div class="cim-row"><div class="cim-lbl">📊 規格標準</div><div class="cim-val">' + info.spec + '</div></div>' +
    '<div class="cim-row"><div class="cim-lbl">🏷️ 常見產品</div><div class="cim-val">' + info.examples + '</div></div>' +
    '<div class="cim-row"><div class="cim-lbl">🎯 主要用途</div><div class="cim-val">' + info.uses + '</div></div>' +
    '<div class="cim-row"><div class="cim-lbl">💰 補助等級</div><div class="cim-val" style="color:#c62828;font-weight:900">' + info.tier + '</div></div>' +
    '<div class="cim-footer">📌 依據: 農糧署 1090424 肥料種類品目及規格修正規定</div>' +
    '</div>';
  modal.classList.add('open');
}}

// ============ 📜 歷史雨量地圖 (可選年+月) ============
const histMap = L.map('histMap', {{zoomControl: true, attributionControl: false, minZoom: 6, maxZoom: 12, maxBounds: L.latLngBounds([[20.5, 118.0], [26.5, 123.5]]), maxBoundsViscosity: 1.0}}).setView([23.7, 121.0], 7);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom: 15, opacity: 0.5}}).addTo(histMap);
let histMapLayer = null;

(function initHistMap() {{
  const H = window.HISTORY || {{}};
  if (!H.data) return;
  // 動態年份 (取 HISTORY 有的年份)
  const yearsSet = new Set();
  Object.values(H.data).forEach(cty => Object.keys(cty).forEach(y => yearsSet.add(y)));
  const years = [...yearsSet].sort((a,b) => b.localeCompare(a));  // 新→舊
  const ysel = document.getElementById('hmYear');
  years.forEach(y => {{
    const opt = document.createElement('option');
    opt.value = y; opt.textContent = y + ' 年';
    ysel.appendChild(opt);
  }});
  ysel.value = String(new Date().getFullYear());
  document.getElementById('hmMonth').value = String(new Date().getMonth() + 1);

  ['hmYear','hmMonth','hmMetric'].forEach(id => {{
    document.getElementById(id).addEventListener('change', renderHistMap);
  }});
  // 等 GeoJSON 載入完再首次繪
  if (typeof GEOJSON_URL !== 'undefined') {{
    fetch(GEOJSON_URL).then(r => r.json()).then(gj => {{
      window._histGeoJson = gj;
      setTimeout(() => {{ histMap.invalidateSize(); renderHistMap(); }}, 300);
    }}).catch(() => {{}});
  }}
}})();

function renderHistMap() {{
  const H = window.HISTORY;
  if (!H || !window._histGeoJson) return;
  const year = document.getElementById('hmYear').value;
  const month = document.getElementById('hmMonth').value;
  const metric = document.getElementById('hmMetric').value;

  // 每縣市取值 (全年 = 12 月 sum, 均溫則 avg)
  const values = {{}};
  const rankArr = [];
  Object.keys(H.data).forEach(county => {{
    const yData = H.data[county][year] || {{}};
    let v = null;
    if (month === 'all') {{
      const arr = [];
      for (let m = 1; m <= 12; m++) {{
        const md = yData[String(m)];
        if (md && md[metric] != null) arr.push(md[metric]);
      }}
      if (arr.length > 0) {{
        v = (metric === 'tavg') ? arr.reduce((s,x)=>s+x,0)/arr.length : arr.reduce((s,x)=>s+x,0);
      }}
    }} else {{
      const md = yData[month];
      if (md && md[metric] != null) v = md[metric];
    }}
    if (v != null) values[county] = v;
    // 排名
    const stns = ((H.stations || {{}})[county] || []).map(s => s.name + '(' + s.id + ')').join(',');
    rankArr.push({{county, v: v != null ? v : -1, stns}});
  }});

  const allVals = Object.values(values).filter(v => v != null);
  if (allVals.length === 0) {{
    document.getElementById('hmInfo').innerHTML = '<strong>' + year + '年' + (month==='all'?' 全年':' '+month+'月') + '</strong>: 無資料';
    return;
  }}
  const maxV = Math.max(...allVals);
  const avgV = allVals.reduce((s,v)=>s+v, 0) / allVals.length;

  const metricMeta = {{mm:{{lbl:'累積雨量',unit:'mm'}}, rd:{{lbl:'有雨日',unit:'天'}}, sd:{{lbl:'豪雨日',unit:'天'}}, tavg:{{lbl:'均溫',unit:'°C'}}}};
  const meta = metricMeta[metric];

  document.getElementById('hmInfo').innerHTML =
    '<strong>' + year + '年' + (month==='all'?' 全年累積' : ' ' + month + '月') + '</strong>：' + meta.lbl + ' · ' +
    '全國平均 <strong style="color:#7b1fa2">' + (metric==='tavg' ? avgV.toFixed(1) : avgV.toFixed(0)) + ' ' + meta.unit + '</strong> · ' +
    '最高 <strong style="color:#c62828">' + (metric==='tavg' ? maxV.toFixed(1) : maxV.toFixed(0)) + ' ' + meta.unit + '</strong>';

  // 塗色: 雨量用 BANDS,氣溫用漸層
  function colorFor(v) {{
    if (metric === 'tavg' && v != null) {{
      const t = Math.max(0, Math.min(1, (v - 10) / 25));
      const rr = Math.round(80 + t * 175), bb = Math.round(220 - t * 200);
      return 'rgb(' + rr + ',110,' + bb + ')';
    }}
    if (metric === 'mm') {{
      // 全年模式 scale × 12, 月則用原 BANDS
      const scale = (month === 'all') ? 12 : 1;
      for (const [lo, hi, color] of BANDS) {{
        if (v >= lo * scale && v < hi * scale) return color;
      }}
    }}
    // rd/sd 用漸層
    return `rgba(123,31,162,${{Math.min(v/maxV,1)*0.85+0.15}})`;
  }}

  if (histMapLayer) histMap.removeLayer(histMapLayer);
  histMapLayer = L.geoJson(window._histGeoJson, {{
    style: (feat) => {{
      const name = (feat.properties.COUNTYNAME || feat.properties.name);
      const nm = (typeof NAME_MAP !== 'undefined' && NAME_MAP[name]) || name;
      const v = values[nm];
      return {{fillColor: v != null ? colorFor(v) : '#eee', fillOpacity: 0.75, color: '#333', weight: 1}};
    }},
    onEachFeature: (feat, layer) => {{
      const name = (feat.properties.COUNTYNAME || feat.properties.name);
      const nm = (typeof NAME_MAP !== 'undefined' && NAME_MAP[name]) || name;
      const v = values[nm];
      const stns = ((H.stations || {{}})[nm] || []).map(s => s.name).join('、');
      layer.bindTooltip(nm + '<br>' + meta.lbl + ': ' + (v != null ? (metric==='tavg'?v.toFixed(1):v.toFixed(0)) + meta.unit : '無資料') + '<br>站: ' + stns, {{permanent: false, direction: 'top'}});
    }}
  }}).addTo(histMap);

  // 排名表
  rankArr.sort((a,b) => b.v - a.v);
  const rankBody = document.getElementById('hmRankBody');
  rankBody.innerHTML = '';
  document.getElementById('hmRankTitle').textContent = '全台縣市 · ' + year + '年' + (month==='all'?' 全年':' '+month+'月') + ' · ' + meta.lbl + ' 排名';
  rankArr.forEach((r, i) => {{
    if (r.v < 0) return;
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>#' + (i+1) + '</td><td>' + r.county + '</td><td style="font-size:10px;color:#666">' + r.stns + '</td><td class="n' + (i<3?' top':'') + '">' + (metric==='tavg' ? r.v.toFixed(1) : r.v.toFixed(0)) + ' ' + meta.unit + '</td>';
    rankBody.appendChild(tr);
  }});
}}

function openNcdrDailyMap() {{
  const y = document.getElementById('hmYear').value;
  const m = document.getElementById('hmMonth').value;
  if (m === 'all') {{
    alert('NCDR 只有單日圖,請選具體月份');
    return;
  }}
  // 開對應年月最新一天的 NCDR 圖 (預設 15 號)
  const url = 'https://watch.ncdr.nat.gov.tw/00_Wxmap/8A4_HISTORY_RAINMAP/' + y + '/s_rainmap_' + y + '-' + m.padStart(2,'0') + '-15.png';
  window.open(url, '_blank');
}}

// ============ 🏭 廠商排名 (從農糧署即時抓取) ============
(function initRankBlock() {{
  const R = window.FERT_RANKINGS || {{}};
  if (!R.suppliers) return;

  // KPI
  document.getElementById('rkTotSupp').textContent = R.total_suppliers || 0;
  document.getElementById('rkTotProd').textContent = R.total_products || 0;
  document.getElementById('rkUpd').textContent = R.updated || '–';
  const animal = R.suppliers.reduce((s, r) => s + (r.by_code['5-08'] || 0) + (r.by_code['5-09'] || 0), 0);
  const plant = R.suppliers.reduce((s, r) => s + (r.by_code['5-01'] || 0), 0);
  document.getElementById('rkAnimal').textContent = animal;
  document.getElementById('rkPlant').textContent = plant;

  // 品目下拉
  const codeSel = document.getElementById('rankCode');
  const allCodes = new Set();
  R.suppliers.forEach(r => Object.keys(r.by_code).forEach(c => allCodes.add(c)));
  const codeNames = {{'5-01':'植物渣粕','5-08':'雞糞加工','5-09':'禽畜糞堆肥','5-10':'一般堆肥','5-11':'雜項堆肥','5-12':'混合有機質','5-13':'雜項有機質','7-03':'有機介質'}};
  [...allCodes].sort().forEach(c => {{
    const opt = document.createElement('option');
    opt.value = c;
    opt.textContent = c + ' ' + (codeNames[c] || '');
    codeSel.appendChild(opt);
  }});

  // 品目統計小表
  renderCatSummary();
  renderMonitor();
  renderRankTable();
  renderRankAnalysis();

  document.getElementById('rankTier').addEventListener('change', renderRankTable);
  document.getElementById('rankCode').addEventListener('change', renderRankTable);
  document.getElementById('rankKw').addEventListener('input', renderRankTable);
}})();

function renderMonitor() {{
  const R = window.FERT_RANKINGS;
  if (!R) return;
  const added = R.recent_added || [];
  const viols = R.recent_violations || [];
  const removed = R.recent_removed || [];
  const days = R.monitor_days || 30;
  const el = document.getElementById('rankMonitor');
  if (!el) return;
  if (added.length === 0 && viols.length === 0 && removed.length === 0) {{
    el.innerHTML = '';
    return;
  }}
  let h = '<div class="mon-title">🔎 推薦名單監控 <span class="mon-sub">近 ' + days + ' 天:新上架 <strong>' + added.length + '</strong> · 新違規 <strong style="color:#c62828">' + viols.length + '</strong> · 下架 <strong>' + removed.length + '</strong></span></div>';
  h += '<div class="mon-grid">';

  // 新違規
  if (viols.length) {{
    h += '<div class="mon-card mon-viol"><div class="mon-h">⚠️ 新違規案件 (' + viols.length + ')</div><ul>';
    viols.slice(0, 10).forEach(v => {{
      h += '<li><span class="tag">[' + (v.cat || '?') + ']</span> <strong>' + (v.brand||'?') + '</strong>' +
           '<div class="who">' + (v.date||'') + ' · ' + (v.supplier||'') + '</div>' +
           (v.reason ? '<div class="reason">' + v.reason + '</div>' : '') + '</li>';
    }});
    if (viols.length > 10) h += '<li style="color:#888">... 及 ' + (viols.length-10) + ' 筆</li>';
    h += '</ul></div>';
  }}

  // 新上架
  if (added.length) {{
    h += '<div class="mon-card mon-add"><div class="mon-h">🆕 新上架 (' + added.length + ')</div><ul>';
    added.slice(0, 10).forEach(a => {{
      h += '<li><span class="tag">[' + (a.cat||'?') + ']</span> <strong>' + (a.brand||'?') + '</strong>' +
           '<div class="who">' + (a.date||'') + ' · ' + (a.supplier||'') + '</div></li>';
    }});
    if (added.length > 10) h += '<li style="color:#888">... 及 ' + (added.length-10) + ' 筆</li>';
    h += '</ul></div>';
  }}

  // 下架
  if (removed.length) {{
    h += '<div class="mon-card mon-rm"><div class="mon-h">📤 下架 (' + removed.length + ')</div><ul>';
    removed.slice(0, 10).forEach(r => {{
      h += '<li><span class="tag">[' + (r.cat||'?') + ']</span> <strong>' + (r.brand||'?') + '</strong>' +
           '<div class="who">' + (r.date||'') + ' · ' + (r.supplier||'') + '</div></li>';
    }});
    if (removed.length > 10) h += '<li style="color:#888">... 及 ' + (removed.length-10) + ' 筆</li>';
    h += '</ul></div>';
  }}

  h += '</div>';
  el.innerHTML = h;
}}

function renderCatSummary() {{
  const R = window.FERT_RANKINGS;
  if (!R || !R.categories) return;
  // 分兩排 by tier
  const tiers = {{'2+2元': [], '2元': []}};
  R.categories.forEach(c => {{
    if (tiers[c.tier]) tiers[c.tier].push(c);
  }});
  let html = '<div class="head">📊 各補助等級·品目統計 (共 ' + R.total_products + ' 產品 / ' + R.total_suppliers + ' 業者)</div>';
  html += '<table><thead><tr><th>補助等級</th><th>品目代碼</th><th>品目名稱</th><th>產品數</th><th>業者數</th><th>平均產品/家</th></tr></thead><tbody>';
  ['2+2元', '2元'].forEach(tier => {{
    tiers[tier].forEach((c, i) => {{
      const cls = tier === '2+2元' ? 'tier-hi' : '';
      html += '<tr>';
      if (i === 0) html += '<td class="' + cls + '" rowspan="' + tiers[tier].length + '"><strong>' + tier + '</strong></td>';
      html += '<td><a class="code-link" onclick="showCodeInfo(\\'' + c.code + '\\')" title="點看界定">' + c.code + '</a></td><td class="name">' + c.name + '</td>';
      html += '<td>' + c.n_prods + '</td><td>' + c.n_suppliers + '</td>';
      html += '<td>' + (c.n_suppliers > 0 ? (c.n_prods / c.n_suppliers).toFixed(1) : '–') + '</td>';
      html += '</tr>';
    }});
  }});
  html += '</tbody></table>';
  document.getElementById('rankCatSummary').innerHTML = html;
}}

function renderRankTable() {{
  const R = window.FERT_RANKINGS;
  if (!R || !R.suppliers) return;
  const tier = document.getElementById('rankTier').value;
  const code = document.getElementById('rankCode').value;
  const kw = document.getElementById('rankKw').value.trim();

  // 過濾
  let filtered = R.suppliers.map(r => {{
    // 若有 tier/code 篩選,重算 total = 該 tier/code 的產品數
    let tierTotal = tier === 'all' ? r.total : (r.by_tier[tier] || 0);
    let codeTotal = code === 'all' ? r.total : (r.by_code[code] || 0);
    let showTotal = r.total;
    if (tier !== 'all' && code !== 'all') {{
      // 這裡簡化:用 code 為主
      showTotal = codeTotal;
    }} else if (tier !== 'all') {{
      showTotal = tierTotal;
    }} else if (code !== 'all') {{
      showTotal = codeTotal;
    }}
    return {{...r, showTotal}};
  }}).filter(r => r.showTotal > 0);

  if (kw) filtered = filtered.filter(r => r.name.includes(kw));

  // 重排 rank
  filtered.sort((a, b) => b.showTotal - a.showTotal);
  filtered.forEach((r, i) => r.dynRank = i + 1);

  document.getElementById('rankCount').textContent = '共 ' + filtered.length + ' 家';

  const tbody = document.getElementById('rankTbody');
  tbody.innerHTML = '';
  const codeNames = {{'5-01':'植物渣粕','5-08':'雞糞加工','5-09':'禽畜糞堆肥','5-10':'一般堆肥','5-11':'雜項堆肥','5-12':'混合有機質','5-13':'雜項有機質','7-03':'有機介質'}};
  filtered.forEach(r => {{
    const isDachan = r.name.includes('大成') || r.name.includes('碩成');
    const rankCls = r.dynRank <= 3 ? 'rank top3' : 'rank';
    const nameCls = isDachan ? 'name dachan' : 'name';
    const cats = Object.entries(r.by_code).sort((a,b) => b[1] - a[1])
      .map(([c, n]) => '<span class="cat" onclick="showCodeInfo(\\'' + c + '\\')" title="點看品目界定">' + c + ':' + n + '</span>').join('');
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td class="' + rankCls + '">#' + r.dynRank + '</td>' +
      '<td class="' + nameCls + '">' + r.name + (isDachan ? ' ★' : '') + '</td>' +
      '<td class="n big">' + r.total + '</td>' +
      '<td class="n">' + (r.by_tier['2+2元'] || 0) + '</td>' +
      '<td class="n">' + (r.by_tier['2元'] || 0) + '</td>' +
      '<td class="n">' + r.n_categories + '</td>' +
      '<td class="cats">' + cats + '</td>';
    tbody.appendChild(tr);
  }});
}}

function renderRankAnalysis() {{
  const R = window.FERT_RANKINGS;
  if (!R || !R.suppliers || !R.suppliers.length) return;
  const supps = R.suppliers;
  const top3 = supps.slice(0, 3);
  const top10 = supps.slice(0, 10);
  const T = R.total_products;
  const N = R.total_suppliers;
  const dachan = supps.find(r => r.name.includes('大成') || r.name.includes('碩成'));

  // === 集中度指標 (BI 標準) ===
  const cr = (n) => supps.slice(0, n).reduce((s,r)=>s+r.total, 0);
  const CR3 = cr(3), CR5 = cr(5), CR10 = cr(10);
  const CR3pct = (CR3/T*100), CR5pct = (CR5/T*100), CR10pct = (CR10/T*100);
  // HHI 指數 (Herfindahl-Hirschman Index): sum(marketShare^2) × 10000
  const hhi = supps.reduce((s, r) => {{
    const share = r.total / T;
    return s + share * share;
  }}, 0) * 10000;
  let hhiLevel = '', hhiColor = '';
  if (hhi < 1000) {{ hhiLevel = '低度集中(競爭激烈)'; hhiColor = '#2e7d32'; }}
  else if (hhi < 1800) {{ hhiLevel = '中度集中'; hhiColor = '#f57c00'; }}
  else {{ hhiLevel = '高度集中(寡佔)'; hhiColor = '#c62828'; }}

  // 品目結構分析
  const codeStats = {{}};  // code -> prods/supps
  supps.forEach(r => Object.entries(r.by_code).forEach(([c, n]) => {{
    if (!codeStats[c]) codeStats[c] = {{prods: 0, supps: new Set()}};
    codeStats[c].prods += n;
    codeStats[c].supps.add(r.name);
  }}));
  const codeNames = {{'5-01':'植物渣粕','5-08':'雞糞加工','5-09':'禽畜糞堆肥','5-10':'一般堆肥','5-11':'雜項堆肥','5-12':'混合有機質','5-13':'雜項有機質','7-03':'有機介質'}};

  // 補助結構
  const tier22 = supps.reduce((s,r)=>s+(r.by_tier['2+2元']||0), 0);
  const tier2 = supps.reduce((s,r)=>s+(r.by_tier['2元']||0), 0);

  // 平均值
  const avgProds = T / N;

  // ===== HTML render =====
  let html = '';

  // 執行摘要
  html += '<div class="rank-exec-summary">';
  html += '<div class="es-title">📋 執行摘要 (Executive Summary)</div>';
  html += '<div class="es-grid">';
  html += '  <div class="es-item"><div class="lbl">市場總產品</div><div class="val">' + T + '</div><div class="unit">支</div></div>';
  html += '  <div class="es-item"><div class="lbl">競爭廠商</div><div class="val">' + N + '</div><div class="unit">家</div></div>';
  html += '  <div class="es-item"><div class="lbl">CR3 集中度</div><div class="val">' + CR3pct.toFixed(1) + '<span>%</span></div><div class="unit">Top 3 市佔</div></div>';
  html += '  <div class="es-item"><div class="lbl">CR10 集中度</div><div class="val">' + CR10pct.toFixed(1) + '<span>%</span></div><div class="unit">Top 10 市佔</div></div>';
  html += '  <div class="es-item"><div class="lbl">HHI 指數</div><div class="val" style="color:' + hhiColor + '">' + Math.round(hhi) + '</div><div class="unit" style="color:' + hhiColor + '">' + hhiLevel + '</div></div>';
  html += '  <div class="es-item"><div class="lbl">平均產品/家</div><div class="val">' + avgProds.toFixed(1) + '</div><div class="unit">支/廠</div></div>';
  html += '</div></div>';

  // === Dashboard 圖表區 (grid 3 欄) ===
  html += '<div class="rank-dashboard">';

  // Chart 1: 補助結構 donut
  const donutW = 220, cxD = 110, cyD = 90, r1 = 65, r2 = 40;
  const total = tier22 + tier2;
  const ang22 = tier22/total * Math.PI * 2;
  const donutSvg = (() => {{
    const arc = (start, end, rOut, rIn, color) => {{
      const x1 = cxD + rOut*Math.sin(start), y1 = cyD - rOut*Math.cos(start);
      const x2 = cxD + rOut*Math.sin(end), y2 = cyD - rOut*Math.cos(end);
      const x3 = cxD + rIn*Math.sin(end), y3 = cyD - rIn*Math.cos(end);
      const x4 = cxD + rIn*Math.sin(start), y4 = cyD - rIn*Math.cos(start);
      const large = (end - start) > Math.PI ? 1 : 0;
      return '<path d="M ' + x1 + ' ' + y1 + ' A ' + rOut + ' ' + rOut + ' 0 ' + large + ' 1 ' + x2 + ' ' + y2 +
             ' L ' + x3 + ' ' + y3 + ' A ' + rIn + ' ' + rIn + ' 0 ' + large + ' 0 ' + x4 + ' ' + y4 + ' Z" fill="' + color + '"/>';
    }};
    let s = '<svg viewBox="0 0 ' + donutW + ' 200" xmlns="http://www.w3.org/2000/svg">';
    s += arc(0, ang22, r1, r2, '#c62828');
    s += arc(ang22, Math.PI*2, r1, r2, '#1976d2');
    s += '<text x="' + cxD + '" y="' + (cyD-4) + '" text-anchor="middle" font-size="20" font-weight="900" fill="#333">' + T + '</text>';
    s += '<text x="' + cxD + '" y="' + (cyD+14) + '" text-anchor="middle" font-size="10" fill="#666">總產品</text>';
    s += '<text x="' + cxD + '" y="185" text-anchor="middle" font-size="11" font-weight="700" fill="#333">💰 補助等級結構</text>';
    // legend
    s += '<rect x="12" y="' + (cyD-20) + '" width="10" height="10" fill="#c62828"/><text x="26" y="' + (cyD-11) + '" font-size="10" fill="#333">2+2元 ' + tier22 + ' (' + (tier22/total*100).toFixed(0) + '%)</text>';
    s += '<rect x="12" y="' + (cyD+8) + '" width="10" height="10" fill="#1976d2"/><text x="26" y="' + (cyD+17) + '" font-size="10" fill="#333">2元 ' + tier2 + ' (' + (tier2/total*100).toFixed(0) + '%)</text>';
    s += '</svg>';
    return s;
  }})();

  html += '<div class="db-card"><div class="db-head">💰 補助等級結構分析</div><div class="db-body">' + donutSvg;
  html += '<div class="db-insight"><strong>2+2 元高階補助占 ' + (tier22/total*100).toFixed(0) + '%</strong> — 此補助專屬於「原料含<strong style="color:#c62828">雞糞 ≥50%</strong>」的禽畜糞衍生產品 (5-08/5-09/5-13)。碩成/大成禽畜糞系列受惠,通路推廣力道大。</div></div></div>';

  // Chart 2: 品目佔比 horizontal bar (品目名固定在左, bar 中間, 數字在右)
  const codeList = Object.entries(codeStats).sort((a,b) => b[1].prods - a[1].prods);
  const maxCode = Math.max(...codeList.map(([_,v]) => v.prods));
  const cbW = 380, cbBarStart = 130, cbBarMax = 180;  // 品目名+代碼區 130px, bar 最大 180px, 右側 70px 給數字
  let cbSvg = '<svg viewBox="0 0 ' + cbW + ' ' + (codeList.length * 26 + 20) + '" xmlns="http://www.w3.org/2000/svg">';
  codeList.forEach(([c, v], i) => {{
    const w = (v.prods / maxCode) * cbBarMax;
    const y = 8 + i * 26;
    // 左側: 代碼 + 品目名 (固定寬度不重疊)
    cbSvg += '<text x="4" y="' + (y+14) + '" font-size="10" font-weight="900" fill="#6a1b9a" font-family="ui-monospace,Menlo,monospace">' + c + '</text>';
    cbSvg += '<text x="42" y="' + (y+14) + '" font-size="10" fill="#333">' + (codeNames[c] || '').substring(0, 8) + '</text>';
    // Bar
    cbSvg += '<rect x="' + cbBarStart + '" y="' + y + '" width="' + w + '" height="18" fill="url(#gradP)" rx="2"/>';
    // 右側: 數字
    cbSvg += '<text x="' + (cbBarStart + w + 4) + '" y="' + (y+14) + '" font-size="10" font-weight="700" fill="#6a1b9a">' + v.prods + '<tspan fill="#888" font-size="9"> / ' + v.supps.size + '家</tspan></text>';
  }});
  cbSvg += '<defs><linearGradient id="gradP" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#7b1fa2"/><stop offset="100%" stop-color="#c2185b"/></linearGradient></defs>';
  cbSvg += '</svg>';
  html += '<div class="db-card"><div class="db-head">🧩 品目結構 (產品數 × 業者數)</div><div class="db-body">' + cbSvg;
  const topCode = codeList[0];
  html += '<div class="db-insight">最大細分 <strong>' + topCode[0] + ' ' + codeNames[topCode[0]] + '</strong>:' + topCode[1].prods + '產品/' + topCode[1].supps.size + '家,平均 ' + (topCode[1].prods/topCode[1].supps.size).toFixed(1) + ' 產品/家(競爭激烈)。</div></div></div>';

  // Chart 3: Top 10 廠商水平長條 + 大成標示
  const maxT = top10[0].total;
  let barSvg = '<svg viewBox="0 0 340 ' + (top10.length * 26 + 30) + '" xmlns="http://www.w3.org/2000/svg">';
  top10.forEach((s, i) => {{
    const w = (s.total / maxT) * 200;
    const y = 8 + i * 26;
    const isDachan = s.name.includes('大成') || s.name.includes('碩成');
    const color = isDachan ? '#c62828' : (i < 3 ? '#ff9800' : '#6a1b9a');
    const name = s.name.length > 12 ? s.name.substring(0, 10) + '..' : s.name;
    barSvg += '<text x="4" y="' + (y+13) + '" font-size="10" font-weight="900" fill="#333">#' + (i+1) + '</text>';
    barSvg += '<text x="22" y="' + (y+13) + '" font-size="10" fill="' + (isDachan ? '#c62828' : '#333') + '" font-weight="' + (isDachan ? 900 : 600) + '">' + name + '</text>';
    barSvg += '<rect x="128" y="' + y + '" width="' + w + '" height="16" fill="' + color + '" rx="2"/>';
    barSvg += '<text x="' + (w + 132) + '" y="' + (y+12) + '" font-size="10" font-weight="900" fill="' + color + '">' + s.total + '</text>';
  }});
  barSvg += '</svg>';
  html += '<div class="db-card"><div class="db-head">🏆 Top 10 廠商產品數</div><div class="db-body">' + barSvg;
  html += '<div class="db-insight">龍頭 <strong>' + top10[0].name + '</strong> ' + top10[0].total + ' 支,CR3 = ' + CR3pct.toFixed(1) + '%,顯示 <strong style="color:' + hhiColor + '">' + hhiLevel + '</strong>。</div></div></div>';

  html += '</div>';  // /rank-dashboard

  // 大成 SWOT 分析卡
  if (dachan) {{
    const dachanShare = (dachan.total / T * 100);
    const dachanCat = Object.entries(dachan.by_code).sort((a,b) => b[1]-a[1])[0];
    // 大成 vs Top 10 平均
    const top10Avg = top10.reduce((s,r)=>s+r.total, 0) / 10;
    const gap = top10Avg - dachan.total;

    // 未進軍品目
    const notInCodes = Object.keys(codeStats).filter(c => !dachan.by_code[c]);
    const bluOcean = notInCodes.filter(c => codeStats[c].supps.size < 15 && codeStats[c].prods > 5)
      .map(c => c + ' ' + (codeNames[c]||'')).slice(0, 3);

    html += '<div class="rank-swot">';
    html += '<div class="swot-title">🎯 大成/碩成 SWOT 定位分析</div>';
    html += '<div class="swot-grid">';
    html += '  <div class="swot-cell strength"><div class="h">💪 Strength 優勢</div>';
    html += '<ul><li>已進入農糧署 <strong>2+2 元高階補助</strong>白名單 (' + (dachan.by_tier['2+2元']||0) + ' 產品)</li>';
    html += '<li>集中主戰場 <strong>' + dachanCat[0] + ' ' + (codeNames[dachanCat[0]]||'') + '</strong> (' + dachanCat[1] + ' 產品,深耕定位)</li>';
    html += '<li>母公司規模 (大成長城 1210 · TWSE)<strong>資本雄厚</strong></li></ul></div>';

    html += '  <div class="swot-cell weakness"><div class="h">⚠️ Weakness 劣勢</div>';
    html += '<ul><li>全國排名第 <strong>#' + dachan.rank + '</strong>/' + N + ' · 市佔僅 <strong>' + dachanShare.toFixed(2) + '%</strong></li>';
    html += '<li>品目布局窄 (' + dachan.n_categories + '個 vs Top 10 平均 ' + (top10.reduce((s,r)=>s+r.n_categories,0)/10).toFixed(1) + '個)</li>';
    html += '<li>與 Top 10 平均產品數差距 <strong>-' + gap.toFixed(0) + ' 支</strong></li></ul></div>';

    html += '  <div class="swot-cell opportunity"><div class="h">🚀 Opportunity 機會</div>';
    html += '<ul><li><strong>藍海細分市場</strong>(業者少產品少): ' + (bluOcean.length ? bluOcean.join('、') : '需另行盤點') + '</li>';
    html += '<li>市場 HHI = ' + Math.round(hhi) + ' (' + hhiLevel + ') → <strong>無寡佔對手</strong>,前 10 名內仍有搶佔空間</li>';
    html += '<li>2025 銷量翻倍 → 產能與品牌力已達 top 20 級,推薦名單擴充後排名可迅速上升</li></ul></div>';

    html += '  <div class="swot-cell threat"><div class="h">🌪 Threat 威脅</div>';
    html += '<ul><li>Top 3 (' + top3.map(t => t.name.substring(0,6)).join('/') + ') 品牌力強勢,銷售通路先發</li>';
    html += '<li>禽畜糞細分競爭最激烈: ' + (codeStats['5-09'] ? codeStats['5-09'].supps.size + ' 家搶 ' + codeStats['5-09'].prods + ' 產品' : '') + '</li>';
    html += '<li>環保法規對禽畜糞來源、重金屬含量、氨氣排放趨嚴 → 中小廠退場,但同時大廠壓力也增</li></ul></div>';
    html += '</div></div>';
  }}

  // 建議行動
  html += '<div class="rank-actions">';
  html += '<div class="ra-title">🎬 建議行動方案 (Actionable Recommendations)</div>';
  html += '<div class="ra-grid">';
  html += '<div class="ra-item"><div class="p">P1 短期</div><div class="t">增加 5-09 禽畜糞堆肥新品牌通過推薦</div><div class="w">預期效果:排名從 #' + (dachan?dachan.rank:'?') + ' 前進 5-10 名</div></div>';
  html += '<div class="ra-item"><div class="p">P2 中期</div><div class="t">跨足 5-12 混合有機質肥料 (第二大細分市場)</div><div class="w">預期效果:品目數 +1,總產品數翻倍</div></div>';
  html += '<div class="ra-item"><div class="p">P3 長期</div><div class="t">佈局 5-13 雜項有機質 (2+2 元 · 藍海:僅 ' + (codeStats['5-13'] ? codeStats['5-13'].supps.size : '?') + ' 家)</div><div class="w">預期效果:進入獨佔區間,毛利率提升</div></div>';
  html += '</div></div>';

  // 資料源
  const supp10 = supps.slice(0, 3);
  const top3names = supp10.map(t => t.name);
  html += '<div class="rank-footer">';
  html += '📡 資料源: <a href="' + R.source_url + '" target="_blank">農糧署 · 115 年國產有機質肥料品牌推薦名單</a> · ';
  html += '每 7 天自動同步 · 最後更新 ' + R.updated + '<br>';
  html += '💡 分析方法: CR3/CR5/CR10 集中度比、HHI 賀芬達爾指數、SWOT 定位、藍海細分市場識別';
  html += '</div>';

  document.getElementById('rankAnalysis').innerHTML = html;
}}

// 摺疊區塊 (鄉鎮農產/作物基肥) — 點標題 toggle
(function initCollapsible() {{
  document.querySelectorAll('.collapsible > h3').forEach(h => {{
    h.addEventListener('click', () => {{
      const blk = h.parentElement;
      blk.classList.toggle('collapsed');
      // 展開時觸發地圖 resize (讓 leaflet 重繪)
      if (!blk.classList.contains('collapsed')) {{
        setTimeout(() => {{
          try {{ if (blk.id === 'townsBlock' && typeof townsMap !== 'undefined') townsMap.invalidateSize(); }} catch(e){{}}
        }}, 200);
      }}
    }});
  }});
}})();

// 動態重排: 新聞往上提到進階四維後, 作物基肥+鄉鎮農產搬到最底
(function reorderBlocks() {{
  const news = document.getElementById('newsBlock');
  const adv = document.getElementById('advBlock');
  const crop = document.getElementById('cropBlock');
  const towns = document.getElementById('townsBlock');
  const analysis = document.querySelector('.analysis-block');
  if (news && adv && adv.parentNode) {{
    // news 移到 analysis 前 (analysis 之後接 news)
    if (analysis) {{
      analysis.parentNode.insertBefore(news, analysis.nextSibling);
    }} else {{
      adv.parentNode.insertBefore(news, adv.nextSibling);
    }}
  }}
  // solar + crop + towns 搬到 body 最底 (在 copyright badge 之前)
  const solar = document.getElementById('solarBlock');
  const badge = document.querySelector('.copyright-badge');
  [solar, crop, towns].forEach(blk => {{
    if (!blk) return;
    if (badge) badge.parentNode.insertBefore(blk, badge);
    else document.body.appendChild(blk);
  }});
}})();

// CWA sidebar: smooth scroll + active state (仿 CODIS)
(function initSidebar() {{
  const links = document.querySelectorAll('.cwa-sidebar-nav a');
  links.forEach(a => {{
    a.addEventListener('click', (e) => {{
      const target = document.querySelector(a.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      // 若目標在 unified-tab 內, 先切到對應 tab
      const parentBlock = target.closest('.unified-block');
      if (parentBlock && !parentBlock.classList.contains('active')) {{
        const tabBtn = document.querySelector('#unifiedTabs button[data-target="' + parentBlock.id + '"]');
        if (tabBtn) tabBtn.click();
        setTimeout(() => target.scrollIntoView({{behavior: 'smooth', block: 'start'}}), 200);
      }} else {{
        target.scrollIntoView({{behavior: 'smooth', block: 'start'}});
      }}
      links.forEach(x => x.classList.remove('active'));
      a.classList.add('active');
    }});
  }});
  // 滾動時自動高亮
  const sections = [...links].map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);
  window.addEventListener('scroll', () => {{
    const y = window.scrollY + 100;
    let active = null;
    sections.forEach(s => {{
      if (s.offsetTop <= y) active = s;
    }});
    if (active) {{
      links.forEach(x => x.classList.toggle('active', x.getAttribute('href') === '#' + active.id));
    }}
  }}, {{passive: true}});
}})();

// 統一 tab bar: 三選一切換 (雨量觀測/未來預測/鄉鎮農產)
(function initUnifiedTabs() {{
  const tabs = document.getElementById('unifiedTabs');
  if (!tabs) return;
  const btns = tabs.querySelectorAll('button');
  const mapObjs = {{obsBlock: 'map', fcstBlock: 'fcstMap', townsBlock: 'townsMap'}};
  btns.forEach(b => {{
    b.addEventListener('click', () => {{
      const target = b.dataset.target;
      btns.forEach(x => x.classList.toggle('active', x === b));
      document.querySelectorAll('.unified-block').forEach(bl => {{
        bl.classList.toggle('active', bl.id === target);
      }});
      // 對應地圖 invalidate (延遲讓 display:block 先生效)
      const mapVarName = mapObjs[target];
      const mapVar = ({{map: window.map, fcstMap: window.fcstMap, townsMap: window.townsMap}})[mapVarName];
      if (mapVar) setTimeout(() => mapVar.invalidateSize(), 50);
      // 對於 townsMap 用 window.townsMap 可能 undefined (是 const 全域),用 eval fallback
      setTimeout(() => {{
        try {{
          if (target === 'obsBlock' && typeof map !== 'undefined') map.invalidateSize();
          if (target === 'fcstBlock' && typeof fcstMap !== 'undefined') fcstMap.invalidateSize();
          if (target === 'townsBlock' && typeof townsMap !== 'undefined') townsMap.invalidateSize();
          if (target === 'histMapBlock' && typeof histMap !== 'undefined') histMap.invalidateSize();
        }} catch (e) {{}}
      }}, 60);
      // 平滑捲到頂部
      // 切到目標 block 頂端 (直接看到內容, 而非 tab bar)
      const targetEl = document.getElementById(target);
      if (targetEl) {{
        setTimeout(() => {{
          const y = targetEl.getBoundingClientRect().top + window.pageYOffset - 60;
          window.scrollTo({{top: y, behavior: 'smooth'}});
        }}, 100);
      }}
    }});
  }});
}})();

// 影響級距 fab: 手機點擊 toggle (桌面 hover 觸發)
(function initImpactFab() {{
  const fab = document.getElementById('impactFab');
  if (!fab) return;
  const btn = fab.querySelector('.impact-fab-btn');
  btn.addEventListener('click', (e) => {{ e.stopPropagation(); fab.classList.toggle('open'); }});
  document.addEventListener('click', (e) => {{ if (!fab.contains(e.target)) fab.classList.remove('open'); }});
}})();

document.getElementById('townFltCat').addEventListener('change', renderTownsMap);
document.getElementById('townKw').addEventListener('input', renderTownsMap);
renderTownsMap();
// Leaflet 底圖 tile 需要 map 有正確尺寸才會 render, invalidate 多次確保
setTimeout(() => townsMap.invalidateSize(), 100);
setTimeout(() => townsMap.invalidateSize(), 600);
window.addEventListener('load', () => setTimeout(() => townsMap.invalidateSize(), 100));
// 用 IntersectionObserver 在 map 進入視窗時再 invalidate 一次
if ('IntersectionObserver' in window) {{
  const io = new IntersectionObserver((entries) => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{ townsMap.invalidateSize(); io.disconnect(); }}
    }});
  }}, {{threshold: 0.1}});
  io.observe(document.getElementById('townsMap'));
}}

// ============ 🌱 基肥作物交叉篩選 ============
const CROPS = {crops_json};
const PROB_MULT = {{'高': 2.5, '中': 1.5, '低': 0.5}};   // 使用機率 → 年基肥次數係數

(function initCropsFilter() {{
  ['fltCat', 'fltRegion', 'fltArea', 'fltProb', 'fltThisMonth'].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', renderCrops);
  }});
  renderCrops();
}})();

function renderCrops() {{
  const cat = document.getElementById('fltCat').value;
  const region = document.getElementById('fltRegion').value;
  const areaHa = parseFloat(document.getElementById('fltArea').value) || 0;
  const prob = document.getElementById('fltProb').value;
  const onlyThisMonth = document.getElementById('fltThisMonth').checked;
  const currentMonth = new Date().getMonth() + 1;

  let filtered = CROPS.filter(c => {{
    if (cat && c.cat !== cat) return false;
    if (region && !c.regions.includes(region)) return false;
    if (prob && c.prob !== prob) return false;
    if (onlyThisMonth && !c.months.includes(currentMonth)) return false;
    return true;
  }});

  // 排序：本月適合放前面 > 使用機率高 > 每甲用量大
  filtered.sort((a, b) => {{
    const am = a.months.includes(currentMonth) ? 0 : 1;
    const bm = b.months.includes(currentMonth) ? 0 : 1;
    if (am !== bm) return am - bm;
    const pOrder = {{'高': 0, '中': 1, '低': 2}};
    if (pOrder[a.prob] !== pOrder[b.prob]) return pOrder[a.prob] - pOrder[b.prob];
    return b.kgPerHa - a.kgPerHa;
  }});

  // 統計
  const matchThisMonth = filtered.filter(c => c.months.includes(currentMonth));
  const summary = document.getElementById('cropsSummary');
  let annualEstKg = 0;
  if (areaHa > 0) {{
    filtered.forEach(c => {{
      annualEstKg += c.kgPerHa * areaHa * (PROB_MULT[c.prob] || 1);
    }});
  }}
  summary.innerHTML =
    '<span class="stat">符合條件 <strong>' + filtered.length + '</strong><span class="unit">種作物</span></span>' +
    '<span class="stat">本月（' + currentMonth + '月）適合 <strong>' + matchThisMonth.length + '</strong><span class="unit">種</span></span>' +
    (areaHa > 0 ? '<span class="stat">預估年度需求 <strong>' + Math.round(annualEstKg).toLocaleString() + '</strong><span class="unit">kg/戶</span></span>' : '') +
    (matchThisMonth.length ? '<span class="this-month">🎯 本月適合：' + matchThisMonth.slice(0, 5).map(c => c.emoji + c.name).join('、') + (matchThisMonth.length > 5 ? '…' : '') + '</span>' : '');

  // 表格
  const tbody = document.getElementById('cropsTbody');
  tbody.innerHTML = '';
  filtered.forEach(c => {{
    const isMatch = c.months.includes(currentMonth);
    const tr = document.createElement('tr');
    if (isMatch) tr.className = 'match-month';
    const monthsHtml = c.months.map(m =>
      '<span class="m' + (m === currentMonth ? ' now' : '') + '">' + m + '月</span>'
    ).join('');
    const probClass = c.prob === '高' ? 'h' : (c.prob === '中' ? 'm' : 'l');
    const kgTotal = areaHa > 0 ? (c.kgPerHa * areaHa).toLocaleString() : c.kgPerHa.toLocaleString();
    const kgLabel = areaHa > 0 ? (kgTotal + '<br><span style="font-size:10px;color:#888">總量</span>')
                                : c.kgPerHa.toLocaleString();
    tr.innerHTML =
      '<td class="cat">' + c.emoji + '</td>' +
      '<td class="name">' + c.name + '</td>' +
      '<td class="months">' + monthsHtml + '</td>' +
      '<td class="regions">' + c.regions.join('、') + '</td>' +
      '<td class="kg">' + kgLabel + '</td>' +
      '<td class="prob ' + probClass + '">' + c.prob + '</td>' +
      '<td class="note">' + (c.note || '—') + '</td>';
    tbody.appendChild(tr);
  }});
  if (filtered.length === 0) {{
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:#888">無符合條件的作物，請放寬篩選</td></tr>';
  }}
}}

// ============ 排名等級 emoji 對應 ============
function fcstEmoji(mm, isMultiDay) {{
  if (isMultiDay) {{
    if (mm >= 500) return '🌊';
    if (mm >= 300) return '⛈';
    if (mm >= 150) return '☔';
    if (mm >= 80)  return '🌧';
    if (mm >= 30)  return '💧';
    if (mm >= 1)   return '☁';
    return '☀';
  }}
  if (mm >= 200) return '🌀';
  if (mm >= 130) return '🌊';
  if (mm >= 80)  return '⛈';
  if (mm >= 50)  return '☔';
  if (mm >= 30)  return '🌧';
  if (mm >= 10)  return '💧';
  if (mm >= 1)   return '☁';
  return '☀';
}}

// ============ 💧 雨量視覺化 Modal ============
function openRainModal(dateStr, mm, county, wk) {{
  const modal = document.getElementById('rainModal');
  document.getElementById('rmTitle').textContent = dateStr + ' (' + wk + ') · ' + county;
  document.getElementById('rmNum').textContent = mm.toFixed(1);

  // 等級 + 說明
  let lvl = '無雨', lvlColor = '#888';
  if (mm >= 200) {{ lvl = '超大豪雨 · 極端災害級'; lvlColor = '#8b1d8b'; }}
  else if (mm >= 130) {{ lvl = '豪雨 · 嚴重致災'; lvlColor = '#c62828'; }}
  else if (mm >= 80) {{ lvl = '大雨 · 農路積水'; lvlColor = '#ef6c00'; }}
  else if (mm >= 50) {{ lvl = '較大 · 影響出貨'; lvlColor = '#f0c040'; }}
  else if (mm >= 30) {{ lvl = '中雨 · 養分流失'; lvlColor = '#5cb85c'; }}
  else if (mm >= 10) {{ lvl = '小雨 · 補充水分'; lvlColor = '#1976d2'; }}
  else if (mm >= 1)  {{ lvl = '零星降雨 · 無影響'; lvlColor = '#7bb3eb'; }}
  const lvlEl = document.getElementById('rmLvl');
  lvlEl.textContent = lvl;
  lvlEl.style.color = lvlColor;

  // 量杯水位動畫 (以 100mm 為 100% 上限)
  const waterPct = Math.min(mm, 100);
  const waterEl = document.getElementById('rmWater');
  waterEl.style.height = '0%';
  waterEl.style.background = 'linear-gradient(180deg,' + lvlColor + '80,' + lvlColor + ')';
  setTimeout(() => {{ waterEl.style.height = waterPct + '%'; }}, 100);

  // 雨滴動畫 (依 mm 決定滴數，最多 30 個)
  const dropsEl = document.getElementById('rmDrops');
  dropsEl.innerHTML = '';
  const dropCount = Math.min(Math.max(Math.round(mm / 3), 3), 30);
  for (let i = 0; i < dropCount; i++) {{
    const drop = document.createElement('div');
    drop.className = 'rm-drop';
    drop.style.left = (5 + Math.random() * 90) + '%';
    drop.style.animationDuration = (0.8 + Math.random() * 0.9) + 's';
    drop.style.animationDelay = (Math.random() * 2) + 's';
    drop.style.fontSize = (14 + Math.random() * 10) + 'px';
    drop.textContent = '💧';
    dropsEl.appendChild(drop);
  }}

  // 生活對照
  const litersPerSqm = mm.toFixed(1);   // 1mm = 1 L/㎡
  const carWashes = (mm * 1 / 40).toFixed(1);   // 洗車一次約 40L/㎡
  const bathtubs = (mm * 1000 / 200 / 5).toFixed(1);   // 一甲=10000㎡；浴缸約 200L；...簡單版
  const cmps = [];

  cmps.push('📏 <strong>' + litersPerSqm + ' L/㎡</strong> — 每 1 m² 面積接住的水量');
  cmps.push('🌾 <strong>' + Math.round(mm * 10000 / 1000).toLocaleString() + ' 公噸/甲</strong> — 1 甲田地共承接的雨水');
  if (mm >= 1 && mm < 30) {{
    cmps.push('☕ 相當於 ' + Math.round(mm * 4) + ' 杯馬克杯的水（撒在 1 m² 內）');
    cmps.push('👟 一雙鞋子踩過會有淺淺水漬');
  }} else if (mm >= 30 && mm < 80) {{
    cmps.push('🪣 相當於 ' + (mm/10).toFixed(1) + ' 個提桶的水（撒在 1 m² 內）');
    cmps.push('🌱 果樹表層土 3-8 cm 濕潤，養分流失 10-30%');
    cmps.push('🚗 相當於自助洗車 ' + carWashes + ' 次的水量');
  }} else if (mm >= 80 && mm < 150) {{
    cmps.push('🛁 相當於 1 個標準浴缸的水量灌注在 2-3 m²');
    cmps.push('🚜 農路積水、機具進不去');
    cmps.push('⚠ 嚴重養分流失、粒肥泡爛');
  }} else {{
    cmps.push('🌊 <strong>災害級降雨</strong>！相當於瞬間傾倒');
    cmps.push('⛔ 田面積水、微生物轉厭氧、肥效歸零');
    cmps.push('🏠 都會區可能淹水、山區恐土石流');
  }}
  document.getElementById('rmCmps').innerHTML = cmps.map(c => '<li>' + c + '</li>').join('');

  // 對業務影響
  let impact;
  if (mm < 30) {{
    impact = '<span class="label">✅ 對施肥出貨無影響</span>可正常施肥、正常出貨；有機肥可保留水分緩釋。';
  }} else if (mm < 80) {{
    impact = '<span class="label">⚠ 當日施肥效果打折</span>養分流失 10-20%，建議雨後 2-3 天再補撒，或改在早晨施用避開午後陣雨。';
  }} else if (mm < 150) {{
    impact = '<span class="label">🚫 禁施 + 出貨延後</span>農路積水、機具進不易，粒狀肥泡爛。建議延後出貨 1-2 天。';
  }} else {{
    impact = '<span class="label">🚨 嚴重致災</span>田面積水、微生物厭氧、根系活性降。停止一切施肥出貨作業，等田面乾透（3-5 天）。';
  }}
  document.getElementById('rmImpact').innerHTML = impact;

  modal.classList.add('show');
}}
function closeRainModal() {{
  document.getElementById('rainModal').classList.remove('show');
}}
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') closeRainModal();
}});

// ============ 📆 本月降雨日曆 ============
(function initRainyCalendar() {{
  // 縣市 select（依 DATA 順序）
  const cs = document.getElementById('rainyCounty');
  DATA.forEach(c => {{
    const opt = document.createElement('option');
    opt.value = c.name;
    opt.textContent = c.name;
    if (c.name === '臺南市') opt.selected = true;   // 預設用戶主業務區
    cs.appendChild(opt);
  }});
  cs.addEventListener('change', renderRainyCalendar);
  document.getElementById('rainyThreshold').addEventListener('change', renderRainyCalendar);
  renderRainyCalendar();
}})();

function renderRainyCalendar() {{
  const countyName = document.getElementById('rainyCounty').value;
  const threshold = Number(document.getElementById('rainyThreshold').value);
  const c = DATA.find(x => x.name === countyName);
  if (!c || !c.daily) return;

  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = now.getMonth() + 1;
  const monthPrefix = yyyy + '-' + String(mm).padStart(2, '0') + '-';
  const todayStr = yyyy + '-' + String(mm).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
  const daysInMonth = new Date(yyyy, mm, 0).getDate();
  const firstDay = new Date(yyyy, mm - 1, 1).getDay();  // 0=週日

  // 統計本月符合條件的日期
  const matchDays = [];
  let totalRainDays = 0;  // 有雨的天數（不管閾值）
  let totalMm = 0;
  for (let d = 1; d <= daysInMonth; d++) {{
    const key = monthPrefix + String(d).padStart(2, '0');
    const val = c.daily[key];
    if (val === undefined) continue;
    if (val >= 1) totalRainDays++;
    totalMm += val;
    if (val >= threshold) matchDays.push({{d, val, date: key}});
  }}

  // 摘要（改 span 分項，避免深藍底吃掉字）
  const summary = document.getElementById('rainySummary');
  summary.innerHTML =
    '<span class="loc">📍 ' + countyName + '</span>' +
    '<span class="date">' + yyyy + ' 年 ' + mm + ' 月</span>' +
    '<span class="stat">本月累計 <strong>' + totalMm.toFixed(1) + '</strong><span class="unit">mm</span></span>' +
    '<span class="stat">有雨(≥1mm) <strong>' + totalRainDays + '</strong><span class="unit">天</span></span>' +
    '<span class="stat">達 ≥' + threshold + 'mm <strong>' + matchDays.length + '</strong><span class="unit">天</span></span>';

  // 月曆
  const cal = document.getElementById('rainyCalendar');
  cal.innerHTML = '';
  ['日','一','二','三','四','五','六'].forEach(w => {{
    const h = document.createElement('div');
    h.className = 'cal-head';
    h.textContent = w;
    cal.appendChild(h);
  }});
  // 填 firstDay 個空格
  for (let i = 0; i < firstDay; i++) {{
    const e = document.createElement('div');
    e.className = 'cal-cell empty';
    cal.appendChild(e);
  }}
  // 每天格子
  for (let d = 1; d <= daysInMonth; d++) {{
    const key = monthPrefix + String(d).padStart(2, '0');
    const val = c.daily[key];
    const wkIdx = new Date(yyyy, mm - 1, d).getDay();
    const wkChar = '日一二三四五六'[wkIdx];
    const cell = document.createElement('div');
    cell.className = 'cal-cell';
    const dHtml = '<div class="d">' + d + '<span class="wk">' + wkChar + '</span></div>';
    if (val === undefined) {{
      cell.className += ' empty';
      cell.innerHTML = dHtml + '<div class="mm" style="color:#ccc">-</div>';
    }} else if (val < 1) {{
      cell.className += ' dry';
      cell.innerHTML = dHtml + '<div class="mm">0</div>';
      cell.addEventListener('click', () => openRainModal(key, val, countyName, wkChar));
    }} else {{
      let lvl = 1;
      if (val >= 80) lvl = 5;
      else if (val >= 50) lvl = 4;
      else if (val >= 30) lvl = 3;
      else if (val >= 10) lvl = 2;
      cell.className += ' rain-' + lvl;
      cell.innerHTML = dHtml + '<div class="mm">' + val.toFixed(0) + '</div>';
      cell.addEventListener('click', () => openRainModal(key, val, countyName, wkChar));
    }}
    if (key === todayStr) cell.className += ' today';
    cal.appendChild(cell);
  }}

  // 日期列表
  const list = document.getElementById('rainyList');
  if (!matchDays.length) {{
    list.innerHTML = '<span style="color:#888">本月尚無達 ≥' + threshold + 'mm 的日期</span>';
  }} else {{
    list.innerHTML = matchDays.map(x =>
      '<span class="day">' + mm + '/' + x.d + '　<b>' + x.val.toFixed(1) + '</b> mm</span>'
    ).join('');
  }}
}}

// ============ 📽 投影模式 toggle ============
function toggleProjector() {{
  const on = !document.body.classList.contains('projector');
  document.body.classList.toggle('projector', on);
  localStorage.setItem('rain_projector', on ? '1' : '0');
  const btn = document.getElementById('projBtn');
  if (btn) {{
    btn.textContent = on ? '📽 一般模式' : '📽 投影模式';
    btn.style.background = on ? '#4a148c' : '#7b1fa2';
  }}
  // 若 Leaflet 地圖已初始化,通知它重算尺寸
  setTimeout(() => {{
    if (typeof map !== 'undefined' && map.invalidateSize) map.invalidateSize();
    if (typeof fcstMap !== 'undefined' && fcstMap.invalidateSize) fcstMap.invalidateSize();
    if (typeof townsMap !== 'undefined' && townsMap.invalidateSize) townsMap.invalidateSize();
  }}, 200);
}}
// 載入時還原狀態
if (localStorage.getItem('rain_projector') === '1') {{
  document.body.classList.add('projector');
  document.addEventListener('DOMContentLoaded', () => {{
    const btn = document.getElementById('projBtn');
    if (btn) {{
      btn.textContent = '📽 一般模式';
      btn.style.background = '#4a148c';
    }}
  }});
}}

// ============ 🔄 一鍵更新：JS 端直接呼叫 Open-Meteo 22 縣市 ============
async function refreshData() {{
  const btn = document.getElementById('refreshBtn');
  const timeSpan = document.getElementById('refreshTime');
  btn.disabled = true;
  btn.textContent = '⏳ 更新中... (0/22)';
  let done = 0;
  try {{
    // 平行 fetch 22 縣市
    const results = await Promise.all(DATA.map(async (c) => {{
      const url = 'https://api.open-meteo.com/v1/forecast?latitude=' + c.lat +
                  '&longitude=' + c.lon +
                  '&daily=precipitation_sum&timezone=Asia%2FTaipei' +
                  '&past_days=92&forecast_days=7';
      const r = await fetch(url);
      const j = await r.json();
      const daily = {{}};
      j.daily.time.forEach((t, i) => {{
        daily[t] = Math.round((j.daily.precipitation_sum[i] || 0) * 10) / 10;
      }});
      done++;
      btn.textContent = '⏳ 更新中... (' + done + '/22)';
      return {{name: c.name, daily}};
    }}));

    // 用新資料重算 today/month/quarter/forecast
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const todayStr = yyyy + '-' + mm + '-' + dd;
    const monthPrefix = yyyy + '-' + mm + '-';
    const q = Math.floor(now.getMonth() / 3);
    const qMonths = new Set([q*3+1, q*3+2, q*3+3]);

    results.forEach(({{name, daily}}) => {{
      const c = DATA.find(x => x.name === name);
      if (!c) return;
      c.daily = daily;
      c.today = daily[todayStr] || 0;
      let mo = 0, qr = 0;
      const fcast = [];
      Object.entries(daily).forEach(([d, val]) => {{
        if (d.startsWith(monthPrefix)) mo += val;
        const parts = d.split('-');
        if (parts[0] === String(yyyy) && qMonths.has(parseInt(parts[1]))) qr += val;
        if (d > todayStr) fcast.push({{d, mm: val}});
      }});
      c.month = Math.round(mo * 10) / 10;
      c.quarter = Math.round(qr * 10) / 10;
      c.forecast = fcast.sort((a, b) => a.d < b.d ? -1 : 1).slice(0, 7);
    }});

    // 更新 PERIODS 顯示（今日日期可能已跨天）
    PERIODS.today = todayStr + '（全日）';

    // 重繪主地圖
    const activeMode = document.querySelector('.toggle button.active').dataset.mode;
    if (activeMode === 'custom') {{
      applyCustom();
    }} else {{
      render(activeMode);
    }}

    // 重繪預測地圖（若日期變了要重建 tabs）
    const firstRow = DATA.find(x => x.forecast && x.forecast.length);
    if (firstRow) {{
      const newDates = firstRow.forecast.map(f => f.d);
      const changed = JSON.stringify(newDates) !== JSON.stringify(FORECAST_DATES);
      if (changed) {{
        FORECAST_DATES.length = 0;
        newDates.forEach(d => FORECAST_DATES.push(d));
        buildDayTabs();       // 重建單日 tabs
        buildCheckboxes();    // 重建複選 checkbox
      }}
      // 依當前模式重繪
      if (fcstMode === 'single') {{
        renderForecastMap([FORECAST_DATES[0]]);
      }} else if (fcstMode === '3day') {{
        renderForecastMap(FORECAST_DATES.slice(0, 3));
      }} else if (fcstMode === '7day') {{
        renderForecastMap(FORECAST_DATES.slice(0, 7));
      }} else if (fcstMode === 'custom') {{
        applyCustomForecast();
      }}
    }}

    // 重繪本月降雨日曆（新資料）
    renderRainyCalendar();

    const timeStr = now.toTimeString().slice(0, 5);
    btn.textContent = '✓ 已更新 ' + timeStr;
    timeSpan.textContent = '📡 資料時間：' + todayStr + ' ' + timeStr + '（前端即時更新）';
    setTimeout(() => {{
      btn.textContent = '🔄 立即更新雨量資料';
      btn.disabled = false;
    }}, 4000);
  }} catch (e) {{
    console.error(e);
    btn.textContent = '⚠ 更新失敗，請重試';
    setTimeout(() => {{
      btn.textContent = '🔄 立即更新雨量資料';
      btn.disabled = false;
    }}, 3000);
  }}
}}
</script>
</body></html>"""


def fetch_weather_news(max_items: int = 8) -> list:
    """從 Google News RSS 抓最近天氣相關新聞"""
    import feedparser
    keywords = "天氣預報 OR 豪雨 OR 颱風 OR 鋒面 OR 大雨特報"
    from urllib.parse import quote
    url = f"https://news.google.com/rss/search?q={quote(keywords)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        p = feedparser.parse(url)
        out = []
        for e in p.entries[:max_items]:
            title = getattr(e, "title", "").strip()
            link = getattr(e, "link", "").strip()
            pub = ""
            try:
                pub = time.strftime("%m/%d", e.published_parsed)
            except Exception:
                pass
            # 從 title 拆出媒體（Google News 格式："標題 - 媒體名"）
            source = ""
            if " - " in title:
                title, source = title.rsplit(" - ", 1)
            out.append({"title": title[:60], "link": link, "date": pub, "source": source})
        return out
    except Exception as e:
        print(f"[!] 抓天氣新聞失敗: {e}")
        return []


def analyze_pattern(rows: list) -> str:
    """依 4 大區未來 7 天平均降雨產生天氣分析描述（rule-based）"""
    # 4 區代表：北=桃園、中=臺中、南=臺南、東=花蓮（用 COUNTIES 中對應項）
    region_map = {"北": "桃園市", "中": "臺中市", "南": "臺南市", "東": "花蓮縣"}
    region_forecast_avg = {}
    for label, name in region_map.items():
        row = next((r for r in rows if r["name"] == name), None)
        if row and row.get("forecast"):
            mm_list = [f["mm"] for f in row["forecast"]]
            region_forecast_avg[label] = sum(mm_list) / len(mm_list) if mm_list else 0
    if not region_forecast_avg:
        return "（未取得預測資料）"

    avg_all = sum(region_forecast_avg.values()) / len(region_forecast_avg)
    n, m, s, e = (region_forecast_avg.get(k, 0) for k in "北中南東")

    parts = []
    # 整體降雨強度
    if avg_all < 3:
        parts.append("🌤 未來一週全台整體乾燥，日均降雨 < 3 mm，適合施肥出貨。")
    elif avg_all < 15:
        parts.append(f"⛅ 未來一週全台降雨溫和，日均約 {avg_all:.1f} mm，僅零星短陣雨。")
    elif avg_all < 40:
        parts.append(f"🌧 未來一週全台明顯降雨，日均約 {avg_all:.1f} mm，需留意出貨排程。")
    else:
        parts.append(f"⛈ 未來一週全台強降雨，日均 > {avg_all:.1f} mm，可能受颱風/鋒面/西南氣流影響。")

    # 空間 pattern 判讀
    if e > n and e > s and e > m and e > 20:
        parts.append("東部明顯偏多 → 可能為東北季風迎風面/颱風外圍。")
    if s > n and s > m and s > 20:
        parts.append("南部偏多 → 可能為西南氣流影響（夏季常見）。")
    if n > s and n > 20 and date.today().month in (10, 11, 12, 1, 2, 3):
        parts.append("北部偏多 → 東北季風/鋒面影響（秋冬春常見）。")
    if abs(n - s) < 5 and abs(m - e) < 5 and avg_all > 20:
        parts.append("全台分布均勻 → 可能為滯留鋒面/颱風籠罩。")

    # 業務提醒
    if avg_all > 30:
        parts.append("💡 業務建議：本週勿建議客戶施肥；出貨排程延後或改雨後補撒。")
    elif avg_all < 5:
        parts.append("💡 業務建議：本週適合積極洽談出貨，客戶田間可作業。")

    return " ".join(parts)


# 24 節氣 + 有機質肥料(基肥)出貨影響
# 有機質肥料 = 種植前 or 收成後所施的基肥，改良土壤、緩釋供養
# 主要客群：果樹、葉菜、茶葉、有機認證農戶
# 節氣時序排列（1 月放最前，符合陽曆），避免 tuple 比較跨年 bug
SOLAR_TERMS = [
    ((1, 6),  "小寒", "🥶", "深冬寒盛，果樹修剪後基肥期", [
        "🍎 果樹修剪後施基肥，儲備春發養分",
        "🥬 冬季葉菜末期，收成後整地基肥",
        "🍵 茶園休眠期，可施基肥改良土壤（茶區禁禽畜糞，用植物渣粕 5-13）",
        "💡 出貨建議：果樹客戶備冬基肥旺季，主動洽談"]),
    ((1, 20), "大寒", "🥶", "全年最冷，春耕備肥啟動", [
        "🍎 果樹冬肥收尾、修剪後基肥",
        "🥬 冬葉菜末收，準備春作整地",
        "💡 出貨建議：規劃春節後春耕備肥、掌握客戶備貨潮"]),
    ((2, 4),  "立春", "🌱", "春耕開始，一期稻整地基肥", [
        "🌾 南部一期稻整地施基肥（收成前 20 天禁施）",
        "🍎 果樹春肥期（芒果、荔枝、龍眼開花前基肥）",
        "🥬 春葉菜播種前整地基肥",
        "💡 出貨建議：南部果樹、水稻客戶備肥高峰"]),
    ((2, 19), "雨水", "💧", "春雨漸增，搶乾期施基肥", [
        "🌧 有機基肥吸附性強，比化肥耐雨，優先在雨前施用",
        "🍎 果樹謝花前基肥（增果穩果）",
        "💡 出貨建議：搶雨停 3-5 天空檔加速出貨"]),
    ((3, 5),  "驚蟄", "🐛", "萬物復甦，果樹春基肥旺季", [
        "🍎 中南部果樹（芒果、荔枝）結果前基肥",
        "🥬 春葉菜整地基肥",
        "🍵 高山茶春茶採收前基肥（禁禽畜糞、用植物渣粕）",
        "💡 出貨建議：中南部果樹客戶備肥高峰、茶區出貨"]),
    ((3, 20), "春分", "🌸", "晝夜平分，全區春肥沖刺", [
        "🍎 果樹持續施基肥（幼果期補養）",
        "🥬 春葉菜生長期",
        "💡 出貨建議：全區客戶備肥最旺，注意庫存"]),
    ((4, 5),  "清明", "🌿", "種瓜點豆，短期葉菜備肥", [
        "🍉 春夏瓜果（西瓜、鳳梨）播種前基肥",
        "🥬 短期葉菜整地基肥",
        "🍵 春茶採收前 30 天禁施（風味關鍵）",
        "💡 出貨建議：西瓜、鳳梨、芒果農戶備肥期"]),
    ((4, 20), "穀雨", "🌧", "雨生百穀，梅雨前搶出貨", [
        "🌾 一期稻抽穗前追肥期",
        "🍎 果樹幼果膨大前基肥",
        "💡 出貨建議：北中部注意梅雨影響，加速出貨"]),
    ((5, 5),  "立夏", "☀️", "夏季開始，果實膨大期", [
        "🍎 果樹幼果膨大期，施有機肥+鉀肥",
        "🥬 夏季葉菜播種前整地",
        "💡 出貨建議：果樹重要施肥週、庫存充足"]),
    ((5, 21), "小滿", "🌾", "採收前 30 天禁施基肥", [
        "🍎 荔枝、芒果採收前禁施有機肥（避免影響風味）",
        "🌾 一期稻結實期，準備收後整地",
        "💡 出貨建議：果樹客戶減量、備二期稻整地基肥"]),
    ((6, 6),  "芒種", "🌾", "梅雨尾聲，二期稻整地基肥", [
        "🌾 南部一期稻 6/10 起採收，收後整地施基肥",
        "🌾 二期稻整地基肥（收後 20 天內）",
        "🍎 荔枝採收期，收後施基肥恢復樹勢",
        "💡 出貨建議：南部水稻農戶收後整地基肥高峰"]),
    ((6, 21), "夏至", "🌞", "日長極致，二期稻播種備基肥", [
        "🌾 二期稻整地基肥期",
        "🍇 葡萄、龍眼採收前 30 天禁施",
        "💡 出貨建議：中南部水稻客戶備肥沖刺"]),
    ((7, 7),  "小暑", "🥵", "高溫多雨，清晨出貨時段", [
        "🌾 二期稻分蘗期（追肥為主，非基肥重點）",
        "🍍 鳳梨採收期",
        "☝ 高溫下有機肥發酵快，慎選出貨/儲存",
        "💡 出貨建議：清晨傍晚出貨、避午後雷雨"]),
    ((7, 23), "大暑", "🔥", "極熱期，秋作準備期", [
        "🍎 秋作果樹（釋迦、火龍果）補養基肥",
        "🥬 秋葉菜播種前整地基肥開始",
        "💡 出貨建議：與客戶約清晨交貨、注意肥料倉溫"]),
    ((8, 8),  "立秋", "🍂", "秋涼將近，秋作基肥開始", [
        "🌾 二期稻抽穗結實（禁施基肥）",
        "🥬 秋葉菜整地基肥開始（種前基肥）",
        "🍎 秋作果樹（柚子、柑橘、蜜棗）膨大期，重要施肥",
        "💡 出貨建議：中南部秋作備肥、颱風季前調度庫存"]),
    ((8, 23), "處暑", "🌤", "暑氣漸消，秋葉菜整地基肥", [
        "🍎 柑橘、柚子膨大期補養",
        "🥬 秋葉菜整地基肥（種植前基肥重要）",
        "💡 出貨建議：果樹客戶進入重要施肥週"]),
    ((9, 8),  "白露", "🌫", "露水漸生，收成前減量", [
        "🍎 柚子採收前 30 天禁施基肥（麻豆文旦重要）",
        "🍵 秋茶採收後施基肥恢復茶樹",
        "💡 出貨建議：茶葉客戶秋肥期、水稻收成前減量"]),
    ((9, 23), "秋分", "🍁", "秋收開始，收後基肥期", [
        "🌾 中部二期稻開始收成，收後整地基肥",
        "🍎 麻豆文旦採收期",
        "💡 出貨建議：麻豆、水稻客戶收後整地基肥"]),
    ((10, 8), "寒露", "❄️", "寒氣漸生，二期稻收後基肥", [
        "🌾 二期稻收成中，收後整地基肥旺季",
        "🍊 柑橘採收前禁施",
        "🥬 冬季葉菜（高麗菜、大白菜）整地基肥",
        "💡 出貨建議：水稻收後基肥旺季全面啟動"]),
    ((10, 23),"霜降", "🌨", "秋末冬作備肥", [
        "🌾 二期稻收成後整地基肥",
        "🍎 果樹採收後施冬基肥（重要！儲備春發養分）",
        "🥬 冬葉菜生長期",
        "💡 出貨建議：冬作備肥高峰、果樹採收後施基肥"]),
    ((11, 7), "立冬", "🍂", "果樹冬基肥旺季（果農重點）", [
        "🍎 果樹採收後施冬基肥（1 年 1 次最重要施肥）",
        "🥬 冬葉菜生長期",
        "🌾 休耕田整地基肥",
        "💡 出貨建議：果樹冬肥高峰，客戶備貨最熱烈"]),
    ((11, 22),"小雪", "❄️", "冬肥沖刺，注意連日雨", [
        "🍎 柑橘、柚子採收後施冬基肥",
        "🥬 冬葉菜生長期",
        "💡 出貨建議：冬肥沖刺、注意北部東北季風雨季"]),
    ((12, 7), "大雪", "☃️", "深冬時節，年終備肥期", [
        "🍎 果樹冬肥收尾期",
        "🥬 冬葉菜（結球期）追肥",
        "💡 出貨建議：年底衝業績、規劃明年春耕客戶"]),
    ((12, 22),"冬至", "🥟", "冬至陽生，蓄勢年後", [
        "🍎 果樹修剪期，修剪後施基肥",
        "🥬 冬葉菜採收前",
        "💡 出貨建議：年關前最後出貨機會、規劃春節後備貨"]),
]


def _current_solar_term(today: date):
    """回傳 (name, emoji, hint, details_list) — 找最近一個已過的節氣
    (SOLAR_TERMS 已按時序排列，避免跨年 tuple 比較 bug)"""
    md = (today.month, today.day)
    matched = SOLAR_TERMS[0]  # fallback = 小寒
    for term in SOLAR_TERMS:
        if term[0] <= md:
            matched = term
    return matched[1], matched[2], matched[3], matched[4]


# 台灣主要作物基肥施用庫（碩成有機質肥料業務決策用）— 90+ 種
# 欄位：類別、名稱、emoji、基肥適用月份、主要地區、每甲用量 kg、使用機率(高中低)、備註
CROPS_DB = [
    # ===== 果樹（熱帶）=====
    ("果樹", "芒果", "🥭", [11,12,1,2], ["南部","中部"], 1500, "高", "採收前30天禁施"),
    ("果樹", "愛文芒果", "🥭", [11,12,1,2], ["南部"], 1800, "高", "玉井、南化、六龜"),
    ("果樹", "荔枝", "🍒", [10,11,12], ["中部","南部"], 1500, "高", "6月採收前禁施"),
    ("果樹", "龍眼", "🍯", [11,12,1], ["南部","中部"], 1200, "中", ""),
    ("果樹", "香蕉", "🍌", [3,4,5,9,10], ["南部","中部"], 2500, "高", "旗山、集集"),
    ("果樹", "鳳梨", "🍍", [2,3,10,11], ["南部","中部"], 1800, "高", "民雄、大樹"),
    ("果樹", "木瓜", "🥭", [3,4,9,10], ["南部"], 2000, "中", ""),
    ("果樹", "蓮霧", "🌸", [5,6,7], ["南部"], 1500, "中", "屏東林邊"),
    ("果樹", "番石榴", "🥝", [3,4,10,11], ["中部","南部"], 2000, "高", "燕巢、社頭"),
    ("果樹", "酪梨", "🥑", [11,12,1], ["中部","南部"], 1200, "中", "大內"),
    ("果樹", "火龍果", "🐉", [3,4,10,11], ["南部","中部"], 1800, "高", "彰化"),
    ("果樹", "釋迦", "🍏", [3,4,9,10], ["東部"], 2000, "中", "台東主力"),
    ("果樹", "鳳梨釋迦", "🍏", [3,4,9,10], ["東部"], 2000, "中", "台東卑南"),
    ("果樹", "百香果", "💜", [3,4,9,10], ["南部","東部"], 1500, "中", "埔里"),
    ("果樹", "楊桃", "⭐", [3,4,9,10], ["中部","南部"], 1200, "中", "彰化"),
    ("果樹", "枇杷", "🟡", [10,11,12], ["中部"], 1500, "中", "太平、東勢"),
    ("果樹", "紅龍果", "🐉", [3,4,10,11], ["南部","中部"], 1800, "高", ""),
    ("果樹", "楊梅", "🍒", [3,4], ["北部"], 1200, "低", ""),
    # ===== 果樹（柑橘/溫帶）=====
    ("果樹", "椪柑", "🍊", [11,12,1], ["中部"], 1500, "高", "採收前30天禁施"),
    ("果樹", "桶柑", "🍊", [11,12,1], ["中部","北部"], 1500, "中", ""),
    ("果樹", "麻豆文旦", "🍋", [11,12,1], ["南部"], 1500, "高", "麻豆主產、中秋禮盒"),
    ("果樹", "白柚", "🍋", [11,12,1], ["南部"], 1500, "中", "麻豆、鹿谷"),
    ("果樹", "檸檬", "🍋", [10,11,12,1], ["南部"], 1500, "高", "屏東九如"),
    ("果樹", "金桔", "🍊", [10,11,12], ["北部"], 1200, "中", "宜蘭礁溪"),
    ("果樹", "橘子", "🍊", [11,12,1], ["中部"], 1500, "中", ""),
    ("果樹", "水梨(高接梨)", "🍐", [10,11,12], ["中部"], 1500, "中", "東勢、卓蘭"),
    ("果樹", "水蜜桃", "🍑", [11,12,1], ["中部","北部"], 1500, "中", "拉拉山、梨山"),
    ("果樹", "李子", "🌰", [11,12,1], ["中部"], 1200, "中", ""),
    ("果樹", "蘋果", "🍎", [11,12,1], ["中部"], 1500, "低", "梨山高山"),
    ("果樹", "葡萄", "🍇", [3,4,9,10], ["中部"], 1500, "中", "大村、卓蘭"),
    ("果樹", "蜜棗", "🌰", [6,7,8], ["南部"], 1500, "中", "燕巢"),
    ("果樹", "柿子", "🍊", [10,11,12], ["中部"], 1500, "中", "番路"),
    ("果樹", "草莓", "🍓", [8,9,10], ["中部"], 1500, "高", "大湖、獅潭"),
    ("果樹", "藍莓", "🫐", [10,11,12], ["中部"], 1200, "低", ""),
    ("果樹", "無花果", "🫒", [3,4,10,11], ["中部","南部"], 1200, "低", ""),
    # ===== 葉菜 =====
    ("葉菜", "高麗菜", "🥬", [8,9,10,11], ["中部","南部"], 1500, "高", "梨山冬季採收"),
    ("葉菜", "結球白菜", "🥬", [9,10,11], ["中部","南部"], 1200, "高", ""),
    ("葉菜", "青江菜", "🥬", [2,3,9,10], ["南部","北部"], 800, "中", "短期作物"),
    ("葉菜", "菠菜", "🌿", [10,11,12], ["中部","南部"], 800, "中", ""),
    ("葉菜", "萵苣(大陸妹)", "🥗", [9,10,11], ["中部"], 1000, "高", ""),
    ("葉菜", "地瓜葉", "🍃", [3,4,5,9,10], ["南部"], 1000, "高", "多期採收"),
    ("葉菜", "空心菜", "🌱", [3,4,5,6,7], ["南部"], 800, "中", "短期作物"),
    ("葉菜", "小白菜", "🌿", [2,3,9,10,11], ["南部","中部"], 800, "高", "常年供應"),
    ("葉菜", "A菜", "🌿", [2,3,9,10,11], ["南部","中部"], 800, "中", ""),
    ("葉菜", "油菜", "🌼", [2,3,9,10,11], ["南部"], 800, "中", ""),
    ("葉菜", "芥藍", "🥬", [9,10,11], ["中部","南部"], 900, "中", ""),
    ("葉菜", "韭菜", "🌿", [3,4,9,10], ["中部","南部"], 1000, "中", "溪湖"),
    ("葉菜", "莧菜", "🌿", [3,4,5,6,7,8], ["南部"], 800, "中", ""),
    ("葉菜", "山蘇", "🌿", [3,4,9,10], ["東部"], 1000, "中", ""),
    ("葉菜", "皇宮菜", "🌿", [4,5,9,10], ["南部"], 800, "中", ""),
    # ===== 瓜果類 =====
    ("瓜果類", "西瓜", "🍉", [2,3,4], ["南部","中部"], 2000, "高", "麻豆、崙背"),
    ("瓜果類", "洋香瓜", "🍈", [2,3,9,10], ["南部"], 1800, "中", ""),
    ("瓜果類", "美濃瓜", "🍈", [2,3,9,10], ["南部"], 1600, "中", "美濃"),
    ("瓜果類", "番茄", "🍅", [9,10,11], ["南部","中部"], 1500, "高", "美濃、路竹"),
    ("瓜果類", "小番茄", "🍅", [9,10,11], ["南部"], 1500, "高", ""),
    ("瓜果類", "辣椒", "🌶️", [2,3,9,10], ["南部"], 1200, "中", ""),
    ("瓜果類", "彩椒", "🫑", [9,10,11], ["中部","南部"], 1500, "中", ""),
    ("瓜果類", "茄子", "🍆", [3,4,9,10], ["南部"], 1500, "中", ""),
    ("瓜果類", "絲瓜", "🥒", [3,4,5,9,10], ["南部"], 1500, "中", ""),
    ("瓜果類", "苦瓜", "🥒", [3,4,5,9,10], ["南部"], 1500, "中", ""),
    ("瓜果類", "小黃瓜", "🥒", [3,4,9,10], ["南部","中部"], 1200, "中", ""),
    ("瓜果類", "南瓜", "🎃", [2,3,9,10], ["東部","南部"], 1500, "中", ""),
    ("瓜果類", "冬瓜", "🥒", [2,3], ["中部"], 1500, "中", ""),
    ("瓜果類", "櫛瓜", "🥒", [9,10,11], ["南部"], 1500, "中", ""),
    ("瓜果類", "秋葵", "🌿", [3,4,9], ["南部"], 1200, "中", ""),
    ("瓜果類", "四季豆", "🌿", [3,4,9,10], ["中部"], 1000, "中", ""),
    ("瓜果類", "毛豆", "🌿", [3,4,9,10], ["南部"], 1200, "中", "屏東出口"),
    ("瓜果類", "甜玉米", "🌽", [2,3,9,10], ["南部","中部"], 1500, "中", ""),
    ("瓜果類", "糯玉米", "🌽", [2,3,9,10], ["南部"], 1500, "中", ""),
    # ===== 根莖類 =====
    ("根莖類", "洋蔥", "🧅", [9,10,11], ["南部"], 1800, "高", "屏東為主"),
    ("根莖類", "蒜頭", "🧄", [9,10,11], ["中部","南部"], 1200, "高", "雲林主產"),
    ("根莖類", "青蔥", "🌿", [3,4,9,10], ["北部","中部"], 1500, "高", "三星、宜蘭"),
    ("根莖類", "馬鈴薯", "🥔", [10,11,12], ["中部"], 2000, "中", ""),
    ("根莖類", "白蘿蔔", "⚪", [9,10,11], ["南部","中部"], 1000, "中", ""),
    ("根莖類", "紅蘿蔔", "🥕", [9,10,11], ["南部"], 1200, "中", "將軍、佳里"),
    ("根莖類", "地瓜", "🍠", [3,4,8,9], ["南部","中部"], 1500, "高", "金山、雲林"),
    ("根莖類", "薑", "🫚", [2,3,4], ["中部","南部"], 1800, "中", "南投"),
    ("根莖類", "山藥", "🌱", [2,3,4], ["北部"], 1500, "低", "淡水、雙溪"),
    ("根莖類", "芋頭", "🥔", [2,3,4], ["中部"], 1500, "中", "大甲"),
    ("根莖類", "蓮藕", "🪷", [2,3], ["中部","南部"], 1200, "低", "白河"),
    ("根莖類", "菱角", "🌰", [7,8,9], ["南部"], 1200, "低", "官田"),
    ("根莖類", "竹筍(綠竹/麻竹)", "🎋", [3,4,10,11], ["北部","中部"], 1500, "中", "五峰、鹿谷"),
    # ===== 茶葉 =====
    ("茶葉", "高山茶 (>1000m)", "🍵", [1,2,10,11], ["中部"], 1500, "高", "禁禽畜糞、用植物渣粕 5-13"),
    ("茶葉", "阿里山烏龍", "🍵", [1,2,10,11], ["中部"], 1500, "高", "禁禽畜糞"),
    ("茶葉", "包種茶", "🍵", [1,2,10,11], ["北部"], 1500, "中", "坪林、深坑"),
    ("茶葉", "金萱", "🍵", [1,2,10,11], ["中部"], 1500, "中", ""),
    ("茶葉", "凍頂烏龍", "🍵", [1,2,10,11], ["中部"], 1500, "高", "鹿谷"),
    ("茶葉", "鐵觀音", "🍵", [1,2,10,11], ["北部"], 1500, "中", "木柵"),
    ("茶葉", "紅茶", "🍵", [1,2,10,11], ["中部"], 1500, "中", "魚池、日月潭"),
    ("茶葉", "東方美人", "🍵", [1,2,10,11], ["北部"], 1500, "中", "北埔"),
    # ===== 花卉 =====
    ("花卉", "蘭花(蝴蝶蘭)", "🌸", [3,4,9,10], ["南部"], 1200, "中", "溫室"),
    ("花卉", "菊花", "🌼", [3,4,9,10], ["中部"], 1500, "中", "田尾、埔里"),
    ("花卉", "玫瑰", "🌹", [3,4,9,10], ["中部"], 1500, "中", ""),
    ("花卉", "百合", "🌸", [3,4,9,10], ["東部"], 1200, "中", ""),
    ("花卉", "劍蘭/唐菖蒲", "🌸", [3,4,9,10], ["南部"], 1200, "中", ""),
    ("花卉", "桃花心木", "🌳", [3,4], ["南部"], 800, "低", ""),
    # ===== 雜糧 / 特作 =====
    ("雜糧", "花生", "🥜", [3,4,8,9], ["中部","南部"], 1000, "中", "雲林元長"),
    ("雜糧", "紅豆", "🫘", [10,11], ["南部"], 800, "中", "高雄美濃"),
    ("雜糧", "綠豆", "🫘", [3,4,9], ["南部"], 800, "中", ""),
    ("雜糧", "黃豆(有機大豆)", "🫘", [2,3,9,10], ["南部","中部"], 1000, "中", "有機認證熱門"),
    ("雜糧", "咖啡", "☕", [2,3,10,11], ["南部","東部"], 1500, "中", "古坑、雲林"),
    ("雜糧", "檳榔", "🌴", [3,4,9,10], ["中部","東部"], 1200, "低", "南投"),
    # ===== 菇類 =====
    ("菇類", "香菇/木耳(段木)", "🍄", [3,4,9,10], ["中部"], 800, "低", "南投、埔里"),
]


# 台灣特色農產鄉鎮分布（業務決策用）
# 欄位：縣市, 鄉鎮, lat, lon, 主力作物列表, 業務建議 / 別名
TOWN_CROPS = [
    # ===== 北部 =====
    ("新北市", "淡水區",   25.17, 121.44, ["山藥"], "淡水山藥產區"),
    ("新北市", "三芝區",   25.26, 121.50, ["茭白筍","山藥"], ""),
    ("新北市", "石門區",   25.29, 121.57, ["石花菜","綠竹筍"], ""),
    ("新北市", "金山區",   25.22, 121.64, ["地瓜","茭白筍"], "跳石地瓜"),
    ("新北市", "五股區",   25.08, 121.44, ["綠竹筍"], ""),
    ("新北市", "坪林區",   24.94, 121.71, ["包種茶"], "北部茶區、禁禽畜糞"),
    ("宜蘭縣", "三星鄉",   24.67, 121.65, ["青蔥","銀柳"], "三星蔥全國聞名"),
    ("宜蘭縣", "礁溪鄉",   24.83, 121.77, ["金桔","溫泉蔬菜"], ""),
    ("宜蘭縣", "冬山鄉",   24.63, 121.79, ["文旦柚","茶葉"], ""),
    ("桃園市", "大溪區",   24.88, 121.29, ["韭菜","水稻"], ""),
    ("桃園市", "復興區",   24.82, 121.35, ["水蜜桃","綠竹筍"], "拉拉山高冷"),
    ("新竹縣", "北埔鄉",   24.70, 121.05, ["東方美人茶","柿子"], "膨風茶"),
    ("新竹縣", "尖石鄉",   24.71, 121.19, ["水蜜桃","高山蔬菜"], ""),
    ("苗栗縣", "大湖鄉",   24.42, 120.87, ["草莓"], "全國草莓之鄉"),
    ("苗栗縣", "獅潭鄉",   24.53, 120.90, ["草莓","橘子"], ""),
    ("苗栗縣", "卓蘭鎮",   24.30, 120.83, ["葡萄","高接梨"], "水果之鄉"),
    ("苗栗縣", "公館鄉",   24.50, 120.83, ["紅棗","福菜"], ""),
    # ===== 中部 =====
    ("臺中市", "大甲區",   24.35, 120.62, ["芋頭"], "大甲芋頭酥"),
    ("臺中市", "東勢區",   24.26, 120.83, ["水梨","高接梨","柑橘"], ""),
    ("臺中市", "新社區",   24.24, 120.81, ["香菇","蘭花","水梨"], ""),
    ("臺中市", "石岡區",   24.27, 120.79, ["水梨","柿餅"], ""),
    ("臺中市", "太平區",   24.13, 120.72, ["枇杷","龍眼"], ""),
    ("臺中市", "外埔區",   24.33, 120.65, ["葡萄","火龍果"], ""),
    ("臺中市", "梨山",     24.26, 121.25, ["高山蘋果","高山高麗菜","水蜜桃"], "海拔 2000m 高冷"),
    ("彰化縣", "田尾鄉",   23.90, 120.53, ["菊花","玫瑰","蘭花"], "花卉之鄉"),
    ("彰化縣", "大村鄉",   23.99, 120.55, ["葡萄"], "巨峰葡萄"),
    ("彰化縣", "溪湖鎮",   23.96, 120.48, ["葡萄","韭菜"], ""),
    ("彰化縣", "社頭鄉",   23.90, 120.58, ["芭樂"], ""),
    ("彰化縣", "二林鎮",   23.90, 120.38, ["葡萄(釀酒)","蕎麥"], ""),
    ("南投縣", "埔里鎮",   23.97, 120.97, ["茭白筍","百香果","蘭花","香菇"], "美人腿"),
    ("南投縣", "信義鄉",   23.70, 120.85, ["梅子","茶葉","蔬菜"], ""),
    ("南投縣", "鹿谷鄉",   23.75, 120.75, ["凍頂烏龍","孟宗竹筍"], "凍頂烏龍茶"),
    ("南投縣", "竹山鎮",   23.76, 120.68, ["竹筍","地瓜","茶葉"], "紫南宮"),
    ("南投縣", "水里鄉",   23.81, 120.86, ["梅子","荔枝","龍眼"], ""),
    ("南投縣", "魚池鄉",   23.87, 120.94, ["紅茶","茭白筍","蘭花"], "日月潭紅茶"),
    ("南投縣", "國姓鄉",   24.00, 120.86, ["咖啡","草莓","檳榔"], ""),
    ("南投縣", "仁愛鄉",   24.03, 121.14, ["高麗菜","水蜜桃","茶葉"], "清境、廬山"),
    ("雲林縣", "古坑鄉",   23.65, 120.55, ["咖啡","柑橘","茶葉"], "台灣咖啡首選"),
    ("雲林縣", "斗六市",   23.71, 120.55, ["文旦柚","水稻"], ""),
    ("雲林縣", "西螺鎮",   23.80, 120.46, ["醬油","蔬菜"], "台灣蔬菜集散"),
    ("雲林縣", "元長鄉",   23.65, 120.32, ["花生"], "花生產區"),
    ("雲林縣", "麥寮鄉",   23.75, 120.25, ["文蛤","蒜頭"], ""),
    ("雲林縣", "口湖鄉",   23.58, 120.19, ["文蛤","烏魚"], ""),
    # ===== 南部 =====
    ("嘉義縣", "民雄鄉",   23.55, 120.43, ["鳳梨","水稻"], "民雄鳳梨"),
    ("嘉義縣", "太保市",   23.46, 120.34, ["水稻","蔬菜"], ""),
    ("嘉義縣", "梅山鄉",   23.58, 120.65, ["茶葉","高山蔬菜"], "梅山高山茶"),
    ("嘉義縣", "阿里山鄉", 23.51, 120.80, ["阿里山烏龍茶","高山高麗菜"], "海拔 > 1000m 禁禽畜糞"),
    ("嘉義縣", "中埔鄉",   23.42, 120.53, ["蘭花","柑橘"], ""),
    ("嘉義縣", "番路鄉",   23.47, 120.55, ["柿子","茶葉"], ""),
    ("臺南市", "麻豆區",   23.18, 120.25, ["文旦柚","白柚"], "中秋文旦禮盒最大宗"),
    ("臺南市", "玉井區",   23.13, 120.46, ["愛文芒果","釋迦"], "台灣芒果之鄉"),
    ("臺南市", "楠西區",   23.18, 120.49, ["愛文芒果","龍眼"], "楠西山區芒果"),
    ("臺南市", "南化區",   23.10, 120.48, ["愛文芒果","龍眼"], "南化芒果"),
    ("臺南市", "官田區",   23.19, 120.32, ["菱角","水稻"], "官田菱角全台知名"),
    ("臺南市", "白河區",   23.35, 120.42, ["蓮花","蓮藕","文旦"], "蓮花節"),
    ("臺南市", "後壁區",   23.37, 120.36, ["水稻(有機米)","蘭花"], "冠軍米、有機認證"),
    ("臺南市", "新化區",   23.04, 120.31, ["鳳梨","蘭花"], ""),
    ("臺南市", "大內區",   23.14, 120.35, ["酪梨","芒果","柚子"], "酪梨之鄉"),
    ("臺南市", "山上區",   23.10, 120.35, ["水果","蔬菜"], ""),
    ("臺南市", "將軍區",   23.20, 120.10, ["紅蘿蔔","蘆筍"], "紅蘿蔔產區"),
    ("臺南市", "佳里區",   23.16, 120.18, ["紅蘿蔔","牛蒡"], ""),
    ("臺南市", "六甲區",   23.23, 120.35, ["水稻","竹筍"], ""),
    ("高雄市", "旗山區",   22.89, 120.48, ["香蕉"], "台灣香蕉王國"),
    ("高雄市", "美濃區",   22.90, 120.55, ["白玉蘿蔔","小番茄","毛豆","客家蔬菜"], "美濃野蓮"),
    ("高雄市", "六龜區",   22.99, 120.63, ["愛文芒果","蓮霧","蜂蜜"], "六龜芒果"),
    ("高雄市", "燕巢區",   22.79, 120.36, ["芭樂","棗子","西施蜜柚"], "西施芭樂"),
    ("高雄市", "阿蓮區",   22.88, 120.33, ["芭樂","棗子"], ""),
    ("高雄市", "大樹區",   22.69, 120.42, ["鳳梨","荔枝","玉荷包"], "玉荷包荔枝"),
    ("高雄市", "路竹區",   22.85, 120.26, ["小番茄","蕃茄"], ""),
    ("高雄市", "岡山區",   22.80, 120.30, ["羊肉","蜂蜜"], ""),
    ("高雄市", "杉林區",   22.98, 120.53, ["絲瓜","梅子"], ""),
    ("屏東縣", "林邊鄉",   22.44, 120.51, ["黑珍珠蓮霧","石斑"], "黑珍珠蓮霧"),
    ("屏東縣", "九如鄉",   22.74, 120.49, ["檸檬","蓮霧","絲瓜"], "檸檬產區"),
    ("屏東縣", "萬丹鄉",   22.59, 120.48, ["紅豆","牛蒡"], "萬丹紅豆"),
    ("屏東縣", "里港鄉",   22.78, 120.49, ["毛豆","蔬菜"], "毛豆出口日本"),
    ("屏東縣", "枋山鄉",   22.26, 120.66, ["愛文芒果","洋蔥"], "枋山洋蔥"),
    ("屏東縣", "車城鄉",   22.07, 120.71, ["洋蔥","蔥"], "車城洋蔥"),
    ("屏東縣", "恆春鎮",   22.00, 120.75, ["洋蔥","瓊麻"], "恆春洋蔥"),
    ("屏東縣", "內埔鄉",   22.61, 120.57, ["檳榔","蓮霧","可可"], "屏東可可"),
    ("屏東縣", "萬巒鄉",   22.57, 120.55, ["豬腳","檳榔"], ""),
    ("屏東縣", "潮州鎮",   22.55, 120.54, ["蓮霧","西瓜"], ""),
    # ===== 東部 =====
    ("花蓮縣", "壽豐鄉",   23.86, 121.51, ["西瓜","有機蔬菜"], "有機農業重鎮"),
    ("花蓮縣", "光復鄉",   23.66, 121.42, ["水稻(有機)","甘藷"], ""),
    ("花蓮縣", "瑞穗鄉",   23.50, 121.38, ["文旦柚","茶葉"], "瑞穗文旦、蜜香紅茶"),
    ("花蓮縣", "玉里鎮",   23.34, 121.32, ["水稻","文旦"], "玉里米"),
    ("花蓮縣", "富里鄉",   23.19, 121.25, ["水稻(有機)"], "富里米、有機"),
    ("臺東縣", "卑南鄉",   22.79, 121.08, ["鳳梨釋迦","釋迦"], "卑南釋迦"),
    ("臺東縣", "太麻里", 22.61, 121.00, ["洛神花","釋迦","金針"], "太麻里金針花"),
    ("臺東縣", "關山鎮",   23.05, 121.16, ["水稻(有機)"], "關山米"),
    ("臺東縣", "池上鄉",   23.12, 121.22, ["水稻(有機)"], "池上米"),
    ("臺東縣", "鹿野鄉",   22.91, 121.13, ["茶葉","鳳梨"], "紅烏龍"),
]


def _detect_typhoon_alert(news_items: list = None) -> bool:
    """判斷是否颱風警戒中 — 只採信 CWA 官方警特報 API (W-C0033-001)
    避免歷史新聞或年度統計文章誤觸。無 key 或 API 掛掉時 → 不啟動 (safe fallback)"""
    key = os.environ.get("CWA_API_KEY", "").strip()
    if not key:
        return False
    try:
        url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0033-001"
        r = requests.get(url, params={"Authorization": key}, timeout=10)
        r.raise_for_status()
        data = r.json()
        for loc in data.get("records", {}).get("location", []):
            hazards = loc.get("hazardConditions", {}).get("hazards", [])
            for h in hazards:
                phenomena = h.get("info", {}).get("phenomena", "")
                if "颱風" in phenomena:
                    return True
        return False
    except Exception as e:
        print(f"[!] CWA typhoon check 失敗（不啟動警戒）: {e}")
        return False


def _mascot_mood(rows: list) -> tuple:
    """依 4 大區未來 7 天平均降雨決定吉祥物表情 + 台詞
    回傳 (emoji, mood_class, [台詞1, 台詞2, ...])"""
    region_map = {"北": "桃園市", "中": "臺中市", "南": "臺南市", "東": "花蓮縣"}
    avgs = []
    for _, name in region_map.items():
        row = next((r for r in rows if r["name"] == name), None)
        if row and row.get("forecast"):
            mms = [f["mm"] for f in row["forecast"]]
            avgs.append(sum(mms) / len(mms) if mms else 0)
    if not avgs:
        return ("🐔", "normal", ["資料抓取中..."])
    avg = sum(avgs) / len(avgs)

    if avg < 5:
        return ("😎", "sunny", [
            "☀ 本週好天氣！可以積極推銷肥料囉～",
            "客戶田面乾爽，正是出貨黃金期！",
            "記得跟客戶說：\"這週訂單快下，避免下週下雨影響\"",
            "業務員精神！去拜訪客戶啦～",
        ])
    elif avg < 15:
        return ("😊", "mild", [
            "🌤 天氣穩定，一切正常運作",
            "小雨無妨，選晴天出貨即可",
            "記得檢查客戶備肥狀況",
            "適合排定觀摩會、農民座談",
        ])
    elif avg < 40:
        return ("😕", "rainy", [
            "🌧 本週雨多，出貨要看空檔",
            "建議提前跟客戶協調交貨日",
            "農路可能濕滑，注意工安",
            "施肥時機要避開雨後 24 小時",
        ])
    else:
        return ("😱", "storm", [
            "⛈ 豪雨警戒！本週禁施建議",
            "客戶田面積水，暫緩出貨",
            "把握雨停空檔快速補撒",
            "颱風前準備：確認肥料倉庫防水",
        ])


def build_html(rows: list, today: date, history_stats: dict = None, fert_rankings: dict = None) -> str:
    from datetime import timedelta
    import base64
    quarter = (today.month - 1) // 3 + 1

    # 讀碩成 logo → base64 embed (訂貨/折讓平台的官方 logo)
    shuocheng_logo_b64 = ""
    logo_path = Path(__file__).resolve().parent / "shuocheng_logo.png"
    if logo_path.exists():
        try:
            with open(logo_path, "rb") as f:
                shuocheng_logo_b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[Rainfall Map] 讀碩成 logo 失敗: {e}")
    # 讀大成官方 logo (從 dachan.com 抓的)
    dachan_logo_b64 = ""
    dc_path = Path(__file__).resolve().parent / "dachan_logo.png"
    if dc_path.exists():
        try:
            with open(dc_path, "rb") as f:
                dachan_logo_b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[Rainfall Map] 讀大成 logo 失敗: {e}")
    # 讀作者大頭照 (訂貨平台同一張)
    author_avatar_b64 = ""
    av_path = Path(__file__).resolve().parent / "author_avatar.png"
    if av_path.exists():
        try:
            with open(av_path, "rb") as f:
                author_avatar_b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"[Rainfall Map] 讀大頭照失敗: {e}")

    # 算各 mode 的統計期間
    month_start = date(today.year, today.month, 1)
    month_days = (today - month_start).days + 1
    q_start_month = (quarter - 1) * 3 + 1
    quarter_start = date(today.year, q_start_month, 1)
    quarter_days = (today - quarter_start).days + 1

    # 自訂區間可選日期範圍 = 今天往前 92 天（Open-Meteo past_days 上限）
    data_start = (today - timedelta(days=91)).isoformat()

    periods = {
        "today": f"{today.isoformat()}（全日）",
        "month": f"{month_start.isoformat()} ~ {today.isoformat()}（共 {month_days} 天）",
        "quarter": f"{quarter_start.isoformat()} ~ {today.isoformat()}（Q{quarter}，共 {quarter_days} 天）",
        "custom": f"{data_start} ~ {today.isoformat()}（自訂區間，預設為過去 92 天）",
    }

    legend_rows = "\n  ".join(
        f'<div class="legend-row"><div class="legend-swatch" style="background:{c}"></div>'
        f'<span style="color:#1f3a2e;font-weight:700;width:60px">{label}</span>'
        f'<span style="color:#555">{lo}–{hi if hi < 9999 else "∞"} mm</span></div>'
        for lo, hi, c, label in COLOR_BANDS
    )

    # === 未來 7 天預測 — 抽取日期列（第 1 個縣市的 forecast 當基準）===
    first_forecast = next((r["forecast"] for r in rows if r.get("forecast")), [])
    forecast_dates = [f["d"] for f in first_forecast[:7]]
    # === 天氣分析 rule-based 文字 ===
    analysis_text = analyze_pattern(rows)
    # === 相關新聞 ===
    news_items = fetch_weather_news(max_items=8)
    news_html = "\n    ".join(
        f'<li><a href="{n["link"]}" target="_blank" rel="noopener">{n["title"]}</a>'
        f'<span class="meta">{n.get("source","")}{" · " + n["date"] if n.get("date") else ""}</span></li>'
        for n in news_items
    ) or '<li style="color:#888">（本次未抓到相關新聞）</li>'

    # 節氣 + 颱風警戒 + 吉祥物
    term_name, term_emoji, term_hint, term_details = _current_solar_term(today)
    term_details_html = "\n    ".join(
        f'<li>{line}</li>' for line in term_details
    )
    typhoon_alert = _detect_typhoon_alert(news_items)
    mascot_emoji, mascot_mood, mascot_lines = _mascot_mood(rows)

    return HTML_TEMPLATE.format(
        today=today.isoformat(),
        quarter=quarter,
        data_start=data_start,
        data_json=json.dumps(rows, ensure_ascii=False),
        bands_json=json.dumps([[lo, hi, c, lbl] for lo, hi, c, lbl in COLOR_BANDS]),
        name_map_json=json.dumps(COUNTY_NAME_MAP, ensure_ascii=False),
        periods_json=json.dumps(periods, ensure_ascii=False),
        gen_time=time.strftime("%Y-%m-%d %H:%M"),
        legend_rows=legend_rows,
        forecast_dates_json=json.dumps(forecast_dates, ensure_ascii=False),
        analysis_text=analysis_text,
        news_html=news_html,
        term_name=term_name,
        term_emoji=term_emoji,
        term_hint=term_hint,
        term_details_html=term_details_html,
        typhoon_class=("typhoon-alert" if typhoon_alert else ""),
        typhoon_banner=(
            '<div class="typhoon-strip">🌀 <strong>颱風警戒中</strong>　'
            '業務區可能停工，請以中央氣象署為準　🌀</div>'
            if typhoon_alert else ""
        ),
        mascot_emoji=mascot_emoji,
        mascot_mood=mascot_mood,
        mascot_lines_json=json.dumps(mascot_lines, ensure_ascii=False),
        crops_json=json.dumps([
            {"cat": c[0], "name": c[1], "emoji": c[2], "months": c[3],
             "regions": c[4], "kgPerHa": c[5], "prob": c[6], "note": c[7]}
            for c in CROPS_DB
        ], ensure_ascii=False),
        towns_json=json.dumps([
            {"county": t[0], "town": t[1], "lat": t[2], "lon": t[3],
             "crops": t[4], "note": t[5]}
            for t in TOWN_CROPS
        ], ensure_ascii=False),
        history_json=json.dumps(history_stats or {}, ensure_ascii=False),
        shuocheng_logo_b64=shuocheng_logo_b64,
        dachan_logo_b64=dachan_logo_b64,
        author_avatar_b64=author_avatar_b64,
        sales_json=json.dumps(SALES_DATA, ensure_ascii=False),
        fert_rankings_json=json.dumps(fert_rankings or {}, ensure_ascii=False),
    )




def _fetch_cwa_recent_daily(county: str, verbose: bool = False) -> dict:
    """從 CWA CODIS 抓該縣市所有 CWB 主站的過去 365 天日雨量, 取多站 MAX
    回傳: {date_str: mm}"""
    import urllib.request, urllib.parse, http.cookiejar
    _ensure_stations(verbose=False)
    stations = COUNTY_CWA_STATIONS.get(county, [])
    if not stations:
        return {}

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    ua = "Mozilla/5.0"
    try:
        opener.open(urllib.request.Request("https://codis.cwa.gov.tw/StationData",
            headers={"User-Agent": ua}), timeout=15)
    except: return {}

    per_station_daily = []
    for stn_id, stn_name in stations:
        try:
            body = urllib.parse.urlencode({
                "stn_ID": stn_id, "stn_type": "cwb",
                "type": "report_month", "date": f"{date.today().isoformat()}",
            }).encode()
            req = urllib.request.Request("https://codis.cwa.gov.tw/api/station",
                data=body, method="POST",
                headers={"User-Agent": ua,
                         "Referer": "https://codis.cwa.gov.tw/StationData",
                         "Origin": "https://codis.cwa.gov.tw",
                         "Content-Type": "application/x-www-form-urlencoded",
                         "X-Requested-With": "XMLHttpRequest"})
            resp = opener.open(req, timeout=45)
            j = json.loads(resp.read().decode("utf-8"))
            if j.get("code") != 200: continue
            d_map = {}
            for row in j.get("data", []):
                for dt in row.get("dts", []):
                    ds = dt.get("DataDate", "")
                    if len(ds) < 10: continue
                    date_key = ds[:10]  # YYYY-MM-DD
                    p = dt.get("Precipitation") or {}
                    v = p.get("Accumulation")
                    if v is not None:
                        d_map[date_key] = float(v)
            if d_map:
                per_station_daily.append(d_map)
        except Exception as e:
            if verbose: print(f"  [CWA {stn_id}] {e}")
        time.sleep(0.2)

    if not per_station_daily:
        return {}
    # 每日多站取 MAX
    all_dates = set()
    for d in per_station_daily: all_dates.update(d.keys())
    merged = {}
    for dstr in all_dates:
        vals = [d.get(dstr) for d in per_station_daily if d.get(dstr) is not None]
        if vals: merged[dstr] = round(max(vals), 1)
    return merged


def collect_rows(verbose: bool = True) -> list:
    """抓 22 縣市 90 天雨量。混合資料源:
    - 過去+今日: CWA CODIS 官方觀測 (含颱風強降雨真實值)
    - 未來 7 天: Open-Meteo Forecast (CWA 免費 API 無未來預測)"""
    today = date.today()
    today_str = today.isoformat()
    rows = []
    for i, (name, lat, lon) in enumerate(COUNTIES, 1):
        if verbose:
            print(f"  [{i:>2}/{len(COUNTIES)}] {name:<5} ({lat:.2f}, {lon:.2f}) ", end="", flush=True)
        try:
            # 1. Open-Meteo 抓 (作 fallback + 拿未來預測)
            om_daily = fetch_rainfall(lat, lon, past_days=92, forecast_days=7)
            # 2. CWA 抓過去+今日實測 (取代 om 的過去部分)
            cwa_daily = _fetch_cwa_recent_daily(name, verbose=False)
            # 3. Merge: cwa (過去+今日) 優先, om 補未來
            daily = {}
            for d, v in om_daily.items():
                daily[d] = v  # 先 om 全部
            cwa_hit = 0
            for d, v in cwa_daily.items():
                if d <= today_str:  # CWA 只信「已發生」
                    daily[d] = v  # 覆蓋 om (CWA 實測優先)
                    cwa_hit += 1
            agg = aggregate(daily, today)
            forecast = sorted([(d, mm) for d, mm in daily.items() if d > today_str])[:7]
            rows.append({
                "name": name, "lat": lat, "lon": lon,
                "today": agg["today"], "month": agg["month"], "quarter": agg["quarter"],
                "daily": daily,
                "forecast": [{"d": d, "mm": mm} for d, mm in forecast],
                "src": "cwa+openmeteo" if cwa_hit > 0 else "openmeteo",
                "cwa_hit": cwa_hit,
            })
            if verbose:
                src_lbl = f"CWA{cwa_hit}天" if cwa_hit > 0 else "無CWA"
                print(f"[{src_lbl}] 今日 {agg['today']:>5.1f} | 月 {agg['month']:>6.1f} | 季 {agg['quarter']:>6.1f}")
            time.sleep(0.3)
        except Exception as e:
            if verbose:
                print(f"FAIL：{e}")
            rows.append({"name": name, "lat": lat, "lon": lon,
                         "today": 0, "month": 0, "quarter": 0, "daily": {}, "forecast": []})
    return rows


# === 有機肥料部實際銷售噸數 (莊政遠內部業務決策用) ===
SALES_DATA = {
    "unit": "噸",
    "note": "有機肥料部逐月實際銷售 (單位:噸)",
    "monthly": {
        "2022": [331, 75, 317, 65, 42, 122, 92, 181, 284, 301, 153, 181],
        "2023": [317, 161, 169, 75, 386, 269, 371, 326, 328, 434, 305, 214],
        "2024": [346, 369, 313, 364, 503, 403, 597, 519, 731, 814, 728, 469],
        "2025": [569, 649, 607, 692, 1191, 749, 771, 774, 1907, 2250, 1684, 396],
        "2026": [651, 712, 745, 867, 999, 840, 900, None, None, None, None, None],
    },
}


# ============ 農糧署有機質肥料品牌推薦名單 (每公斤補助 2 元 / 2+2 元) ============
# 品目對照 5-01 植物渣粕 · 5-08 雞糞加工 · 5-09 禽畜糞堆肥 · 5-10 一般堆肥 ...
# 抓 article_id=22431 (2元) + 22432 (2+2元) 找到 download ids, 下載 PDF, 解析統計

def _parse_pdf_suppliers(pdf_path: str, pdfplumber_mod) -> list:
    """從農糧署推薦名單 PDF 抽出每筆產品對應的業者名稱 (用 extract_tables 精準抓)
    邏輯: 每個 row 若含 7 位登記證,取業者名欄位第一行 (不限 suffix,涵蓋公司/社/行/廠/個人戶)"""
    import re
    suppliers = []
    try:
        with pdfplumber_mod.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for tbl in tables:
                    if not tbl: continue
                    # 找業者欄 index (在 header 找「業者名稱」關鍵字, 通常是 col 3)
                    supp_col = 3  # 預設
                    for i, cell in enumerate(tbl[0] if tbl else []):
                        if cell and ('業者名稱' in str(cell) or '肥料業者' in str(cell)):
                            supp_col = i
                            break
                    for row in tbl:
                        if not row or len(row) <= supp_col: continue
                        # 該 row 需含 7 位登記證才算資料 row
                        has_reg = any(re.search(r'\b\d{7}\b', str(c or '')) for c in row)
                        if not has_reg: continue
                        supp_cell = row[supp_col]
                        if not supp_cell: continue
                        # 取第一行 (業者名), 過濾電話/地址行
                        first_line = str(supp_cell).split('\n')[0].strip()
                        # 清 0xxx- prefix
                        first_line = re.sub(r'^\d{4}-', '', first_line).strip()
                        # 排除純數字/純符號/太短
                        if not first_line or len(first_line) < 3: continue
                        if re.match(r'^[\d\-\(\)\s+]+$', first_line): continue
                        if first_line in ('肥料業者名稱', '肥料業者\n電話\n地址', '肥料業者'): continue
                        suppliers.append(first_line)
    except Exception as e:
        print(f"  [parse table] {e}")
    return suppliers


def fetch_fertilizer_rankings(verbose: bool = True, use_cache: bool = True) -> dict:
    """從農糧署官網抓最新有機質肥料品牌推薦名單, 統計每業者 × 品目 × 補助等級的產品數。
    緩存到 docs/fert_rankings_cache.json (7 天內用 cache, 過期或 refresh=True 重抓)"""
    import urllib.request, http.cookiejar, re, tempfile
    from collections import defaultdict
    today = date.today()
    cache_path = DOCS_DIR / "fert_rankings_cache.json"

    # 公開資料 → 每次跑都直接爬農糧署官網最新版, 只當日短暫 cache 避免同日重複
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cached_date = cached.get("updated", "")
            # 只當日 cache (同天重跑複用,跨日就重抓)
            if cached_date == today.isoformat():
                if verbose: print(f"[廠商] 今日已抓過 cache ({cached_date}, {cached.get('total_products',0)} 產品)")
                return cached
        except Exception as e:
            if verbose: print(f"[廠商] cache 讀取失敗: {e}")

    try:
        import pdfplumber
    except ImportError:
        if verbose: print("[廠商] pdfplumber 未安裝, 跳過抓取")
        return {}

    ua = "Mozilla/5.0"

    # Step 1: 從兩篇 article 找 download ids
    def get_download_ids(article_id):
        url = f"https://www.afa.gov.tw/cht/index.php?code=list&flag=detail&ids=2212&article_id={article_id}"
        try:
            html = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=30).read().decode("utf-8", errors="ignore")
            return re.findall(r'index\.php\?act=download&ids=(\d+)', html)
        except Exception as e:
            if verbose: print(f"[廠商] 抓 article {article_id} 失敗: {e}")
            return []

    tier_articles = {"2元": "22431", "2+2元": "22432"}

    # 品目 code 從檔名判斷
    code_pattern = re.compile(r'\((5-\d{2}|7-\d{2})\)')
    code_name_map = {
        "5-01": "植物渣粕肥料", "5-02": "副產植物質", "5-03": "魚廢渣", "5-04": "動物廢渣",
        "5-08": "雞糞加工肥料", "5-09": "禽畜糞堆肥", "5-10": "一般堆肥",
        "5-11": "雜項堆肥", "5-12": "混合有機質肥料", "5-13": "雜項有機質肥料",
        "5-14": "液態雜項有機質", "5-15": "液態有機質", "7-02": "雜項有機質介質",
        "7-03": "有機質栽培介質",
    }

    stats = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))  # stats[supplier][tier][code] = n_products
    cat_totals = defaultdict(lambda: {"n_prods": 0, "suppliers": set()})  # by (tier, code)

    for tier, aid in tier_articles.items():
        ids = get_download_ids(aid)
        if verbose: print(f"[廠商] article {aid} ({tier}) → {len(ids)} 個下載")
        for did in ids:
            # 抓 PDF header 拿檔名
            try:
                req = urllib.request.Request(f"https://www.afa.gov.tw/cht/index.php?act=download&ids={did}",
                    headers={"User-Agent": ua, "Referer": "https://www.afa.gov.tw/"})
                resp = urllib.request.urlopen(req, timeout=60)
                cd = resp.headers.get("Content-Disposition", "")
                fname_raw = re.search(r'filename="?([^";\r\n]+)', cd)
                fname = urllib.parse.unquote(fname_raw.group(1)) if fname_raw else did
                # 跳過違規名單
                if "違規" in fname:
                    if verbose: print(f"  [{did}] skip 違規名單: {fname[:40]}")
                    continue
                m = code_pattern.search(fname)
                if not m:
                    if verbose: print(f"  [{did}] skip 無 code: {fname[:40]}")
                    continue
                code = m.group(1)
                data = resp.read()
                # 寫暫存讀
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                    tf.write(data); tpath = tf.name
                try:
                    matches = _parse_pdf_suppliers(tpath, pdfplumber)
                    n_prods = len(matches)
                    cat_totals[(tier, code)]["n_prods"] += n_prods
                    for supp in matches:
                        stats[supp][tier][code] += 1
                        cat_totals[(tier, code)]["suppliers"].add(supp)
                    if verbose: print(f"  [{did}] {code} ({tier}): {n_prods} 產品 {fname[:35]}")
                finally:
                    try: os.remove(tpath)
                    except: pass
            except Exception as e:
                if verbose: print(f"  [{did}] FAIL: {e}")

    # 轉換為可 JSON 序列化
    suppliers_list = []
    for supp, tiers in stats.items():
        row = {"name": supp, "total": 0, "by_tier": {}, "by_code": defaultdict(int), "n_categories": 0}
        for tier, codes in tiers.items():
            row["by_tier"][tier] = sum(codes.values())
            row["total"] += row["by_tier"][tier]
            for code, cnt in codes.items():
                row["by_code"][code] += cnt
        row["n_categories"] = len(row["by_code"])
        row["by_code"] = dict(row["by_code"])
        suppliers_list.append(row)
    # 排序 by total desc
    suppliers_list.sort(key=lambda x: -x["total"])
    for i, r in enumerate(suppliers_list):
        r["rank"] = i + 1

    # cat_totals: 轉 unique 業者數
    cat_summary = []
    for (tier, code), v in cat_totals.items():
        cat_summary.append({
            "tier": tier, "code": code, "name": code_name_map.get(code, code),
            "n_prods": v["n_prods"], "n_suppliers": len(v["suppliers"]),
        })
    cat_summary.sort(key=lambda x: (x["tier"], -x["n_prods"]))

    total_prods = sum(r["total"] for r in suppliers_list)
    result = {
        "updated": today.isoformat(),
        "source": "農糧署 · 115 年國產有機質肥料品牌推薦名單",
        "source_url": "https://www.afa.gov.tw/cht/index.php?code=list&ids=2212",
        "total_products": total_prods,
        "total_suppliers": len(suppliers_list),
        "suppliers": suppliers_list,
        "categories": cat_summary,
    }

    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        if verbose: print(f"[廠商] cache 寫入 {cache_path}")
    except Exception as e:
        if verbose: print(f"[廠商] cache 寫入失敗: {e}")

    return result


# 動態從 CODIS station_list 抓「全台所有 CWB 局屬有人站」分縣清單
def _fetch_all_cwa_stations(verbose: bool = True) -> dict:
    """回傳 {縣市: [(stn_id, stn_name), ...]}, 動態每次抓最新的 CODIS 現役站清單"""
    import urllib.request, http.cookiejar
    from collections import defaultdict
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    ua = "Mozilla/5.0"
    try:
        opener.open(urllib.request.Request("https://codis.cwa.gov.tw/StationData",
            headers={"User-Agent": ua}), timeout=15)
        r = opener.open(urllib.request.Request("https://codis.cwa.gov.tw/api/station_list",
            headers={"User-Agent": ua}), timeout=30)
        j = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        if verbose: print(f"[CWA] station_list FAIL: {e}, 用 fallback 靜態表")
        return {}

    by_county = defaultdict(list)
    for group in j.get("data", []):
        if group.get("stationAttribute") != "cwb":
            continue
        for s in group.get("item", []):
            if s.get("stationEndDate"):  # 已停測
                continue
            county = s.get("countryName", "")
            by_county[county].append((s["stationID"], s["stationName"]))
    # 對沒有 CWB 主站的縣, 用鄰縣代表
    fallback_neighbor = {
        "新竹市": [("467571", "新竹")],
        "苗栗縣": [("467280", "後龍")],
        "雲林縣": [("467290", "古坑")],
    }
    for c, lst in fallback_neighbor.items():
        if c not in by_county or not by_county[c]:
            by_county[c] = lst
    if verbose:
        total = sum(len(v) for v in by_county.values())
        print(f"[CWA] station_list ✓ {len(by_county)} 縣市 · {total} 個現役 CWB 有人站")
    return dict(by_county)


COUNTY_CWA_STATIONS = None  # lazy init


def _ensure_stations(verbose: bool = True):
    global COUNTY_CWA_STATIONS
    if COUNTY_CWA_STATIONS is None:
        COUNTY_CWA_STATIONS = _fetch_all_cwa_stations(verbose=verbose)
        # fallback 若抓失敗
        if not COUNTY_CWA_STATIONS:
            COUNTY_CWA_STATIONS = {
                "臺北市": [("466920","臺北")], "新北市": [("466881","新北"),("466900","淡水")],
                "基隆市": [("466940","基隆")], "桃園市": [("467050","新屋")],
                "新竹市": [("467571","新竹")], "新竹縣": [("467571","新竹")],
                "宜蘭縣": [("467080","宜蘭")], "苗栗縣": [("467280","後龍")],
                "臺中市": [("467490","臺中")], "彰化縣": [("467270","田中")],
                "南投縣": [("467650","日月潭"),("467550","玉山")],
                "雲林縣": [("467290","古坑")], "嘉義市": [("467480","嘉義")],
                "嘉義縣": [("467530","阿里山")], "臺南市": [("467410","臺南"),("467420","永康")],
                "高雄市": [("467441","高雄")], "屏東縣": [("467590","恆春")],
                "花蓮縣": [("466990","花蓮")],
                "臺東縣": [("467660","臺東"),("467540","大武"),("467610","成功"),("467620","蘭嶼")],
                "澎湖縣": [("467350","澎湖"),("467300","東吉島")],
                "金門縣": [("467110","金門")], "連江縣": [("467990","馬祖")],
            }


def _fetch_one_cwa_station(stn_id: str, verbose: bool = False) -> dict:
    """單站抓 report_year → {year_str: {month_str: {mm, rd, sd, tavg, tmax, tmin}}}"""
    import urllib.request, urllib.parse, http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    ua = "Mozilla/5.0"
    try:
        opener.open(urllib.request.Request("https://codis.cwa.gov.tw/StationData",
            headers={"User-Agent": ua}), timeout=15)
        body = urllib.parse.urlencode({
            "stn_ID": stn_id, "stn_type": "cwb",
            "type": "report_year", "date": f"{date.today().year}-01-01",
        }).encode()
        req = urllib.request.Request("https://codis.cwa.gov.tw/api/station",
            data=body, method="POST",
            headers={"User-Agent": ua,
                     "Referer": "https://codis.cwa.gov.tw/StationData",
                     "Origin": "https://codis.cwa.gov.tw",
                     "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                     "X-Requested-With": "XMLHttpRequest"})
        resp = opener.open(req, timeout=60)
        j = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        if verbose: print(f" station {stn_id} FAIL: {e}")
        return {}
    if j.get("code") != 200:
        return {}
    result = {}
    for row in j.get("data", []):
        for dt in row.get("dts", []):
            ym = dt.get("DataYearMonth", "")
            if len(ym) < 7: continue
            y_k, m_k = ym[:4], str(int(ym[5:7]))
            p = dt.get("Precipitation") or {}
            at = dt.get("AirTemperature") or {}
            if y_k not in result: result[y_k] = {}
            result[y_k][m_k] = {
                "mm": round(float(p.get("Accumulation")), 1) if p.get("Accumulation") is not None else None,
                "rd": p.get("PrecipitationDays") or p.get("GE1Days") or None,
                "sd": p.get("GE50Days") or 0,
                "tavg": at.get("Mean"),
                "tmax": at.get("Maximum"),
                "tmin": at.get("Minimum"),
            }
    return result


def fetch_cwa_codis_history(county: str, verbose: bool = True) -> tuple:
    """該縣所有 CWB 現役站抓 → merge (雨量取 MAX, 氣溫取平均) → 回傳 (data, stations_meta)"""
    _ensure_stations(verbose=verbose)
    stations = COUNTY_CWA_STATIONS.get(county, [])
    if not stations:
        return ({}, [])
    per_station = {}
    for stn_id, stn_name in stations:
        d = _fetch_one_cwa_station(stn_id, verbose=verbose)
        if d:
            per_station[stn_id] = {"name": stn_name, "data": d}
        time.sleep(0.3)
    if not per_station:
        return ({}, [])

    # Merge: 每 (year, month) 取多站的 max 雨量、max 雨日、max 豪雨、avg 氣溫
    all_ym = {}
    for meta in per_station.values():
        for y, months in meta["data"].items():
            if y not in all_ym: all_ym[y] = {}
            for m, v in months.items():
                if m not in all_ym[y]:
                    all_ym[y][m] = {"mms": [], "rds": [], "sds": [], "tavgs": [], "tmaxs": [], "tmins": []}
                if v.get("mm") is not None: all_ym[y][m]["mms"].append(v["mm"])
                if v.get("rd") is not None: all_ym[y][m]["rds"].append(v["rd"])
                if v.get("sd") is not None: all_ym[y][m]["sds"].append(v["sd"])
                if v.get("tavg") is not None: all_ym[y][m]["tavgs"].append(v["tavg"])
                if v.get("tmax") is not None: all_ym[y][m]["tmaxs"].append(v["tmax"])
                if v.get("tmin") is not None: all_ym[y][m]["tmins"].append(v["tmin"])
    merged = {}
    for y in all_ym:
        merged[y] = {}
        for m, agg in all_ym[y].items():
            merged[y][m] = {
                "mm": round(max(agg["mms"]), 1) if agg["mms"] else 0,
                "rd": max(agg["rds"]) if agg["rds"] else 0,
                "sd": max(agg["sds"]) if agg["sds"] else 0,
                "tavg": round(sum(agg["tavgs"])/len(agg["tavgs"]), 1) if agg["tavgs"] else None,
                "tmax": max(agg["tmaxs"]) if agg["tmaxs"] else None,
                "tmin": min(agg["tmins"]) if agg["tmins"] else None,
                "src": "cwa",
                "nStn": len(per_station),
            }
    stations_meta = [{"id": sid, "name": m["name"]} for sid, m in per_station.items()]
    return (merged, stations_meta)


COUNTY_SAMPLE_POINTS = {
    "臺北市": [(25.04, 121.51), (25.13, 121.55), (25.09, 121.42)],
    "新北市": [(25.01, 121.46), (24.98, 121.54), (25.17, 121.65), (24.87, 121.53)],
    "基隆市": [(25.13, 121.74), (25.11, 121.68), (25.08, 121.79)],
    "桃園市": [(24.99, 121.31), (24.86, 121.24), (24.77, 121.16), (25.09, 121.20)],
    "新竹市": [(24.81, 120.97), (24.79, 120.94)],
    "新竹縣": [(24.84, 121.01), (24.70, 121.18), (24.72, 121.06)],
    "宜蘭縣": [(24.70, 121.74), (24.60, 121.85), (24.85, 121.79), (24.42, 121.51)],
    "苗栗縣": [(24.56, 120.82), (24.42, 120.95), (24.68, 121.02)],
    "臺中市": [(24.15, 120.68), (24.35, 120.71), (24.19, 121.30), (24.10, 120.55)],
    "彰化縣": [(24.07, 120.54), (23.98, 120.58), (24.05, 120.43)],
    "南投縣": [(23.91, 120.69), (23.87, 120.90), (24.05, 121.15), (23.68, 120.98)],
    "雲林縣": [(23.71, 120.43), (23.57, 120.30), (23.65, 120.58)],
    "嘉義市": [(23.48, 120.45)],
    "嘉義縣": [(23.45, 120.45), (23.50, 120.75), (23.51, 120.80), (23.32, 120.60)],
    "臺南市": [(22.99, 120.21), (23.18, 120.25), (23.31, 120.32), (23.13, 120.46), (23.09, 120.38)],
    "高雄市": [(22.62, 120.31), (22.79, 120.29), (22.88, 120.49), (22.98, 120.63), (23.05, 120.72)],
    "屏東縣": [(22.55, 120.55), (22.35, 120.60), (22.00, 120.75), (22.75, 120.68)],
    "花蓮縣": [(23.99, 121.60), (23.68, 121.44), (24.10, 121.35), (23.35, 121.31)],
    "臺東縣": [(22.75, 121.15), (23.10, 121.37), (22.48, 120.98), (22.05, 121.02)],
    "澎湖縣": [(23.57, 119.58), (23.66, 119.62)],
    "金門縣": [(24.43, 118.32), (24.48, 118.40)],
    "連江縣": [(26.16, 119.95), (26.35, 120.00)],
}


def _fetch_history_one_point(lat: float, lon: float, start: str, end: str) -> dict:
    """單點 archive 抓 daily,回傳 {date: mm}"""
    import urllib.request
    for model_param in ["&models=ecmwf_ifs", ""]:  # 先試高解析,失敗 fallback era5
        try:
            url = (
                "https://archive-api.open-meteo.com/v1/archive?"
                f"latitude={lat}&longitude={lon}"
                f"&start_date={start}&end_date={end}"
                f"&daily=precipitation_sum&timezone=Asia%2FTaipei{model_param}"
            )
            with urllib.request.urlopen(url, timeout=60) as resp:
                j = json.loads(resp.read().decode("utf-8"))
            times = j.get("daily", {}).get("time", [])
            precs = j.get("daily", {}).get("precipitation_sum", [])
            daily = {}
            for t, v in zip(times, precs):
                if v is None: continue
                daily[t] = float(v)
            # ecmwf_ifs 若全 0 (該區無資料),試 fallback
            if daily and sum(daily.values()) > 0:
                return daily
        except Exception:
            continue
    return {}


def collect_history_stats(verbose: bool = True, n_years: int = 10, use_cache: bool = True, current_rows: list = None) -> dict:
    """一次撈全台 22 縣市過去 N 年每日雨量 → 每縣市多點採樣取 MAX → 聚合成月統計。
    資料源:Open-Meteo Archive ECMWF-IFS (9km 高解析) + 每縣市 2-5 點涵蓋山區/平原/沿海
    有本地 cache;要強制重抓可刪除 docs/history_cache.json"""
    import urllib.request, urllib.parse
    today = date.today()
    cache_path = DOCS_DIR / "history_cache.json"

    # 讀 cache: 若同月已有就直接用, 否則呼叫 API 抓一次
    result = None
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cached_updated = cached.get("updated", "")
            if cached_updated[:7] == today.isoformat()[:7]:
                if verbose:
                    print(f"[歷史] 使用本地 cache ({cached_updated}, {len(cached.get('data', {}))} 縣市)")
                result = cached
        except Exception as e:
            if verbose:
                print(f"[歷史] cache 讀取失敗, 重抓: {e}")

    if result is None:
        end_year = today.year
        start_year = end_year - n_years + 1

        _ensure_stations(verbose=verbose)
        result = {
            "years": list(range(start_year, end_year + 1)),
            "counties": [c[0] for c in COUNTIES],
            "data": {},
            "source": "中央氣象署 CODIS · 全台 CWB 局屬有人氣象站官方觀測 · 每縣多站取 MAX",
            "source_url": "https://codis.cwa.gov.tw/StationData",
            "stations": {},  # {縣市: [{id, name}]}
            "updated": today.isoformat(),
        }

        for i, (name, lat, lon) in enumerate(COUNTIES, 1):
            stns = COUNTY_CWA_STATIONS.get(name, [])
            if verbose:
                print(f"  [CWA {i:>2}/{len(COUNTIES)}] {name:<5} {len(stns)}站 ({','.join(s[1] for s in stns) or '無'}) ...", end="", flush=True)
            cwa_months, stations_meta = fetch_cwa_codis_history(name, verbose=False) if stns else ({}, [])
            result["stations"][name] = stations_meta
            if cwa_months:
                result["data"][name] = cwa_months
                # 檢查最近 5 年是否有缺月 → 用 Open-Meteo 補
                cur_y = today.year
                missing_recent = []
                for y in range(cur_y - 4, cur_y + 1):
                    y_k = str(y)
                    y_data = cwa_months.get(y_k, {})
                    # 該年應有月份 (至今為止的月)
                    max_m = today.month if y == cur_y else 12
                    for m in range(1, max_m + 1):
                        m_k = str(m)
                        if m_k not in y_data or (y_data.get(m_k, {}).get("mm", 0) == 0 and y_data.get(m_k, {}).get("rd", 0) == 0):
                            missing_recent.append((y, m))
                if missing_recent and len(missing_recent) > 3:  # 缺 3 個月以上才 fallback
                    if verbose: print(f" ✓ CWA {sorted(cwa_months.keys())[0]}–{sorted(cwa_months.keys())[-1]},缺{len(missing_recent)}月補Open-Meteo...", end="", flush=True)
                    om_start = f"{cur_y - 4}-01-01"
                    om_daily = _fetch_history_one_point(lat, lon, om_start, today.isoformat())
                    om_months = {}
                    for t, v in om_daily.items():
                        y_k, m_k = t[:4], str(int(t[5:7]))
                        if y_k not in om_months: om_months[y_k] = {}
                        if m_k not in om_months[y_k]: om_months[y_k][m_k] = {"mm": 0.0, "rd": 0, "sd": 0, "src": "openmeteo-fallback"}
                        om_months[y_k][m_k]["mm"] += v
                        if v >= 1: om_months[y_k][m_k]["rd"] += 1
                        if v >= 80: om_months[y_k][m_k]["sd"] += 1
                    for y, m in missing_recent:
                        y_k, m_k = str(y), str(m)
                        if y_k in om_months and m_k in om_months[y_k]:
                            v = om_months[y_k][m_k]
                            v["mm"] = round(v["mm"], 1)
                            if y_k not in result["data"][name]:
                                result["data"][name][y_k] = {}
                            result["data"][name][y_k][m_k] = v
                    if verbose: print(f" ✓")
                else:
                    if verbose:
                        years_c = sorted(cwa_months.keys())
                        total_m = sum(len(v) for v in cwa_months.values())
                        print(f" ✓ CWA {years_c[0]}–{years_c[-1]}·{total_m}月")
            else:
                # Fallback: Open-Meteo (無 CWA 主站或抓失敗時)
                if verbose: print(" CWA失敗, fallback Open-Meteo ...", end="", flush=True)
                points = COUNTY_SAMPLE_POINTS.get(name, [(lat, lon)])
                point_daily_list = []
                for p_lat, p_lon in points:
                    d = _fetch_history_one_point(p_lat, p_lon,
                        f"{start_year}-01-01", today.isoformat())
                    if d: point_daily_list.append(d)
                    time.sleep(0.2)
                months = {}
                if point_daily_list:
                    all_dates = set()
                    for d in point_daily_list: all_dates.update(d.keys())
                    for t in all_dates:
                        v = max(d.get(t, 0.0) for d in point_daily_list)
                        y_k, m_k = t[:4], str(int(t[5:7]))
                        if y_k not in months: months[y_k] = {}
                        if m_k not in months[y_k]: months[y_k][m_k] = {"mm": 0.0, "rd": 0, "sd": 0, "src": "openmeteo"}
                        months[y_k][m_k]["mm"] += v
                        if v >= 1: months[y_k][m_k]["rd"] += 1
                        if v >= 80: months[y_k][m_k]["sd"] += 1
                    for y_k in months:
                        for m_k in months[y_k]:
                            months[y_k][m_k]["mm"] = round(months[y_k][m_k]["mm"], 1)
                result["data"][name] = months
                if verbose: print(f" ✓ Open-Meteo {len(months)}年")
            time.sleep(0.5)

        try:
            DOCS_DIR.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
            if verbose:
                print(f"[歷史] cache 寫入 {cache_path}")
        except Exception as e:
            if verbose:
                print(f"[歷史] cache 寫入失敗: {e}")

    # === 用地圖資料源覆蓋當年 (今年整年) — 讓數字與地圖顯示一致 ===
    if current_rows:
        cur_year = today.year
        override_cnt = 0
        for row in current_rows:
            name = row.get("name")
            daily = row.get("daily") or {}
            if not daily or name not in result["data"]:
                continue
            cur_year_k = str(cur_year)  # JSON key 是 str
            monthly = {}
            for d_str, v in daily.items():
                if not isinstance(v, (int, float)) or d_str[:4] != cur_year_k:
                    continue
                if d_str > today.isoformat():
                    continue
                m_k = str(int(d_str[5:7]))
                if m_k not in monthly:
                    monthly[m_k] = {"mm": 0.0, "rd": 0, "sd": 0}
                monthly[m_k]["mm"] += float(v)
                if v >= 1: monthly[m_k]["rd"] += 1
                if v >= 80: monthly[m_k]["sd"] += 1
            for m_k in monthly:
                monthly[m_k]["mm"] = round(monthly[m_k]["mm"], 1)
                monthly[m_k]["src"] = "forecast"
            if monthly:
                if cur_year_k not in result["data"][name]:
                    result["data"][name][cur_year_k] = {}
                # 清掉舊 int key (可能來自新抓那條路徑)
                if cur_year in result["data"][name]:
                    del result["data"][name][cur_year]
                result["data"][name][cur_year_k].update(monthly)
                override_cnt += 1
        if verbose:
            print(f"[歷史] 用地圖 (Forecast API) 覆蓋 {cur_year} 年 · {override_cnt} 縣市 → 與上方地圖數字一致")
        result["note"] = f"當年 ({cur_year}) 用 Open-Meteo Forecast API 高解析 (11km) 覆蓋，跟本頁上方地圖同源; 歷年為 ERA5 全球再分析 (25km) 可能對局部強降雨低估,主要比較趨勢"
    return result


def _git_commit_and_push_docs(verbose: bool = True) -> bool:
    """在 GitHub Actions runner 自動 commit + push docs/taiwan_rainfall_map.html
    本機跑時提示用戶手動 push。"""
    in_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    if not in_actions:
        if verbose:
            print("[Rainfall Map] (本機) 已寫入 docs/，請手動 git push 才會更新 GitHub Pages")
        return False
    try:
        subprocess.run(["git", "config", "user.email",
                         "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "add", "docs/taiwan_rainfall_map.html"], check=True)
        diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff.returncode != 0:  # 有差異才 commit
            subprocess.run(["git", "commit", "-m",
                             f"chore(map): rainfall {date.today().isoformat()}"], check=True)
            # rebase 拉新後 push（其他 workflow 可能也推過）
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
            if verbose:
                print("[Rainfall Map] ✓ 推到 GitHub，Pages 將自動部署（約 30-60 秒）")
        else:
            if verbose:
                print("[Rainfall Map] docs/ 內容無變動，跳過 commit")
        return True
    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"[Rainfall Map] [!] git 操作失敗：{e}")
        return False


def generate_and_publish(verbose: bool = True) -> str:
    """產地圖 HTML → 寫到 docs/（GitHub Pages 源）→ commit+push（Actions）→ 回傳公開 URL。
    GitHub Pages 會回正確 Content-Type: text/html（catbox 會回 text/plain）。"""
    today = date.today()
    if verbose:
        print(f"[Rainfall Map] 產出全台 22 縣市互動地圖 ...")
    rows = collect_rows(verbose=verbose)
    if verbose:
        print(f"[Rainfall Map] 抓取歷史雨量 10 年 × 22 縣市 (Python 端預打包) ...")
    history_stats = collect_history_stats(verbose=verbose, n_years=10, current_rows=rows)
    if verbose:
        print(f"[Rainfall Map] 抓取農糧署有機肥廠商排名 ...")
    fert_rankings = fetch_fertilizer_rankings(verbose=verbose)
    # 加入 PDF 監控 (新上架/新違規 · 從 scraper_pdf 復用)
    try:
        from scraper_pdf import scrape_all as _scrape_pdf
        if verbose: print(f"[Rainfall Map] 抓農糧署 PDF 監控 (新上架/新違規) ...")
        _pdf_result = _scrape_pdf()
        # 精簡欄位塞進 fert_rankings 讓前端 embed
        if fert_rankings is None: fert_rankings = {}
        fert_rankings["recent_added"] = [
            {"cat": p.get("品目",""), "date": p.get("上架日") or p.get("上網日",""),
             "brand": p.get("廠牌商品名稱",""), "supplier": p.get("業者名稱","")}
            for p in _pdf_result.get("recent_added", [])[:20]
        ]
        fert_rankings["recent_violations"] = [
            {"cat": p.get("原品目") or p.get("品目",""), "date": p.get("下網日",""),
             "brand": p.get("廠牌商品名稱",""), "supplier": p.get("業者名稱",""),
             "reason": p.get("違規原因","") or p.get("違規事由","")}
            for p in _pdf_result.get("recent_violations", [])[:20]
        ]
        fert_rankings["recent_removed"] = [
            {"cat": p.get("品目",""), "date": p.get("下架日",""),
             "brand": p.get("廠牌商品名稱",""), "supplier": p.get("業者名稱","")}
            for p in _pdf_result.get("recent_removed", [])[:20]
        ]
        fert_rankings["monitor_days"] = _pdf_result.get("change_days", 30)
        if verbose:
            print(f"  → 新上架 {len(fert_rankings['recent_added'])} · "
                  f"新違規 {len(fert_rankings['recent_violations'])} · "
                  f"下架 {len(fert_rankings['recent_removed'])}")
    except Exception as e:
        if verbose: print(f"[Rainfall Map] PDF 監控失敗: {e}")
    html = build_html(rows, today, history_stats, fert_rankings)

    # 寫到 docs/ (GitHub Pages 來源，固定檔名讓 URL 不變)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    docs_path = DOCS_DIR / "taiwan_rainfall_map.html"
    docs_path.write_text(html, encoding="utf-8")
    if verbose:
        print(f"[Rainfall Map] 寫入 {docs_path}")

    # 本機備份（每次跑都存一份歷史）
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"taiwan_rainfall_map_{today.strftime('%Y%m%d')}.html") \
        .write_text(html, encoding="utf-8")

    # 在 Actions 環境自動 push；本機需自己 push
    _git_commit_and_push_docs(verbose=verbose)

    # 加 ?v=YYYYMMDDHHMM 強制 cache bust；?openExternalBrowser=1 強制 LINE 開外部瀏覽器
    ts = datetime.now().strftime("%Y%m%d%H%M")
    return f"{GITHUB_PAGES_BASE}/taiwan_rainfall_map.html?v={ts}&openExternalBrowser=1"


# 向下相容（weekly_line_push 還在用舊名稱）
def generate_and_upload(verbose: bool = True) -> str:
    return generate_and_publish(verbose=verbose)


def main():
    today = date.today()
    print(f"=== 全台雨量地圖產出 · {today} ===\n")
    # 載 .env (供 catbox userhash 等)
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    url = generate_and_publish(verbose=True)
    if url:
        print(f"\n🌐 公開 URL（GitHub Pages，永久）：\n  {url}")
        print(f"\n注意：本機跑只寫了 docs/，請 git push 後 Pages 才會更新（~30-60 秒）")


if __name__ == "__main__":
    main()
