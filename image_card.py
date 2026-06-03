"""
用 PIL 生成商業風格的有機肥料週報卡片
- 節氣施肥重點卡：漸層 header、區域 chip、雙欄資訊
- 各區作物面積/基肥對照卡：本月焦點區 highlight + 4 區詳細

Mac 用 STHeiti Medium 字型。GitHub Actions 用 CARD_FONT_PATH 指定其他字型。
"""

import os
from datetime import date
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

import agri_kb
import motivation_picker
import solar_term

# ---------- 字型 ----------
DEFAULT_FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]

# ---------- 配色（商業風）----------
# 主色
COLOR_BG = "#f5f6f3"          # 米白底
COLOR_PANEL = "#ffffff"        # 內容區白底
COLOR_HEADER_GREEN_TOP = "#1b5e3e"
COLOR_HEADER_GREEN_BOTTOM = "#4caf73"
COLOR_HEADER_BROWN_TOP = "#5b3a00"
COLOR_HEADER_BROWN_BOTTOM = "#a06a18"
COLOR_HEADER_BLUE_TOP = "#0e3a6b"
COLOR_HEADER_BLUE_BOTTOM = "#2a7ec8"

# 文字
COLOR_TEXT_DARK = "#1f2933"
COLOR_TEXT_MID = "#52616b"
COLOR_TEXT_LIGHT = "#9aa5b1"
COLOR_TEXT_HEADER = "#ffffff"
COLOR_TEXT_SUBHEADER = "#d8efde"

# 強調
COLOR_HIGHLIGHT_BG = "#fff6db"     # 焦點區金黃底
COLOR_HIGHLIGHT_BORDER = "#f0b400"
COLOR_HIGHLIGHT_TEXT = "#6b4800"
COLOR_FOCUS_TAG = "#c92a2a"        # 「本月焦點」紅色 tag

# 區域顏色
REGION_COLORS = {
    "北部": ("#dfeefc", "#1864ab"),  # (背景, 文字)
    "中部": ("#e6f4d7", "#3b6e0e"),
    "南部": ("#fde0d0", "#a3370b"),
    "東部": ("#f0e0fa", "#5e2c8f"),
}

WIDTH = 1080  # 與 LINE 慣用寬度接近

OUTPUT_DIR = Path("output/cards")


def _find_font_path() -> str:
    env = os.environ.get("CARD_FONT_PATH", "").strip()
    if env and Path(env).exists():
        return env
    for p in DEFAULT_FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise RuntimeError("找不到中文字型；請設 CARD_FONT_PATH 或安裝 STHeiti/Noto CJK/wqy-microhei")


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_find_font_path(), size)


def _measure(text: str, font) -> Tuple[int, int]:
    bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _gradient_rect(img: Image.Image, xy: Tuple[int, int, int, int],
                    top_color: str, bottom_color: str):
    """畫垂直漸層矩形 (簡易版：N 條橫線插值)"""
    x1, y1, x2, y2 = xy
    h = y2 - y1
    if h <= 0:
        return
    top = _hex_to_rgb(top_color)
    bot = _hex_to_rgb(bottom_color)
    draw = ImageDraw.Draw(img)
    for i in range(h):
        t = i / h
        c = (
            int(top[0] + (bot[0] - top[0]) * t),
            int(top[1] + (bot[1] - top[1]) * t),
            int(top[2] + (bot[2] - top[2]) * t),
        )
        draw.line([(x1, y1 + i), (x2, y1 + i)], fill=c)


def _hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _draw_text_wrapped(draw, text, x, y, font, fill, max_width, line_spacing=8):
    """中英混排自動換行"""
    if not text:
        return y
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for ch in paragraph:
            test = line + ch
            w, _ = _measure(test, font)
            if w > max_width and line:
                lines.append(line)
                line = ch
            else:
                line = test
        if line:
            lines.append(line)
    line_h = font.size + line_spacing
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h
    return y


def _draw_gradient_header(img, title, subtitle, color_top, color_bottom, height=180):
    _gradient_rect(img, (0, 0, WIDTH, height), color_top, color_bottom)
    draw = ImageDraw.Draw(img)
    # 標題
    f_title = _font(52)
    draw.text((48, 36), title, font=f_title, fill=COLOR_TEXT_HEADER)
    # 副標
    if subtitle:
        f_sub = _font(26)
        draw.text((48, 108), subtitle, font=f_sub, fill=COLOR_TEXT_SUBHEADER)
    # 底部裝飾線
    draw.rectangle([(0, height - 3), (WIDTH, height)], fill=color_top)


def _draw_panel(img, xy, fill=COLOR_PANEL, radius=16):
    """畫圓角面板"""
    draw = ImageDraw.Draw(img)
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    except AttributeError:
        draw.rectangle(xy, fill=fill)


