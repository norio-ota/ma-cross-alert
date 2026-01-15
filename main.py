import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, time
from datetime import date
import jpholiday
import pytz
import os

# JST
JST = pytz.timezone("Asia/Tokyo")
now = datetime.now(JST).time()

def is_trading_time(nowDt):
#    if not is_trading_day(now):
#        return False

    t = nowDt

    # 前場 9:00-11:30
    if time(9, 0) <= t <= time(11, 30):
        return True

    # 後場 12:30-15:30
    if time(12, 30) <= t <= time(15, 30):
        return True

    return False


# 東証 昼休み（11:30–12:30）
if not is_trading_time(now):
    exit()

def is_trading_day(now=None):
    if now is None:
        now = datetime.now(JST)

    # 土日除外
    if now.weekday() >= 5:
        return False

    # 祝日除外
    if jpholiday.is_holiday(now.date()):
        return False

    return True


# ===== 設定 =====
TICKER = os.environ.get("TICKER")   # 監視したい銘柄
if not TICKER:
    raise ValueError("TICKER environment variable is not set")

STATE_FILE = "state.txt"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

#state = load_state()

# ===== データ取得（1分足）=====
df = yf.download(
    TICKER,
    interval="1m",
    period="1d",
    progress=False
)

if len(df) < 80:
    print("データ不足")
    exit()

close = df["Close"]

# ===== 移動平均 =====
df["MA5"]  = close.rolling(5).mean()
df["MA25"] = close.rolling(25).mean()
df["MA75"] = close.rolling(75).mean()

prev = df.iloc[-2]
curr = df.iloc[-1]

# ===== クロス判定 =====
signals = []

def check_cross(sht, lng, name):
    prev_short = df[sht].iloc[-2]
    prev_long  = df[lng].iloc[-2]
    curr_short = df[sht].iloc[-1]
    curr_long  = df[lng].iloc[-1]

    if prev_short < prev_long and curr_short > curr_long:
        return f"📈 ゴールデンクロス ({name})"
    if prev_short > prev_long and curr_short < curr_long:
        return f"📉 デッドクロス ({name})"
    return None

for s, l, n in [
    ("MA5", "MA25", "5-25"),
    ("MA25", "MA75", "25-75"),
    ("MA5", "MA75", "5-75"),
]:
    result = check_cross(s, l, n)
    if result:
        print("クロスあり")
        signals.append(result)

if not signals:
    print("クロスなし")
    exit()


# ===== 前回状態読み込み =====
prev_state = "NONE"
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        prev_state = f.read().strip()
        print(prev_state)

current_state = "|".join(signals)

if current_state == prev_state:
    print("同一シグナルのため通知なし")
    exit()

# ===== GitHub Issue 作成（iPhone通知）=====
repo = os.environ["GITHUB_REPOSITORY"]
token = os.environ["GITHUB_TOKEN"]

body = "\n".join(signals)
title = f"{TICKER} 移動平均クロス検出"

res = requests.post(
    f"https://api.github.com/repos/{repo}/issues",
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    },
    json={
        "title": title,
        "body": body
    }
)

print("通知送信:", res.status_code)

# ===== 状態保存 =====
with open(STATE_FILE, "w") as f:
    f.write(current_state)
