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
# 1. RENDER PORT BINDING (Dummy Server)
# ==========================================
def run_server():
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()


threading.Thread(target=run_server, daemon=True).start()

# ==========================================
# 2. TELEGRAM CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = "8993254284:AAGs5LwFD5PD0UMViDpDd8OY35lOSTMwyNE"
TELEGRAM_CHAT_ID = "5660614483"
IST = pytz.timezone("Asia/Kolkata")


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


# Safe Downloader with Header & Longer Delay to Prevent Rate Limit
def safe_download(ticker, period, interval):
    try:
        time.sleep(3.5)  # Safe delay to prevent rate limit
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0"
                " Safari/537.36"
            )
        })
        ticker_obj = yf.Ticker(ticker, session=session)
        df = ticker_obj.history(period=period, interval=interval)
        return df
    except Exception as e:
        print(f"Download Error for {ticker}: {e}")
        return pd.DataFrame()


# ==========================================
# 3. TECHNICAL INDICATORS
# ==========================================
def calculate_rsi(data, window=14):
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_atr(data, window=14):
    high_low = data["High"] - data["Low"]
    high_close = np.abs(data["High"] - data["Close"].shift())
    low_close = np.abs(data["Low"] - data["Close"].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window).mean()


# ==========================================
# 4. WATCHLIST (NIFTY 100 Selected Top Stocks)
# ==========================================
NIFTY_100_WATCHLIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "SBIN.NS",
    "ICICIBANK.NS",
    "HDFCBANK.NS",
    "TATAMOTORS.NS",
    "BHARTIARTL.NS",
    "LT.NS",
    "AXISBANK.NS",
]


# ==========================================
# 5. ALL STRATEGIES IN SINGLE PASS (To Save Rate Limits)
# ==========================================
def scan_all_strategies():
    # 1. Option Scanning (Indices)
    for name, ticker in {"NIFTY 50": "^NSEI", "BANKNIFTY": "^NSEBANK"}.items():
        try:
            df = safe_download(ticker, period="5d", interval="5m")
            if not df.empty and len(df) >= 20:
                df["RSI"] = calculate_rsi(df)
                df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()
                latest = df.iloc[-1]
                close, rsi, ema20 = (
                    round(float(latest["Close"]), 2),
                    round(float(latest["RSI"]), 2),
                    float(latest["EMA_20"]),
                )

                step = 50 if name == "NIFTY 50" else 100
                atm = round(close / step) * step

                if close > ema20 and rsi > 60:
                    send_telegram(
                        f"🎯 *OPTIONS TRADE SIGNAL*\n\n📌 *Index:*"
                        f" `{name}`\n💡 *BUY CALL:* `{atm} CE` | Spot Entry:"
                        f" `{close}`"
                    )
                elif close < ema20 and rsi < 40:
                    send_telegram(
                        f"🎯 *OPTIONS TRADE SIGNAL*\n\n📌 *Index:*"
                        f" `{name}`\n💡 *BUY PUT:* `{atm} PE` | Spot Entry:"
                        f" `{close}`"
                    )
        except Exception as e:
            print(f"Options error for {name}: {e}")

    # 2. Stock Strategies (Confluence + Intraday + Swing)
    for ticker in NIFTY_100_WATCHLIST:
        try:
            # 5 Min Data
            df_5m = safe_download(ticker, period="5d", interval="5m")
            if df_5m.empty or len(df_5m) < 20:
                continue

            df_5m["RSI"] = calculate_rsi(df_5m)
            df_5m["EMA_9"] = df_5m["Close"].ewm(span=9, adjust=False).mean()
            df_5m["EMA_21"] = df_5m["Close"].ewm(span=21, adjust=False).mean()
            df_5m["ATR"] = calculate_atr(df_5m)

            latest = df_5m.iloc[-1]
            close = round(float(latest["Close"]), 2)
            rsi = round(float(latest["RSI"]), 2)
            ema9 = float(latest["EMA_9"])
            ema21 = float(latest["EMA_21"])
            atr = float(latest["ATR"]) if not np.isnan(latest["ATR"]) else 2.0
            name = ticker.replace(".NS", "")

            # Intraday Check
            if ema9 > ema21 and rsi > 55:
                send_telegram(
                    f"⚡ *INTRADAY TRADE SIGNAL*\n\n📌 *Stock:* `{name}`\n📈"
                    f" *BUY:* `{close}` | Target: `{round(close*1.01, 2)}` | SL:"
                    f" `{round(close*0.995, 2)}`"
                )

            # Confluence Check (1H Higher Trend)
            df_1h = safe_download(ticker, period="10d", interval="60m")
            if not df_1h.empty and len(df_1h) >= 50:
                df_1h["EMA_50"] = (
                    df_1h["Close"].ewm(span=50, adjust=False).mean()
                )
                trend = (
                    "UPTREND"
                    if df_1h["Close"].iloc[-1] > df_1h["EMA_50"].iloc[-1]
                    else "DOWNTREND"
                )

                support = df_5m["Low"].tail(20).min()
                resistance = df_5m["High"].tail(20).max()
                sl_points = round(atr * 1.5, 2)
                target_points = round(sl_points * 2, 2)

                if (
                    trend == "UPTREND"
                    and close > ema9 > ema21
                    and rsi > 52
                    and (close - support) / close < 0.01
                ):
                    sl = round(close - sl_points, 2)
                    target = round(close + target_points, 2)
                    send_telegram(
                        f"🧠 *NIFTY 100 CONFLUENCE TRADE*\n────────────────────────\n📌"
                        f" *Stock:* `{name}`\n📈 *Action:* BUY (High"
                        f" Accuracy)\n📊 *Major Trend (1H):* {trend}\n🎯 *Entry"
                        f" Price:* `{close}`\n🎯 *Target (1:2 R:R):*"
                        f" `{target}`\n🛑 *Stop Loss (ATR):* `{sl}`\n🔍"
                        f" *Confluence:* Support Bounce + EMA Cross + RSI `{rsi}`"
                    )

                elif (
                    trend == "DOWNTREND"
                    and close < ema9 < ema21
                    and rsi < 48
                    and (resistance - close) / close < 0.01
                ):
                    sl = round(close + sl_points, 2)
                    target = round(close - target_points, 2)
                    send_telegram(
                        f"🧠 *NIFTY 100 CONFLUENCE TRADE*\n────────────────────────\n📌"
                        f" *Stock:* `{name}`\n📉 *Action:* SHORT SELL\n📊"
                        f" *Major Trend (1H):* {trend}\n🎯 *Entry Price:*"
                        f" `{close}`\n🎯 *Target (1:2 R:R):* `{target}`\n🛑 *Stop"
                        f" Loss (ATR):* `{sl}`\n🔍 *Confluence:* Resistance"
                        f" Rejection + EMA Cross + RSI `{rsi}`"
                    )

        except Exception as e:
            print(f"Error scanning {ticker}: {e}")


# ==========================================
# 6. MAIN SCHEDULER
# ==========================================
morning_sent = False
send_telegram(
    "🚀 *Rate Limit Fix Applied (Optimized Scan)! Bot is fully running.*"
)

while True:
    now_ist = datetime.now(IST)
    curr_time = now_ist.strftime("%H:%M")

    if "09:00" <= curr_time <= "09:05" and not morning_sent:
        send_telegram("☀️ *GOOD MORNING!* Market opening soon. Bot is active.")
        morning_sent = True

    if curr_time == "09:10":
        morning_sent = False

    if "09:15" <= curr_time <= "15:30":
        print(f"[{curr_time}] Optimized Market Scanning Running...")
        scan_all_strategies()

    time.sleep(300)
