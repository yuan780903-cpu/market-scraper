"""
從 snapshots/license_index.json 重新產出兩份 HTML 目錄頁並上傳 catbox：
  - 肥料登記證目錄（多張產品卡）
  - 營運許可證目錄
產生後驗證遠端檔案非 0 bytes，再把新 URL 寫回 JSON、回傳給呼叫端使用。
獨立執行：python3 license_publisher.py
"""

import json
from datetime import date
from pathlib import Path

import requests

import uploader

SNAPSHOT = Path("snapshots/license_index.json")
OUT_DIR = Path("output")

CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang TC","Microsoft JhengHei",sans-serif;background:#f5f6f3;color:#1f2933;line-height:1.6}
.container{max-width:780px;margin:0 auto;padding:24px 16px}
.hero{background:linear-gradient(135deg,#1f3a2e,#4caf73);color:white;padding:28px;border-radius:14px;margin-bottom:20px}
.hero h1{margin:0;font-size:22px}
.hero p{margin:6px 0 0;color:#d8efde;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}
.card{background:white;border-radius:12px;padding:20px;text-decoration:none;color:inherit;box-shadow:0 1px 4px rgba(0,0,0,0.06);transition:transform .15s;display:block}
.card:active{transform:scale(0.98)}
.icon{font-size:38px;text-align:center;margin-bottom:8px}
.name{font-size:17px;font-weight:600;color:#1f3a2e;text-align:center}
.cert{font-size:13px;color:#888;text-align:center;font-family:ui-monospace,Menlo,monospace;margin-top:4px;min-height:18px}
.btn{margin-top:14px;background:#2d6a4f;color:white;padding:10px;border-radius:8px;text-align:center;font-size:14px;font-weight:600}
.footer{text-align:center;color:#888;font-size:12px;margin-top:24px;padding:16px 0}
"""


def _card(item: dict) -> str:
    name = item.get("name", "")
    cert = item.get("cert", "") or ""
    url = item.get("url", "")
    cert_html = f"登記證字號 {cert}" if cert else "&nbsp;"
    return (
        f'<a class="card" href="{url}" target="_blank" rel="noopener">'
        f'<div class="icon">📄</div>'
        f'<div class="name">{name}</div>'
        f'<div class="cert">{cert_html}</div>'
        f'<div class="btn">點此查看 / 下載 PDF</div>'
        f'</a>'
    )


def _build_html(title: str, subtitle: str, items: list, updated: str) -> str:
    cards = "\n      ".join(_card(it) for it in items)
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{CSS}</style></head>
<body><div class="container">
  <header class="hero"><h1>{title}</h1><p>{subtitle}</p></header>
  <div class="grid">
      {cards}
  </div>
  <div class="footer">最後更新 {updated} · 大成長城企業股份有限公司有機肥料部 · 業務聯絡 0910-373286</div>
</div></body></html>"""


def _verify_remote(url: str) -> int:
    """回傳遠端檔案大小（bytes）。catbox 對 HEAD 不一定回 Content-Length，
    所以直接 GET 一次拿整個 body。檔案小（< 10 KB），不用 stream。"""
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            print(f"    GET 回 {r.status_code}")
            return 0
        return len(r.content)
    except Exception as e:
        print(f"    GET 拋例外：{e}")
        return -1


def _upload_with_verify(html: str, filename: str, max_retry: int = 3) -> str:
    """上傳 HTML 並驗證遠端非空檔；失敗會重試。"""
    last_url = ""
    for attempt in range(1, max_retry + 1):
        url = uploader.upload_html(html, filename=filename)
        size = _verify_remote(url)
        print(f"  [try {attempt}] 上傳 → {url} (遠端 {size} bytes)")
        if size > 100:
            return url
        last_url = url
        print(f"  ⚠ 遠端檔案太小，重試 ...")
    raise RuntimeError(f"上傳後遠端仍為空檔（最後一次：{last_url}）")


def publish() -> dict:
    """產出 + 上傳 + 寫回 snapshot，回傳更新後的 index dict。"""
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    updated = date.today().isoformat()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 肥料登記證
    print("\n[1] 產 + 上傳『肥料登記證』目錄頁 ...")
    licenses = data.get("licenses", [])
    print(f"    共 {len(licenses)} 張產品")
    lic_html = _build_html(
        title="碩成肥料 - 肥料登記證",
        subtitle="農糧署核發 · 點擊任一產品查看登記證 PDF",
        items=licenses,
        updated=updated,
    )
    (OUT_DIR / "license_index.html").write_text(lic_html, encoding="utf-8")
    lic_url = _upload_with_verify(lic_html, "license_index.html")

    # 2. 營運許可證
    print("\n[2] 產 + 上傳『營運許可證』目錄頁 ...")
    operations = data.get("operations", [])
    print(f"    共 {len(operations)} 張")
    op_html = _build_html(
        title="碩成肥料 - 營運許可證",
        subtitle="農糧署核發 · 點擊查看營運許可證 PDF",
        items=operations,
        updated=updated,
    )
    (OUT_DIR / "operation_index.html").write_text(op_html, encoding="utf-8")
    op_url = _upload_with_verify(op_html, "operation_index.html")

    # 3. 寫回 snapshot
    data["license_index_url"] = lic_url
    data["operation_index_url"] = op_url
    data["updated"] = updated
    SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[3] 已寫回 snapshots/license_index.json")

    return {"license_index_url": lic_url, "operation_index_url": op_url}


if __name__ == "__main__":
    print("=" * 60)
    print("肥料登記證 / 營運許可證 目錄頁重發布")
    print("=" * 60)
    urls = publish()
    print("\n" + "=" * 60)
    print("完成 — 新 URL：")
    print(f"  肥料登記證: {urls['license_index_url']}")
    print(f"  營運許可證: {urls['operation_index_url']}")
    print("=" * 60)
