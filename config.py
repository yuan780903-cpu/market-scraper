"""
設定檔 — 你可以自己改這裡的關鍵字、網站清單
不需要懂程式，只要照格式增刪即可
"""

KEYWORDS = [
    # 肥料類
    "有機質肥料",
    "有機肥料",
    "有機肥",
    "肥料",
    "堆肥",
    "生物肥料",
    "微生物肥料",
    "有機農業",
    "肥料補助",
    "國產有機質肥料",
    "推薦補助",
    "肥料價格",
    "肥料登記",
    # 活動類（改良場常用）
    "觀摩會",
    "示範會",
    "推廣會",
    "研習",
    "訓練班",
    "報名",
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

    # 7 個區農業改良場（共用 theme_list.php?theme=hotnews_ws 結構）
    # 套 KEYWORDS 過濾（含肥料 + 活動詞）
    {"name": "桃園區農改場", "structure": "dares_grid", "requires_keyword": True,
     "url": "https://www.tydares.gov.tw/theme_list.php?theme=hotnews_ws"},
    {"name": "苗栗區農改場", "structure": "dares_grid", "requires_keyword": True,
     "url": "https://www.mdares.gov.tw/theme_list.php?theme=hotnews_ws"},
    {"name": "台中區農改場", "structure": "dares_grid", "requires_keyword": True,
     "url": "https://www.tcdares.gov.tw/theme_list.php?theme=hotnews_ws"},
    {"name": "台南區農改場", "structure": "dares_grid", "requires_keyword": True,
     "url": "https://www.tndais.gov.tw/theme_list.php?theme=hotnews_ws"},
    {"name": "高雄區農改場", "structure": "dares_grid", "requires_keyword": True,
     "url": "https://www.kdais.gov.tw/theme_list.php?theme=hotnews_ws"},
    {"name": "花蓮區農改場", "structure": "dares_grid", "requires_keyword": True,
     "url": "https://www.hdares.gov.tw/theme_list.php?theme=hotnews_ws"},
    {"name": "台東區農改場", "structure": "dares_grid", "requires_keyword": True,
     "url": "https://www.ttdares.gov.tw/theme_list.php?theme=hotnews_ws"},
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
    {"name": "Google News - 泰霖生物科技", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E6%B3%B0%E9%9C%96%E7%94%9F%E7%89%A9%E7%A7%91%E6%8A%80+%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 泰霖", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E6%B3%B0%E9%9C%96+%E6%9C%89%E6%A9%9F%E8%82%A5&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    # 主要競爭對手 / 大廠
    {"name": "Google News - 台肥", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E5%8F%B0%E8%82%A5+%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 興農肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E8%88%88%E8%BE%B2+%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 中華肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E4%B8%AD%E8%8F%AF%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 禾康肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E7%A6%BE%E5%BA%B7+%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    # 價格 / 促銷 / 補助 動態
    {"name": "Google News - 肥料價格", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E8%82%A5%E6%96%99+%E5%83%B9%E6%A0%BC&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 肥料漲價", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E8%82%A5%E6%96%99+%E6%BC%B2%E5%83%B9&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 有機資材補助", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E6%9C%89%E6%A9%9F%E8%B3%87%E6%9D%90+%E8%A3%9C%E5%8A%A9&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 有機認證", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E6%9C%89%E6%A9%9F%E8%AA%8D%E8%AD%89&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 農會肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E8%BE%B2%E6%9C%83+%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    # 上游/原料/趨勢
    {"name": "Google News - 雞糞 肥料", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E9%9B%9E%E7%B3%9E+%E8%82%A5%E6%96%99&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google News - 廚餘 堆肥", "category": "新聞",
     "url": "https://news.google.com/rss/search?q=%E5%BB%9A%E9%A4%98+%E5%A0%86%E8%82%A5&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
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

# ==========================================
# FB 粉專追蹤（透過 Apify）
# ==========================================
# 注意：apify/facebook-posts-scraper 是 paid actor，實測 $5/月可能跑 1-2 次完整推送
# 若 6/1 配額刷新後又用完，請考慮：
#   (1) 把 FB_PAGES 再砍半 (2) 改抽便宜 scraper (3) 升級 Apify
#
# 目前精選 12 個業務最相關的粉專（同業/重點改良場/重點農會/農糧署）
FB_PAGES = [
    # ===== 競爭同業 / 經銷商（4 個）=====
    "https://www.facebook.com/888HS888/",                                       # 宏生農業生化
    "https://www.facebook.com/fsfeiliao/",                                      # 福壽肥料
    "https://www.facebook.com/p/泰霖生物科技有限公司-100063778283357/",            # 泰霖生物科技
    "https://www.facebook.com/people/台肥農業推廣中心/100057266087190/",            # 台肥農業推廣中心

    # ===== 政府/官方（1 個）=====
    "https://www.facebook.com/afayayaya/",       # 農糧署（鮮享農YA）

    # ===== 重點改良場（4 個，主要農業大區）=====
    "https://www.facebook.com/tydares/",         # 桃園農改場
    "https://www.facebook.com/tdares/",          # 台中農改場
    "https://www.facebook.com/tndais/",          # 台南農改場
    "https://www.facebook.com/Kaohsiung.DAIS/",  # 高雄農改場

    # ===== 重點縣農會（3 個，有機/稻作大縣）=====
    "https://www.facebook.com/p/雲林縣農會-100090170528272/",  # 雲林（米倉）
    "https://www.facebook.com/chiayifarmers/",                # 嘉義
    "https://www.facebook.com/fwres3030/",                    # 屏東（有機大縣）
]

# 每個粉專最多抓最近幾篇貼文（影響 Apify 配額消耗）
FB_POSTS_PER_PAGE = 8

# Apify 餘額低於此值時自動跳過 FB 抓取（避免重蹈覆轍）
APIFY_MIN_REMAINING_USD = 0.5

# HTML 日報顯示天數（多少天內的新聞算「近期」）
# 有機肥料新聞不是每天都有，建議 7~30 天
REPORT_RECENT_DAYS = 14

# 近期資料 < 此筆數時，自動 fallback 顯示最新 N 則
REPORT_FALLBACK_MIN = 5
REPORT_FALLBACK_TOP = 15
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
