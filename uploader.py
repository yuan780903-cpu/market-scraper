"""
HTML / 圖片公開上傳 — 主用 catbox.moe (永久 URL)，失敗 fallback 到 litterbox (72h)
回傳可直接給 LINE 訊息用的 URL
"""

from pathlib import Path
from typing import Union

import requests


def _upload(file_data: bytes, filename: str, mime: str) -> str:
    """通用上傳函式：先 catbox 主站，失敗 fallback litterbox 72h"""
    # 1) catbox 主站（永久）
    try:
        r = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (filename, file_data, mime)},
            timeout=60,
        )
        url = r.text.strip()
        if r.status_code == 200 and url.startswith("http"):
            return url
        print(f"  [!] catbox 回應異常 ({r.status_code}): {url[:100]}")
    except requests.RequestException as e:
        print(f"  [!] catbox 失敗: {e}，改用 litterbox (72h)")

    # 2) Fallback: litterbox 72h
    try:
        r = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "72h"},
            files={"fileToUpload": (filename, file_data, mime)},
            timeout=60,
        )
        url = r.text.strip()
        if r.status_code == 200 and url.startswith("http"):
            return url
        raise RuntimeError(f"litterbox 回應異常: {r.status_code} / {url[:100]}")
    except requests.RequestException as e:
        raise RuntimeError(f"所有上傳服務都失敗：{e}")


def upload_html(html_content: str, filename: str = "report.html") -> str:
    """上傳 HTML 字串到公開檔案 host，回傳公開 URL。"""
    return _upload(html_content.encode("utf-8"), filename, "text/html")


def upload_image(image_path: Union[str, Path]) -> str:
    """上傳本機 PNG/JPG 檔到公開 host，回傳公開 URL。"""
    p = Path(image_path)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    return _upload(p.read_bytes(), p.name, mime)


if __name__ == "__main__":
    sample = "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Test</title></head><body><h1>Hello</h1></body></html>"
    url = upload_html(sample)
    print(f"OK: {url}")
