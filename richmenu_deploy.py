"""
LINE Rich Menu 自動部署
- 用 Messaging API 建立 Rich Menu
- 上傳圖（richmenu_designer 產生的 PNG）
- 設為所有用戶的預設選單
- 同時刪除舊的選單（避免累積）

兩種用法：
  python3 richmenu_deploy.py                                  # 用預設靜態 URL
  python3 richmenu_deploy.py --report URL --solar URL         # 指定動態 URL
"""

import os
import sys
import time

import requests

from email_sender import _load_env
import image_card
import richmenu_designer
import uploader

API = "https://api.line.me/v2/bot"
DATA_API = "https://api-data.line.me/v2/bot"

# 預設按鈕 URL（靜態的）
DEFAULT_REPORT_URL = "https://files.catbox.moe/"   # placeholder，可能會被命令列覆寫
DEFAULT_SOLAR_URL = "https://files.catbox.moe/"
AFA_SUBSIDY_URL = "https://www.afa.gov.tw/cht/index.php?code=list&flag=detail&ids=2212&article_id=22432"
AFA_NEWS_URL = "https://www.afa.gov.tw/cht/index.php?code=list&ids=307"
AFA_PRODSALES_URL = "https://agrpmg.afa.gov.tw/agr-Sed/agrJsp/main.jsp?page=00"
AFA_FERT_BRAND_URL = "https://fims.afa.gov.tw/WFR/PublicFun/QueryFertBrand.aspx"
AFA_FERT_LAW_URL = "https://www.afa.gov.tw/cht/index.php?code=list&ids=353&mod_code=view&a_id=176"
AFA_AGRI_REPORT_URL = "https://agr.afa.gov.tw/afa/afa_frame.jsp"


def _get_token() -> str:
    _load_env()
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 LINE_CHANNEL_ACCESS_TOKEN")
    return token


def _headers(token: str, ct: str = "application/json"):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": ct,
    }


def list_rich_menus(token: str) -> list:
    r = requests.get(f"{API}/richmenu/list", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    r.raise_for_status()
    return r.json().get("richmenus", [])


def delete_rich_menu(token: str, menu_id: str) -> None:
    r = requests.delete(f"{API}/richmenu/{menu_id}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=20)
    if r.status_code == 200:
        print(f"  ✓ 已刪除舊選單 {menu_id[:12]}…")
    else:
        print(f"  ⚠ 刪除 {menu_id[:12]}… 回 {r.status_code}: {r.text[:200]}")


def build_richmenu_payload(report_url: str, solar_url: str,
                             target_url: str, price_url: str, card_url: str) -> dict:
    """組合 Rich Menu 結構：6 個按鈕的位置與動作"""
    areas_geo = richmenu_designer.get_button_areas()

    # 6 個按鈕對應動作
    actions = [
        {"type": "uri", "uri": AFA_PRODSALES_URL,
         "label": "產銷班查詢"},
        {"type": "uri", "uri": AFA_FERT_BRAND_URL,
         "label": "肥料廠牌查詢"},
        {"type": "uri", "uri": target_url or AFA_SUBSIDY_URL,
         "label": "目標業績"},
        {"type": "uri", "uri": AFA_AGRI_REPORT_URL,
         "label": "農情報告網"},
        {"type": "uri", "uri": price_url or AFA_SUBSIDY_URL,
         "label": "產品牌價"},
        {"type": "uri", "uri": AFA_FERT_LAW_URL,
         "label": "肥料法規"},
    ]

    payload = {
        "size": {"width": richmenu_designer.WIDTH, "height": richmenu_designer.HEIGHT},
        "selected": True,
        "name": f"市場資訊主選單 v{int(time.time())}",
        "chatBarText": "點開選單",
        "areas": [
            {"bounds": a["bounds"], "action": act}
            for a, act in zip(areas_geo, actions)
        ],
    }
    return payload


def create_rich_menu(token: str, payload: dict) -> str:
    r = requests.post(f"{API}/richmenu", headers=_headers(token), json=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"建立 Rich Menu 失敗 {r.status_code}: {r.text[:300]}")
    return r.json()["richMenuId"]


def upload_image(token: str, menu_id: str, image_path: str) -> None:
    with open(image_path, "rb") as f:
        data = f.read()
    r = requests.post(
        f"{DATA_API}/richmenu/{menu_id}/content",
        headers=_headers(token, ct="image/png"),
        data=data,
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"上傳圖失敗 {r.status_code}: {r.text[:300]}")


def set_default(token: str, menu_id: str) -> None:
    r = requests.post(
        f"{API}/user/all/richmenu/{menu_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"設定預設失敗 {r.status_code}: {r.text[:300]}")


def deploy(report_url: str = "", solar_url: str = "") -> None:
    token = _get_token()

    print("[1/6] 生成 Rich Menu 圖 ...")
    img_path = richmenu_designer.make_richmenu_image()
    print(f"  ✓ 圖已生成：{img_path}")

    print("\n[2/6] 生成名片 + 業績 + 牌價並上傳 catbox ...")
    card_url = ""
    target_url = ""
    price_url = ""
    try:
        card_url = uploader.upload_image(image_card.make_business_card_image())
        print(f"  ✓ 名片 URL：{card_url}")
    except Exception as e:
        print(f"  [!] 名片失敗（用 fallback）：{e}")
    try:
        target_url = uploader.upload_image(image_card.make_sales_target_image())
        print(f"  ✓ 業績 URL：{target_url}")
    except Exception as e:
        print(f"  [!] 業績圖失敗（用 fallback）：{e}")
    try:
        price_url = uploader.upload_image(image_card.make_price_image())
        print(f"  ✓ 牌價 URL：{price_url}")
    except Exception as e:
        print(f"  [!] 牌價圖失敗（用 fallback）：{e}")

    print("\n[3/6] 刪除舊選單（避免累積）...")
    old_menus = list_rich_menus(token)
    print(f"  目前有 {len(old_menus)} 個舊選單")
    for m in old_menus:
        delete_rich_menu(token, m["richMenuId"])

    print("\n[4/6] 建立新 Rich Menu 結構 ...")
    payload = build_richmenu_payload(report_url, solar_url, target_url, price_url, card_url)
    menu_id = create_rich_menu(token, payload)
    print(f"  ✓ menuId: {menu_id}")

    print("\n[5/6] 上傳選單圖片 ...")
    upload_image(token, menu_id, str(img_path))
    print("  ✓ 圖已上傳")

    print("\n[6/6] 設為所有粉絲的預設選單 ...")
    set_default(token, menu_id)
    print("  ✓ 完成")

    print()
    print("=" * 50)
    print("Rich Menu 已部署到你的 LINE 官方帳號！")
    print("打開手機 LINE，找到「農業有機質肥料市場報告」")
    print("聊天視窗下方應該會出現 6 格選單")
    print("=" * 50)


def main():
    args = sys.argv[1:]
    report_url = ""
    solar_url = ""
    i = 0
    while i < len(args):
        if args[i] == "--report" and i + 1 < len(args):
            report_url = args[i + 1]
            i += 2
        elif args[i] == "--solar" and i + 1 < len(args):
            solar_url = args[i + 1]
            i += 2
        else:
            i += 1
    deploy(report_url, solar_url)


if __name__ == "__main__":
    main()
