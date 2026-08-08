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
# 2. TELEGRAM & CACHE SETTINGS
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
        print(f"Telegram error: {e}")


def is_duplicate_alert(symbol, alert_type, cooldown_minutes=45):
    """45 मिनट तक एक ही शेयर का दोबारा मैसेज नहीं भेजेगा"""
    key = f"{symbol}_{alert_type}"
    now = time.time()
    if key in sent_alerts:
        if now - sent_alerts[key] < cooldown_minutes * 60:
            return True
    sent_alerts[key] = now
    return False


# ==========================================
# 3. BUDGET WATCHLIST (UNDER ~₹500-600 STOCKS)
# ==========================================
BUDGET_WATCHLIST = [
    "GAIL.NS",  # ~₹180 - ₹220
    "NTPC.NS",  # ~₹300 - ₹380
    "IOC.NS",  # ~₹130 - ₹170
    "BPCL.NS",  # ~₹280 - ₹350
    "TATAMOTORS.NS",  # Budget Heavy
    "FEDERALBNK.NS",  # ~₹180 - ₹210
    "PFC.NS",  # ~₹400 - ₹480
    "REC.NS",  # ~₹450 - ₹520
    "ASHOKLEY.NS",  # ~₹210 - ₹250
    "PNB.NS",  # ~₹100 - ₹130
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
# 5. HIGH ACCURACY BUDGET SCANNER
# ==========================================
def scan_budget_stocks():
    try:
        data_5m = yf.download(
            tickers=BUDGET_WATCHLIST,
            period="5d",
            interval="5m",
            group_by="ticker",
            progress=False,
            threads=True,
        )
        data_1h = yf.download(
            tickers=BUDGET_WATCHLIST,
            period="15d",
            interval="60m",
            group_by="ticker",
            progress=False,
            threads=True,
        )
    except Exception as e:
        print(f"Data Fetch Error: {e}")
        return

    for ticker in BUDGET_WATCHLIST:
        try:
            df_5m = (
                data_5m[ticker].dropna()
                if ticker in data_5m
                else pd.DataFrame()
            )
            df_1h = (
                data_1h[ticker].dropna()
                if ticker in data_1h
                else pd.DataFrame()
            )

            if len(df_5m) < 30 or len(df_1h) < 40:
                continue

            name = ticker.replace(".NS", "")

            # 1H Trend Confirmation (Filter 1)
            df_1h["EMA_50"] = df_1h["Close"].ewm(span=50, adjust=False).mean()
            h1_trend = (
                "UPTREND"
                if df_1h["Close"].iloc[-1] > df_1h["EMA_50"].iloc[-1]
                else "DOWNTREND"
            )

            # 5M Indicators (Filter 2, 3 & 4)
            df_5m["RSI"] = calculate_rsi(df_5m["Close"])
            df_5m["EMA_9"] = df_5m["Close"].ewm(span=9, adjust=False).mean()
            df_5m["EMA_21"] = df_5m["Close"].ewm(span=21, adjust=False).mean()
            df_5m["ATR"] = calculate_atr(df_5m)
            df_5m["VOL_SMA"] = df_5m["Volume"].rolling(10).mean()

            latest = df_5m.iloc[-1]
            prev = df_5m.iloc[-2]

            close = round(float(latest["Close"]), 2)
            rsi = round(float(latest["RSI"]), 2)

            # Strict Budget Limit Check (Under ~₹600)
            if close > 650:
                continue

            atr = (
                float(latest["ATR"])
                if not np.isnan(latest["ATR"])
                else (close * 0.006)
            )
            high_vol = (
                latest["Volume"] > 1.5 * latest["VOL_SMA"]
                if not np.isnan(latest["VOL_SMA"])
                else True
            )

            # Tight Stoploss and Safe 1:2 Target Calculation
            sl_points = round(atr * 1.2, 2)  # Tight SL to minimize loss
            target_points = round(sl_points * 2.0, 2)  # Minimum 1:2 RR

            # 🎯 SAFE BUY SIGNAL:
            # 1H Trend UP + 9 EMA Crossover + High Vol + RSI in Sweet Spot (58-68)
            if (
                h1_trend == "UPTREND"
                and prev["EMA_9"] <= prev["EMA_21"]
                and latest["EMA_9"] > latest["EMA_21"]
                and 58 <= rsi <= 68
                and high_vol
            ):

                if not is_duplicate_alert(name, "BUY", 45):
                    sl = round(close - sl_points, 2)
                    target = round(close + target_points, 2)
                    risk_per_share = round(close - sl, 2)

                    send_telegram(
                        f"🎯 *LOW RISK BUDGET BUY ALERT*\n────────────────────────\n📌"
                        f" *Stock:* `{name}`\n💰 *Price:* `₹{close}` (Budget"
                        f" Stock)\n📈 *Signal:* HIGH ACCURACY BUY\n📊 *1H"
                        f" Trend:* UPTREND\n\n🎯 *Target:* `₹{target}`\n🛑 *Stop"
                        f" Loss:* `₹{sl}`\n⚠️ *Max Risk/Share:* `₹{risk_per_share}`"
                        f" (Minimal Loss)\n🔍 *Confluence:* EMA Cross + High"
                        f" Volume + RSI `{rsi}`"
                    )

            # 🎯 SAFE SHORT/SELL SIGNAL:
            elif (
                h1_trend == "DOWNTREND"
                and prev["EMA_9"] >= prev["EMA_21"]
                and latest["EMA_9"] < latest["EMA_21"]
                and 32 <= rsi <= 42
                and high_vol
            ):

                if not is_duplicate_alert(name, "SELL", 45):
                    sl = round(close + sl_points, 2)
                    target = round(close - target_points, 2)
                    risk_per_share = round(sl - close, 2)

                    send_telegram(
                        f"🎯 *LOW RISK BUDGET SHORT ALERT*\n────────────────────────\n📌"
                        f" *Stock:* `{name}`\n💰 *Price:* `₹{close}` (Budget"
                        f" Stock)\n📉 *Signal:* HIGH ACCURACY SHORT\n📊 *1H"
                        f" Trend:* DOWNTREND\n\n🎯 *Target:* `₹{target}`\n🛑 *Stop"
                        f" Loss:* `₹{sl}`\n⚠️ *Max Risk/Share:* `₹{risk_per_share}`"
                        f" (Minimal Loss)\n🔍 *Confluence:* EMA Cross + High"
                        f" Volume + RSI `{rsi}`"
                    )

        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")


# ==========================================
# 6. SCHEDULER & MARKET RUNNER
# ==========================================
send_telegram(
    "🟢 *Budget Stocks Strategy Deployed (Under ₹500 - Low Risk Engine Active)*"
)

while True:
    now_ist = datetime.now(IST)
    weekday = now_ist.weekday()
    curr_time = now_ist.strftime("%H:%M")

    # Weekend check
    if weekday in [5, 6]:
        print(f"[{curr_time}] Weekend - Market Closed.")
        time.sleep(1800)
        continue

    # Live Market Scanning
    if "09:15" <= curr_time <= "15:30":
        print(f"[{curr_time}] Deep Analysis Running for Budget Stocks...")
        scan_budget_stocks()
        time.sleep(300)
    else:
        print(f"[{curr_time}] Market Closed. Sleeping...")
        time.sleep(600)
