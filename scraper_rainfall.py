"""
中央氣象署 雨量資料抓取
- 用 O-A0003-001 自動氣象站 (有 24h 累積) 或 O-A0002-001 自動雨量站
- 每次跑：抓 4 區代表站今日讀數
- 累積到 snapshots/rainfall_YYYYMM.json
- 同時統計本月、本季累積

API 文件：https://opendata.cwa.gov.tw/dist/opendata-swagger.html
"""

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from email_sender import _load_env
from config import (
    RAINFALL_QUARTERLY_WATCH,
    RAINFALL_REGIONS,
    RAINFALL_STATIONS,
    RAINFALL_THRESHOLDS,
    SNAPSHOT_DIR,
)

API_BASE = "https://opendata.cwa.gov.tw/api/v1/rest/datastore"
# 自動雨量站（O-A0002-001）— RainfallElement 有 Past1hr~Past3days 累積
ENDPOINT = "O-A0002-001"


def _get_api_key() -> str:
    _load_env()
    key = os.environ.get("CWA_API_KEY", "").strip()
    if not key:
        raise RuntimeError("缺少 CWA_API_KEY（中央氣象署 API 授權碼）")
    return key


def _snapshot_path(today: Optional[date] = None) -> Path:
    today = today or date.today()
    return Path(SNAPSHOT_DIR) / f"rainfall_{today.year}{today.month:02d}.json"


def fetch_region_max(stations: Optional[List[Dict]] = None) -> Dict[str, Dict]:
    """按 4 區設定 group 取最大雨量，回傳 {region: {past24h, past3d, station, county, town}}
    每區可指定 counties + 可選 townships（聚焦特定鄉鎮）"""
    if stations is None:
        stations = fetch_all_stations()

    # 建立每區的篩選條件
    region_filters = {}  # region -> (counties_set, townships_set_or_None)
    for cfg in RAINFALL_REGIONS:
        towns = set(cfg.get("townships", []))
        region_filters[cfg["region"]] = (set(cfg["counties"]),
                                           towns if towns else None)

    result = {r["region"]: {"past24h": 0.0, "past3d": 0.0,
                              "station": "", "county": "", "town": ""}
              for r in RAINFALL_REGIONS}

    for s in stations:
        geo = s.get("GeoInfo", {})
        county = geo.get("CountyName", "")
        town = geo.get("TownName", "")
        re_data = s.get("RainfallElement", {})
        p24 = _to_float(re_data.get("Past24hr", {}).get("Precipitation"))
        p3d = _to_float(re_data.get("Past3days", {}).get("Precipitation"))

        for region, (counties, townships) in region_filters.items():
            if county not in counties:
                continue
            if townships is not None and town not in townships:
                continue
            # 此站可代表此區，看是否創新高
            if p24 > result[region]["past24h"] or (
                p24 == result[region]["past24h"] and p3d > result[region]["past3d"]
            ):
                result[region] = {
                    "past24h": round(p24, 1),
                    "past3d": round(p3d, 1),
                    "station": s.get("StationName", ""),
                    "county": county,
                    "town": town,
                }
    return result


def _to_float(v) -> float:
    """字串轉 float，無效資料回 0"""
    try:
        f = float(v)
        # CWA 用 -99 表示無資料
        return max(0.0, f) if f > -90 else 0.0
    except (ValueError, TypeError):
        return 0.0


def _parse_24h_rainfall(station_data: Dict) -> float:
    """抽出 Past24hr 累積雨量 (mm)"""
    if not station_data:
        return 0.0
    re_data = station_data.get("RainfallElement", {})
    past24 = re_data.get("Past24hr", {})
    return _to_float(past24.get("Precipitation"))


def _parse_3days_rainfall(station_data: Dict) -> float:
    """抽出 Past3days 累積雨量 (mm)，用於短期警示"""
    if not station_data:
        return 0.0
    re_data = station_data.get("RainfallElement", {})
    past3d = re_data.get("Past3days", {})
    return _to_float(past3d.get("Precipitation"))


