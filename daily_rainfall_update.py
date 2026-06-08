"""
每日雨量 snapshot 更新 — 給 GitHub Actions cron 每天跑一次
不推 LINE / 不寄 Email / 不消耗任何外部配額
純粹抓 CWA 雨量 + 累積到 snapshots/rainfall_YYYYMM.json

為什麼需要：scraper_rainfall.update_snapshot() 每天會抓「過去 24h 雨量最大值」
存到 days[YYYY-MM-DD]，月累積 = 該月所有 days 的加總。
所以每天都要跑一次，月累積才會反映真實降雨；
若只在週推播時跑，等於整月只計入 4-5 天的數據，會嚴重低估。
"""

import sys
import traceback
from datetime import datetime

import scraper_rainfall


def main() -> int:
    print("=" * 60)
    print("每日雨量 snapshot 更新")
    print(f"執行時間: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 60)

    try:
        result = scraper_rainfall.scrape_all()
    except Exception as e:
        print(f"\n[!] 雨量抓取拋例外：{e}")
        traceback.print_exc()
        return 1

    if not result or result.get("skipped"):
        print("\n[!] CWA API 沒回資料（可能金鑰失效或暫時掛掉）— 不阻塞，下次再試")
        return 0  # 不算失敗（避免 cron 一次 fail 就一直警告）

    regions = result.get("regions", [])
    print(f"\n✓ 已更新 {len(regions)} 區雨量資料到 snapshot")
    print("  下次推播（週一 8:00）會用到這份累積後的數據")
    return 0


if __name__ == "__main__":
    sys.exit(main())
