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
    if not TELEGRAM_BOT_TOKEN or "PASTE_YOUR_NEW" in TELEGRAM_BOT_TOKEN:
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
# 5. DUPLICATE ALERT PROTECTION (COOLDOWN LOGIC)
# ============================================================

sent_alerts = {}


def is_duplicate_alert(symbol, alert_type, cooldown_minutes=45):
    key = f"{symbol}_{alert_type}"
    now = time.time()

    if key in sent_alerts:
        elapsed = now - sent_alerts[key]
        if elapsed < cooldown_minutes * 60:
            return True

    sent_alerts[key] = now
    return False


# ============================================================
# 6. WATCHLIST (EQUITY, F&O, COMMODITIES)
# ============================================================

WATCHLIST = {
    # -------------------------
    # F&O INDEX FUTURES & STOCKS
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
# 7. SESSION VWAP
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


# ============================================================
# 8. RSI
# ============================================================

def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


# ============================================================
# 9. ATR
# ============================================================

def calculate_atr(df, window=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


# ============================================================
# 10. MARKET HOURS
# ============================================================

def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday/Sunday
        return False

    current_time = now.time()
    if current_time.hour >= 9 and current_time.hour <= 23:
        return True

    return False


# ============================================================
# 11. CANDLE CONFIRMATION
# ============================================================

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
# 12. SCAN MARKETS
# ============================================================

def scan_markets():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    })

    for ticker, display_name in WATCHLIST.items():
        try:
            print(f"\nScanning: {display_name}")

            ticker_obj = yf.Ticker(ticker, session=session)
            df = ticker_obj.history(period="5d", interval="5m", auto_adjust=False, prepost=False)

            if df.empty:
                print(f"{display_name}: No data.")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            required_columns = ["Open", "High", "Low", "Close", "Volume"]
            if not all(col in df.columns for col in required_columns):
                print(f"{display_name}: Required columns missing.")
                continue

            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            if len(df) < 30:
                print(f"{display_name}: Not enough candles.")
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

            print(f"{display_name}: Price=₹{close:.2f} | RSI={rsi:.2f} | BUY={buy_score}/7 | SELL={sell_score}/7")

            sl_points = max(atr * 1.20, close * 0.004)
            target_points = sl_points * 2

            # BUY ALERT
            if buy_score >= 5 and above_vwap:
                if not is_duplicate_alert(display_name, "BUY", cooldown_minutes=45):
                    sl = close - sl_points
                    target = close + target_points
                    risk = close - sl
                    reward = target - close

                    message = (
                        "🟢 *BUY ALERT (F&O / Equity / Commodity)*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{display_name}`\n"
                        f"💰 *Price:* `₹{close:.2f}`\n"
                        f"📊 *VWAP:* `₹{vwap:.2f}` (Above ✅)\n"
                        f"📈 *RSI:* `{rsi:.2f}`\n"
                        f"📈 *EMA 9/21:* `{ema9:.2f}` / `{ema21:.2f}`\n\n"
                        f"🎯 *Entry:* `₹{close:.2f}`\n"
                        f"🎯 *Target:* `₹{target:.2f}` (+₹{reward:.2f})\n"
                        f"🛑 *Stop Loss:* `₹{sl:.2f}` (-₹{risk:.2f})\n"
                        f"⚖️ *Risk/Reward:* 1:2\n"
                        f"⭐ *Score:* `{buy_score}/7`"
                    )
                    send_telegram(message)

            # SELL ALERT
            elif sell_score >= 5 and below_vwap:
                if not is_duplicate_alert(display_name, "SELL", cooldown_minutes=45):
                    sl = close + sl_points
                    target = close - target_points
                    risk = sl - close
                    reward = close - target

                    message = (
                        "🔴 *SELL ALERT (F&O / Equity / Commodity)*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{display_name}`\n"
                        f"💰 *Price:* `₹{close:.2f}`\n"
                        f"📊 *VWAP:* `₹{vwap:.2f}` (Below 🔻)\n"
                        f"📉 *RSI:* `{rsi:.2f}`\n"
                        f"📉 *EMA 9/21:* `{ema9:.2f}` / `{ema21:.2f}`\n\n"
                        f"🎯 *Entry:* `₹{close:.2f}`\n"
                        f"🎯 *Target:* `₹{target:.2f}` (-₹{reward:.2f})\n"
                        f"🛑 *Stop Loss:* `₹{sl:.2f}` (+₹{risk:.2f})\n"
                        f"⚖️ *Risk/Reward:* 1:2\n"
                        f"⭐ *Score:* `{sell_score}/7`"
                    )
                    send_telegram(message)

        except Exception as e:
            print(f"[Error scanning {display_name}] {e}")


# ============================================================
# 13. MAIN LOOP EXECUTION
# ============================================================

if __name__ == "__main__":
    print("Initializing Application...")

    startup_msg = (
        "🚀 *MANI TRADING BOT SYSTEM ACTIVE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "✅ *Token & Chat ID:* Configured\n"
        "✅ *Currency:* INR (₹)\n"
        "✅ *Markets:* F&O, Commodities, Stocks\n"
        "⏳ *Cooldown Filter:* Active (45 Min)"
    )

    send_telegram(startup_msg)

    while True:
        try:
            if is_market_open():
                scan_markets()
            else:
                print("Market is closed. Sleeping...")
        except Exception as e:
            print(f"[MAIN LOOP ERROR] {e}")

        time.sleep(300)  # Scan every 5 minutes
