"""
一鍵 GitHub 自動化設定
- 自動 push 程式碼到 GitHub（如果還沒 push）
- 設定 5 個 Secrets（GMAIL_*、MAIL_TO、LINE_*、APIFY_*）
- 觸發第一次 workflow 執行（手動排程）
- 顯示 workflow 執行 URL 讓你監看

使用方式：
  python3 setup_github.py
照提示貼上 tokens 即可
"""

import base64
import getpass
import os
import subprocess
import sys
import time

import requests
from nacl import encoding, public

from email_sender import _load_env

REPO_OWNER = "yuan780903-cpu"
REPO_NAME = "market-scraper"
REPO = f"{REPO_OWNER}/{REPO_NAME}"
API = "https://api.github.com"


def prompt(label, secret=False):
    """提示輸入，secret=True 時不顯示輸入內容"""
    if secret:
        v = getpass.getpass(f"  {label}（輸入時不會顯示）: ")
    else:
        v = input(f"  {label}: ")
    return v.strip()


def gh_get(url, pat):
    r = requests.get(url, headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def gh_put(url, pat, payload):
    r = requests.put(url, headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }, json=payload, timeout=30)
    return r


def gh_post(url, pat, payload):
    r = requests.post(url, headers={
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
    }, json=payload, timeout=30)
    return r


def encrypt_secret(public_key_b64: str, value: str) -> str:
    pk = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(value.encode("utf-8"))
    return base64.b64encode(sealed).decode("utf-8")


def try_git_push(pat: str) -> bool:
    """用 PAT 在 URL 內嵌 push。處理 3 種狀況：
    1) 本機有未 commit 變更 → auto add+commit
    2) 遠端較新 → pull --rebase 再 push
    3) 兩者皆有 → 先 commit、再 pull、再 push"""
    print("\n[git] 推送程式碼到 GitHub ...")
    push_url = f"https://{REPO_OWNER}:{pat}@github.com/{REPO}.git"

    def _run(cmd):
        return subprocess.run(cmd, cwd=".", capture_output=True, text=True)

    def _print(result):
        out = (result.stdout + result.stderr).replace(pat, "***")
        print(out[-500:] if len(out) > 500 else out)

    # 設 identity（rebase / commit 都需要）
    _run(["git", "config", "user.email", "yuan780903@gmail.com"])
    _run(["git", "config", "user.name", REPO_OWNER])

    # Step 1: 若有未 commit 的變更，自動 commit
    status = _run(["git", "status", "--porcelain"])
    if status.stdout.strip():
        print("  [git] 本機有變更，自動 commit ...")
        _run(["git", "add", "-A"])
        commit_msg = f"chore: local changes synced via setup_github @ {time.strftime('%Y-%m-%d %H:%M')}"
        commit_result = _run(["git", "commit", "-m", commit_msg])
        if commit_result.returncode != 0:
            _print(commit_result)
        else:
            print("  ✓ 自動 commit 完成")

    # Step 2: 嘗試 push
    result = _run(["git", "push", "-u", push_url, "main"])
    if result.returncode == 0:
        _print(result)
        return True

    # Step 3: 被拒 → pull --rebase 再 push；rebase 衝突就 force push
    err = (result.stdout + result.stderr).lower()
    if "rejected" in err or "fetch first" in err or "non-fast-forward" in err:
        print("  ⚠ 遠端較新，自動 pull --rebase 整合 ...")
        pull_result = _run(["git", "pull", "--rebase", push_url, "main"])
        if pull_result.returncode == 0:
            print("  ✓ pull 成功，重試 push ...")
            retry = _run(["git", "push", "-u", push_url, "main"])
            _print(retry)
            return retry.returncode == 0

        # rebase 衝突 → abort + force push（私有 repo 安全）
        _print(pull_result)
        print("  ⚠ rebase 衝突，自動 abort 後 force push 覆寫遠端")
        print("    （此 repo 為私有，本機是最新版本，遠端只有空 Initial commit）")
        _run(["git", "rebase", "--abort"])
        force = _run(["git", "push", "-u", "--force", push_url, "main"])
        _print(force)
        return force.returncode == 0

    _print(result)
    return False


