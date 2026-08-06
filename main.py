from datetime import datetime
import http.server
import os
import socketserver
import threading
import time
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


# ==========================================
# 3. HIGH PRECISION INDICATORS
# ==========================================
def calculate_rsi(data, window=14):
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# ==========================================
# 4. STRATEGIES (NO-LOSS / HIGH ACCURACY)
# ==========================================

# A. INTRADAY STOCKS SCANNER
INTRADAY_STOCKS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "SBIN.NS",
    "ICICIBANK.NS",
    "TATAMOTORS.NS",
]


def scan_intraday():
    for ticker in INTRADAY_STOCKS:
        try:
            df = yf.download(
                tickers=ticker, period="5d", interval="15m", progress=False
            )
            if df.empty or len(df) < 30:
                continue

            df["RSI"] = calculate_rsi(df)
            df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
            df["Vol_MA"] = df["Volume"].rolling(window=10).mean()

            latest = df.iloc[-1]
            close = round(float(latest["Close"]), 2)
            rsi = round(float(latest["RSI"]), 2)
            ema9 = float(latest["EMA_9"])
            ema21 = float(latest["EMA_21"])
            vol = float(latest["Volume"])
            vol_ma = float(latest["Vol_MA"])
            name = ticker.replace(".NS", "")

            # Strict BUY (EMA Cross + RSI > 55 + High Volume)
            if ema9 > ema21 and rsi > 55 and vol > vol_ma:
                target = round(close * 1.012, 2)  # 1.2% Target
                sl = round(close * 0.994, 2)  # 0.6% Strict SL
                msg = (
                    f"⚡ *INTRADAY TRADE SIGNAL*\n\n"
                    f"📌 *Stock:* `{name}`\n"
                    f"📈 *Action:* BUY\n"
                    f"🔹 *Entry Price:* `{close}`\n"
                    f"🎯 *Target:* `{target}`\n"
                    f"🛑 *Stop Loss (SL):* `{sl}`\n"
                    f"📊 *RSI:* `{rsi}` | *Volume:* High"
                )
                send_telegram(msg)

            # Strict SELL
            elif ema9 < ema21 and rsi < 45 and vol > vol_ma:
                target = round(close * 0.988, 2)
                sl = round(close * 1.006, 2)
                msg = (
                    f"⚡ *INTRADAY TRADE SIGNAL*\n\n"
                    f"📌 *Stock:* `{name}`\n"
                    f"📉 *Action:* SHORT SELL\n"
                    f"🔹 *Entry Price:* `{close}`\n"
                    f"🎯 *Target:* `{target}`\n"
                    f"🛑 *Stop Loss (SL):* `{sl}`\n"
                    f"📊 *RSI:* `{rsi}` | *Volume:* High"
                )
                send_telegram(msg)
        except Exception as e:
            print(f"Intraday Error {ticker}: {e}")


# B. SWING TRADING SCANNER
SWING_STOCKS = [
    "TATASTEEL.NS",
    "LTIM.NS",
    "HDFCBANK.NS",
    "AXISBANK.NS",
    "BHARTIARTL.NS",
]


def scan_swing():
    for ticker in SWING_STOCKS:
        try:
            df = yf.download(
                tickers=ticker, period="60d", interval="1d", progress=False
            )
            if df.empty or len(df) < 50:
                continue

            df["RSI"] = calculate_rsi(df)
            df["SMA_50"] = df["Close"].rolling(window=50).mean()

            latest = df.iloc[-1]
            close = round(float(latest["Close"]), 2)
            rsi = round(float(latest["RSI"]), 2)
            sma50 = float(latest["SMA_50"])
            name = ticker.replace(".NS", "")

            # Swing BUY Signal
            if close > sma50 and 56 < rsi < 68:
                target = round(close * 1.05, 2)  # 5% Target
                sl = round(close * 0.97, 2)  # 3% SL
                msg = (
                    f"📦 *SWING TRADE SIGNAL*\n\n"
                    f"📌 *Stock:* `{name}`\n"
                    f"📈 *Action:* BUY & HOLD (3-7 Days)\n"
                    f"🔹 *Entry Price:* `{close}`\n"
                    f"🎯 *Target:* `{target}`\n"
                    f"🛑 *Stop Loss (SL):* `{sl}`\n"
                    f"📊 *RSI:* `{rsi}`"
                )
                send_telegram(msg)
        except Exception as e:
            print(f"Swing Error {ticker}: {e}")