def fetch_all_stations() -> List[Dict]:
    """抓全國所有雨量站，回傳 list（用於縣市排名）"""
    key = _get_api_key()
    url = f"{API_BASE}/{ENDPOINT}"
    try:
        r = requests.get(url, params={"Authorization": key, "format": "JSON"}, timeout=60)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[Rainfall] 全國測站抓取失敗：{e}")
        return []
    return data.get("records", {}).get("Station", [])


def get_county_top(metric: str = "Past24hr", top_n: int = 3,
                    stations: Optional[List[Dict]] = None) -> List[Dict]:
    """按縣市取最高雨量站，回傳 top N（重災排名）"""
    if stations is None:
        stations = fetch_all_stations()
    by_county = {}  # {county: (max_mm, station_name)}
    for s in stations:
        county = s.get("GeoInfo", {}).get("CountyName", "")
        if not county:
            continue
        re_data = s.get("RainfallElement", {})
        mm = _to_float(re_data.get(metric, {}).get("Precipitation"))
        sname = s.get("StationName", "")
        if county not in by_county or mm > by_county[county][0]:
            by_county[county] = (mm, sname)

    ranked = sorted(
        [{"county": c, "mm": round(mm, 1), "station": st}
         for c, (mm, st) in by_county.items()],
        key=lambda x: -x["mm"],
    )
    return ranked[:top_n]


def get_township_top(metric: str = "Past24hr", top_n: int = 5,
                      stations: Optional[List[Dict]] = None) -> List[Dict]:
    """按 (縣市, 鄉鎮) 取最高雨量站，回傳 top N（鄉鎮級重災排名）"""
    if stations is None:
        stations = fetch_all_stations()
    by_town = {}  # {(county, town): (max_mm, station_name)}
    for s in stations:
        geo = s.get("GeoInfo", {})
        county = geo.get("CountyName", "")
        town = geo.get("TownName", "")
        if not county or not town:
            continue
        re_data = s.get("RainfallElement", {})
        mm = _to_float(re_data.get(metric, {}).get("Precipitation"))
        sname = s.get("StationName", "")
        key = (county, town)
        if key not in by_town or mm > by_town[key][0]:
            by_town[key] = (mm, sname)

    ranked = sorted(
        [{"county": c, "town": t, "mm": round(mm, 1), "station": st}
         for (c, t), (mm, st) in by_town.items()],
        key=lambda x: -x["mm"],
    )
    return ranked[:top_n]


def get_map_data(stations: Optional[List[Dict]] = None,
                  min_rainfall: float = 0.0) -> List[Dict]:
    """為 dashboard 雨量泡泡圖準備座標資料
    回傳 [{lat, lon, county, town, station, past24h, past3d}, ...]
    min_rainfall: 過濾 0 雨量站（預設全部）"""
    if stations is None:
        stations = fetch_all_stations()
    out = []
    for s in stations:
        geo = s.get("GeoInfo", {})
        coords = geo.get("Coordinates", [])
        wgs = next((c for c in coords if c.get("CoordinateName") == "WGS84"), {})
        try:
            lat = float(wgs.get("StationLatitude", 0))
            lon = float(wgs.get("StationLongitude", 0))
        except (ValueError, TypeError):
            continue
        if not (20 < lat < 26 and 119 < lon < 123):  # 台灣範圍
            continue
        re_data = s.get("RainfallElement", {})
        past24h = _to_float(re_data.get("Past24hr", {}).get("Precipitation"))
        past3d = _to_float(re_data.get("Past3days", {}).get("Precipitation"))
        # 過濾極端值
        if max(past24h, past3d) < min_rainfall:
            continue
        out.append({
            "lat": lat,
            "lon": lon,
            "county": geo.get("CountyName", ""),
            "town": geo.get("TownName", ""),
            "station": s.get("StationName", ""),
            "past24h": round(past24h, 1),
            "past3d": round(past3d, 1),
        })
    return out


