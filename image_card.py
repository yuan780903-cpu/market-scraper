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


if __name__ == "__main__":
    p1 = make_solar_term_image()
    p2 = make_regional_crops_image()
    p3 = make_motivation_image()
    print(f"已產出：{p1}")
    print(f"已產出：{p2}")
    print(f"已產出：{p3}")
