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
import report
import uploader
import line_flex
import line_sender
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

    # 5. 推 LINE
    if dry_run:
        print("\n[Dry-run] 略過實際推送")
        print("\n（要看完整 JSON 可看 output/last_flex.json）")
        with open(os.path.join(OUTPUT_DIR, "last_flex.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(flex_msg, ensure_ascii=False, indent=2))
        return

    try:
        line_sender.broadcast_flex(flex_msg)
    except Exception as e:
        print(f"\n[!] LINE 推播失敗：{e}")
        sys.exit(1)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
