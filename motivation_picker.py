"""
不重複輪播挑選器
- 用過的 ID 存到 snapshots/used_motivation.json
- 每次挑「未用過」中的隨機 1 條
- 全部用完才重置（金句、銷售手段各自獨立追蹤）
"""

import json
import random
from pathlib import Path
from typing import Dict, Optional

from config import SNAPSHOT_DIR
import motivation_kb

USED_FILE = Path(SNAPSHOT_DIR) / "used_motivation.json"


def _load() -> Dict:
    if not USED_FILE.exists():
        return {"quotes": [], "tactics": []}
    try:
        return json.loads(USED_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"quotes": [], "tactics": []}


def _save(data: Dict) -> None:
    USED_FILE.parent.mkdir(parents=True, exist_ok=True)
    USED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _pick(pool: list, used_ids: list, key: str) -> Optional[Dict]:
    available = [x for x in pool if x["id"] not in used_ids]
    if not available:
        # 全用完了 → 重置該類別（log 一下方便追蹤）
        print(f"[Motivation] {key} 池已輪播完一輪，重置")
        return None  # caller 會處理重置
    return random.choice(available)


def pick_quote_and_tactic(mark_used: bool = True) -> Dict:
    """挑一條未用過的金句 + 一條未用過的銷售手段。
    mark_used=True：標記為已用（正式推播用）
    mark_used=False：不寫檔（dry-run 預覽用）"""
    data = _load()

    quote = _pick(motivation_kb.QUOTES, data["quotes"], "quotes")
    if quote is None:
        data["quotes"] = []
        quote = _pick(motivation_kb.QUOTES, data["quotes"], "quotes")

    tactic = _pick(motivation_kb.TACTICS, data["tactics"], "tactics")
    if tactic is None:
        data["tactics"] = []
        tactic = _pick(motivation_kb.TACTICS, data["tactics"], "tactics")

    if mark_used:
        data["quotes"].append(quote["id"])
        data["tactics"].append(tactic["id"])
        _save(data)
        print(f"[Motivation] 本期金句 {quote['id']}（已用 {len(data['quotes'])}/{len(motivation_kb.QUOTES)}）｜"
              f"手段 {tactic['id']}（已用 {len(data['tactics'])}/{len(motivation_kb.TACTICS)}）")
    else:
        print(f"[Motivation] (dry-run) 預覽金句 {quote['id']}｜手段 {tactic['id']}")
    return {"quote": quote, "tactic": tactic}


if __name__ == "__main__":
    for i in range(3):
        result = pick_quote_and_tactic()
        print(f"\n--- 第 {i+1} 次 ---")
        print(f"金句：{result['quote']['text']}  — {result['quote']['author']}")
        print(f"手段：{result['tactic']['title']}")
