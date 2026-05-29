"""
設定檔 — 你可以自己改這裡的關鍵字、網站清單
不需要懂程式，只要照格式增刪即可
"""

KEYWORDS = [
    "有機質肥料",
    "有機肥料",
    "有機肥",
    "堆肥",
    "生物肥料",
    "微生物肥料",
    "有機農業",
    "肥料補助",
    "肥料價格",
    "肥料登記",
]

GOV_SOURCES = [
    # AFA 卡片結構 (agricultural-news class) — 自動抽出標題+日期
    {
        "name": "農糧署 - 農業新聞",
        "url": "https://www.afa.gov.tw/cht/index.php?code=list&ids=307",
        "structure": "afa_card",
        "requires_keyword": False,
    },
    {
        "name": "農糧署 - 最新消息",
        "url": "https://www.afa.gov.tw/cht/index.php?code=list&ids=379",
        "structure": "afa_card",
        "requires_keyword": False,
    },
    {
        "name": "農糧署 - 近日焦點",
        "url": "https://www.afa.gov.tw/cht/index.php?code=list&ids=310",
        "structure": "afa_card",
        "requires_keyword": False,
    },
]

# RSS 來源 — category 區分「新聞」「活動」，HTML 報表會分開顯示
# 想加新的關鍵字：複製一行改 q= 後面的關鍵字（URL 編碼用 https://www.urlencoder.org/）
RSS_FEEDS = [
    # ===== 新聞類 =====
    {"name": "Google News - 有機肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E6%9C%89%E6%A9%9F%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 有機質肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E6%9C%89%E6%A9%9F%E8%B3%AA%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 堆肥", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E5%A0%86%E8%82%A5+%E8%BE%B2%E6%A5%AD&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 肥料補助", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E8%82%A5%E6%96%99%E8%A3%9C%E5%8A%A9&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    # 同業/品牌 (888HS888 = 宏生農業生化、福壽肥料)
    {"name": "Google News - 福壽肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E7%A6%8F%E5%A3%BD+%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 宏生農業", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E5%AE%8F%E7%94%9F+%E6%9C%89%E6%A9%9F%E8%82%A5&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "農傳媒", "category": "新聞",
     "url": "https://www.agriharvest.tw/feed"},

    # ===== 活動類（觀摩會、推廣會、示範會、研習）=====
    {"name": "Google News - 肥料觀摩會", "category": "活動",
     "url": "https://news.google.com/rss/search?q=%E8%82%A5%E6%96%99+%E8%A7%80%E6%91%A9%E6%9C%83&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 有機肥推廣", "category": "活動",
     "url": "https://news.google.com/rss/search?q=%E6%9C%89%E6%A9%9F%E8%82%A5+%E6%8E%A8%E5%BB%A3&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 農改場觀摩會", "category": "活動",
     "url": "https://news.google.com/rss/search?q=%E8%BE%B2%E6%94%B9%E5%A0%B4+%E8%A7%80%E6%91%A9%E6%9C%83&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 田間示範", "category": "活動",
     "url": "https://news.google.com/rss/search?q=%E7%94%B0%E9%96%93+%E7%A4%BA%E7%AF%84&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 農業推廣會", "category": "活動",
     "url": "https://news.google.com/rss/search?q=%E8%BE%B2%E6%A5%AD+%E6%8E%A8%E5%BB%A3%E6%9C%83&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 農業試驗所", "category": "活動",
     "url": "https://news.google.com/rss/search?q=%E8%BE%B2%E6%A5%AD%E8%A9%A6%E9%A9%97%E6%89%80+%E6%8E%A8%E5%BB%A3&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
]

OUTPUT_DIR = "output"
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1.5

# 農糧署有機質肥料推薦名單 PDF（要監控上架/下架的核心資料）
# 同類型公告若更新，到 config 改 article_id 即可
PDF_LIST_PAGE = "https://www.afa.gov.tw/cht/index.php?code=list&flag=detail&ids=2212&article_id=22432"

# 快照存放（每次跑會比對上次）
SNAPSHOT_DIR = "snapshots"

# PDF 變動報表只顯示近 N 天（依上網日/下網日篩選）
PDF_CHANGE_DAYS = 30

# HTML 日報顯示天數（多少天內的新聞算「近期」）
# 有機肥料新聞不是每天都有，建議 7~30 天
REPORT_RECENT_DAYS = 14

# 近期資料 < 此筆數時，自動 fallback 顯示最新 N 則
REPORT_FALLBACK_MIN = 5
REPORT_FALLBACK_TOP = 15
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
