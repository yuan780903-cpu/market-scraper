"""
主程式 — 一鍵跑完：爬資料 → 抓 PDF + 比對上下架 → 產 Excel + HTML → 寄 Email
用法：
  python3 main.py            # 完整流程（含寄信）
  python3 main.py --no-mail  # 只爬資料、產檔案，不寄信
"""

import os
import sys
import traceback
from datetime import datetime

import pandas as pd

import scraper_gov
import scraper_news
import scraper_pdf
import scraper_facebook
import report
import email_sender
from config import OUTPUT_DIR


def main(send_mail: bool = True):
    print("=" * 60)
    print("有機肥料市場資訊蒐集程式")
    print(f"開始時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

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

    if not rows and not pdf_result:
        print("\n沒有抓到任何資料。")
        return

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    if not df.empty:
        df = df.drop_duplicates(subset=["連結"]).reset_index(drop=True)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    xlsx_path = os.path.join(OUTPUT_DIR, f"市場資訊_{timestamp}.xlsx")
    csv_path = os.path.join(OUTPUT_DIR, f"市場資訊_{timestamp}.csv")
    html_path = os.path.join(OUTPUT_DIR, f"市場日報_{timestamp}.html")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        if not df.empty:
            df.to_excel(writer, sheet_name="新聞與公告", index=False)
            for source_type, group in df.groupby("來源類型"):
                sheet_name = source_type[:30]
                group.to_excel(writer, sheet_name=sheet_name, index=False)

        if pdf_result:
            products_df = pd.DataFrame(pdf_result["products"])
            products_df.to_excel(writer, sheet_name="推薦名單總表", index=False)

            for cat, group in products_df.groupby("品目"):
                sheet = f"品目_{cat}"[:30]
                group.to_excel(writer, sheet_name=sheet, index=False)

            days = pdf_result.get("change_days", 30)
            if pdf_result.get("recent_added"):
                pd.DataFrame(pdf_result["recent_added"]).to_excel(
                    writer, sheet_name=f"近{days}天新上架", index=False
                )
            if pdf_result.get("recent_removed"):
                pd.DataFrame(pdf_result["recent_removed"]).to_excel(
                    writer, sheet_name=f"近{days}天下架", index=False
                )
            if pdf_result.get("recent_violations"):
                pd.DataFrame(pdf_result["recent_violations"]).to_excel(
                    writer, sheet_name=f"近{days}天新違規", index=False
                )

    if not df.empty:
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    html_body = report.generate_html(
        df.to_dict(orient="records") if not df.empty else [],
        pdf_result=pdf_result,
    )
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_body)

    print("\n" + "=" * 60)
    if not df.empty:
        print(f"新聞/公告：{len(df)} 筆")
    if pdf_result:
        days = pdf_result.get("change_days", 30)
        print(f"推薦名單產品：{len(pdf_result['products'])} 筆")
        print(
            f"  近 {days} 天：新上架 {len(pdf_result.get('recent_added', []))} ｜ "
            f"下架 {len(pdf_result.get('recent_removed', []))} ｜ "
            f"新違規 {len(pdf_result.get('recent_violations', []))}"
        )
    print(f"Excel: {xlsx_path}")
    print(f"HTML:  {html_path}")
    print("=" * 60)

    if send_mail:
        try:
            # 不附 Excel；Excel 仍會存在 output/ 供本機查閱
            email_sender.send_report(html_body)
        except Exception as e:
            print(f"\n[!] 寄信失敗：{e}")
            print("HTML 與 Excel 已產出在 output/，可手動寄送")


if __name__ == "__main__":
    send_mail = "--no-mail" not in sys.argv
    main(send_mail=send_mail)
