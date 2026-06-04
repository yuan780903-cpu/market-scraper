"""
LINE Rich Menu 圖文選單設計 (2x4 = 8 按鈕，可愛動物/作物風格)
- 規格：2500 x 1686（large size）
- 版型：2 列 × 4 欄 = 8 個按鈕
- 每格鮮豔不同色背景 + Twemoji 圖示 + 主標/副標
"""

from pathlib import Path
from typing import List

from PIL import Image, ImageDraw, ImageFont

from image_card import _find_font_path

# Rich Menu 大尺寸
WIDTH = 2500
HEIGHT = 1686

# 2x4 grid
COLS = 4
ROWS = 2
CELL_W = WIDTH // COLS   # 625
CELL_H = HEIGHT // ROWS  # 843

# 文字顏色
COLOR_TEXT_TITLE = "#1f2933"
COLOR_TEXT_SUB = "#5b5b5b"

EMOJI_DIR = Path("output/emoji")
OUTPUT_DIR = Path("output/richmenu")


# 8 個按鈕：(col, row, 背景色, emoji 檔名, 主標, 副標)
BUTTONS = [
    (0, 0, "#bce4a8", "1f96c.png", "產銷班查詢", "農糧署系統"),       # 蔬菜 嫩綠
    (1, 0, "#ffe27a", "1f414.png", "肥料廠牌查詢", "登記查詢"),        # 蛋雞 蛋黃
    (2, 0, "#ffc3d8", "1f437.png", "目標業績", "達成追蹤"),            # 豬   蜜桃粉
    (3, 0, "#a3dfe0", "1f986.png", "農情報告網", "即時農情"),          # 鴨子 湖水藍
    (0, 1, "#ffa39e", "1f34e.png", "產品牌價", "各通路價格"),          # 蘋果 番茄紅
    (1, 1, "#a4ccf2", "1f41f.png", "肥料法規", "管理法規"),            # 魚   天空藍
    (2, 1, "#d9b9f0", "1f404.png", "肥料登記證", "產品登記查詢"),      # 乳牛 薰衣草紫
    (3, 1, "#ffc88c", "1f347.png", "營運許可證", "業者許可查詢"),      # 葡萄 橘子橙
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_find_font_path(), size)


def _measure(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _load_emoji(filename: str, size: int) -> Image.Image:
    """載入 Twemoji 並 resize 到指定大小"""
    p = EMOJI_DIR / filename
    img = Image.open(p).convert("RGBA")
    return img.resize((size, size), Image.LANCZOS)


def _draw_button(img, draw, col, row, bg_color, emoji_file, title, subtitle):
    """畫一格按鈕。subtitle 參數保留向後相容，但不再渲染（使用者要求去除）。"""
    x0 = col * CELL_W
    y0 = row * CELL_H
    x1 = x0 + CELL_W
    y1 = y0 + CELL_H

    # 1. 鮮豔色背景（鋪滿整格）
    draw.rectangle([(x0, y0), (x1, y1)], fill=bg_color)

    # 2. 白色圓圈底襯（配合字級放大）
    circle_r = 200
    cx_circle = x0 + CELL_W // 2
    cy_circle = y0 + 270
    draw.ellipse(
        [(cx_circle - circle_r, cy_circle - circle_r),
         (cx_circle + circle_r, cy_circle + circle_r)],
        fill="#ffffff",
    )

    # 3. Emoji（放大、置中於白圓內）
    emoji_size = 320
    emoji_img = _load_emoji(emoji_file, emoji_size)
    ex = x0 + CELL_W // 2 - emoji_size // 2
    ey = cy_circle - emoji_size // 2
    img.paste(emoji_img, (ex, ey), emoji_img)

    # 4. 主標（單行、置中、加描邊模擬粗體效果）
    f_title = _font(72)
    tw, th = _measure(draw, title, f_title)
    draw.text(
        (x0 + CELL_W // 2 - tw // 2, y0 + 600),
        title,
        font=f_title,
        fill=COLOR_TEXT_TITLE,
        stroke_width=2,
        stroke_fill=COLOR_TEXT_TITLE,
    )

    # 5. 白色細邊框（區隔各格）
    draw.rectangle([(x0, y0), (x1, y1)], outline="#ffffff", width=8)


def make_richmenu_image() -> Path:
    img = Image.new("RGB", (WIDTH, HEIGHT), "#ffffff")
    draw = ImageDraw.Draw(img)
    for col, row, bg, emoji, title, subtitle in BUTTONS:
        _draw_button(img, draw, col, row, bg, emoji, title, subtitle)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "richmenu_v2.png"
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
        print(f"  {a['title']:<10} x={b['x']:<4} y={b['y']:<4} w={b['width']} h={b['height']}")