def _draw_chip(draw, x, y, text, bg, fg, font, padding_x=14, padding_y=6):
    """畫區域標籤（圓角矩形 + 文字）"""
    w, h = _measure(text, font)
    box_w = w + padding_x * 2
    box_h = h + padding_y * 2
    try:
        draw.rounded_rectangle(
            [(x, y), (x + box_w, y + box_h)],
            radius=box_h // 2, fill=bg,
        )
    except AttributeError:
        draw.rectangle([(x, y), (x + box_w, y + box_h)], fill=bg)
    draw.text((x + padding_x, y + padding_y - 2), text, font=font, fill=fg)
    return box_w, box_h


def _draw_section_label(draw, y, text, color=COLOR_HEADER_GREEN_TOP, padding_left=48):
    """畫小節標籤（左側色棒 + 字）"""
    f = _font(30)
    # 左側色棒
    draw.rectangle([(padding_left, y + 6), (padding_left + 6, y + 32)], fill=color)
    # 文字
    draw.text((padding_left + 18, y), text, font=f, fill=color)
    return y + 50


def _draw_divider(draw, y, padding=48):
    draw.line([(padding, y), (WIDTH - padding, y)], fill="#e0e3df", width=1)


def _draw_footnote(draw, y, text):
    f = _font(20)
    draw.text((48, y), text, font=f, fill=COLOR_TEXT_LIGHT)


# ---------- 節氣施肥重點卡 ----------

def make_solar_term_image(today: Optional[date] = None) -> Path:
    if today is None:
        today = date.today()
    term, term_start, next_term, next_start = solar_term.current_and_next(today)
    g = agri_kb.guide_for(term)
    days_in = (today - term_start).days
    days_to_next = (next_start - today).days

    HEIGHT = 1500
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG)
    _draw_gradient_header(img, f"節氣施肥重點 · {term}",
                           f"{today.isoformat()}　·　{term}已過 {days_in} 天　·　距「{next_term}」{days_to_next} 天",
                           COLOR_HEADER_BROWN_TOP, COLOR_HEADER_BROWN_BOTTOM, height=200)
    draw = ImageDraw.Draw(img)

    y = 240

    # 氣候特徵 panel
    _draw_panel(img, (32, y, WIDTH - 32, y + 110))
    y2 = _draw_section_label(draw, y + 20, "氣候特徵", color="#5b3a00")
    f_body = _font(28)
    _draw_text_wrapped(draw, g.get("climate", "—"), 64, y2, f_body,
                        COLOR_TEXT_DARK, WIDTH - 128)
    y += 140

    # 各區當期作物 panel
    panel_h = 60 + len(g.get("regions", {})) * 64 + 24
    _draw_panel(img, (32, y, WIDTH - 32, y + panel_h))
    y_label = _draw_section_label(draw, y + 20, "各區當期作物", color=COLOR_HEADER_GREEN_TOP)
    f_chip = _font(24)
    f_crop = _font(26)
    cur_y = y_label + 6
    for region, crops in g.get("regions", {}).items():
        bg, fg = REGION_COLORS.get(region, ("#eef2f7", "#1f2933"))
        chip_w, chip_h = _draw_chip(draw, 64, cur_y, region, bg, fg, f_chip)
        _draw_text_wrapped(draw, crops, 64 + chip_w + 16, cur_y + 4, f_crop,
                            COLOR_TEXT_DARK, WIDTH - (64 + chip_w + 16) - 48)
        cur_y += 64
    y += panel_h + 20

    # 施肥重點 panel
    _draw_panel(img, (32, y, WIDTH - 32, y + 140))
    y_label = _draw_section_label(draw, y + 20, "施肥重點", color="#5b3a00")
    _draw_text_wrapped(draw, g.get("focus", "—"), 64, y_label, f_body,
                        COLOR_TEXT_DARK, WIDTH - 128)
    y += 160

    # 業務建議 panel（紅色強調）
    _draw_panel(img, (32, y, WIDTH - 32, y + 160), fill="#fff5f5")
    y_label = _draw_section_label(draw, y + 20, "業務建議 · 本期主推", color="#c92a2a")
    _draw_text_wrapped(draw, g.get("sales", "—"), 64, y_label, f_body,
                        COLOR_TEXT_DARK, WIDTH - 128)
    y += 180

    # 註腳
    _draw_footnote(draw, HEIGHT - 50, "※ 業界常識參考，非即時銷售數據　|　有機肥料市場週報")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"solar_term_{today.isoformat()}.png"
    img.save(out, optimize=True)
    return out


