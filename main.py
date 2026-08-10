from datetime import datetime
import http.server
import os
import socketserver
import threading
import time
import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf

# ==========================================
# 1. RENDER PORT BINDING & KEEP-ALIVE
# ==========================================
PORT = int(os.environ.get("PORT", 10000))
APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "")


def run_server():
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        httpd.serve_forever()


threading.Thread(target=run_server, daemon=True).start()


def keep_alive():
    while True:
        time.sleep(600)  # Self ping every 10 mins
        if APP_URL:
            try:
                requests.get(APP_URL)
            except Exception as e:
                print(f"[Keep-Alive Error]: {e}")


threading.Thread(target=keep_alive, daemon=True).start()

# ==========================================
# 2. TELEGRAM CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = "8993254284:AAGs5LwFD5PD0UMViDpDd8OY35lOSTMwyNE"
TELEGRAM_CHAT_ID = "5660614483"
IST = pytz.timezone("Asia/Kolkata")

sent_alerts = {}


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")


def is_duplicate_alert(symbol, alert_type, cooldown_minutes=30):
    key = f"{symbol}_{alert_type}"
    now = time.time()
    if key in sent_alerts:
        if now - sent_alerts[key] < cooldown_minutes * 60:
            return True
    sent_alerts[key] = now
    return False


# ==========================================
# 3. BUDGET WATCHLIST (UNDER ~₹500 STOCKS)
# ==========================================
BUDGET_WATCHLIST = [
    "PNB.NS",  # ~₹100
    "GAIL.NS",  # ~₹180 - ₹220
    "IOC.NS",  # ~₹130 - ₹170
    "FEDERALBNK.NS",  # ~₹180 - ₹210
    "ASHOKLEY.NS",  # ~₹210 - ₹250
    "BPCL.NS",  # ~₹280 - ₹350
    "NTPC.NS",  # ~₹300 - ₹380
    "PFC.NS",  # ~₹400 - ₹480
    "REC.NS",  # ~₹450 - ₹520
    "BHEL.NS",  # ~₹250 - ₹300
    "SBIN.NS",  # Budget Heavy Bank
]


# ==========================================
# 4. TECHNICAL INDICATORS
# ==========================================
def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_atr(df, window=14):
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window).mean()


# ==========================================
# 5. SAFE LIVE MARKET SCANNER
# ==========================================
def scan_budget_stocks():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    })

    for ticker in BUDGET_WATCHLIST:
        try:
            t = yf.Ticker(ticker, session=session)
            df_5m = t.history(period="3d", interval="5m")

            if df_5m.empty or len(df_5m) < 25:
                continue

            name = ticker.replace(".NS", "")

            # Technical Calculation
            df_5m["RSI"] = calculate_rsi(df_5m["Close"])
            df_5m["EMA_9"] = df_5m["Close"].ewm(span=9, adjust=False).mean()
            df_5m["EMA_21"] = df_5m["Close"].ewm(span=21, adjust=False).mean()
            df_5m["ATR"] = calculate_atr(df_5m)

            latest = df_5m.iloc[-1]
            prev = df_5m.iloc[-2]

            close = round(float(latest["Close"]), 2)
            rsi = round(float(latest["RSI"]), 2)
            ema9 = float(latest["EMA_9"])
            ema21 = float(latest["EMA_21"])
            prev_ema9 = float(prev["EMA_9"])
            prev_ema21 = float(prev["EMA_21"])

            # Filter out expensive stocks dynamically
            if close > 850:
                continue

            atr = (
                float(latest["ATR"])
                if not np.isnan(latest["ATR"])
                else (close * 0.005)
            )

            # Tight Stoploss and Safe 1:2 Target
            sl_points = round(atr * 1.1, 2)
            target_points = round(sl_points * 2.0, 2)

            # 🟢 HIGH ACCURACY BUY SIGNAL
            if prev_ema9 <= prev_ema21 and ema9 > ema21 and 52 <= rsi <= 70:
                if not is_duplicate_alert(name, "BUY", 30):
                    sl = round(close - sl_points, 2)
                    target = round(close + target_points, 2)
                    risk = round(close - sl, 2)

                    send_telegram(
                        f"🎯 *LOW RISK BUDGET BUY ALERT*\n────────────────────────\n📌"
                        f" *Stock:* `{name}`\n💰 *Price:* `₹{close}` (Under"
                        f" Budget)\n📈 *Signal:* BUY (EMA Cross + Safe RSI)\n📊"
                        f" *RSI:* `{rsi}`\n\n🎯 *Target:* `₹{target}`\n🛑 *Stop"
                        f" Loss:* `₹{sl}`\n⚠️ *Max Risk/Share:* `₹{risk}`"
                        " (Minimal Loss)"
                    )

            # 🔴 HIGH ACCURACY SHORT SIGNAL
            elif prev_ema9 >= prev_ema21 and ema9 < ema21 and 30 <= rsi <= 48:
                if not is_duplicate_alert(name, "SELL", 30):
                    sl = round(close + sl_points, 2)
                    target = round(close - target_points, 2)
                    risk = round(sl - close, 2)

                    send_telegram(
                        f"🎯 *LOW RISK BUDGET SHORT ALERT*\n────────────────────────\n📌"
                        f" *Stock:* `{name}`\n💰 *Price:* `₹{close}` (Under"
                        f" Budget)\n📉 *Signal:* SHORT SELL\n📊 *RSI:* `{rsi}`\n\n🎯"
                        f" *Target:* `₹{target}`\n🛑 *Stop Loss:* `₹{sl}`\n⚠️"
                        f" *Max Risk/Share:* `₹{risk}` (Minimal Loss)"
                    )

            time.sleep(1.2)  # Prevent Yahoo Rate Limit Block

        except Exception as e:
            print(f"Error checking {ticker}: {e}")


# ==========================================
# 6. SCHEDULER
# ==========================================
send_telegram(
    "🟢 *Low Risk Budget Stocks Engine Deployed & Active! Scanning...*"
)

while True:
    now_ist = datetime.now(IST)
    curr_time = now_ist.strftime("%H:%M")

    print(f"[{curr_time}] Running Deep Budget Scan...")
    scan_budget_stocks()

    time.sleep(180)  # Scan every 3 minutes
