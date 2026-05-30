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
import report
import uploader
import line_flex
import line_sender
import image_card
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

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df = df.drop_duplicates(subset=["連結"]).reset_index(drop=True)
    rows = df.to_dict(orient="records") if not df.empty else []

    # 2. 產 HTML 報表 + 存檔備份
    html_body = report.generate_html(rows, pdf_result=pdf_result)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    html_path = os.path.join(OUTPUT_DIR, f"市場週報_{timestamp}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_body)
    print(f"\n[HTML] 本機備份：{html_path}")

    # 3. 上傳 HTML 取得公開 URL
    print("[Upload] 上傳 HTML 到 catbox.moe ...")
    try:
        report_url = uploader.upload_html(
            html_body, filename=f"market_weekly_{timestamp}.html"
        )
        print(f"[Upload] ✓ 公開 URL：{report_url}")
    except Exception as e:
        print(f"[!] 上傳失敗：{e}")
        report_url = ""

    # 3.5 生成 3 張靜態圖片卡（節氣 + 區域作物 + 業務充電站）並上傳
    print("\n[Image] 生成節氣 / 區域作物 / 業務充電站圖片卡 ...")
    image_messages = []
    try:
        solar_img = image_card.make_solar_term_image()
        crops_img = image_card.make_regional_crops_image()
        # dry-run 不消耗金句池
        motiv_img = image_card.make_motivation_image(mark_used=not dry_run)
        print(f"[Image] 已生成：{solar_img.name}, {crops_img.name}, {motiv_img.name}")
        solar_url = uploader.upload_image(solar_img)
        crops_url = uploader.upload_image(crops_img)
        motiv_url = uploader.upload_image(motiv_img)
        print(f"[Image] 節氣卡 URL：{solar_url}")
        print(f"[Image] 區域卡 URL：{crops_url}")
        print(f"[Image] 充電站 URL：{motiv_url}")
        image_messages.append(line_sender.image_message(solar_url))
        image_messages.append(line_sender.image_message(crops_url))
        image_messages.append(line_sender.image_message(motiv_url))
    except Exception as e:
        print(f"[!] 圖片卡產出/上傳失敗（已忽略）：{e}")

    # 4. 生成 LINE Flex Message
    flex_msg = line_flex.build_flex(rows, pdf_result, report_url)
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


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
