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


def fetch_rainfall(lat: float, lon: float, past_days: int = 92) -> dict:
    """回傳 {YYYY-MM-DD: precipitation_mm}（含今日）"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "precipitation_sum",
        "timezone": "Asia/Taipei",
        "past_days": past_days,
        "forecast_days": 1,
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
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,"PingFang TC","Microsoft JhengHei",sans-serif;background:#f5f6f3;color:#1f2933}}
  .header{{background:linear-gradient(135deg,#1f3a2e,#4caf73);color:white;padding:18px 16px;text-align:center}}
  .header h1{{margin:0;font-size:20px;font-weight:700}}
  .header p{{margin:4px 0 0;color:#d8efde;font-size:13px}}
  .toggle{{display:flex;justify-content:center;gap:8px;padding:14px 14px 8px;background:#fff;border-bottom:none}}
  .toggle button{{padding:10px 22px;border:2px solid #d6dade;background:#fff;color:#555;font-size:15px;font-weight:600;border-radius:24px;cursor:pointer;transition:all .15s}}
  .toggle button.active{{background:#2d6a4f;color:#fff;border-color:#2d6a4f}}
  .period{{padding:8px 16px 14px;background:#fff;border-bottom:1px solid #e6e8eb;text-align:center;font-size:13px;color:#555}}
  .period strong{{color:#1f3a2e;font-weight:700;font-family:ui-monospace,Menlo,monospace}}
  #map{{width:100%;height:60vh;background:#cfe9ff}}
  .county-label{{background:rgba(255,255,255,0.85);border:1px solid rgba(0,0,0,0.15);border-radius:4px;padding:1px 5px;font-size:11px;font-weight:600;color:#1f2933;white-space:nowrap;box-shadow:0 1px 2px rgba(0,0,0,0.1)}}
  .county-label .mm{{color:#c92a2a;margin-left:3px}}
  .legend{{padding:14px 16px;background:#fff;border-top:1px solid #e6e8eb}}
  .legend-title{{font-weight:700;color:#1f3a2e;margin-bottom:8px;font-size:14px}}
  .legend-row{{display:flex;align-items:center;gap:8px;font-size:13px;margin:4px 0}}
  .legend-swatch{{width:24px;height:14px;border-radius:3px;flex-shrink:0;border:1px solid #ddd}}
  .ranking{{padding:14px 16px;background:#fff;margin-top:8px}}
  .ranking h3{{margin:0 0 10px;font-size:15px;color:#1f3a2e}}
  .ranking table{{width:100%;border-collapse:collapse;font-size:13px}}
  .ranking td{{padding:6px 4px;border-bottom:1px solid #f0f2f4}}
  .ranking td.rank{{width:32px;color:#888;font-weight:600}}
  .ranking td.county{{width:80px;font-weight:600}}
  .ranking td.mm{{text-align:right;font-family:ui-monospace,Menlo,monospace;font-weight:700}}
  .impact{{padding:14px 16px;background:#fff;margin-top:8px}}
  .impact h3{{margin:0 0 10px;font-size:15px;color:#1864ab}}
  .impact .group-title{{margin:10px 0 4px;font-size:13px;font-weight:700;color:#52616b}}
  .impact .row{{display:flex;gap:10px;font-size:13px;margin:3px 0;align-items:baseline}}
  .impact .rng{{width:90px;font-weight:700;font-family:ui-monospace,Menlo,monospace;flex-shrink:0}}
  .impact .note{{color:#1f2933;flex:1}}
  .impact .green{{color:#2d6a4f}}
  .impact .amber{{color:#a05c00}}
  .impact .red{{color:#c92a2a}}
  .impact .gray{{color:#52616b}}
  .impact .info-note{{margin-top:14px;padding:10px;background:#f5f6f3;border-left:3px solid #4caf73;border-radius:4px;font-size:12px;color:#52616b;line-height:1.6}}
  .source{{padding:14px 16px;background:#fff;margin-top:8px;border-top:2px solid #e6e8eb}}
  .source h3{{margin:0 0 10px;font-size:14px;color:#52616b}}
  .source ul{{margin:0;padding-left:20px;font-size:12px;color:#52616b;line-height:1.7}}
  .source li{{margin:3px 0}}
  .source a{{color:#1864ab;text-decoration:none;word-break:break-all}}
  .footer{{padding:14px;text-align:center;color:#888;font-size:11px;background:#f5f6f3}}
  .popup-content{{font-size:14px}}
  .popup-content strong{{color:#1f3a2e}}
</style></head>
<body>
<div class="header">
  <h1>🗺️ 全台累積雨量地圖</h1>
  <p>資料來源 Open-Meteo (ERA5)　·　22 縣市</p>
</div>

<div class="toggle">
  <button data-mode="today">今日</button>
  <button data-mode="month" class="active">本月</button>
  <button data-mode="quarter">本季 (Q{quarter})</button>
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

<div class="source">
  <h3>📚 資料來源 / 方法說明</h3>
  <ul>
    <li><strong>雨量數據</strong>：Open-Meteo Forecast API（基於 ECMWF & ERA5 reanalysis），準度約 ±10%，分辨率約 11 km。
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
  document.getElementById('ranking-title').textContent =
    (mode === 'today' ? '今日' : mode === 'month' ? '本月' : '本季') + '累積雨量排名';
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
      const modeLabel = mode === 'today' ? '今日' : mode === 'month' ? '本月累積' : '本季累積';
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
            html: name.replace('縣','').replace('市','') + '<span class="mm">' + v.toFixed(0) + '</span>',
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
    render(b.dataset.mode);
  }});
}});

render('month');
</script>
</body></html>"""


