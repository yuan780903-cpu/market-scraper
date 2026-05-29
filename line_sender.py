"""
LINE Messaging API 推播
- 用 Channel Access Token 呼叫 Broadcast API
- Broadcast 會推給該官方帳號的所有粉絲
- 免費方案每月 200 則訊息
"""

import os
import requests

from email_sender import _load_env  # reuse 同一個 .env loader

BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
PUSH_URL = "https://api.line.me/v2/bot/message/push"


def _get_token() -> str:
    _load_env()
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "缺少 LINE_CHANNEL_ACCESS_TOKEN。\n"
            "請：\n"
            "  1. 到 https://developers.line.biz/console/ 建立 Messaging API channel\n"
            "  2. 在 'Messaging API' 分頁 issue 'Channel access token (long-lived)'\n"
            "  3. 把 token 加進 .env 檔的 LINE_CHANNEL_ACCESS_TOKEN= 後面"
        )
    return token


def _post_broadcast(messages: list) -> None:
    token = _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    r = requests.post(BROADCAST_URL, headers=headers, json={"messages": messages}, timeout=30)
    if r.status_code == 200:
        print("[LINE] ✓ 廣播訊息已推送")
        return

    try:
        body = r.json()
        msg = body.get("message", r.text)
        details = body.get("details") or []
        if details:
            msg += " | " + "; ".join(
                f"{d.get('property', '')}: {d.get('message', '')}" for d in details
            )
    except ValueError:
        msg = r.text
    if r.status_code == 401:
        raise RuntimeError(f"LINE token 無效或過期：{msg}")
    if r.status_code == 403:
        raise RuntimeError(f"LINE 權限不足（檢查 channel 設定）：{msg}")
    if r.status_code == 429:
        raise RuntimeError(f"LINE 配額用完（免費方案每月 200 則）：{msg}")
    raise RuntimeError(f"LINE 推播失敗 {r.status_code}: {msg}")


def broadcast_text(text: str) -> None:
    """推播純文字給所有官方帳號粉絲。"""
    _post_broadcast([{"type": "text", "text": text}])


def broadcast_flex(flex_message: dict) -> None:
    """推播 Flex Message 卡片。flex_message 須含 type/altText/contents。"""
    _post_broadcast([flex_message])


def push_text_to_user(user_id: str, text: str) -> None:
    """推給單一 user（測試用，需要對方先加入官方帳號並抓 user_id）。
    一般用 broadcast_text 就好。"""
    token = _get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"to": user_id, "messages": [{"type": "text", "text": text}]}
    r = requests.post(PUSH_URL, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    print(f"[LINE] ✓ 已推給 {user_id[:8]}...")


if __name__ == "__main__":
    broadcast_text("[測試] 有機肥料市場爬蟲串接 LINE 成功！")
