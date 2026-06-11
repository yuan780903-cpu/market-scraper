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

# 版權署名 banner（底部裝飾，不可點）
BANNER_H = 200
BANNER_Y = HEIGHT - BANNER_H  # = 1486，從這 y 起算到底部

# 3x3 grid (9 宮格) — 從 banner 下方開始
COLS = 3
ROWS = 3
CELL_W = WIDTH // COLS                    # 833
CELL_H = (HEIGHT - BANNER_H) // ROWS      # 495

PORTRAIT_PATH = Path("output/portrait_circle.png")

# 文字顏色
COLOR_TEXT_TITLE = "#1f2933"
COLOR_TEXT_SUB = "#5b5b5b"

EMOJI_DIR = Path("output/emoji")
OUTPUT_DIR = Path("output/richmenu")


# 9 個按鈕：(col, row, 背景色, emoji 檔名, 主標, 副標)
BUTTONS = [
    # 第一列
    (0, 0, "#bce4a8", "1f96c.png", "產銷班查詢", "農糧署系統"),       # 蔬菜 嫩綠
    (1, 0, "#ffe27a", "1f414.png", "肥料廠牌查詢", "登記查詢"),        # 蛋雞 蛋黃
    (2, 0, "#ffc3d8", "1f437.png", "目標業績", "達成追蹤"),            # 豬   蜜桃粉
    # 第二列
    (0, 1, "#a3dfe0", "1f986.png", "農情報告網", "即時農情"),          # 鴨子 湖水藍
    (1, 1, "#ffa39e", "1f34e.png", "產品牌價", "各通路價格"),          # 蘋果 番茄紅
    (2, 1, "#a4ccf2", "1f41f.png", "品牌推薦規範", "農糧署作業規範"),   # 魚   天空藍
    # 第三列
    (0, 2, "#d9b9f0", "1f9fe.png", "報價系統", "線上開單"),            # 收據 薰衣草紫
    (1, 2, "#ffc88c", "1f347.png", "肥料品目規格", "農糧署修正規定"),  # 葡萄 橘子橙
    (2, 2, "#f5d0a9", "1f404.png", "預先登錄申請", "銷售申報系統"),    # 乳牛 奶茶色
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


def _draw_banner(img, draw):
    """底部裝飾橫條：頭像 + 版權署名（不可點區域）"""
    # 1. 漸層綠色背景 — 從左到右淺到深，y 從 BANNER_Y 開始
    for x in range(WIDTH):
        ratio = x / WIDTH
        r = int(31 + (76 - 31) * ratio)   # #1f3a2e → #4caf73
        g = int(58 + (175 - 58) * ratio)
        b = int(46 + (115 - 46) * ratio)
        draw.line([(x, BANNER_Y), (x, HEIGHT)], fill=(r, g, b))

    # 2. 頭像（圓形，左側偏中）
    portrait_size = 160
    portrait_x = WIDTH // 2 - 460          # 頭像中心點 X
    portrait_y = BANNER_Y + BANNER_H // 2  # 頭像中心點 Y（banner 垂直中央）
    if PORTRAIT_PATH.exists():
        try:
            p_img = Image.open(PORTRAIT_PATH).convert("RGBA")
            p_img = p_img.resize((portrait_size, portrait_size), Image.LANCZOS)
            # 白色描邊圓框
            ring_r = portrait_size // 2 + 6
            draw.ellipse(
                [(portrait_x - ring_r, portrait_y - ring_r),
                 (portrait_x + ring_r, portrait_y + ring_r)],
                fill="#ffffff",
            )
            img.paste(p_img,
                      (portrait_x - portrait_size // 2, portrait_y - portrait_size // 2),
                      p_img)
        except Exception:
            pass

    # 3. 版權文字（頭像右側）
    text = "系統版權所有人：莊政遠"
    f = _font(64)
    tw, th = _measure(draw, text, f)
    tx = portrait_x + portrait_size // 2 + 50
    ty = BANNER_Y + BANNER_H // 2 - th // 2 - 6
    draw.text((tx, ty), text, font=f, fill="#ffffff",
              stroke_width=2, stroke_fill="#ffffff")


def _draw_button(img, draw, col, row, bg_color, emoji_file, title, subtitle):
    """畫一格按鈕。subtitle 參數保留向後相容，但不再渲染（使用者要求去除）。"""
    x0 = col * CELL_W
    y0 = row * CELL_H              # 9 格從頂部開始，底部留給 banner
    x1 = x0 + CELL_W
    y1 = y0 + CELL_H

    # 1. 鮮豔色背景（鋪滿整格）
    draw.rectangle([(x0, y0), (x1, y1)], fill=bg_color)

    # 9 宮格 layout：CELL 833×495（高度縮過為 banner 騰空間），重新排版
    # 2. 白色圓圈底襯
    circle_r = 150
    cx_circle = x0 + CELL_W // 2
    cy_circle = y0 + 170
    draw.ellipse(
        [(cx_circle - circle_r, cy_circle - circle_r),
         (cx_circle + circle_r, cy_circle + circle_r)],
        fill="#ffffff",
    )

    # 3. Emoji（置中於白圓內）
    emoji_size = 230
    emoji_img = _load_emoji(emoji_file, emoji_size)
    ex = x0 + CELL_W // 2 - emoji_size // 2
    ey = cy_circle - emoji_size // 2
    img.paste(emoji_img, (ex, ey), emoji_img)

    # 4. 主標（單行、置中、加描邊模擬粗體效果）
    f_title = _font(60)
    tw, th = _measure(draw, title, f_title)
    draw.text(
        (x0 + CELL_W // 2 - tw // 2, y0 + 350),
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
    _draw_banner(img, draw)
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
                "y": row * CELL_H,             # 9 格從頂部開始
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
