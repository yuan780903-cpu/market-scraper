"""
節氣計算 — 給定日期回傳當前節氣（最近一個已過的節氣）
資料表涵蓋 2026-2027，日期準度 ±1 天
"""

from datetime import date
from typing import Tuple

# 24 節氣對照表（西元日期，準度 ±1 天可接受）
# 涵蓋 2026 全年 + 2027 初的 小寒/大寒（處理跨年）
SOLAR_TERMS = [
    ("立春", date(2026, 2, 4)),
    ("雨水", date(2026, 2, 19)),
    ("驚蟄", date(2026, 3, 5)),
    ("春分", date(2026, 3, 20)),
    ("清明", date(2026, 4, 5)),
    ("穀雨", date(2026, 4, 20)),
    ("立夏", date(2026, 5, 5)),
    ("小滿", date(2026, 5, 21)),
    ("芒種", date(2026, 6, 5)),
    ("夏至", date(2026, 6, 21)),
    ("小暑", date(2026, 7, 7)),
    ("大暑", date(2026, 7, 23)),
    ("立秋", date(2026, 8, 7)),
    ("處暑", date(2026, 8, 23)),
    ("白露", date(2026, 9, 7)),
    ("秋分", date(2026, 9, 23)),
    ("寒露", date(2026, 10, 8)),
    ("霜降", date(2026, 10, 23)),
    ("立冬", date(2026, 11, 7)),
    ("小雪", date(2026, 11, 22)),
    ("大雪", date(2026, 12, 7)),
    ("冬至", date(2026, 12, 21)),
    ("小寒", date(2027, 1, 5)),
    ("大寒", date(2027, 1, 20)),
    # 跨年銜接 2027 立春
    ("立春", date(2027, 2, 4)),
]


def current_and_next(today: date = None) -> Tuple[str, date, str, date]:
    """回傳 (當前節氣名, 當前節氣起始日, 下一節氣名, 下一節氣起始日)"""
    if today is None:
        today = date.today()

    # 找最近一個 <= today 的節氣
    current_name, current_date = SOLAR_TERMS[0]
    next_name, next_date = SOLAR_TERMS[1]
    for i, (name, d) in enumerate(SOLAR_TERMS):
        if d <= today:
            current_name, current_date = name, d
            if i + 1 < len(SOLAR_TERMS):
                next_name, next_date = SOLAR_TERMS[i + 1]
        else:
            break
    return current_name, current_date, next_name, next_date


def current_term(today: date = None) -> str:
    """簡化版：只回傳當前節氣名"""
    return current_and_next(today)[0]


if __name__ == "__main__":
    today = date.today()
    name, start, next_name, next_start = current_and_next(today)
    days_in = (today - start).days
    days_to_next = (next_start - today).days
    print(f"今日：{today}")
    print(f"當前節氣：{name}（{start.isoformat()}）已過 {days_in} 天")
    print(f"下一節氣：{next_name}（{next_start.isoformat()}）還有 {days_to_next} 天")
