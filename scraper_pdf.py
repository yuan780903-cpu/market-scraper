"""
農糧署「國產有機質肥料品牌推薦名單」PDF 監控
- 下載 4 個 PDF（5-08 雞糞、5-09 禽畜糞、5-13 雜項、違規案件名單）
- 解析表格：登記證字號、廠牌、業者、上網日（推薦類）或下網日+違規原因（違規類）
- 從檔名抽出品目代碼、資料更新日期
- 兩種變動偵測：
    (1) 上架（依「上網日」直接 filter 近 30 天，無需 snapshot）
    (2) 下架（snapshot 比對：上次有、本次無 → 下架日 = 本次資料更新日期）
    (3) 新違規（snapshot 比對 + 下網日 filter）
"""

import io
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urljoin

import pdfplumber
import requests
from bs4 import BeautifulSoup

from config import (
    OUTPUT_DIR,
    PDF_CHANGE_DAYS,
    PDF_LIST_PAGE,
    REQUEST_TIMEOUT,
    SNAPSHOT_DIR,
    USER_AGENT,
)

LICENSE_RE = re.compile(r"^\d{6,8}$")
CATEGORY_VIOLATION = "違規案件名單"

# 由廠牌/業者名稱關鍵字推斷品目（cross-reference 找不到時的 fallback）
# 越具體的關鍵字越前面，會優先匹配
BRAND_KEYWORD_TO_CATEGORY = [
    ("雞糞加工", "5-08"),
    ("雞糞", "5-08"),
    ("雞王", "5-08"),
    ("禽畜糞", "5-09"),
    ("禽畜", "5-09"),
    ("堆肥", "5-09"),
    ("雜項", "5-13"),
    ("有機質肥料", "5-13"),
    ("有機質", "5-13"),
]


def _match_category(text: str) -> str:
    # 清掉所有空白與分隔符（PDF 抽出常有 "有 / 機質肥料" 這種斷裂）
    cleaned = re.sub(r"[\s/,()()、，]+", "", text or "")
    for kw, cat in BRAND_KEYWORD_TO_CATEGORY:
        if kw in cleaned:
            return cat
    return ""


def attach_inferred_category(products: List[Dict]) -> None:
    """為違規類產品附加「原品目」欄。
    優先順序：1) cross-reference 現行推薦類 PDF；2) 廠牌關鍵字；3) 業者關鍵字。"""
    lookup = {
        p["登記證字號"]: p["品目"]
        for p in products
        if p["品目"] != CATEGORY_VIOLATION
    }
    for p in products:
        if p["品目"] != CATEGORY_VIOLATION:
            p["原品目"] = p["品目"]
            continue
        license_no = p.get("登記證字號", "")
        if license_no in lookup:
            p["原品目"] = lookup[license_no]
            continue
        # 廠牌先推
        inferred = _match_category(p.get("廠牌商品名稱", ""))
        if not inferred:
            inferred = _match_category(p.get("業者資訊", ""))
        p["原品目"] = inferred or "未知"


def _http_get(url: str) -> requests.Response:
    return requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)


# ---------- 日期工具：民國 ↔ 西元 ----------

def roc_to_date(y, m, d) -> Optional[date]:
    try:
        yi = int(y)
        # 兩位數視為民國年（如 99 → 民國 99 = 2010），三位數同樣 + 1911
        return date(yi + 1911, int(m), int(d))
    except (ValueError, TypeError):
        return None


def parse_roc_date(s: str) -> Optional[date]:
    """parse '110.05.24' or '110/05/24' → date"""
    if not s:
        return None
    m = re.search(r"(\d{2,3})[./](\d{1,2})[./](\d{1,2})", s)
    if not m:
        return None
    return roc_to_date(m.group(1), m.group(2), m.group(3))


# ---------- 找 PDF 連結 / 下載 ----------

def find_pdf_links(list_page_url: str = PDF_LIST_PAGE) -> List[str]:
    r = _http_get(list_page_url)
    r.encoding = r.apparent_encoding or "utf-8"
    soup = BeautifulSoup(r.text, "lxml")
    links, seen = [], set()
    for a in soup.select('a[href*="download"]'):
        href = urljoin(list_page_url, a.get("href", ""))
        if href not in seen:
            links.append(href)
            seen.add(href)
    return links


def download_pdf(url: str, dest_dir: Path) -> Optional[Path]:
    try:
        r = _http_get(url)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  [!] 下載失敗 {url}: {e}")
        return None

    content = r.content
    if content[:3] == b"\xef\xbb\xbf":
        content = content[3:]
    if not content.startswith(b"%PDF"):
        print(f"  [!] 非 PDF 內容：{url}")
        return None

    cd = r.headers.get("Content-Disposition", "")
    m = re.search(r'filename="([^"]+)"', cd)
    fname = unquote(m.group(1)) if m else url.rsplit("=", 1)[-1] + ".pdf"

    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / fname
    path.write_bytes(content)
    return path


