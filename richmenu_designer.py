"""
LINE Rich Menu 圖文選單設計
- 規格：2500 x 1686（large size，最常見）
- 版型：2 列 × 3 欄 = 6 個按鈕
- 風格：深綠 + 米白底，B2B 專業資訊調性
- 每個按鈕：頂部圖示（幾何形狀）+ 主標題 + 副標題
"""

from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

from image_card import _find_font_path

# Rich Menu 大尺寸
WIDTH = 2500
HEIGHT = 1686

# 2x3 grid
COLS = 3
ROWS = 2
CELL_W = WIDTH // COLS   # 833
CELL_H = HEIGHT // ROWS  # 843

# 配色（B2B 專業）
COLOR_BG = "#fafaf6"
COLOR_SEPARATOR = "#e8e6df"
COLOR_TEXT_TITLE = "#1f3a2e"      # 深綠
COLOR_TEXT_SUB = "#7a7565"        # 暖灰
COLOR_ICON_BG = "#1f3a2e"         # 深綠
COLOR_ICON_FG = "#ffffff"

# 強調色 (每個按鈕的小圓形色塊)
BUTTON_ACCENT = [
    "#2d6a4f",  # 綠
    "#1864ab",  # 藍
    "#a05c00",  # 棕
    "#5b4e8c",  # 紫
    "#c92a2a",  # 紅
    "#0e3a6b",  # 深藍
]

OUTPUT_DIR = Path("output/richmenu")


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_find_font_path(), size)


def _measure(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _draw_icon_circle(draw, cx, cy, radius, color, label_text=None):
    """畫一個圓形圖示底，可選擇在中央放短字（如「報」「肥」）"""
    draw.ellipse([(cx - radius, cy - radius), (cx + radius, cy + radius)], fill=color)
    if label_text:
        f = _font(int(radius * 1.2))
        w, h = _measure(draw, label_text, f)
        draw.text((cx - w // 2, cy - h // 2 - 6), label_text,
                  font=f, fill=COLOR_ICON_FG)


def _draw_button(draw, img, col, row, accent, icon_char, title, subtitle):
    """畫一格按鈕"""
    x = col * CELL_W
    y = row * CELL_H
    cx = x + CELL_W // 2
    cy = y + CELL_H // 2

    # 圓形圖示（上半部）
    icon_radius = 110
    _draw_icon_circle(draw, cx, y + 220, icon_radius, accent, icon_char)

    # 主標題（中央）
    f_title = _font(78)
    tw, th = _measure(draw, title, f_title)
    draw.text((cx - tw // 2, y + 410), title, font=f_title, fill=COLOR_TEXT_TITLE)

    # 副標題（標題下）
    f_sub = _font(36)
    sw, sh = _measure(draw, subtitle, f_sub)
    draw.text((cx - sw // 2, y + 530), subtitle, font=f_sub, fill=COLOR_TEXT_SUB)

    # 底部 accent 色條
    draw.rectangle([(x + 60, y + CELL_H - 90), (x + CELL_W - 60, y + CELL_H - 84)],
                    fill=accent)


def _draw_grid_lines(draw):
    """畫分隔線（淺色，當作按鈕邊界）"""
    # 垂直線
    for c in range(1, COLS):
        x = c * CELL_W
        draw.line([(x, 40), (x, HEIGHT - 40)], fill=COLOR_SEPARATOR, width=3)
    # 水平線
    for r in range(1, ROWS):
        y = r * CELL_H
        draw.line([(40, y), (WIDTH - 40, y)], fill=COLOR_SEPARATOR, width=3)


# Rich Menu 6 個按鈕設定（可在這裡改）
BUTTONS = [
    # (col, row, accent, icon, title, subtitle)
    (0, 0, BUTTON_ACCENT[0], "查", "產銷班查詢", "農糧署產銷班系統"),
    (1, 0, BUTTON_ACCENT[1], "牌", "肥料廠牌查詢", "農糧署登記查詢"),
    (2, 0, BUTTON_ACCENT[2], "標", "目標業績", "年度/季/月達成追蹤"),
    (0, 1, BUTTON_ACCENT[3], "情", "農情報告網", "農糧署即時農情"),
    (1, 1, BUTTON_ACCENT[4], "價", "產品牌價", "各通路最新單價"),
    (2, 1, BUTTON_ACCENT[5], "法", "肥料法規", "農糧署管理法規"),
]


def make_richmenu_image() -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), COLOR_BG)
    draw = ImageDraw.Draw(img)

    # 6 個按鈕
    for col, row, accent, icon, title, subtitle in BUTTONS:
        _draw_button(draw, img, col, row, accent, icon, title, subtitle)

    # 分隔線
    _draw_grid_lines(draw)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "richmenu_v1.png"
    img.save(out, optimize=True)
    return out


def get_button_areas() -> List[dict]:
    """回傳每個按鈕的座標區域（LINE Rich Menu API 用）"""
    areas = []
    for col, row, _, _, title, _ in BUTTONS:
        areas.append({
            "title": title,
            "bounds": {
                "x": col * CELL_W,
                "y": row * CELL_H,
                "width": CELL_W,
                "height": CELL_H,
            },
        })
    return areas


if __name__ == "__main__":
    p = make_richmenu_image()
    print(f"已產出：{p}")
    print(f"\n按鈕座標：")
    for a in get_button_areas():
        b = a["bounds"]
        print(f"  {a['title']:<8} x={b['x']:<4} y={b['y']:<4} w={b['width']} h={b['height']}")
