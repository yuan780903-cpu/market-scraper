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
  .rainy-summary{{padding:12px 14px;background:var(--cwa-primary);color:#fff;border-radius:3px;margin-bottom:12px;font-size:14px;line-height:1.8}}
  .rainy-summary strong{{font-size:20px;color:#ffd54f;margin:0 4px;font-family:ui-monospace,Menlo,monospace}}
  .cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;font-size:12px;margin-bottom:12px;background:var(--cwa-border);padding:2px;border-radius:3px}}
  .cal-head{{padding:6px;text-align:center;font-weight:700;background:var(--cwa-primary);color:#fff;font-size:11px}}
  .cal-head:first-child{{color:#ffd54f}}   /* 週日 */
  .cal-head:last-child{{color:#ffcccc}}   /* 週六 */
  .cal-cell{{aspect-ratio:1;padding:4px;display:flex;flex-direction:column;justify-content:space-between;text-align:center;background:#fff;color:var(--cwa-text)}}
  .cal-cell.empty{{background:transparent}}
  .cal-cell.dry{{background:#fafafa;color:var(--cwa-text-light)}}
  .cal-cell.rain-1{{background:#e3f2fd;color:#0d47a1}}
  .cal-cell.rain-2{{background:#64b5f6;color:#fff}}
  .cal-cell.rain-3{{background:#1976d2;color:#fff}}
  .cal-cell.rain-4{{background:#ef6c00;color:#fff}}
  .cal-cell.rain-5{{background:#c62828;color:#fff}}
  .cal-cell.today{{outline:3px solid #ffd54f;outline-offset:-3px;font-weight:900}}
  .cal-cell .d{{font-size:14px;font-weight:700}}
  .cal-cell .mm{{font-size:10px;font-weight:600}}
  .rainy-list{{max-height:180px;overflow-y:auto;background:var(--cwa-hover);padding:10px 12px;border-radius:3px;font-size:12px;line-height:1.8;border:1px solid var(--cwa-border)}}
  .rainy-list .day{{display:inline-block;padding:3px 10px;margin:3px;background:#fff;border-radius:2px;border:1px solid var(--cwa-border);font-family:ui-monospace,Menlo,monospace}}
  .rainy-list .day b{{color:var(--cwa-danger)}}

  /* ===== 未來 7 天預測地圖 ===== */
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
<body>
<div class="header">
  <h1>🗺️ 全台累積雨量地圖</h1>
  <p>資料來源 Open-Meteo (ECMWF)　·　22 縣市</p>
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
  <div class="fcst-day-tabs" id="fcstTabs"></div>
  <div class="fcst-wrap">
    <div id="fcstMap"></div>
    <div class="fcst-legend">
      <div class="fcst-legend-title">顏色 → 日雨量 (mm)</div>
      <div id="fcstLegendBars"></div>
      <div class="fcst-legend-hint">📍 兩指縮放可看鄉鎮街道<br>👆 點縣市顯示詳細數字</div>
    </div>
  </div>
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
    const row = document.createElement('tr');
    row.innerHTML = '<td class="rank">' + (i + 1) + '</td>' +
                    '<td class="county">' + c.name + '</td>' +
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

// 建日期 tabs
const fcstTabs = document.getElementById('fcstTabs');
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
    renderForecastMap(d);
  }});
  fcstTabs.appendChild(btn);
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

function renderForecastMap(dateStr) {{
  if (fcstGeoLayer) fcstMap.removeLayer(fcstGeoLayer);
  fcstLabelLayer.clearLayers();

  const drawIt = (geo) => {{
    fcstGeoLayer = L.geoJSON(geo, {{
      style: (feature) => {{
        const {{row}} = getDataForFeature(feature);
        const f = row && row.forecast ? row.forecast.find(x => x.d === dateStr) : null;
        const mm = f ? f.mm : 0;
        return {{fillColor: fcstColor(mm), weight: 0.8, color: '#fff', fillOpacity: 0.75}};
      }},
      onEachFeature: (feature, layer) => {{
        const {{name, row}} = getDataForFeature(feature);
        const f = row && row.forecast ? row.forecast.find(x => x.d === dateStr) : null;
        const mm = f ? f.mm : 0;
        const c = fcstColor(mm);
        layer.bindPopup(
          `<div class="popup-content"><strong>${{name}}</strong><br>` +
          `${{dateStr}} 預測：<strong style="color:${{c}};font-size:16px">${{mm.toFixed(1)}} mm</strong><br>` +
          `<span style="color:#888">（${{fcstLabel(mm)}}）</span></div>`
        );
        if (row) {{
          const center = layer.getBounds().getCenter();
          L.marker([center.lat, center.lng], {{
            icon: L.divIcon({{
              className: 'county-label',
              html: name.replace('縣','').replace('市','') + '<span class="mm">' + mm.toFixed(0) + '</span>',
              iconSize: null,
            }}),
          }}).addTo(fcstLabelLayer);
        }}
      }},
    }}).addTo(fcstMap);
  }};

  if (window._geo) {{
    drawIt(window._geo);
  }} else {{
    fetch(GEOJSON_URL).then(r => r.json()).then(g => {{ window._geo = g; drawIt(g); }});
  }}
}}

// 預設載入第一天預測
if (FORECAST_DATES.length > 0) {{
  renderForecastMap(FORECAST_DATES[0]);
}}

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

  // 摘要
  const summary = document.getElementById('rainySummary');
  summary.innerHTML =
    '📍 <strong style="color:#1f3a2e">' + countyName + '</strong>' +
    ' · ' + yyyy + ' 年 ' + mm + ' 月　|　' +
    '本月累計降雨 <strong>' + totalMm.toFixed(1) + '</strong> mm　|　' +
    '有雨（≥1mm）共 <strong>' + totalRainDays + '</strong> 天　|　' +
    '達 ≥' + threshold + 'mm 共 <strong>' + matchDays.length + '</strong> 天';

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
    const cell = document.createElement('div');
    cell.className = 'cal-cell';
    if (val === undefined) {{
      cell.className += ' empty';
      cell.innerHTML = '<div class="d">' + d + '</div><div class="mm" style="color:#ccc">-</div>';
    }} else if (val < 1) {{
      cell.className += ' dry';
      cell.innerHTML = '<div class="d">' + d + '</div><div class="mm">0</div>';
    }} else {{
      // 分級：1-10, 10-30, 30-50, 50-80, 80+
      let lvl = 1;
      if (val >= 80) lvl = 5;
      else if (val >= 50) lvl = 4;
      else if (val >= 30) lvl = 3;
      else if (val >= 10) lvl = 2;
      cell.className += ' rain-' + lvl;
      cell.innerHTML = '<div class="d">' + d + '</div><div class="mm">' + val.toFixed(0) + '</div>';
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
        // 重建 tabs
        const tabsEl = document.getElementById('fcstTabs');
        tabsEl.innerHTML = '';
        FORECAST_DATES.forEach((d, i) => {{
          const dt = new Date(d);
          const wk = '日一二三四五六'[dt.getDay()];
          const b = document.createElement('button');
          b.textContent = (dt.getMonth()+1) + '/' + dt.getDate() + '(' + wk + ')';
          b.dataset.date = d;
          if (i === 0) b.classList.add('active');
          b.addEventListener('click', () => {{
            document.querySelectorAll('#fcstTabs button').forEach(x => x.classList.remove('active'));
            b.classList.add('active');
            renderForecastMap(d);
          }});
          tabsEl.appendChild(b);
        }});
      }}
      renderForecastMap(FORECAST_DATES[0]);
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