def build_html(rows: list, today: date) -> str:
    quarter = (today.month - 1) // 3 + 1

    # 算各 mode 的統計期間
    month_start = date(today.year, today.month, 1)
    month_days = (today - month_start).days + 1
    q_start_month = (quarter - 1) * 3 + 1
    quarter_start = date(today.year, q_start_month, 1)
    quarter_days = (today - quarter_start).days + 1

    periods = {
        "today": f"{today.isoformat()}（全日）",
        "month": f"{month_start.isoformat()} ~ {today.isoformat()}（共 {month_days} 天）",
        "quarter": f"{quarter_start.isoformat()} ~ {today.isoformat()}（Q{quarter}，共 {quarter_days} 天）",
    }

    legend_rows = "\n  ".join(
        f'<div class="legend-row"><div class="legend-swatch" style="background:{c}"></div>'
        f'<span style="color:#1f3a2e;font-weight:700;width:60px">{label}</span>'
        f'<span style="color:#555">{lo}–{hi if hi < 9999 else "∞"} mm</span></div>'
        for lo, hi, c, label in COLOR_BANDS
    )
    return HTML_TEMPLATE.format(
        today=today.isoformat(),
        quarter=quarter,
        data_json=json.dumps(rows, ensure_ascii=False),
        bands_json=json.dumps([[lo, hi, c, lbl] for lo, hi, c, lbl in COLOR_BANDS]),
        name_map_json=json.dumps(COUNTY_NAME_MAP, ensure_ascii=False),
        periods_json=json.dumps(periods, ensure_ascii=False),
        gen_time=time.strftime("%Y-%m-%d %H:%M"),
        legend_rows=legend_rows,
    )


def collect_rows(verbose: bool = True) -> list:
    """抓 22 縣市 90 天雨量，回傳 rows 給 HTML 用"""
    today = date.today()
    rows = []
    for i, (name, lat, lon) in enumerate(COUNTIES, 1):
        if verbose:
            print(f"  [{i:>2}/{len(COUNTIES)}] {name:<5} ({lat:.2f}, {lon:.2f}) ... ", end="", flush=True)
        try:
            daily = fetch_rainfall(lat, lon, past_days=92)
            agg = aggregate(daily, today)
            rows.append({
                "name": name, "lat": lat, "lon": lon,
                "today": agg["today"],
                "month": agg["month"],
                "quarter": agg["quarter"],
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