# ---------- 從檔名抽 metadata ----------

def extract_pdf_meta(pdf_path: Path) -> Dict:
    name = pdf_path.name
    # 品目代碼，如 (5-08), (5-09), (5-13)
    m = re.search(r"\((\d-\d{2})\)", name)
    if m:
        category = m.group(1)
    elif "違規" in name:
        category = CATEGORY_VIOLATION
    else:
        category = "其他"

    # 資料更新日期，如 (115.05.26更新)
    m = re.search(r"\((\d{3})\.(\d{2})\.(\d{2})\s*更新\)", name)
    update_date = roc_to_date(m.group(1), m.group(2), m.group(3)) if m else None

    return {"品目": category, "資料更新日期": update_date}


# ---------- 解析每張 PDF ----------

def _clean(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(text)).strip() if text else ""


def _clean_multiline(text: Optional[str]) -> str:
    if text is None:
        return ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in str(text).split("\n")]
    return " / ".join(l for l in lines if l)


def _looks_like_license(s: str) -> bool:
    parts = (s or "").split()
    return bool(parts and LICENSE_RE.match(parts[0]))


def extract_products(pdf_path: Path) -> List[Dict]:
    """從 PDF 表格抽出產品。
    欄位假設：第 2 欄=廠牌, 第 3 欄=登記證+有效期限, 第 4 欄=業者, 最後欄=上網日/下網日。
    違規 PDF 的最後欄含「下網日 + 處分機關 + 違規原因」（多行）。"""
    meta = extract_pdf_meta(pdf_path)
    is_violation = meta["品目"] == CATEGORY_VIOLATION
    update_iso = meta["資料更新日期"].isoformat() if meta["資料更新日期"] else ""

    products = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for table in (page.extract_tables() or []):
                    for row in table:
                        if not row or len(row) < 4:
                            continue
                        license_cell = _clean(row[2])
                        license_no = license_cell.split()[0] if license_cell else ""
                        if not _looks_like_license(license_no):
                            continue

                        brand = _clean_multiline(row[1])
                        company_cell = _clean_multiline(row[3])
                        company = company_cell.split(" / ")[0] if company_cell else ""

                        # 最後欄：抽 ROC 日期 + 剩餘文字 (違規原因)
                        last_cell_raw = str(row[-1] or "")
                        date_m = re.search(r"(\d{2,3})[./](\d{1,2})[./](\d{1,2})", last_cell_raw)
                        if date_m:
                            d = roc_to_date(date_m.group(1), date_m.group(2), date_m.group(3))
                            net_date_iso = d.isoformat() if d else ""
                            after = last_cell_raw[date_m.end():]
                            reason = re.sub(r"\s+", "", after).strip(" /，,") if is_violation else ""
                        else:
                            net_date_iso = ""
                            reason = ""

                        products.append({
                            "品目": meta["品目"],
                            "登記證字號": license_no,
                            "廠牌商品名稱": brand,
                            "業者名稱": company,
                            "業者資訊": company_cell,
                            "上網日": "" if is_violation else net_date_iso,
                            "下網日": net_date_iso if is_violation else "",
                            "違規原因": reason,
                            "資料更新日期": update_iso,
                            "PDF": pdf_path.name,
                        })
    except Exception as e:
        print(f"  [!] 解析 PDF 失敗 {pdf_path.name}: {e}")
        return []

    seen, unique = set(), []
    for p in products:
        if p["登記證字號"] in seen:
            continue
        seen.add(p["登記證字號"])
        unique.append(p)
    return unique


# ---------- Snapshot ----------

def _snapshot_path() -> Path:
    return Path(SNAPSHOT_DIR) / "latest_products.json"


