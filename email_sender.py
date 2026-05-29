"""
Gmail SMTP 寄信
- 從 .env 讀帳密（GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO）
- 寄 HTML 內文 + Excel 附件
"""

import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path


def _load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def send_report(html_body: str, attachment_path: str = None, subject: str = None):
    _load_env()

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    mail_to = os.environ.get("MAIL_TO") or gmail_user

    if not gmail_user or not gmail_pass:
        raise RuntimeError(
            "缺少 GMAIL_USER 或 GMAIL_APP_PASSWORD。\n"
            "請複製 .env.example 為 .env 並填入帳密。\n"
            "App Password 申請：https://myaccount.google.com/apppasswords"
        )

    if subject is None:
        subject = f"有機肥料市場日報 {datetime.now().strftime('%Y-%m-%d')}"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = mail_to
    msg.set_content("此信為 HTML 格式，若無法顯示請改用支援 HTML 的郵件 App")
    msg.add_alternative(html_body, subtype="html")

    if attachment_path and Path(attachment_path).exists():
        with open(attachment_path, "rb") as f:
            data = f.read()
        filename = Path(attachment_path).name
        msg.add_attachment(
            data,
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(gmail_user, gmail_pass)
        server.send_message(msg)

    print(f"[Mail] ✓ 已寄到 {mail_to}")


if __name__ == "__main__":
    send_report(
        "<h1>測試</h1><p>這是測試信</p>",
        subject="[測試] 有機肥料爬蟲寄信測試",
    )