# ---------- 各區作物 / 基肥對照卡 ----------

def make_regional_crops_image(today: Optional[date] = None) -> Path:
    if today is None:
        today = date.today()
    focus = agri_kb.monthly_focus(today.month)

    HEIGHT = 2000
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG)
    _draw_gradient_header(img, "各區作物面積 / 基肥對照",
                           f"{today.year} 年 {today.month} 月　·　業務區域戰情",
                           COLOR_HEADER_BLUE_TOP, COLOR_HEADER_BLUE_BOTTOM, height=200)
    draw = ImageDraw.Draw(img)

    y = 240

    # ========= 本月基肥焦點區 highlight box =========
    focus_h = 280
    _draw_panel(img, (32, y, WIDTH - 32, y + focus_h), fill=COLOR_HIGHLIGHT_BG)
    # 左側紅色「焦點」tag
    draw.rectangle([(32, y), (40, y + focus_h)], fill=COLOR_FOCUS_TAG)
    # 「本月焦點」chip
    f_tag = _font(22)
    _draw_chip(draw, 64, y + 24, "★ 本月基肥焦點區",
                COLOR_FOCUS_TAG, "#ffffff", f_tag, padding_x=18, padding_y=8)
    # 區域名稱（大字）
    f_region_big = _font(48)
    draw.text((64, y + 78), focus.get("region", "—"),
              font=f_region_big, fill=COLOR_HIGHLIGHT_TEXT)
    # 作物
    f_focus_crop = _font(28)
    draw.text((64, y + 142), focus.get("crop", "—"),
              font=f_focus_crop, fill=COLOR_TEXT_DARK)
    # 規模 / 原因 / 建議產品
    f_info = _font(24)
    info_y = y + 188
    if focus.get("scale"):
        draw.text((64, info_y), f"規模：{focus['scale']}", font=f_info, fill=COLOR_TEXT_MID)
        info_y += 32
    if focus.get("products"):
        draw.text((64, info_y), f"主推：{focus['products']}", font=f_info, fill=COLOR_TEXT_MID)
    y += focus_h + 16

    # 焦點原因（小字 panel 外）
    if focus.get("reason"):
        f_reason = _font(22)
        _draw_text_wrapped(draw, f"※ {focus['reason']}", 48, y, f_reason,
                            COLOR_TEXT_MID, WIDTH - 96)
        y += 60

    # ========= 四區詳細對照 =========
    y_label = _draw_section_label(draw, y, "四區作物面積與基肥對照",
                                    color=COLOR_HEADER_BLUE_TOP)
    y = y_label + 8

    f_region = _font(32)
    f_crop = _font(24)
    f_fert = _font(22)
    f_chip = _font(22)

    for r in agri_kb.REGIONAL_CROPS:
        # 取北/中/南/東短名
        short = r["region"].split(" ")[0]  # "北部 (台北...)" → "北部"
        # 預估高度
        block_h = 70 + len(r["crops"]) * 36 + 50
        _draw_panel(img, (32, y, WIDTH - 32, y + block_h))
        bg, fg = REGION_COLORS.get(short, ("#eef2f7", "#1f2933"))
        # 區域 chip
        _draw_chip(draw, 48, y + 22, short, bg, fg, f_chip, padding_x=18, padding_y=8)
        # 完整區域名稱
        chip_w, _ = _measure(short, f_chip)
        full_name = r["region"].split(" ", 1)[1] if " " in r["region"] else ""
        if full_name:
            draw.text((48 + chip_w + 56, y + 28), full_name,
                      font=_font(22), fill=COLOR_TEXT_MID)
        # 作物清單
        cur_y = y + 80
        for crop in r["crops"]:
            draw.text((64, cur_y), f"·  {crop}", font=f_crop, fill=COLOR_TEXT_DARK)
            cur_y += 36
        # 常用基肥
        cur_y += 4
        _draw_text_wrapped(draw, f"常用基肥：{r['common_fertilizer']}",
                            64, cur_y, f_fert, "#5b3a00", WIDTH - 128, line_spacing=4)
        y += block_h + 16

    # 註腳
    _draw_footnote(draw, HEIGHT - 50, "※ 面積為農業統計年報概略值　|　基肥對照為業界常識參考")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"regional_crops_{today.isoformat()}.png"
    img.save(out, optimize=True)
    return out


COLOR_HEADER_PURPLE_TOP = "#3d2466"
COLOR_HEADER_PURPLE_BOTTOM = "#7c4dcc"


# ---------- 業務充電站卡 ----------

