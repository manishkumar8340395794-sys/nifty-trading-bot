import http.server
import socketserver
import threading
import os
import time
from datetime import datetime
import pytz
import requests
import yfinance as yf
import pandas as pd
import numpy as np

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
IST = pytz.timezone('Asia/Kolkata')

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

def safe_download(ticker, period, interval):
    try:
        time.sleep(1.5)  # Rate limit safety delay
        df = yf.download(tickers=ticker, period=period, interval=interval, progress=False)
        return df
    except Exception as e:
        print(f"Download Error for {ticker}: {e}")
        return pd.DataFrame()

# ==========================================
# 3. TECHNICAL INDICATORS
# ==========================================
def calculate_rsi(data, window=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(data, window=14):
    high_low = data['High'] - data['Low']
    high_close = np.abs(data['High'] - data['Close'].shift())
    low_close = np.abs(data['Low'] - data['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(window).mean()

# ==========================================
# 4. NIFTY 100 WATCHLIST (NIFTY 500 Hata Kar)
# ==========================================
NIFTY_100_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "SBIN.NS", "ICICIBANK.NS", "HDFCBANK.NS", 
    "TATAMOTORS.NS", "BHARTIARTL.NS", "LT.NS", "AXISBANK.NS", "KOTAKBANK.NS", 
    "HINDUNILVR.NS", "ITC.NS", "BAJFINANCE.NS", "MARUTI.NS", "SUNPHARMA.NS", 
    "TATASTEEL.NS", "NTPC.NS", "POWERGRID.NS", "TITAN.NS", "ULTRACEMCO.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS", "M&M.NS"
]

# ==========================================
# 5. STRATEGY 1: MULTI-TIMEFRAME CONFLUENCE
# ==========================================
def scan_confluence_strategy():
    for ticker in NIFTY_100_WATCHLIST:
        try:
            # Step 1: Big Trend Check (1 Hour Timeframe)
            df_1h = safe_download(ticker, period="10d", interval="60m")
            if df_1h.empty or len(df_1h) < 50:
                continue
            df_1h['EMA_50'] = df_1h['Close'].ewm(span=50, adjust=False).mean()
            trend = "UPTREND" if df_1h['Close'].iloc[-1] > df_1h['EMA_50'].iloc[-1] else "DOWNTREND"

            # Step 2: Key Level Check (15 Min S/R)
            df_15m = safe_download(ticker, period="5d", interval="15m")
            if df_15m.empty or len(df_15m) < 20:
                continue
            support = df_15m['Low'].tail(20).min()
            resistance = df_15m['High'].tail(20).max()

            # Step 3: Entry & Risk Management (5 Min)
            df_5m = safe_download(ticker, period="5d", interval="5m")
            if df_5m.empty or len(df_5m) < 20:
                continue

            df_5m['RSI'] = calculate_rsi(df_5m)
            df_5m['EMA_9'] = df_5m['Close'].ewm(span=9, adjust=False).mean()
            df_5m['EMA_21'] = df_5m['Close'].ewm(span=21, adjust=False).mean()
            df_5m['ATR'] = calculate_atr(df_5m)

            latest = df_5m.iloc[-1]
            close = round(float(latest['Close']), 2)
            rsi = round(float(latest['RSI']), 2)
            ema9 = float(latest['EMA_9'])
            ema21 = float(latest['EMA_21'])
            atr = float(latest['ATR']) if not np.isnan(latest['ATR']) else 2.0
            name = ticker.replace(".NS", "")

            sl_points = round(atr * 1.5, 2)
            target_points = round(sl_points * 2, 2)

            # BUY Conditions
            if trend == "UPTREND" and close > ema9 > ema21 and rsi > 52 and (close - support)/close < 0.01:
                sl = round(close - sl_points, 2)
                target = round(close + target_points, 2)
                msg = (
                    f"🧠 *NIFTY 100 CONFLUENCE TRADE*\n"
                    f"────────────────────────\n"
                    f"📌 *Stock:* `{name}`\n"
                    f"📈 *Action:* BUY (High Probability)\n"
                    f"📊 *Major Trend (1H):* {trend}\n"
                    f"🎯 *Entry Price:* `{close}`\n"
                    f"🎯 *Target (1:2 R:R):* `{target}`\n"
                    f"🛑 *Stop Loss (ATR):* `{sl}`\n"
                    f"🔍 *Confluence:* Support Bounce + EMA Cross + RSI `{rsi}`"
                )
                send_telegram(msg)

            # SELL Conditions
            elif trend == "DOWNTREND" and close < ema9 < ema21 and rsi < 48 and (resistance - close)/close < 0.01:
                sl = round(close + sl_points, 2)
                target = round(close - target_points, 2)
                msg = (
                    f"🧠 *NIFTY 100 CONFLUENCE TRADE*\n"
                    f"────────────────────────\n"
                    f"📌 *Stock:* `{name}`\n"
                    f"📉 *Action:* SHORT SELL\n"
                    f"📊 *Major Trend (1H):* {trend}\n"
                    f"🎯 *Entry Price:* `{close}`\n"
                    f"🎯 *Target (1:2 R:R):* `{target}`\n"
                    f"🛑 *Stop Loss (ATR):* `{sl}`\n"
                    f"🔍 *Confluence:* Resistance Rejection + EMA Cross + RSI `{rsi}`"
                )
                send_telegram(msg)
        except Exception as e:
            print(f"Confluence Error {ticker}: {e}")

# ==========================================
# 6. STRATEGY 2: INTRADAY
# ==========================================
def scan_intraday():
    for ticker in NIFTY_100_WATCHLIST[:10]:
        try:
            df = safe_download(ticker, period="5d", interval="15m")
            if df.empty or len(df) < 25:
                continue
            df['RSI'] = calculate_rsi(df)
            df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
            df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()

            latest = df.iloc[-1]
            close = round(float(latest['Close']), 2)
            rsi = round(float(latest['RSI']), 2)
            ema9, ema21 = float(latest['EMA_9']), float(latest['EMA_21'])
            name = ticker.replace(".NS", "")

            if ema9 > ema21 and rsi > 55:
                send_telegram(f"⚡ *INTRADAY TRADE SIGNAL*\n\n📌 *Stock:* `{name}`\n📈 *BUY:* `{close}` | Target: `{round(close*1.01, 2)}` | SL: `{round(close*0.995, 2)}`")
        except Exception as e:
            pass

# ==========================================
# 7. STRATEGY 3: SWING TRADING
# ==========================================
def scan_swing():
    for ticker in NIFTY_100_WATCHLIST[:10]:
        try:
            df = safe_download(ticker, period="60d", interval="1d")
            if df.empty or len(df) < 50:
                continue
            df['RSI'] = calculate_rsi(df)
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            latest = df.iloc[-1]
            close, rsi, sma50 = round(float(latest['Close']), 2), round(float(latest['RSI']), 2), float(latest['SMA_50'])
            name = ticker.replace(".NS", "")

            if close > sma50 and 55 < rsi < 70:
                send_telegram(f"📦 *SWING TRADE SIGNAL*\n\n📌 *Stock:* `{name}`\n📈 *BUY & HOLD:* `{close}` | Target: `{round(close*1.05, 2)}` | SL: `{round(close*0.97, 2)}`")
        except Exception as e:
            pass

# ==========================================
# 8. STRATEGY 4: OPTIONS (NIFTY & BANKNIFTY)
# ==========================================
def scan_options():
    for name, ticker in {"NIFTY 50": "^NSEI", "BANKNIFTY": "^NSEBANK"}.items():
        try:
            df = safe_download(ticker, period="5d", interval="5m")
            if df.empty or len(df) < 20:
                continue
            df['RSI'] = calculate_rsi(df)
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
            latest = df.iloc[-1]
            close, rsi, ema20 = round(float(latest['Close']), 2), round(float(latest['RSI']), 2), float(latest['EMA_20'])
            
            step = 50 if name == "NIFTY 50" else 100
            atm = round(close / step) * step

            if close > ema20 and rsi > 60:
                send_telegram(f"🎯 *OPTIONS TRADE SIGNAL*\n\n📌 *Index:* `{name}`\n💡 *BUY CALL:* `{atm} CE` | Spot Entry: `{close}`")
            elif close < ema20 and rsi < 40:
                send_telegram(f"🎯 *OPTIONS TRADE SIGNAL*\n\n📌 *Index:* `{name}`\n💡 *BUY PUT:* `{atm} PE` | Spot Entry: `{close}`")
        except Exception as e:
            pass

# ==========================================
# 9. MAIN SCHEDULER
# ==========================================
morning_sent = False
send_telegram("🚀 *Bot Updated! Configured for NIFTY 100 Stocks with All Strategies.*")

while True:
    now_ist = datetime.now(IST)
    curr_time = now_ist.strftime("%H:%M")

    if "09:00" <= curr_time <= "09:05" and not morning_sent:
        send_telegram("☀️ *GOOD MORNING!* Market opening soon. Bot is active.")
        morning_sent = True

    if curr_time == "09:10":
        morning_sent = False

    if "09:15" <= curr_time <= "15:30":
        print(f"[{curr_time}] Scanning NIFTY 100 Markets...")
        scan_confluence_strategy()
        scan_intraday()
        scan_swing()
        scan_options()

    time.sleep(300)