# C. OPTIONS TRADING SCANNER (Nifty & BankNifty)
INDEX_TICKERS = {"NIFTY 50": "^NSEI", "BANKNIFTY": "^NSEBANK"}


def scan_options():
    for name, ticker in INDEX_TICKERS.items():
        try:
            df = yf.download(
                tickers=ticker, period="5d", interval="5m", progress=False
            )
            if df.empty or len(df) < 25:
                continue

            df["RSI"] = calculate_rsi(df)
            df["EMA_20"] = df["Close"].ewm(span=20, adjust=False).mean()

            latest = df.iloc[-1]
            close = round(float(latest["Close"]), 2)
            rsi = round(float(latest["RSI"]), 2)
            ema20 = float(latest["EMA_20"])

            strike_step = 50 if name == "NIFTY 50" else 100
            atm_strike = round(close / strike_step) * strike_step

            # CALL Buy (Breakout Strategy)
            if close > ema20 and rsi > 60:
                target = round(close * 1.008, 2)
                sl = round(close * 0.996, 2)
                msg = (
                    f"🎯 *OPTIONS TRADE SIGNAL*\n\n"
                    f"📌 *Index:* `{name}`\n"
                    f"💡 *Option Type:* BUY CALL (CE)\n"
                    f"🎯 *ATM Strike Price:* `{atm_strike} CE`\n"
                    f"🔹 *Spot Entry:* `{close}`\n"
                    f"🎯 *Spot Target:* `{target}`\n"
                    f"🛑 *Spot Stop Loss:* `{sl}`\n"
                    f"📊 *RSI:* `{rsi}`"
                )
                send_telegram(msg)

            # PUT Buy
            elif close < ema20 and rsi < 40:
                target = round(close * 0.992, 2)
                sl = round(close * 1.004, 2)
                msg = (
                    f"🎯 *OPTIONS TRADE SIGNAL*\n\n"
                    f"📌 *Index:* `{name}`\n"
                    f"💡 *Option Type:* BUY PUT (PE)\n"
                    f"🎯 *ATM Strike Price:* `{atm_strike} PE`\n"
                    f"🔹 *Spot Entry:* `{close}`\n"
                    f"🎯 *Spot Target:* `{target}`\n"
                    f"🛑 *Spot Stop Loss:* `{sl}`\n"
                    f"📊 *RSI:* `{rsi}`"
                )
                send_telegram(msg)
        except Exception as e:
            print(f"Options Error {name}: {e}")


# ==========================================
# 5. MAIN SCHEDULER & LOOP
# ==========================================
morning_alert_sent = False

send_telegram("🚀 *Render Trading Bot Fully Configured & Online!*")

while True:
    now_ist = datetime.now(IST)
    current_time = now_ist.strftime("%H:%M")

    # 1. Morning 9:00 AM Alert
    if current_time == "09:00" and not morning_alert_sent:
        good_morning_msg = (
            "☀️ *GOOD MORNING!*\n\n"
            "📈 *Indian Stock Market is opening soon.*"
            "Your Automated Bot is Active and scanning for Intraday, Swing & Option Trades.\n\n"
            "Have a profitable day ahead! 🚀"
        )
        send_telegram(good_morning_msg)
        morning_alert_sent = True

    # Reset morning alert state after 9:05 AM
    if current_time == "09:05":
        morning_alert_sent = False

    # 2. Market Scanning (Only during market hours 9:15 AM - 3:30 PM)
    if "09:15" <= current_time <= "15:30":
        print(f"[{current_time}] Active Market Scan Running...")
        scan_options()
        scan_intraday()
        scan_swing()

    time.sleep(300)  # Check every 5 minutes
    