def make_motivation_image(today: Optional[date] = None, mark_used: bool = True) -> Path:
    """每週推播：1 條金句 + 1 條銷售手段（自動輪播不重複）
    mark_used=True：正式推播，標記為已用
    mark_used=False：dry-run 預覽，不寫檔"""
    if today is None:
        today = date.today()
    picked = motivation_picker.pick_quote_and_tactic(mark_used=mark_used)
    quote = picked["quote"]
    tactic = picked["tactic"]

    HEIGHT = 1500
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG)
    _draw_gradient_header(img, "業務充電站",
                           f"{today.isoformat()}　·　本週金句 + 銷售手段",
                           COLOR_HEADER_PURPLE_TOP, COLOR_HEADER_PURPLE_BOTTOM, height=200)
    draw = ImageDraw.Draw(img)

    y = 240

    # ========== 金句區（大引號式設計）==========
    quote_h = 520
    _draw_panel(img, (32, y, WIDTH - 32, y + quote_h), fill="#fff9ec")
    # 左側金色 tag
    draw.rectangle([(32, y), (40, y + quote_h)], fill="#f0b400")
    # 大引號裝飾
    f_quote_mark = _font(160)
    draw.text((56, y + 8), "“", font=f_quote_mark, fill="#e6c980")
    # 小標
    f_tag = _font(22)
    _draw_chip(draw, 64, y + 24, f"本週金句 · {quote['id']}",
                "#f0b400", "#ffffff", f_tag, padding_x=16, padding_y=6)
    # 金句正文（大字、置中區）
    f_quote = _font(38)
    text_y = y + 130
    text_y = _draw_text_wrapped(draw, quote["text"], 72, text_y, f_quote,
                                  "#3d2800", WIDTH - 144, line_spacing=14)
    # 作者
    f_author = _font(24)
    author_text = f"— {quote['author']}"
    aw, _ = _measure(author_text, f_author)
    draw.text((WIDTH - 72 - aw, y + quote_h - 60), author_text,
              font=f_author, fill="#8a6500")

    y += quote_h + 24

    # ========== 銷售手段區 ==========
    # 標題列
    _draw_panel(img, (32, y, WIDTH - 32, y + 60), fill="#1864ab")
    f_tactic_label = _font(28)
    _draw_chip(draw, 64, y + 12, f"本週銷售手段 · {tactic['id']}",
                "#ffffff", "#1864ab", f_tactic_label, padding_x=18, padding_y=6)
    y += 80

    # 手段標題
    f_tactic_title = _font(40)
    _draw_panel(img, (32, y, WIDTH - 32, y + 90))
    draw.text((64, y + 20), tactic["title"], font=f_tactic_title, fill="#0e3a6b")
    y += 110

    # 手段內容
    body_h = 280
    _draw_panel(img, (32, y, WIDTH - 32, y + body_h))
    f_body = _font(26)
    _draw_text_wrapped(draw, tactic["body"], 64, y + 24, f_body,
                        COLOR_TEXT_DARK, WIDTH - 128, line_spacing=10)
    y += body_h + 20

    # 註腳
    _draw_footnote(draw, HEIGHT - 50,
                    f"※ 金句池 {len(motivation_picker.motivation_kb.QUOTES)} 條／手段池 "
                    f"{len(motivation_picker.motivation_kb.TACTICS)} 條　·　自動輪播不重複")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"motivation_{today.isoformat()}.png"
    img.save(out, optimize=True)
    return out


# ---------- 目標業績儀表板 ----------
# 修改業績數字改這裡
SALES_TARGET = {
    "year": 2026,
    "unit": "噸",  # 單位（噸/件/萬）— 改這裡
    "people": [
        ("施敏楷", [256, 240, 233, 249, 336, 234, 304, 319, 532, 626, 492, 317]),
        ("莊政遠", [256, 240, 233, 249, 336, 234, 304, 319, 532, 626, 492, 317]),
        ("曾思博", [256, 240, 233, 249, 336, 234, 304, 319, 532, 626, 492, 317]),
    ],
    "channels": [
        ("嘉義縣農會", [120, 106, 70, 70, 70, 70, 190, 220, 220, 210, 122, 122]),
    ],
}