def load_previous_snapshot() -> Dict[str, Dict]:
    p = _snapshot_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_snapshot(products: List[Dict]) -> None:
    p = _snapshot_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {x["登記證字號"]: x for x in products}
    p.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    (p.parent / f"snapshot_{ts}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------- 變動偵測 ----------

def _recent_listings(products: List[Dict], days: int = PDF_CHANGE_DAYS) -> List[Dict]:
    """近 N 天上架：filter 推薦類產品的上網日（已是 ISO 字串）"""
    cutoff = date.today() - timedelta(days=days)
    result = []
    for p in products:
        if p["品目"] == CATEGORY_VIOLATION:
            continue
        try:
            d = date.fromisoformat(p.get("上網日", ""))
        except ValueError:
            continue
        if d >= cutoff:
            item = dict(p)
            item["上架日"] = p.get("上網日", "")
            result.append(item)
    return result


def _recent_violations(products: List[Dict], days: int = PDF_CHANGE_DAYS) -> List[Dict]:
    """近 N 天新違規：filter 違規類產品的下網日"""
    cutoff = date.today() - timedelta(days=days)
    result = []
    for p in products:
        if p["品目"] != CATEGORY_VIOLATION:
            continue
        try:
            d = date.fromisoformat(p.get("下網日", ""))
        except ValueError:
            d = None
        if d and d >= cutoff:
            result.append(p)
    return result


def _removed_from_recommendation(
    current: List[Dict], previous: Dict[str, Dict], pdf_results: List[Dict], days: int = PDF_CHANGE_DAYS
) -> List[Dict]:
    """下架：上次推薦名單有、本次無。下架日 = 該品目本次 PDF 的資料更新日期。"""
    cur_recommended_keys = {p["登記證字號"] for p in current if p["品目"] != CATEGORY_VIOLATION}
    prev_recommended = {
        k: v for k, v in previous.items() if v.get("品目") != CATEGORY_VIOLATION
    }
    removed_keys = set(prev_recommended.keys()) - cur_recommended_keys

    # 各品目本次資料更新日期
    update_by_cat = {}
    for r in pdf_results:
        meta = r.get("meta", {})
        if meta.get("資料更新日期"):
            update_by_cat[meta["品目"]] = meta["資料更新日期"]

    cutoff = date.today() - timedelta(days=days)
    result = []
    for k in removed_keys:
        item = dict(prev_recommended[k])
        cat = item.get("品目", "")
        removal_date = update_by_cat.get(cat)
        item["下架日"] = removal_date.isoformat() if removal_date else ""
        try:
            d = date.fromisoformat(item["下架日"])
        except ValueError:
            d = None
        if d and d >= cutoff:
            result.append(item)
    return result


# ---------- 主流程 ----------

def scrape_all() -> Dict:
    print("[PDF] 抓取農糧署推薦名單頁 ...")
    pdf_dir = Path(OUTPUT_DIR) / "pdfs"
    links = find_pdf_links()
    print(f"  → 找到 {len(links)} 個 PDF 連結")

    pdf_results = []
    for url in links:
        path = download_pdf(url, pdf_dir)
        if not path:
            continue
        meta = extract_pdf_meta(path)
        products = extract_products(path)
        pdf_results.append({"path": path, "meta": meta, "products": products})
        update_str = meta["資料更新日期"].isoformat() if meta["資料更新日期"] else "未知"
        print(f"  ✓ {meta['品目']:>15} 更新日 {update_str} 共 {len(products)} 筆 ({path.name})")

    all_products = []
    seen = set()
    for r in pdf_results:
        for p in r["products"]:
            if p["登記證字號"] in seen:
                continue
            seen.add(p["登記證字號"])
            all_products.append(p)

    # 為違規類產品標上「原品目」(5-08/5-09/5-13)
    attach_inferred_category(all_products)

    previous = load_previous_snapshot()
    is_first_run = not previous

    if is_first_run:
        recent_added = _recent_listings(all_products)
        recent_removed = []
        recent_violations = _recent_violations(all_products)
        print(f"  → 首次執行，基準快照 {len(all_products)} 筆已建立")
    else:
        recent_added = _recent_listings(all_products)
        recent_removed = _removed_from_recommendation(all_products, previous, pdf_results)
        recent_violations = _recent_violations(all_products)

    print(
        f"  → 近 {PDF_CHANGE_DAYS} 天：新上架 {len(recent_added)} ｜ "
        f"下架 {len(recent_removed)} ｜ 新違規 {len(recent_violations)}"
    )

    save_snapshot(all_products)

    return {
        "products": all_products,
        "pdf_results": pdf_results,
        "recent_added": recent_added,
        "recent_removed": recent_removed,
        "recent_violations": recent_violations,
        "is_first_run": is_first_run,
        "change_days": PDF_CHANGE_DAYS,
    }


if __name__ == "__main__":
    r = scrape_all()
    print(f"\n總產品 {len(r['products'])} 筆")
    if r["recent_added"]:
        print(f"\n近 {r['change_days']} 天新上架 {len(r['recent_added'])} 筆 (前 5):")
        for p in r["recent_added"][:5]:
            print(f"  + [{p['品目']}] {p['上架日']} {p['登記證字號']} {p['廠牌商品名稱']} ({p['業者名稱']})")
    if r["recent_violations"]:
        print(f"\n近 {r['change_days']} 天新違規 {len(r['recent_violations'])} 筆 (前 5):")
        for p in r["recent_violations"][:5]:
            print(f"  ! {p['下網日']} {p['登記證字號']} {p['廠牌商品名稱']} - {p['違規原因'][:30]}")
