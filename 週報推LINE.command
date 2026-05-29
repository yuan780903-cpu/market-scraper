#!/bin/bash
# 雙擊執行：爬最新資料 → 上傳 HTML → 推 LINE 官方帳號廣播

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
cd "$(cd -P "$(dirname "$SOURCE")" && pwd)"

echo "================================================"
echo "  週報 LINE 推播"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"
echo ""

python3 weekly_line_push.py

EXIT_CODE=$?

echo ""
echo "================================================"
if [ $EXIT_CODE -eq 0 ]; then
  echo "  完成！按任意鍵關閉"
else
  echo "  失敗 (exit code: $EXIT_CODE)，按任意鍵關閉"
fi
echo "================================================"
read -n 1 -s
