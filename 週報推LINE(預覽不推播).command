#!/bin/bash
# 雙擊執行：爬資料、產 HTML、上傳取 URL、生成 LINE 訊息文字但不真的推
# 用來確認訊息內容、URL 對不對

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
cd "$(cd -P "$(dirname "$SOURCE")" && pwd)"

echo "================================================"
echo "  週報 LINE 預覽（不推播）"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"
echo ""

python3 weekly_line_push.py --dry-run

echo ""
echo "================================================"
echo "  完成！按任意鍵關閉"
echo "================================================"
read -n 1 -s
