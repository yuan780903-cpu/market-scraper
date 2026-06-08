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
import time
from datetime import date, timedelta
from pathlib import Path

import requests

OUTPUT_DIR = Path("output")

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

# 顏色級距（mm）— 給「本月累積」用；今日/本季會自動 scale
COLOR_BANDS = [
    (0, 30, "#cfe9ff", "極少"),
    (30, 80, "#7bb3eb", "少雨"),
    (80, 150, "#3a82c4", "普通"),
    (150, 300, "#1d4f93", "略多"),
    (300, 500, "#7b3aa2", "多雨"),
    (500, 800, "#c92a2a", "豪雨"),
    (800, 99999, "#6b0606", "暴雨"),
]


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
  .toggle{{display:flex;justify-content:center;gap:8px;padding:14px;background:#fff;border-bottom:1px solid #e6e8eb}}
  .toggle button{{padding:10px 22px;border:2px solid #d6dade;background:#fff;color:#555;font-size:15px;font-weight:600;border-radius:24px;cursor:pointer;transition:all .15s}}
  .toggle button.active{{background:#2d6a4f;color:#fff;border-color:#2d6a4f}}
  #map{{width:100%;height:62vh}}
  .legend{{padding:14px 16px;background:#fff;border-top:1px solid #e6e8eb}}
  .legend-title{{font-weight:700;color:#1f3a2e;margin-bottom:8px;font-size:14px}}
  .legend-row{{display:flex;align-items:center;gap:8px;font-size:13px;margin:4px 0}}
  .legend-swatch{{width:24px;height:14px;border-radius:3px;flex-shrink:0}}
  .ranking{{padding:14px 16px;background:#fff;margin-top:8px}}
  .ranking h3{{margin:0 0 10px;font-size:15px;color:#1f3a2e}}
  .ranking table{{width:100%;border-collapse:collapse;font-size:13px}}
  .ranking td{{padding:6px 4px;border-bottom:1px solid #f0f2f4}}
  .ranking td.rank{{width:32px;color:#888;font-weight:600}}
  .ranking td.county{{width:80px;font-weight:600}}
  .ranking td.mm{{text-align:right;font-family:ui-monospace,Menlo,monospace;font-weight:700}}
  .footer{{padding:14px;text-align:center;color:#888;font-size:11px;background:#f5f6f3}}
  .popup-content{{font-size:14px}}
  .popup-content strong{{color:#1f3a2e}}
</style></head>
<body>
<div class="header">
  <h1>🗺️ 全台累積雨量地圖</h1>
  <p>{today} · 資料來源 Open-Meteo (ERA5) · 22 縣市</p>
</div>

<div class="toggle">
  <button data-mode="today">今日</button>
  <button data-mode="month" class="active">本月</button>
  <button data-mode="quarter">本季 (Q{quarter})</button>
</div>

<div id="map"></div>

<div class="legend">
  <div class="legend-title">📊 顏色級距（本月 / 本季用，今日按比例縮放）</div>
  {legend_rows}
</div>

<div class="ranking" id="ranking">
  <h3 id="ranking-title">本月累積雨量排名</h3>
  <table id="ranking-table"><tbody></tbody></table>
</div>

<div class="footer">
  本機產出於 {gen_time}　·　資料涵蓋過去 92 天　·　大成長城企業有機肥料部
</div>

<script>
const DATA = {data_json};
const BANDS = {bands_json};

function pickBand(v, mode) {{
  // 今日 mode 用較小級距（÷10 因為單日 vs 月累積）
  const scale = (mode === 'today') ? 0.1 : 1.0;
  for (const [lo, hi, color, label] of BANDS) {{
    if (v >= lo * scale && v < hi * scale) return {{color, label}};
  }}
  return {{color: '#cfe9ff', label: '極少'}};
}}

const map = L.map('map').setView([23.7, 121.0], 7);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap',
  maxZoom: 18,
}}).addTo(map);

let markers = [];
function render(mode) {{
  markers.forEach(m => map.removeLayer(m));
  markers = [];
  const sorted = [...DATA].sort((a, b) => b[mode] - a[mode]);
  for (const c of DATA) {{
    const v = c[mode];
    const {{color, label}} = pickBand(v, mode);
    // 半徑：sqrt(雨量) * 5，上下限 8-40
    const r = Math.max(8, Math.min(40, Math.sqrt(Math.max(v, 1)) * (mode === 'today' ? 4 : 1.5)));
    const m = L.circleMarker([c.lat, c.lon], {{
      radius: r,
      color: '#fff',
      weight: 2,
      fillColor: color,
      fillOpacity: 0.78,
    }}).addTo(map);
    m.bindPopup(
      `<div class="popup-content"><strong>${{c.name}}</strong><br>` +
      `${{mode === 'today' ? '今日' : mode === 'month' ? '本月累積' : '本季累積'}}：` +
      `<strong style="color:${{color}};font-size:16px">${{v.toFixed(1)}} mm</strong><br>` +
      `<span style="color:#888">（${{label}}）</span></div>`
    );
    markers.push(m);
  }}
  // 排名
  document.getElementById('ranking-title').textContent =
    (mode === 'today' ? '今日' : mode === 'month' ? '本月' : '本季') + '累積雨量排名';
  const tbody = document.querySelector('#ranking-table tbody');
  tbody.innerHTML = '';
  sorted.slice(0, 10).forEach((c, i) => {{
    const {{color}} = pickBand(c[mode], mode);
    const row = document.createElement('tr');
    row.innerHTML = `<td class="rank">${{i + 1}}</td>` +
                    `<td class="county">${{c.name}}</td>` +
                    `<td class="mm" style="color:${{color}}">${{c[mode].toFixed(1)}} mm</td>`;
    tbody.appendChild(row);
  }});
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
    legend_rows = "\n  ".join(
        f'<div class="legend-row"><div class="legend-swatch" style="background:{c}"></div>'
        f'<span style="color:{c};font-weight:700;width:60px">{label}</span>'
        f'<span style="color:#555">{lo}–{hi if hi < 9999 else "∞"} mm</span></div>'
        for lo, hi, c, label in COLOR_BANDS
    )
    return HTML_TEMPLATE.format(
        today=today.isoformat(),
        quarter=quarter,
        data_json=json.dumps(rows, ensure_ascii=False),
        bands_json=json.dumps([[lo, hi, c, lbl] for lo, hi, c, lbl in COLOR_BANDS]),
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


def generate_and_upload(verbose: bool = True) -> str:
    """產地圖 HTML → 寫本機 → 上傳 catbox → 回傳 URL（失敗回 ""）。
    給 weekly_line_push 在推播前呼叫，把 URL 加進 Flex 雨量卡的 footer 按鈕。"""
    today = date.today()
    if verbose:
        print(f"[Rainfall Map] 產出全台 22 縣市互動地圖 ...")
    rows = collect_rows(verbose=verbose)
    html = build_html(rows, today)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"taiwan_rainfall_map_{today.strftime('%Y%m%d')}.html"
    out_path.write_text(html, encoding="utf-8")
    if verbose:
        print(f"[Rainfall Map] 本機備份：{out_path}")
    try:
        import uploader
        url = uploader.upload_html(
            html, filename=f"taiwan_rainfall_map_{today.strftime('%Y%m%d')}.html"
        )
        if verbose:
            print(f"[Rainfall Map] ✓ 公開 URL：{url}")
        return url
    except Exception as e:
        if verbose:
            print(f"[Rainfall Map] [!] 上傳失敗：{e}")
        return ""


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
    url = generate_and_upload(verbose=True)
    if url:
        print(f"\n🌐 catbox URL（永久）：\n  {url}")


if __name__ == "__main__":
    main()
