#!/bin/bash
# 雙擊執行：自動爬資料、抓 PDF、產報表、寄 email
# 跑完後視窗不會自動關閉，按任意鍵才會關閉

# 解析 symlink 後切到實際專案目錄（讓 Desktop 捷徑也能用）
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
cd "$(cd -P "$(dirname "$SOURCE")" && pwd)"

echo "================================================"
echo "  有機肥料市場資訊蒐集"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"
echo ""

# 跑主程式（含寄信）
python3 main.py

EXIT_CODE=$?

echo ""
echo "================================================"
if [ $EXIT_CODE -eq 0 ]; then
  echo "  ✓ 完成！按任意鍵關閉視窗"
else
  echo "  ⚠ 執行有錯誤（exit code: $EXIT_CODE），按任意鍵關閉"
fi
echo "================================================"
read -n 1 -s
