"""
週報 LINE 推播主流程
- 爬最新資料、產 HTML
- 上傳 HTML 到公開 host (catbox.moe)
- 生成 LINE 文字摘要 + URL
- 用 Messaging API broadcast 推給官方帳號所有粉絲

可獨立執行：python3 weekly_line_push.py
也可加 --dry-run 看訊息但不真的推
"""

import os
import sys
import traceback
from datetime import datetime

import pandas as pd

import json

import scraper_gov
import scraper_news
import scraper_pdf
import scraper_facebook
import scraper_rainfall
import motivation_picker
import report
import dashboard
import email_sender
import uploader
import line_flex
import line_sender
import image_card
import richmenu_deploy
from config import OUTPUT_DIR


def main(dry_run: bool = False) -> None:
    print("=" * 60)
    print("週報 LINE 推播")
    print(f"開始時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if dry_run:
        print("（dry-run：產內容但不真的推 LINE）")
    print("=" * 60)

    # 1. 爬資料
    pdf_result = None
    try:
        pdf_result = scraper_pdf.scrape_all()
    except Exception as e:
        print(f"[!] PDF 流程失敗：{e}")
        traceback.print_exc()

    rows = []
    rows.extend(scraper_gov.scrape_all())
    rows.extend(scraper_news.scrape_all())
    try:
        rows.extend(scraper_facebook.scrape_all())
    except Exception as e:
        print(f"[!] FB 流程失敗（已忽略）：{e}")

    # 雨量資料（沒設 CWA_API_KEY 會自動跳過）
    rainfall_result = None
    try:
        rainfall_result = scraper_rainfall.scrape_all()
    except Exception as e:
        print(f"[!] 雨量流程失敗（已忽略）：{e}")

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df = df.drop_duplicates(subset=["連結"]).reset_index(drop=True)
    rows = df.to_dict(orient="records") if not df.empty else []

    # 1.9 挑選本期金句+銷售手段（dry-run 不消耗，傳給 dashboard 與 Flex 共用）
    motivation_picked = motivation_picker.pick_quote_and_tactic(mark_used=not dry_run)

    # 2. 產 Dashboard HTML（含 Taiwan 雨量泡泡圖 + 業務充電站）
    html_body = dashboard.generate_dashboard(rows, pdf_result=pdf_result,
                                              rainfall_result=rainfall_result,
                                              motivation_picked=motivation_picked)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    html_path = os.path.join(OUTPUT_DIR, f"市場週報_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_body)
    print(f"\n[HTML] 本機備份：{html_path}")

    # 3. 上傳 dashboard 取得公開 URL
    print("[Upload] 上傳 dashboard 到 catbox.moe ...")
    try:
        report_url = uploader.upload_html(
            html_body, filename=f"market_weekly_{timestamp}.html"
        )
        print(f"[Upload] ✓ 公開 URL：{report_url}")
    except Exception as e:
        print(f"[!] 上傳失敗：{e}")
        report_url = ""

    # 3.5 只生成節氣圖片給 Rich Menu 用（推送的卡片改用 Flex bubble）
    print("\n[Image] 生成節氣圖（供 Rich Menu 連結用）...")
    image_messages = []  # 不再推圖片，全部走 Flex carousel
    solar_url = ""
    try:
        solar_img = image_card.make_solar_term_image()
        solar_url = uploader.upload_image(solar_img)
        print(f"[Image] 節氣卡 URL：{solar_url}")
    except Exception as e:
        print(f"[!] 節氣圖產製失敗（已忽略）：{e}")

    # 4. 生成 LINE Flex Message Carousel（金句已挑、不會重複消耗）
    flex_msg = line_flex.build_flex(rows, pdf_result, report_url,
                                     mark_motivation_used=False,
                                     rainfall_result=rainfall_result,
                                     motivation_picked=motivation_picked)
    flex_json = json.dumps(flex_msg, ensure_ascii=False)

    print("\n" + "-" * 60)
    print("LINE Flex Message 預覽：")
    print("-" * 60)
    print(f"altText: {flex_msg['altText']}")
    print(f"JSON 大小: {len(flex_json)} bytes (上限 50KB)")

    container = flex_msg.get("contents", {})
    if container.get("type") == "carousel":
        bubbles = container.get("contents", [])
        print(f"Carousel 共 {len(bubbles)} 張卡片：")
        for i, b in enumerate(bubbles, 1):
            header = b.get("header", {}).get("contents", [])
            title = header[0].get("text", "") if header else ""
            subtitle = header[1].get("text", "") if len(header) > 1 else ""
            item_count = len(b.get("body", {}).get("contents", []))
            print(f"  {i:2}. {title}  ({subtitle})  - {item_count} 行")
    print(f"按鈕連結：{report_url or '(無)'}")
    print("-" * 60)

    # 5. 推 LINE：圖片 + Flex 一次推（LINE 單次 broadcast 上限 5 則）
    all_messages = image_messages + [flex_msg]
    print(f"\n[LINE] 準備推送 {len(all_messages)} 則訊息（{len(image_messages)} 圖片 + 1 Flex）")

    if dry_run:
        print("[Dry-run] 略過實際推送")
        with open(os.path.join(OUTPUT_DIR, "last_flex.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(flex_msg, ensure_ascii=False, indent=2))
        return

    try:
        line_sender.broadcast_messages(all_messages)
    except Exception as e:
        print(f"\n[!] LINE 推播失敗：{e}")
        sys.exit(1)

    # 6. 同步更新 Rich Menu 兩個動態按鈕的 URL（最新週報 / 節氣施肥）
    if report_url or solar_url:
        print("\n[RichMenu] 同步更新 Rich Menu 按鈕 URL ...")
        try:
            richmenu_deploy.deploy(report_url=report_url, solar_url=solar_url)
        except Exception as e:
            print(f"[!] Rich Menu 更新失敗（已忽略）：{e}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
