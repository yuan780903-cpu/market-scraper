# 有機肥料市場資訊蒐集程式

自動蒐集政府公告 + 新聞 + 觀摩活動，監控農糧署推薦名單 PDF 的上架/下架/違規，
輸出 Excel + HTML 報表，可寄到 Gmail，可週報推播到 LINE 官方帳號。

## 一鍵按鈕（桌面快捷）

| 按鈕 | 用途 |
|---|---|
| `市場爬蟲執行.command` | 跑完整爬蟲，寄 Email |
| `市場爬蟲執行(不寄信).command` | 只爬資料、開啟 HTML 預覽，不寄信 |
| `週報推LINE.command` | 跑爬蟲 → 上傳 HTML → 推 LINE 官方帳號廣播 |
| `週報推LINE(預覽不推播).command` | 同上但只預覽訊息內容、不真的推 |

雙擊就跑，終端視窗會留到你按任意鍵才關。

## 第一次使用

### 1. 安裝套件
```bash
cd ~/Desktop/市場爬蟲
pip3 install -r requirements.txt
```

### 2. 設定 .env
```bash
cp .env.example .env && open -e .env
```
照註解說明填入 Gmail 與 LINE 的設定。

### 3. Gmail 設定（寄信用）
- 開兩步驟驗證：https://myaccount.google.com/security
- 產生 App Password：https://myaccount.google.com/apppasswords（複製 16 碼）
- 填到 `.env` 的 `GMAIL_APP_PASSWORD=`

### 4. LINE 官方帳號設定（週報推播用）
1. 到 https://developers.line.biz/console/ 用 LINE 帳號登入
2. **建立 Provider**（第一次用）
3. 在 Provider 下「**Create a Messaging API channel**」
4. 重要：到 https://manager.line.biz/ → 你的官方帳號 → 「設定」→「Messaging API」→ 啟用並連到剛剛建的 channel
5. 回 LINE Developers Console → 你的 channel → 「Messaging API」分頁
6. 拉到下方「Channel access token」→ 點「Issue」產生長效 token
7. 把 token 完整貼到 `.env` 的 `LINE_CHANNEL_ACCESS_TOKEN=` 後面

⚠️ **免費方案限制**：每月 200 則訊息（週報每月 4 則綽綽有餘）  
⚠️ **Broadcast 會推給「所有粉絲」**：先測試「預覽不推播」確認內容後再正式推

## 客製化（修改 config.py）

| 設定 | 預設 | 說明 |
|---|---|---|
| `KEYWORDS` | 9 個關鍵字 | 政府公告與「新聞」類 RSS 的標題過濾字詞 |
| `RSS_FEEDS` | 13 個 RSS | Google News + 農傳媒，分「新聞 / 活動」兩類 |
| `GOV_SOURCES` | 3 個 AFA | 農糧署的新聞/最新消息/近日焦點 |
| `PDF_CHANGE_DAYS` | 30 | PDF 變動只顯示近 N 天 |
| `REPORT_RECENT_DAYS` | 14 | HTML 報表顯示近 N 天新聞 |

### 加新的 Google News 關鍵字
複製 `config.py` 內 RSS_FEEDS 任一筆，把 `q=` 後面字詞改成你要的（URL 編碼用 https://www.urlencoder.org/）。

## 已知限制

- **Facebook 抓不到** — FB 鎖死非登入存取（用 Google News 搜該粉專相關新聞當替代）
- **政府網站常 timeout** — 已改用 AFA 卡片結構抓取，較穩定
- **HTML 報表 URL 用 catbox.moe** — 公開可見（注意機密內容），若 catbox 失效會 fallback 到 litterbox（72h 暫存）

## 檔案結構

```
市場爬蟲/
├── main.py                       # Email 主流程
├── weekly_line_push.py           # LINE 週報主流程
├── config.py                     # 設定檔
├── scraper_gov.py                # 政府公告
├── scraper_news.py               # 新聞 RSS
├── scraper_pdf.py                # 農糧署 PDF 監控
├── report.py                     # HTML 報表生成
├── email_sender.py               # Gmail 寄信
├── line_sender.py                # LINE Messaging API
├── line_summary.py               # LINE 文字摘要
├── uploader.py                   # HTML 上傳到公開 host
├── .env / .env.example
├── requirements.txt
├── 市場爬蟲*.command             # 一鍵按鈕
├── 週報推LINE*.command
├── output/                       # 產出 HTML/Excel/CSV/PDF
└── snapshots/                    # PDF 監控的歷史快照
```

## 後續可能要的功能

- **每週自動推播** → 需上 GitHub Actions 雲端排程（Mac 會關機）
- **HTML 報表永久 URL** → 改用 GitHub Pages 取代 catbox.moe
- **更多競爭對手品牌追蹤** → 在 config.py RSS_FEEDS 加品牌名關鍵字
