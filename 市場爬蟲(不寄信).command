#!/bin/bash
# 雙擊執行：只爬資料、產報表，不寄 email（測試用）

# 解析 symlink 後切到實際專案目錄（讓 Desktop 捷徑也能用）
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
cd "$(cd -P "$(dirname "$SOURCE")" && pwd)"

echo "================================================"
echo "  有機肥料市場資訊蒐集（不寄信）"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"
echo ""

python3 main.py --no-mail

EXIT_CODE=$?

echo ""
echo "================================================"
if [ $EXIT_CODE -eq 0 ]; then
  echo "  ✓ 完成！HTML 報表已開啟，按任意鍵關閉視窗"
  # 自動打開最新 HTML 報表
  LATEST_HTML=$(ls -t output/市場日報_*.html 2>/dev/null | head -1)
  if [ -n "$LATEST_HTML" ]; then
    open "$LATEST_HTML"
  fi
else
  echo "  ⚠ 執行有錯誤（exit code: $EXIT_CODE），按任意鍵關閉"
fi
echo "================================================"
read -n 1 -s