def main():
    print("=" * 60)
    print("  GitHub 自動化設定 — 一鍵搞定")
    print(f"  目標 repo: {REPO}")
    print("=" * 60)

    print("\n請依序貼入下列資訊（之前已重置過的請貼新的）：\n")

    # 從 .env 自動載入 3 個 token（你只需要提供 GitHub PAT）
    _load_env()
    line_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    apify_token = os.environ.get("APIFY_API_TOKEN", "").strip()
    cwa_token = os.environ.get("CWA_API_KEY", "").strip()

    print("從 .env 自動載入：")
    print(f"  ✓ LINE_CHANNEL_ACCESS_TOKEN: {line_token[:8]}...{line_token[-6:] if len(line_token) > 14 else ''}")
    print(f"  ✓ APIFY_API_TOKEN:           {apify_token[:14]}...{apify_token[-4:] if len(apify_token) > 18 else ''}")
    print(f"  ✓ CWA_API_KEY:               {cwa_token[:12]}...{cwa_token[-6:] if len(cwa_token) > 18 else ''}")
    print()

    missing = [n for n, v in [("LINE", line_token), ("Apify", apify_token), ("CWA", cwa_token)] if not v]
    if missing:
        print(f"⚠ 缺：{', '.join(missing)}（請先補進 .env 再跑此腳本）")
        sys.exit(1)
    print()

    pat = prompt("請貼 GitHub Personal Access Token (ghp_...)", secret=True)
    if not pat.startswith("ghp_") and not pat.startswith("github_pat_"):
        print(f"⚠ token 格式怪怪的（{pat[:8]}...），繼續嘗試")

    secrets = {
        "LINE_CHANNEL_ACCESS_TOKEN": line_token,
        "APIFY_API_TOKEN": apify_token,
        "CWA_API_KEY": cwa_token,
    }

    # === 0. 驗證 PAT ===
    print("\n[1/4] 驗證 GitHub PAT ...")
    try:
        user = gh_get(f"{API}/user", pat)
        print(f"  ✓ 登入身分：{user['login']}")
    except Exception as e:
        print(f"  ✗ PAT 無效或網路問題：{e}")
        sys.exit(1)

    # === 1. push 程式碼 ===
    print("\n[2/4] 推送程式碼到 GitHub")
    push_ok = try_git_push(pat)
    if push_ok:
        print("  ✓ push 成功")
    else:
        print("  ⚠ push 失敗（可能已是最新，繼續往下）")

    # === 2. 取得 repo public key ===
    print("\n[3/4] 設定 5 個 Secrets")
    try:
        key_data = gh_get(f"{API}/repos/{REPO}/actions/secrets/public-key", pat)
    except Exception as e:
        print(f"  ✗ 取不到 repo public key：{e}")
        print("  → 確認 repo 存在且 PAT 有 repo 權限")
        sys.exit(1)
    public_key = key_data["key"]
    key_id = key_data["key_id"]

    # === 3. 設 5 個 secrets ===
    for name, value in secrets.items():
        if not value:
            print(f"  - {name}: 空值，跳過")
            continue
        encrypted = encrypt_secret(public_key, value)
        r = gh_put(
            f"{API}/repos/{REPO}/actions/secrets/{name}",
            pat,
            {"encrypted_value": encrypted, "key_id": key_id},
        )
        if r.status_code in (201, 204):
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name}: {r.status_code} {r.text[:100]}")

    # === 4. 觸發 workflow ===
    print("\n[4/4] 觸發第一次 workflow")
    r = gh_post(
        f"{API}/repos/{REPO}/actions/workflows/weekly.yml/dispatches",
        pat,
        {"ref": "main"},
    )
    if r.status_code == 204:
        print("  ✓ 已觸發！")
    else:
        print(f"  ⚠ 觸發回 {r.status_code}: {r.text[:200]}")
        print("  → 如果是 404，到 GitHub Actions 頁面手動點 Enable Actions 再重跑此腳本")

    print()
    print("=" * 60)
    print("完成！監看連結：")
    print(f"  https://github.com/{REPO}/actions")
    print("等 3-5 分鐘後，手機 LINE 應該會收到完整週報")
    print("=" * 60)


if __name__ == "__main__":
    main()
