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


# ============================================================
# 1. RENDER PORT & HEALTH SERVER
# ============================================================

PORT = int(os.environ.get("PORT", 10000))
APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "")


def run_server():
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    try:
        with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
            print(f"Health server started on port {PORT}")
            httpd.serve_forever()
    except Exception as e:
        print(f"[Health Server Error] {e}")


threading.Thread(target=run_server, daemon=True).start()


# ============================================================
# 2. KEEP ALIVE
# ============================================================

def keep_alive():
    while True:
        time.sleep(300)
        if APP_URL:
            try:
                requests.get(APP_URL, timeout=15)
                print("[Keep Alive] OK")
            except Exception as e:
                print(f"[Keep Alive Error] {e}")


threading.Thread(target=keep_alive, daemon=True).start()


# ============================================================
# 3. TELEGRAM SETTINGS
# ============================================================

TELEGRAM_BOT_TOKEN = "8303140788:AAGE7DE1bhttDpRVB4GtoErn4kyDqemJ-Ns"
TELEGRAM_CHAT_ID = "5660614483"

IST = pytz.timezone("Asia/Kolkata")


# ============================================================
# 4. TELEGRAM FUNCTION
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN:
        print("[Telegram] ERROR: Bot token is missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        result = response.json()

        if result.get("ok"):
            print("[Telegram] Message sent successfully.")
            return True

        print(f"[Telegram] API Error: {result}")
        return False

    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False


# ============================================================
# 5. STRICT COOLDOWN LOGIC (एक ही स्क्रिप्ट बार-बार नहीं आएगी)
# ============================================================

sent_alerts = {}

def should_send_alert(symbol, alert_type, cooldown_minutes=45):
    key = f"{symbol}_{alert_type}"
    now = time.time()

    if key in sent_alerts:
        elapsed_minutes = (now - sent_alerts[key]) / 60
        if elapsed_minutes < cooldown_minutes:
            print(f"[SKIP] {symbol} ({alert_type}) blocked by cooldown ({int(cooldown_minutes - elapsed_minutes)} min left)")
            return False

    # रिकॉर्ड अपडेट करें
    sent_alerts[key] = now
    return True


# ============================================================
# 6. WATCHLIST (EQUITY, F&O, COMMODITIES)
# ============================================================

WATCHLIST = {
    # -------------------------
    # F&O INDEX & STOCKS
    # -------------------------
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "SBIN.NS": "SBI",
    "PNB.NS": "PNB",
    "GAIL.NS": "GAIL",
    "IOC.NS": "IOC",
    "FEDERALBNK.NS": "FEDERAL BANK",
    "ASHOKLEY.NS": "ASHOK LEYLAND",
    "BPCL.NS": "BPCL",
    "NTPC.NS": "NTPC",
    "PFC.NS": "PFC",
    "BHEL.NS": "BHEL",
    "TATAMOTORS.NS": "TATA MOTORS",
    "RELIANCE.NS": "RELIANCE",

    # -------------------------
    # COMMODITIES
    # -------------------------
    "GC=F": "GOLD",
    "SI=F": "SILVER",
    "CL=F": "CRUDE OIL",
    "NG=F": "NATURAL GAS",
}


# ============================================================
# 7. TECHNICAL INDICATORS
# ============================================================

def calculate_vwap(df):
    data = df.copy()
    volume = data["Volume"].fillna(0)
    typical_price = (data["High"] + data["Low"] + data["Close"]) / 3

    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")

    data.index = data.index.tz_convert(IST)
    session_date = data.index.date

    cumulative_pv = (typical_price * volume).groupby(session_date).cumsum()
    cumulative_volume = volume.groupby(session_date).cumsum()

    return cumulative_pv / (cumulative_volume + 1e-9)


def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_atr(df, window=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def bullish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    body = abs(row["Close"] - row["Open"])
    return row["Close"] > row["Open"] and (body / candle_range) >= 0.45


def bearish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    body = abs(row["Close"] - row["Open"])
    return row["Close"] < row["Open"] and (body / candle_range) >= 0.45


# ============================================================
# 8. MARKET SCANNER
# ============================================================

def scan_markets():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    })

    for ticker, display_name in WATCHLIST.items():
        try:
            ticker_obj = yf.Ticker(ticker, session=session)
            df = ticker_obj.history(period="5d", interval="5m", auto_adjust=False, prepost=False)

            if df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            if len(df) < 30:
                continue

            df["VWAP"] = calculate_vwap(df)
            df["RSI"] = calculate_rsi(df["Close"])
            df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
            df["ATR"] = calculate_atr(df)
            df["Volume_MA"] = df["Volume"].rolling(20).mean()

            latest = df.iloc[-2]
            prev = df.iloc[-3]

            close = float(latest["Close"])
            vwap = float(latest["VWAP"])
            rsi = float(latest["RSI"])
            ema9 = float(latest["EMA_9"])
            ema21 = float(latest["EMA_21"])
            prev_ema9 = float(prev["EMA_9"])
            prev_ema21 = float(prev["EMA_21"])
            atr = float(latest["ATR"])
            volume = float(latest["Volume"])
            volume_ma = float(latest["Volume_MA"])

            values = [close, vwap, rsi, ema9, ema21, prev_ema9, prev_ema21, atr, volume_ma]
            if any(np.isnan(x) for x in values) or atr <= 0:
                continue

            bullish_cross = prev_ema9 <= prev_ema21 and ema9 > ema21
            bearish_cross = prev_ema9 >= prev_ema21 and ema9 < ema21
            above_vwap = close > vwap
            below_vwap = close < vwap
            bullish_rsi = 50 <= rsi <= 70
            bearish_rsi = 30 <= rsi <= 50
            volume_confirmed = volume >= volume_ma * 1.10
            bullish_confirmed = bullish_candle(latest)
            bearish_confirmed = bearish_candle(latest)
            bullish_trend = ema9 > ema21 and close > ema9
            bearish_trend = ema9 < ema21 and close < ema9

            buy_score = sum([above_vwap, bullish_cross * 2, bullish_trend, bullish_rsi, volume_confirmed, bullish_confirmed])
            sell_score = sum([below_vwap, bearish_cross * 2, bearish_trend, bearish_rsi, volume_confirmed, bearish_confirmed])

            sl_points = max(atr * 1.20, close * 0.004)
            target_points = sl_points * 2

            # BUY ALERT
            if buy_score >= 5 and above_vwap:
                if should_send_alert(display_name, "BUY", cooldown_minutes=45):
                    sl = close - sl_points
                    target = close + target_points
                    risk = close - sl
                    reward = target - close

                    message = (
                        "🟢 *BUY ALERT*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{display_name}`\n"
                        f"💰 *Price:* `₹{close:.2f}`\n"
                        f"📊 *VWAP:* `₹{vwap:.2f}` (Above ✅)\n"
                        f"📈 *RSI:* `{rsi:.2f}`\n\n"
                        f"🎯 *Entry:* `₹{close:.2f}`\n"
                        f"🎯 *Target:* `₹{target:.2f}` (+₹{reward:.2f})\n"
                        f"🛑 *Stop Loss:* `₹{sl:.2f}` (-₹{risk:.2f})\n"
                        f"⭐ *Score:* `{buy_score}/7`"
                    )
                    send_telegram(message)

            # SELL ALERT
            elif sell_score >= 5 and below_vwap:
                if should_send_alert(display_name, "SELL", cooldown_minutes=45):
                    sl = close + sl_points
                    target = close - target_points
                    risk = sl - close
                    reward = close - target

                    message = (
                        "🔴 *SELL ALERT*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{display_name}`\n"
                        f"💰 *Price:* `₹{close:.2f}`\n"
                        f"📊 *VWAP:* `₹{vwap:.2f}` (Below 🔻)\n"
                        f"📉 *RSI:* `{rsi:.2f}`\n\n"
                        f"🎯 *Entry:* `₹{close:.2f}`\n"
                        f"🎯 *Target:* `₹{target:.2f}` (-₹{reward:.2f})\n"
                        f"🛑 *Stop Loss:* `₹{sl:.2f}` (+₹{risk:.2f})\n"
                        f"⭐ *Score:* `{sell_score}/7`"
                    )
                    send_telegram(message)

        except Exception as e:
            print(f"[Error scanning {display_name}] {e}")


# ============================================================
# 9. MAIN LOOP EXECUTION
# ============================================================

if __name__ == "__main__":
    print("Initializing Application...")

    startup_msg = (
        "🚀 *MANI TRADING BOT ACTIVATED*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ *Currency:* INR (₹)\n"
        "✅ *Cooldown:* 45 Minutes per Asset\n"
        "📡 *Status:* Scanning Active"
    )

    send_telegram(startup_msg)

    while True:
        try:
            scan_markets()
        except Exception as e:
            print(f"[MAIN LOOP ERROR] {e}")

        time.sleep(180)  # Scan every 3 minutes