def assess_24h_level(mm: float) -> str:
    """單日雨量級距判讀"""
    if mm < 10: return "正常"
    if mm < 30: return "輕雨"
    if mm < 50: return "養分流失"
    if mm < 80: return "不宜施肥"
    return "豪雨警戒"


def assess_3days_level(mm: float) -> str:
    """連續累積級距判讀"""
    if mm < 50: return "正常"
    if mm < 100: return "黏土泥濘"
    if mm < 150: return "全面影響"
    return "田面積水"


def update_snapshot(today: Optional[date] = None,
                     stations: Optional[List[Dict]] = None) -> Dict:
    """抓當前觀測，累積到本月 snapshot 並回傳完整月份資料
    用 4 區農業大縣 group 取最大值（不再用單一市區站）"""
    today = today or date.today()
    path = _snapshot_path(today)

    if path.exists():
        try:
            month_data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            month_data = {}
    else:
        month_data = {}
    month_data.setdefault("days", {})

    region_max = fetch_region_max(stations=stations)
    today_key = today.isoformat()
    today_record = month_data["days"].get(today_key, {})
    month_data.setdefault("recent_3days", {})
    month_data.setdefault("region_meta", {})  # 記錄站點名稱用

    for region, data in region_max.items():
        today_record[region] = data["past24h"]
        month_data["recent_3days"][region] = data["past3d"]
        month_data["region_meta"][region] = {
            "station": data["station"],
            "county": data["county"],
            "town": data.get("town", ""),
        }
    month_data["days"][today_key] = today_record
    month_data["last_updated"] = datetime.now().isoformat(timespec="seconds")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(month_data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return month_data


def _region_keys() -> List[str]:
    return [r["region"] for r in RAINFALL_REGIONS]


def get_monthly_accumulation(today: Optional[date] = None) -> Dict[str, float]:
    """回傳 {region: 本月至今累積 mm}"""
    today = today or date.today()
    path = _snapshot_path(today)
    totals = {r: 0.0 for r in _region_keys()}
    if not path.exists():
        return totals
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return totals
    for day_record in data.get("days", {}).values():
        for region, mm in day_record.items():
            if region in totals:
                totals[region] += float(mm or 0)
    return {k: round(v, 1) for k, v in totals.items()}


def get_quarterly_accumulation(today: Optional[date] = None) -> Dict[str, float]:
    """回傳 {region: 本季至今累積 mm}"""
    today = today or date.today()
    q = (today.month - 1) // 3 + 1
    q_months = [(q - 1) * 3 + i + 1 for i in range(3)]

    totals = {r: 0.0 for r in _region_keys()}
    for m in q_months:
        if m > today.month:
            break
        path = Path(SNAPSHOT_DIR) / f"rainfall_{today.year}{m:02d}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for day_record in data.get("days", {}).values():
            for region, mm in day_record.items():
                if region in totals:
                    totals[region] += float(mm or 0)
    return {k: round(v, 1) for k, v in totals.items()}


def get_recent_3days(today: Optional[date] = None) -> Dict[str, float]:
    """回傳 {region: 近 3 日累積 mm}"""
    today = today or date.today()
    path = _snapshot_path(today)
    if not path.exists():
        return {r: 0.0 for r in _region_keys()}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {r: 0.0 for r in _region_keys()}
    return data.get("recent_3days", {})


def get_region_meta(today: Optional[date] = None) -> Dict[str, Dict]:
    """回傳 {region: {station, county}}：該區當期最大雨量是哪個站"""
    today = today or date.today()
    path = _snapshot_path(today)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data.get("region_meta", {})


def assess_business_impact(monthly_mm: float, quarterly_mm: float, month: int) -> Dict:
    """根據閾值給出業務影響等級與文字"""
    th = RAINFALL_THRESHOLDS
    q_watch = RAINFALL_QUARTERLY_WATCH.get((month - 1) // 3 + 1, 600)

    if monthly_mm < th["normal"]:
        level = "正常"
        color = "#2d6a4f"
        note = "施肥黃金期"
    elif monthly_mm < th["watch"]:
        level = "普通"
        color = "#52616b"
        note = "看天氣空檔出貨"
    elif monthly_mm < th["warning"]:
        level = "留意"
        color = "#a05c00"
        note = "銷量預期下滑 20-30%"
    else:
        level = "警戒"
        color = "#c92a2a"
        note = "出貨低谷，延後排程"

    quarterly_alert = quarterly_mm > q_watch

    return {
        "monthly_level": level,
        "monthly_color": color,
        "monthly_note": note,
        "quarterly_alert": quarterly_alert,
        "quarterly_watch_value": q_watch,
    }


def scrape_all(today: Optional[date] = None) -> Dict:
    """主入口：更新 snapshot，回傳組裝好的 4 區雨量摘要
    優化：所有資料共用一次全國 API 抓取"""
    today = today or date.today()
    print(f"[Rainfall] 抓取全台 1000+ 雨量站 ...")
    try:
        # 一次抓全國，給所有子功能共用
        all_stations = fetch_all_stations()
        if not all_stations:
            raise RuntimeError("CWA API 無回應")
        update_snapshot(today, stations=all_stations)
    except RuntimeError as e:
        print(f"[Rainfall] 略過：{e}")
        return {"regions": [], "skipped": True}

    monthly = get_monthly_accumulation(today)
    quarterly = get_quarterly_accumulation(today)
    recent_3d = get_recent_3days(today)
    region_meta = get_region_meta(today)

    regions = []
    for cfg in RAINFALL_REGIONS:
        region = cfg["region"]
        m_mm = monthly.get(region, 0)
        q_mm = quarterly.get(region, 0)
        r3 = recent_3d.get(region, 0)
        meta = region_meta.get(region, {})
        impact = assess_business_impact(m_mm, q_mm, today.month)
        regions.append({
            "region": region,
            "station": f"{meta.get('county','')}{meta.get('town','')} {meta.get('station','')}".strip() or "—",
            "monthly_mm": m_mm,
            "quarterly_mm": q_mm,
            "recent_3days_mm": r3,
            **impact,
        })

    print(f"[Rainfall] 4 區資料已更新（snapshot: {_snapshot_path(today).name}）")
    for r in regions:
        print(f"  {r['region']:<4} ({r['station']:<14}) 近3日 {r['recent_3days_mm']:>5} mm　月 {r['monthly_mm']:>5}　季 {r['quarterly_mm']:>5}　[{r['monthly_level']}]")

    # 全台排名 + 泡泡圖（共用前面抓的 stations）
    top_24h = get_county_top("Past24hr", top_n=3, stations=all_stations)
    top_3days = get_county_top("Past3days", top_n=3, stations=all_stations)
    top_24h_town = get_township_top("Past24hr", top_n=5, stations=all_stations)
    top_3days_town = get_township_top("Past3days", top_n=5, stations=all_stations)
    map_data = get_map_data(stations=all_stations, min_rainfall=0.5)
    print(f"  縣市 24h TOP 1: {top_24h[0] if top_24h else '無'}")
    print(f"  鄉鎮 24h TOP 1: {top_24h_town[0] if top_24h_town else '無'}")
    print(f"  泡泡圖資料：{len(map_data)} 站（有雨）")

    # 月期間
    month_start = date(today.year, today.month, 1)
    # 季期間
    q = (today.month - 1) // 3 + 1
    q_start_month = (q - 1) * 3 + 1
    quarter_start = date(today.year, q_start_month, 1)

    return {
        "today": today.isoformat(),
        "quarter": q,
        "month_period": f"{month_start.isoformat()} ~ {today.isoformat()}",
        "quarter_period": f"{quarter_start.isoformat()} ~ {today.isoformat()}",
        "regions": regions,
        "top_24h": top_24h,
        "top_3days": top_3days,
        "top_24h_town": top_24h_town,
        "top_3days_town": top_3days_town,
        "map_data": map_data,
        "skipped": False,
    }


if __name__ == "__main__":
    result = scrape_all()
    print(json.dumps(result, ensure_ascii=False, indent=2))
