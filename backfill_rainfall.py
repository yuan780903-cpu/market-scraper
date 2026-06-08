"""
回填歷史雨量到 snapshot — 用 Open-Meteo Historical API (免費,無 key,ERA5 reanalysis)

用途：CWA OpenData 只給「現在」的觀測值，daily-rainfall.yml 從今天起才會
累積，但 Q2 檢討報告需要 4/5 月歷史資料。這支腳本一次補齊。

寫入結構與現有 rainfall_YYYYMM.json 一致：
{
  "days": {
    "2026-04-01": {"北部": 8.5, "中部": 12.0, "南部": 0.5, "東部": 22.3},
    ...
  },
  "recent_3days": {...},
  "region_meta": {...},
  "last_updated": "...",
  "_source": "open-meteo-historical"  # 標記非 CWA 即時觀測
}

用法：
  python3 backfill_rainfall.py 2026-04 2026-05         # 補 2 個月
  python3 backfill_rainfall.py 2026-04                 # 補 1 個月
"""

import json
import sys
import time
from calendar import monthrange
from datetime import date
from pathlib import Path

import requests

SNAPSHOT_DIR = Path("snapshots")

# 4 區代表觀測點 (lat, lon, 顯示名)
# 用各區「最會下雨的山區」或農業大縣中心，與 scraper_rainfall 的 4 區 group 概念對齊
REGION_POINTS = {
    "北部": {
        "lat": 24.85, "lon": 121.40,  # 桃園市復興區 華陵附近 (中央山脈北段迎風)
        "station": "桃園市復興區 華陵(估)",
        "county": "桃園市", "town": "復興區",
    },
    "中部": {
        "lat": 23.97, "lon": 120.97,  # 南投縣埔里鎮 北坑附近 (中央山脈中段)
        "station": "南投縣埔里鎮 北坑(估)",
        "county": "南投縣", "town": "埔里鎮",
    },
    "南部": {
        "lat": 23.08, "lon": 120.43,  # 臺南市楠西區 (中央山脈西側迎風)
        "station": "臺南市楠西區 (估)",
        "county": "臺南市", "town": "楠西區",
    },
    "東部": {
        "lat": 24.20, "lon": 121.55,  # 宜蘭縣大同鄉 太平山附近
        "station": "宜蘭縣大同鄉 太平山(估)",
        "county": "宜蘭縣", "town": "大同鄉",
    },
}


def fetch_daily_rainfall(lat: float, lon: float, start: str, end: str) -> dict:
    """回傳 {YYYY-MM-DD: precipitation_mm}"""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "precipitation_sum",
        "timezone": "Asia/Taipei",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    times = data["daily"]["time"]
    rains = data["daily"]["precipitation_sum"]
    return {t: round(float(p or 0), 1) for t, p in zip(times, rains)}


def backfill_month(year: int, month: int) -> Path:
    """為指定月份產出 snapshots/rainfall_YYYYMM.json"""
    first = date(year, month, 1).isoformat()
    last_day = monthrange(year, month)[1]
    last = date(year, month, last_day).isoformat()
    print(f"\n=== 回填 {year}-{month:02d}（{first} ~ {last}）===")

    # 每區抓
    region_dailies = {}
    for region, pt in REGION_POINTS.items():
        print(f"  [{region}] lat={pt['lat']} lon={pt['lon']} ... ", end="", flush=True)
        try:
            daily = fetch_daily_rainfall(pt["lat"], pt["lon"], first, last)
            total = sum(daily.values())
            print(f"OK，{len(daily)} 天，月累積 {total:.1f} mm")
            region_dailies[region] = daily
            time.sleep(0.3)  # 友善 API
        except Exception as e:
            print(f"FAIL：{e}")
            region_dailies[region] = {}

    # 組裝成 snapshot 格式
    days_struct = {}
    all_dates = sorted(set().union(*(d.keys() for d in region_dailies.values())))
    for d in all_dates:
        day_record = {}
        for region, daily in region_dailies.items():
            if d in daily:
                day_record[region] = daily[d]
        days_struct[d] = day_record

    # 近 3 日（用該月最後 3 天的加總，僅供顯示用）
    last_3 = all_dates[-3:] if len(all_dates) >= 3 else all_dates
    recent_3days = {}
    for region in REGION_POINTS:
        recent_3days[region] = round(
            sum(region_dailies.get(region, {}).get(d, 0) for d in last_3), 1
        )

    region_meta = {
        region: {"station": pt["station"], "county": pt["county"], "town": pt["town"]}
        for region, pt in REGION_POINTS.items()
    }

    snapshot = {
        "days": days_struct,
        "recent_3days": recent_3days,
        "region_meta": region_meta,
        "last_updated": date.today().isoformat(),
        "_source": "open-meteo-historical (ERA5 reanalysis)",
        "_note": "歷史回填數據，準確度約 ±10%，僅供月/季趨勢參考",
    }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"rainfall_{year}{month:02d}.json"
    if path.exists():
        # 不覆蓋已有資料（避免蓋掉真實 CWA 觀測）
        confirm = input(f"  ⚠ {path} 已存在。覆蓋? [y/N] ").strip().lower()
        if confirm != "y":
            print("  跳過（保留原檔）")
            return path

    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ 已寫入 {path}")

    # 統計
    totals = {region: sum(d.values()) for region, d in region_dailies.items()}
    print(f"  月累積：" + "  ".join(f"{r}:{m:.0f}mm" for r, m in totals.items()))
    return path


def main():
    args = sys.argv[1:]
    if not args:
        print("用法：python3 backfill_rainfall.py YYYY-MM [YYYY-MM ...]")
        print("例：python3 backfill_rainfall.py 2026-04 2026-05")
        sys.exit(1)

    for arg in args:
        try:
            y, m = map(int, arg.split("-"))
        except ValueError:
            print(f"⚠ 跳過格式錯誤：{arg}")
            continue
        backfill_month(y, m)

    print("\n完成。請跑 `python3 -c \"import scraper_rainfall; print(scraper_rainfall.get_quarterly_accumulation())\"` 驗證")


if __name__ == "__main__":
    main()
