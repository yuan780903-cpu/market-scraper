#!/bin/bash
# 雙擊執行：一鍵設定 GitHub Secrets + push + 觸發 workflow

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
cd "$(cd -P "$(dirname "$SOURCE")" && pwd)"

echo "================================================"
echo "  GitHub 自動化一鍵設定"
echo "================================================"
echo ""

python3 setup_github.py

echo ""
echo "================================================"
echo "  按任意鍵關閉視窗"
echo "================================================"
read -n 1 -s
