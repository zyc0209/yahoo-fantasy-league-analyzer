"""重新授權 Yahoo Fantasy API，並更新 .yahoo_data/.env 的 token。

用法：
    cd ~/fantasy && .venv/bin/python reauth_yahoo.py
"""
import shutil
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
TOKEN_ENV = ROOT / ".yahoo_data" / ".env"
REDIRECT_URI = "https://localhost:8888"  # 必須和 Yahoo App 設定的 Redirect URI 一致
AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API = "https://fantasysports.yahooapis.com/fantasy/v2"


def read_env(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def main() -> None:
    cfg = read_env(ENV)
    key, secret = cfg["YAHOO_CONSUMER_KEY"], cfg["YAHOO_CONSUMER_SECRET"]
    league_id = cfg.get("YAHOO_LEAGUE_ID", "")

    url = AUTH_URL + "?" + urllib.parse.urlencode(
        {"client_id": key, "redirect_uri": REDIRECT_URI, "response_type": "code"}
    )
    print("1) 瀏覽器會開啟 Yahoo 登入頁，請登入並按「同意」。")
    print("   如果沒有自動開啟，請手動打開：\n   " + url)
    webbrowser.open(url)
    print("\n2) 同意後會跳到 https://localhost:8888/?code=...，頁面顯示無法連線是正常的。")
    raw = input("   請把網址列的完整網址貼上（或只貼 code）：").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [raw])[0]

    r = requests.post(
        TOKEN_URL,
        auth=(key, secret),
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI},
        timeout=30,
    )
    if r.status_code != 200:
        sys.exit(f"換 token 失敗 HTTP {r.status_code}: {r.text[:300]}")
    tok = r.json()

    TOKEN_ENV.parent.mkdir(exist_ok=True)
    if TOKEN_ENV.exists():
        backup = TOKEN_ENV.with_name(f".env.bak-{int(time.time())}")
        shutil.copy2(TOKEN_ENV, backup)
        print(f"   舊 token 已備份為 .yahoo_data/{backup.name}")
    fields = {
        "YAHOO_ACCESS_TOKEN": tok["access_token"],
        "YAHOO_CONSUMER_KEY": key,
        "YAHOO_CONSUMER_SECRET": secret,
        "YAHOO_GUID": tok.get("xoauth_yahoo_guid") or "None",
        "YAHOO_REFRESH_TOKEN": tok["refresh_token"],
        "YAHOO_TOKEN_TIME": str(time.time()),
        "YAHOO_TOKEN_TYPE": tok.get("token_type", "bearer"),
    }
    TOKEN_ENV.write_text("\n".join(f"{k}={v}" for k, v in fields.items()) + "\n")
    TOKEN_ENV.chmod(0o600)
    print("3) 新 token 已寫入 .yahoo_data/.env\n")

    headers = {"Authorization": f"Bearer {tok['access_token']}"}

    def get(path: str):
        return requests.get(f"{API}/{path}", params={"format": "json"}, headers=headers, timeout=30)

    r = get("game/nba")
    print(f"測試 game/nba：HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])
        return

    if league_id:
        r = get(f"league/nba.l.{league_id}/settings")
        print(f"測試聯盟 {league_id}：HTTP {r.status_code}")
        if r.status_code != 200:
            print(r.text[:300])
            return
        try:
            lg = r.json()["fantasy_content"]["league"]
            print("聯盟名稱：", lg[0].get("name"), "｜季度：", lg[0].get("season"))
            stats = [s["stat"] for s in lg[1]["settings"][0]["stat_categories"]["stats"]]
            scoring = [s["display_name"] for s in stats if str(s.get("is_only_display_stat", "0")) != "1"]
            print(f"計分項目（{len(scoring)} 項）：", ", ".join(scoring))
        except Exception as e:  # 結構不如預期時，至少確認連線成功
            print("連線成功，但解析設定時出錯：", e)

    print("\n完成！請完全結束（Cmd+Q）並重新開啟 Claude 桌面 App。")


if __name__ == "__main__":
    main()