def make_sales_target_image(today: Optional[date] = None) -> Path:
    """目標業績儀表板圖卡，當月用色塊強調"""
    if today is None:
        today = date.today()
    current_month_idx = today.month - 1  # 0-based

    W = 1600
    HEIGHT = 920
    img = Image.new("RGB", (W, HEIGHT), COLOR_BG)
    _draw_gradient_header(img, f"目標業績 · {SALES_TARGET['year']} 年",
                           f"當月：{today.month} 月　·　單位：{SALES_TARGET['unit']}",
                           "#0e3a6b", "#1864ab", height=140)
    draw = ImageDraw.Draw(img)

    # 表格尺寸
    label_col_w = 200
    month_col_w = (W - label_col_w - 100) // 13  # 12 月 + 合計 = 13
    table_x = 60
    table_y = 180
    row_h = 50

    f_q = _font(22)
    f_month = _font(20)
    f_label = _font(22)
    f_num = _font(22)

    # === 季標題列 ===
    quarter_colors = ["#dbeafe", "#dcfce7", "#fef3c7", "#fde0e4"]
    for q in range(4):
        x1 = table_x + label_col_w + q * 3 * month_col_w
        x2 = x1 + 3 * month_col_w
        draw.rectangle([(x1, table_y), (x2, table_y + row_h)],
                        fill=quarter_colors[q], outline="#cccccc")
        label = f"{SALES_TARGET['year']}Q{q + 1}"
        tw, _ = _measure(label, f_q)
        draw.text(((x1 + x2) // 2 - tw // 2, table_y + 12),
                  label, font=f_q, fill="#1f2933")
    # 合計欄
    total_x1 = table_x + label_col_w + 12 * month_col_w
    total_x2 = total_x1 + month_col_w
    draw.rectangle([(total_x1, table_y), (total_x2, table_y + row_h)],
                    fill="#e5e7eb", outline="#999999")
    draw.text((total_x1 + 30, table_y + 12), "合計", font=f_q, fill="#1f2933")

    # === 月份列 ===
    month_row_y = table_y + row_h
    # 標籤格（空白）
    draw.rectangle([(table_x, month_row_y), (table_x + label_col_w, month_row_y + row_h)],
                    fill="#f4f6f8", outline="#cccccc")
    for m in range(12):
        mx = table_x + label_col_w + m * month_col_w
        fill = "#fff2c7" if m == current_month_idx else "#ffffff"
        draw.rectangle([(mx, month_row_y), (mx + month_col_w, month_row_y + row_h)],
                        fill=fill, outline="#cccccc")
        label = f"{m + 1}月"
        tw, _ = _measure(label, f_month)
        text_color = "#c92a2a" if m == current_month_idx else "#52616b"
        draw.text((mx + month_col_w // 2 - tw // 2, month_row_y + 14),
                  label, font=f_month, fill=text_color)
    draw.rectangle([(total_x1, month_row_y), (total_x2, month_row_y + row_h)],
                    fill="#f4f6f8", outline="#cccccc")

    # === Body rows ===
    def draw_row(y, name, values, fill_label="#ffffff", fill_cell="#ffffff", text_color="#1f2933"):
        # 標籤
        draw.rectangle([(table_x, y), (table_x + label_col_w, y + row_h)],
                        fill=fill_label, outline="#cccccc")
        draw.text((table_x + 16, y + 14), name, font=f_label, fill=text_color)
        # 12 個月
        for m, v in enumerate(values):
            mx = table_x + label_col_w + m * month_col_w
            cell_fill = "#fff2c7" if m == current_month_idx else fill_cell
            draw.rectangle([(mx, y), (mx + month_col_w, y + row_h)],
                            fill=cell_fill, outline="#cccccc")
            txt = f"{v:,}" if v else "-"
            tw, _ = _measure(txt, f_num)
            cell_text = "#c92a2a" if m == current_month_idx else text_color
            draw.text((mx + month_col_w - tw - 12, y + 14),
                      txt, font=f_num, fill=cell_text)
        # 合計
        total = sum(values)
        draw.rectangle([(total_x1, y), (total_x2, y + row_h)],
                        fill="#e5e7eb", outline="#999999")
        ttxt = f"{total:,}"
        tw, _ = _measure(ttxt, f_num)
        draw.text((total_x2 - tw - 12, y + 14),
                  ttxt, font=f_num, fill="#1f2933")

    cur_y = month_row_y + row_h

    # 業務員
    for name, values in SALES_TARGET["people"]:
        draw_row(cur_y, name, values, fill_label="#fafafa")
        cur_y += row_h

    # 小計（業務員總和）
    months_count = 12
    subtotal = [sum(p[1][m] for p in SALES_TARGET["people"]) for m in range(months_count)]
    draw_row(cur_y, "小計", subtotal,
             fill_label="#bbf7d0", fill_cell="#dcfce7", text_color="#14532d")
    cur_y += row_h

    # 通路（農會）
    for name, values in SALES_TARGET["channels"]:
        draw_row(cur_y, name, values, fill_label="#fde68a", fill_cell="#fef3c7", text_color="#78350f")
        cur_y += row_h

    # 總計
    grand_total = [subtotal[m] + sum(c[1][m] for c in SALES_TARGET["channels"]) for m in range(months_count)]
    draw_row(cur_y, "總計", grand_total,
             fill_label="#fecaca", fill_cell="#fee2e2", text_color="#7f1d1d")
    cur_y += row_h

    # 註腳：當月進度
    cur_month_target = grand_total[current_month_idx]
    cur_q = (today.month - 1) // 3
    q_target = sum(grand_total[cur_q * 3:(cur_q + 1) * 3])
    year_target = sum(grand_total)
    f_note = _font(22)
    note_y = cur_y + 32
    draw.text((table_x, note_y),
              f"本月目標 {cur_month_target:,} {SALES_TARGET['unit']}　·　"
              f"本季目標 {q_target:,}　·　年度目標 {year_target:,}",
              font=f_note, fill="#1f2933")

    _draw_footnote(draw, HEIGHT - 50, "※ 業績目標表　·　當月以黃底紅字標示")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"sales_target_{today.year}-{today.month:02d}.png"
    img.save(out, optimize=True)
    return out


# ---------- 產品牌價卡 ----------
# 更新牌價改這裡
PRODUCT_PRICES = {
    "update_date": "2026/05/13",
    "note": "針對粒狀料全面調整為 4mm 規格的價格",
    "unit": "元/KG",
    "channels": ["經銷商", "農會", "直營大客戶", "現銷"],
    "products": [
        {
            "name": "碩成有機質肥料 2 號",
            "rows": [
                ("袋粉", [3.2, 3.7, 4.2, 6.0]),
                ("袋粒", [6.2, 6.4, 6.7, 9.0]),
            ],
        },
        {
            "name": "碩成有機質肥料 1 號+",
            "rows": [
                ("袋粉", [3.7, 4.0, 4.6, 7.0]),
                ("袋粒", [6.7, 6.9, 7.2, 9.5]),
            ],
        },
        {
            "name": "碩成有機質肥料 2 號+",
            "rows": [
                ("袋粉", [3.8, 4.3, 4.8, 7.0]),
                ("袋粒", [7.2, 7.4, 7.7, 10.0]),
            ],
        },
    ],
}


def make_price_image() -> Path:
    """產品牌價圖卡：3 產品 × 2 包裝 × 4 通路"""
    W = 1280
    # 估算高度：標題 200 + 表頭 100 + 每產品（袋粉+袋粒）80*2 = 160，3 產品 = 480 + 註腳 80
    HEIGHT = 200 + 100 + 3 * 160 + 100
    img = Image.new("RGB", (W, HEIGHT), COLOR_BG)

    # 紅色頂部 banner（更新日期 + 註記）
    banner_h = 80
    _gradient_rect(img, (0, 0, W, banner_h), "#9b0a23", "#c8102e")
    draw = ImageDraw.Draw(img)
    f_top = _font(26)
    top_text = f"{PRODUCT_PRICES['update_date']}　{PRODUCT_PRICES['note']}"
    tw, _ = _measure(top_text, f_top)
    draw.text((W // 2 - tw // 2, 24), top_text, font=f_top, fill="#ffffff")

    # 副標：產品牌價
    sub_y = banner_h + 20
    f_sub = _font(40)
    sub = f"產品牌價　·　各通路單價（{PRODUCT_PRICES['unit']}）"
    sw, _ = _measure(sub, f_sub)
    draw.text((W // 2 - sw // 2, sub_y), sub, font=f_sub, fill="#1f2933")

    # 表格
    table_x = 40
    table_y = 200
    name_col_w = 280
    pkg_col_w = 110
    channel_col_w = (W - table_x * 2 - name_col_w - pkg_col_w) // 4  # 4 通路
    row_h = 70

    f_h = _font(26)
    f_label = _font(26)
    f_price = _font(28)
    f_price_red = _font(28)

    # === 表頭 ===
    # 第一列：產品名稱（合併 2 列）/ 包裝型態（合併 2 列）/ 各通路的牌價(元/KG)（合併 4 欄）
    header_h = 50

    # 產品名稱（rowspan 2）
    draw.rectangle([(table_x, table_y),
                     (table_x + name_col_w, table_y + header_h * 2)],
                    fill="#1f3a2e", outline="#cccccc")
    tw, _ = _measure("產品名稱", f_h)
    draw.text((table_x + name_col_w // 2 - tw // 2,
                table_y + header_h - 18),
              "產品名稱", font=f_h, fill="#ffffff")

    # 包裝型態（rowspan 2）
    px = table_x + name_col_w
    draw.rectangle([(px, table_y), (px + pkg_col_w, table_y + header_h * 2)],
                    fill="#1f3a2e", outline="#cccccc")
    tw, _ = _measure("包裝型態", f_h)
    draw.text((px + pkg_col_w // 2 - tw // 2,
                table_y + header_h - 18),
              "包裝型態", font=f_h, fill="#ffffff")

    # 各通路的牌價（colspan 4）
    cx = px + pkg_col_w
    cw = channel_col_w * 4
    draw.rectangle([(cx, table_y), (cx + cw, table_y + header_h)],
                    fill="#0e3a6b", outline="#cccccc")
    tw, _ = _measure(f"各通路的牌價（{PRODUCT_PRICES['unit']}）", f_h)
    draw.text((cx + cw // 2 - tw // 2, table_y + 14),
              f"各通路的牌價（{PRODUCT_PRICES['unit']}）",
              font=f_h, fill="#ffffff")

    # 通路子標題
    sub_y2 = table_y + header_h
    for i, ch in enumerate(PRODUCT_PRICES["channels"]):
        x1 = cx + i * channel_col_w
        x2 = x1 + channel_col_w
        draw.rectangle([(x1, sub_y2), (x2, sub_y2 + header_h)],
                        fill="#dbeafe", outline="#cccccc")
        tw, _ = _measure(ch, f_h)
        draw.text((x1 + channel_col_w // 2 - tw // 2, sub_y2 + 14),
                  ch, font=f_h, fill="#0e3a6b")

    # === 各產品列 ===
    body_y = table_y + header_h * 2
    cur_y = body_y

    for prod in PRODUCT_PRICES["products"]:
        # 產品名稱（rowspan 2）
        prod_h = row_h * 2
        draw.rectangle([(table_x, cur_y),
                         (table_x + name_col_w, cur_y + prod_h)],
                        fill="#f4f6f8", outline="#cccccc")
        tw, _ = _measure(prod["name"], f_label)
        draw.text((table_x + name_col_w // 2 - tw // 2,
                    cur_y + prod_h // 2 - 16),
                  prod["name"], font=f_label, fill="#1f3a2e")

        # 兩列：袋粉 / 袋粒
        for ri, (pkg, prices) in enumerate(prod["rows"]):
            ry = cur_y + ri * row_h
            is_granule = ("粒" in pkg)
            cell_fill = "#fff5f5" if is_granule else "#ffffff"
            text_color = "#c92a2a" if is_granule else "#1f2933"
            price_font = f_price_red if is_granule else f_price

            # 包裝型態
            draw.rectangle([(px, ry), (px + pkg_col_w, ry + row_h)],
                            fill=cell_fill, outline="#cccccc")
            tw, _ = _measure(pkg, f_label)
            draw.text((px + pkg_col_w // 2 - tw // 2, ry + 22),
                      pkg, font=f_label, fill=text_color)

            # 4 通路價格
            for ci, price in enumerate(prices):
                x1 = cx + ci * channel_col_w
                x2 = x1 + channel_col_w
                draw.rectangle([(x1, ry), (x2, ry + row_h)],
                                fill=cell_fill, outline="#cccccc")
                txt = f"{price:g}"  # 6.0 → 6
                tw, _ = _measure(txt, price_font)
                draw.text((x1 + channel_col_w // 2 - tw // 2, ry + 20),
                          txt, font=price_font, fill=text_color)

        cur_y += prod_h

    # 註腳
    _draw_footnote(draw, HEIGHT - 50,
                    f"※ 紅字為粒狀（袋粒）規格價格　·　最後更新 {PRODUCT_PRICES['update_date']}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "product_prices.png"
    img.save(out, optimize=True)
    return out


# ---------- 業務名片卡 ----------

# 名片資訊（要改聯絡資訊改這裡）
BUSINESS_CARD = {
    "name": "莊政遠",
    "title": "有機肥料部　業務襄理",
    "company_zh": "大成長城企業股份有限公司",
    "company_en": "GREAT WALL ENTERPRISE CO., LTD.",
    "factory_label": "有機肥料廠",
    "factory_addr": "621 嘉義縣民雄鄉西昌村竹子腳 7-22 號",
    "factory_tel": "(05) 2267170",
    "factory_fax": "(05) 2267101",
    "hq_label": "總公司",
    "hq_addr": "71042 台南市永康區蔦松二街 3 號",
    "hq_tel": "(06) 2531111",
    "hq_fax": "(06) 2541208",
    "uniform_no": "73008303",
    "mobile": "0910-373286",
    "email": "yuan780903@ms.greatwall.com.tw",
}


def make_business_card_image() -> Path:
    """產出乾淨數位版業務名片"""
    W, H = 1280, 800
    img = Image.new("RGB", (W, H), "#ffffff")
    draw = ImageDraw.Draw(img)

    # 頂部紅色裝飾條
    draw.rectangle([(0, 0), (W, 14)], fill="#c8102e")

    # 左側紅色 Logo 區塊
    logo_x, logo_y = 60, 60
    logo_r = 80
    draw.ellipse([(logo_x, logo_y), (logo_x + logo_r * 2, logo_y + logo_r * 2)],
                  fill="#c8102e")
    f_logo = _font(60)
    logo_text = "大成"
    lw, lh = _measure(logo_text, f_logo)
    draw.text((logo_x + logo_r - lw // 2, logo_y + logo_r - lh // 2 - 6),
              logo_text, font=f_logo, fill="#ffffff")
    f_logo_en = _font(20)
    draw.text((logo_x + 32, logo_y + logo_r * 2 + 12), "DaChan",
              font=f_logo_en, fill="#c8102e")

    # 右上：姓名 + 職稱
    f_name = _font(80)
    nw, _ = _measure(BUSINESS_CARD["name"], f_name)
    draw.text((W - 60 - nw, 60), BUSINESS_CARD["name"],
              font=f_name, fill="#1f2933")
    f_title = _font(28)
    tw, _ = _measure(BUSINESS_CARD["title"], f_title)
    draw.text((W - 60 - tw, 160), BUSINESS_CARD["title"],
              font=f_title, fill="#52616b")

    # 中央：公司名（兩行）
    f_company_zh = _font(48)
    f_company_en = _font(24)
    company_y = 280
    cw, _ = _measure(BUSINESS_CARD["company_zh"], f_company_zh)
    draw.text(((W - cw) // 2, company_y), BUSINESS_CARD["company_zh"],
              font=f_company_zh, fill="#1f2933")
    ew, _ = _measure(BUSINESS_CARD["company_en"], f_company_en)
    draw.text(((W - ew) // 2, company_y + 60), BUSINESS_CARD["company_en"],
              font=f_company_en, fill="#52616b")

    # 分隔線
    draw.line([(60, 400), (W - 60, 400)], fill="#e8e6df", width=2)

    # 聯絡資訊區塊
    f_section = _font(22)
    f_body = _font(22)
    f_label = _font(22)
    f_mobile = _font(32)  # 行動電話放大顯眼
    cx = 80
    cy = 430

    def _square_bullet(x, y):
        draw.rectangle([(x, y + 6), (x + 16, y + 22)], fill="#9aa5b1")

    # 有機肥料廠
    _square_bullet(cx, cy)
    draw.text((cx + 30, cy), f"{BUSINESS_CARD['factory_label']}：{BUSINESS_CARD['factory_addr']}",
              font=f_body, fill="#1f2933")
    cy += 36
    draw.text((cx + 50, cy),
              f"電話：{BUSINESS_CARD['factory_tel']}　　傳真：{BUSINESS_CARD['factory_fax']}",
              font=f_body, fill="#52616b")
    cy += 44

    # 總公司
    _square_bullet(cx, cy)
    draw.text((cx + 30, cy), f"{BUSINESS_CARD['hq_label']}：{BUSINESS_CARD['hq_addr']}",
              font=f_body, fill="#1f2933")
    cy += 36
    draw.text((cx + 50, cy),
              f"電話：{BUSINESS_CARD['hq_tel']}　　傳真：{BUSINESS_CARD['hq_fax']}",
              font=f_body, fill="#52616b")
    cy += 48

    # 行動電話（紅色強調）
    _square_bullet(cx, cy)
    draw.text((cx + 30, cy - 4), "行動電話：",
              font=f_body, fill="#1f2933")
    draw.text((cx + 30 + 130, cy - 8), BUSINESS_CARD["mobile"],
              font=f_mobile, fill="#c8102e")
    cy += 50

    # Email
    _square_bullet(cx, cy)
    draw.text((cx + 30, cy), f"電子郵件：{BUSINESS_CARD['email']}",
              font=f_body, fill="#1f2933")
    cy += 36

    # 統一編號（小字）
    f_small = _font(18)
    draw.text((cx + 30, cy), f"統一編號：{BUSINESS_CARD['uniform_no']}",
              font=f_small, fill="#9aa5b1")

    # 底部紅色裝飾條
    draw.rectangle([(0, H - 10), (W * 0.6, H)], fill="#c8102e")
    draw.rectangle([(W * 0.6, H - 10), (W, H)], fill="#52616b")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "business_card.png"
    img.save(out, optimize=True)
    return out


if __name__ == "__main__":
    p1 = make_solar_term_image()
    p2 = make_regional_crops_image()
    p3 = make_motivation_image()
    p4 = make_business_card_image()
    p5 = make_sales_target_image()
    print(f"已產出：{p1}")
    print(f"已產出：{p2}")
    print(f"已產出：{p3}")
    print(f"已產出：{p4}")
    print(f"已產出：{p5}")
