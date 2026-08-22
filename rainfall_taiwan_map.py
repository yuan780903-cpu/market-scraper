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
    """計算 今日 / 本月累積 / 本季累積 / 各月累積"""
    today_str = today.isoformat()
    today_val = daily.get(today_str, 0)

    # 本月：所有 today.year-today.month 的日值加總
    month_prefix = f"{today.year}-{today.month:02d}-"
    month_total = sum(v for d, v in daily.items() if d.startswith(month_prefix))

    # 本季
    q = (today.month - 1) // 3 + 1
    q_months = {(q - 1) * 3 + i + 1 for i in range(3)}
    q_total = sum(
        v for d, v in daily.items()
        if d.startswith(f"{today.year}-")
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
  body{{font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",-apple-system,sans-serif;background:var(--cwa-bg);color:var(--cwa-text);line-height:1.5;font-size:14px}}

  /* ===== Header (深藍官方橫幅) ===== */
  .header{{background:linear-gradient(180deg,var(--cwa-dark) 0%,var(--cwa-primary) 100%);color:#fff;padding:20px 20px 16px;border-bottom:3px solid #ffb300}}
  .header h1{{margin:0;font-size:22px;font-weight:700;letter-spacing:.5px}}
  .header p{{margin:6px 0 0;color:#cfe0f0;font-size:12px;letter-spacing:.3px}}

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

  /* ===== 影響級距表 ===== */
  .impact .group-title{{margin:12px 0 6px;font-size:13px;font-weight:700;color:var(--cwa-primary);background:var(--cwa-hover);padding:4px 10px;border-left:3px solid var(--cwa-primary)}}
  .impact .row{{display:flex;gap:12px;font-size:13px;margin:4px 0;align-items:baseline;padding:4px 10px}}
  .impact .row:nth-child(even){{background:var(--cwa-hover)}}
  .impact .rng{{width:100px;font-weight:700;font-family:ui-monospace,Menlo,monospace;flex-shrink:0}}
  .impact .note{{color:var(--cwa-text);flex:1}}
  .impact .green{{color:var(--cwa-success)}}
  .impact .amber{{color:var(--cwa-warning)}}
  .impact .red{{color:var(--cwa-danger)}}
  .impact .gray{{color:var(--cwa-text-muted)}}
  .impact .info-note{{margin-top:14px;padding:12px 14px;background:var(--cwa-light);border-left:4px solid var(--cwa-primary);border-radius:2px;font-size:12px;color:var(--cwa-text);line-height:1.7}}
  .impact .info-note strong{{color:var(--cwa-primary)}}

  /* ===== 資料來源 ===== */
  .source{{border-top:2px solid var(--cwa-border);background:var(--cwa-hover)}}
  .source h3{{background:transparent;border-left-color:var(--cwa-text-muted);color:var(--cwa-text-muted)}}
  .source ul{{margin:0;padding-left:20px;font-size:12px;color:var(--cwa-text-muted);line-height:1.8}}
  .source li{{margin:4px 0}}
  .source a{{color:var(--cwa-accent);text-decoration:none;word-break:break-all}}
  .source a:hover{{text-decoration:underline}}

  /* ===== 頁尾 ===== */
  .footer{{padding:16px;text-align:center;color:var(--cwa-text-light);font-size:11px;background:var(--cwa-card);border-top:1px solid var(--cwa-border);font-family:ui-monospace,Menlo,monospace}}

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
<div class="header">
  <h1>🗺️ 全台累積雨量地圖</h1>
  <p>資料來源 Open-Meteo (ECMWF)　·　22 縣市</p>
  <div class="term-strip">
    <span class="term-emoji">{term_emoji}</span>
    <span class="term-name">{term_name}</span>
    <span class="term-hint">{term_hint}</span>
  </div>
</div>

<!-- 天氣吉祥物 -->
<div class="mascot mascot-{mascot_mood}" id="mascot">
  <div class="mascot-bubble" id="mascotBubble"></div>
  <div class="mascot-face">{mascot_emoji}</div>
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
  <span class="refresh-time" id="refreshTime">📡 資料時間：{gen_time}</span>
  <a class="cwa-link" href="https://www.cwa.gov.tw/V8/C/W/OBS_County.html" target="_blank" rel="noopener">📊 對照中央氣象署即時觀測</a>
</div>
<div class="accuracy-note">
  ⚠️ Open-Meteo 為 ECMWF 全球模型（11 km 分辨率），對台灣<strong>山區、颱風局部豪雨可能低估</strong>。
  颱風/豪雨警報請以<a href="https://www.cwa.gov.tw/" target="_blank" rel="noopener"><strong>中央氣象署</strong></a>為準。
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

<div id="map"></div>

<div class="legend">
  <div class="legend-title">📊 顏色級距（本月 / 本季用，今日按比例縮放）</div>
  <div style="font-size:12px;color:#52616b;margin-bottom:8px;padding:6px 8px;background:#f5f6f3;border-radius:4px">
    ※ 地圖上縣市名稱旁的數字 = 該期間累積雨量（單位：mm）
  </div>
  {legend_rows}
</div>

<div class="impact">
  <h3>💧 雨量對有機質肥料施用的影響程度</h3>
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

<!-- ===================== 未來 7 天雨量預測 ===================== -->
<div class="forecast-block">
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

<!-- ===================== 節氣 × 有機質基肥出貨影響 ===================== -->
<div class="term-detail-block">
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
<div class="crops-block">
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

<!-- ===================== 鄉鎮特色農產地圖 ===================== -->
<div class="towns-block">
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

<!-- ===================== 歷史雨量比較 · 出貨影響對照 ===================== -->
<div class="history-block">
  <h3>📊 歷史雨量比較 · 近 5 年同月對照 (向老闆報告用)</h3>
  <div class="history-filters">
    <label>地區</label>
    <select id="histRegion">
      <option value="桃園市">北部 · 桃園</option>
      <option value="臺中市">中部 · 臺中</option>
      <option value="臺南市" selected>南部 · 臺南（主業務區）</option>
      <option value="高雄市">南部 · 高雄</option>
      <option value="屏東縣">南部 · 屏東</option>
      <option value="花蓮縣">東部 · 花蓮</option>
      <option value="臺東縣">東部 · 臺東</option>
    </select>
    <label>月份</label>
    <select id="histMonth"></select>
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
      👆 選好地區與月份，按「撈取比較」抓取 Open-Meteo Historical 資料 (ERA5, 免費)<br>
      <span style="font-size:11px">首次撈取約 5-15 秒，撈過的組合會 cache</span>
    </div>
  </div>
  <div class="history-table-wrap" id="histTableWrap" style="display:none">
    <table class="history-table">
      <thead><tr>
        <th>年份</th>
        <th>該月累積雨量</th>
        <th>有雨天數 (≥1mm)</th>
        <th>豪雨日 (≥80mm)</th>
        <th>vs 均值差異</th>
        <th>vs 均值 %</th>
      </tr></thead>
      <tbody id="histTbody"></tbody>
    </table>
  </div>
  <div class="history-report" id="histReport" style="display:none"></div>
</div>

<!-- ===================== 天氣分析 ===================== -->
<div class="analysis-block">
  <h3>🌦️ 未來一週天氣分析</h3>
  <p class="analysis-text">{analysis_text}</p>
</div>

<!-- ===================== 相關新聞 ===================== -->
<div class="news-block">
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

<div class="footer">
  產出於 {gen_time}　·　資料涵蓋過去 92 天　·　大成長城企業有機肥料部
</div>

<script>
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

const map = L.map('map', {{zoomControl: true, attributionControl: true}}).setView([23.7, 121.0], 7);
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
const fcstMap = L.map('fcstMap', {{zoomControl: true, attributionControl: false}}).setView([23.7, 121.0], 7);
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

// ============ 📊 歷史雨量比較 ============
const HIST_LATLON = {{
  '桃園市': [24.99, 121.31], '臺中市': [24.15, 120.68], '臺南市': [22.99, 120.21],
  '高雄市': [22.62, 120.31], '屏東縣': [22.55, 120.55], '花蓮縣': [23.99, 121.60], '臺東縣': [22.75, 121.15],
}};
window._histCache = {{}};

// 建月份下拉 (預設當月)
(function initHistMonth() {{
  const sel = document.getElementById('histMonth');
  const curM = new Date().getMonth() + 1;
  for (let m = 1; m <= 12; m++) {{
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m + ' 月';
    if (m === curM) opt.selected = true;
    sel.appendChild(opt);
  }}
}})();

async function fetchYearMonth(lat, lon, year, month) {{
  // 抓某年某月每日雨量
  const dim = new Date(year, month, 0).getDate();  // 該月天數
  const start = year + '-' + String(month).padStart(2, '0') + '-01';
  const end = year + '-' + String(month).padStart(2, '0') + '-' + String(dim).padStart(2, '0');
  const url = 'https://archive-api.open-meteo.com/v1/archive?' +
              'latitude=' + lat + '&longitude=' + lon +
              '&start_date=' + start + '&end_date=' + end +
              '&daily=precipitation_sum&timezone=Asia%2FTaipei';
  const r = await fetch(url);
  if (!r.ok) throw new Error('archive API HTTP ' + r.status);
  const j = await r.json();
  const daily = {{}};
  j.daily.time.forEach((t, i) => {{
    daily[t] = Math.round((j.daily.precipitation_sum[i] || 0) * 10) / 10;
  }});
  return daily;
}}

async function loadHistoryData() {{
  const region = document.getElementById('histRegion').value;
  const month = parseInt(document.getElementById('histMonth').value);
  const nYears = parseInt(document.getElementById('histYears').value);
  const btn = document.getElementById('histRun');
  const status = document.getElementById('histStatus');
  const currentYear = new Date().getFullYear();
  const years = [];
  for (let i = 0; i < nYears; i++) years.push(currentYear - i);
  years.sort();
  const [lat, lon] = HIST_LATLON[region];

  btn.disabled = true;
  btn.textContent = '⏳ 撈取中... (0/' + years.length + ')';
  status.className = 'history-status show';
  status.innerHTML = '正在抓取 <strong>' + region + '</strong> 過去 ' + nYears + ' 年 <strong>' + month + ' 月</strong>的歷史雨量資料...';

  try {{
    let done = 0;
    const results = await Promise.all(years.map(async (year) => {{
      const cacheKey = region + '_' + year + '_' + month;
      let daily;
      if (window._histCache[cacheKey]) {{
        daily = window._histCache[cacheKey];
      }} else {{
        daily = await fetchYearMonth(lat, lon, year, month);
        window._histCache[cacheKey] = daily;
      }}
      done++;
      btn.textContent = '⏳ 撈取中... (' + done + '/' + years.length + ')';
      // 統計
      let sum = 0, rainDays = 0, stormDays = 0;
      Object.values(daily).forEach(v => {{
        sum += v;
        if (v >= 1) rainDays++;
        if (v >= 80) stormDays++;
      }});
      return {{
        year, mm: Math.round(sum * 10) / 10,
        rainDays, stormDays,
        daily,
      }};
    }}));

    btn.textContent = '🔍 撈取比較';
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
      tr.innerHTML =
        '<td class="yr">' + r.year + '</td>' +
        '<td class="mm">' + r.mm.toFixed(1) + ' mm</td>' +
        '<td>' + r.rainDays + ' 天</td>' +
        '<td>' + r.stormDays + ' 天</td>' +
        '<td class="diff ' + upDown + '">' + arrow + Math.abs(diff).toFixed(1) + ' mm</td>' +
        '<td class="diff ' + upDown + '">' + arrow + Math.abs(diffPct).toFixed(1) + '%</td>';
      tbody.appendChild(tr);
    }});
    // 均值列
    const avgTr = document.createElement('tr');
    avgTr.className = 'avg-row';
    avgTr.innerHTML =
      '<td class="yr">近 ' + nYears + ' 年均</td>' +
      '<td class="mm">' + avgMm.toFixed(1) + ' mm</td>' +
      '<td>' + avgDays.toFixed(1) + ' 天</td>' +
      '<td>—</td><td>—</td><td>—</td>';
    tbody.appendChild(avgTr);
    document.getElementById('histTableWrap').style.display = '';

    // SVG 長條圖
    renderHistChart(results, avgMm, region, month);

    // 業務報告文字
    renderHistReport(results, avgMm, avgDays, region, month, currentYear);

    status.innerHTML = '✅ <strong>' + region + '</strong> · ' + month + ' 月 · 近 ' + nYears + ' 年資料已載入（Open-Meteo Historical，ERA5 reanalysis）';
  }} catch (e) {{
    console.error(e);
    btn.textContent = '🔍 撈取比較';
    btn.disabled = false;
    status.innerHTML = '❌ 抓取失敗：' + e.message;
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
    '<span class="label">📋 向老闆報告摘要 (' + region + ' · ' + month + ' 月)</span>' +
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
const townsMap = L.map('townsMap', {{zoomControl: true, attributionControl: false}}).setView([23.7, 121.0], 7);
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

document.getElementById('townFltCat').addEventListener('change', renderTownsMap);
document.getElementById('townKw').addEventListener('input', renderTownsMap);
renderTownsMap();

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

// ============ 🐔 天氣吉祥物對話輪播 ============
const MASCOT_LINES = {mascot_lines_json};
(function initMascot() {{
  const bubble = document.getElementById('mascotBubble');
  const mascot = document.getElementById('mascot');
  let idx = 0;
  let showTimer = null;
  function showLine() {{
    bubble.textContent = MASCOT_LINES[idx % MASCOT_LINES.length];
    bubble.classList.add('show');
    clearTimeout(showTimer);
    showTimer = setTimeout(() => bubble.classList.remove('show'), 4500);
    idx++;
  }}
  // 首次載入 1.5 秒後顯示
  setTimeout(showLine, 1500);
  // 每 8 秒輪播
  setInterval(showLine, 8000);
  // 點吉祥物立即換一句
  mascot.addEventListener('click', showLine);
}})();

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


def build_html(rows: list, today: date) -> str:
    from datetime import timedelta
    quarter = (today.month - 1) // 3 + 1

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
    )




def collect_rows(verbose: bool = True) -> list:
    """抓 22 縣市 90 天雨量，回傳 rows 給 HTML 用"""
    today = date.today()
    rows = []
    for i, (name, lat, lon) in enumerate(COUNTIES, 1):
        if verbose:
            print(f"  [{i:>2}/{len(COUNTIES)}] {name:<5} ({lat:.2f}, {lon:.2f}) ... ", end="", flush=True)
        try:
            daily = fetch_rainfall(lat, lon, past_days=92, forecast_days=7)
            agg = aggregate(daily, today)
            # 拆出未來 7 天預測（從 today+1 開始）
            today_str = today.isoformat()
            forecast = sorted([(d, mm) for d, mm in daily.items() if d > today_str])[:7]
            rows.append({
                "name": name, "lat": lat, "lon": lon,
                "today": agg["today"],
                "month": agg["month"],
                "quarter": agg["quarter"],
                "daily": daily,   # 完整每日雨量 → 讓 JS 端算自訂區間
                "forecast": [{"d": d, "mm": mm} for d, mm in forecast],
            })
            if verbose:
                print(f"今日 {agg['today']:>5.1f} | 月 {agg['month']:>6.1f} | 季 {agg['quarter']:>6.1f}")
            time.sleep(0.25)
        except Exception as e:
            if verbose:
                print(f"FAIL：{e}")
            rows.append({"name": name, "lat": lat, "lon": lon,
                         "today": 0, "month": 0, "quarter": 0})
    return rows


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
    html = build_html(rows, today)

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
