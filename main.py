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
# 2. INTERNAL AUTO KEEP-ALIVE (FORCES RENDER TO STAY AWAKE)
# ============================================================
def keep_alive():
    time.sleep(15)
    # बाहरी नेटवर्क पर निर्भर न रहकर अंदरूनी (Localhost) पोर्ट को पिंग करेगा
    local_url = f"http://127.0.0.1:{PORT}"

    while True:
        try:
            res = requests.get(local_url, timeout=10)
            print(
                f"[{datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}]"
                f" Internal Ping Status: {res.status_code}"
            )
        except Exception as e:
            print(f"[Keep-Alive Note] {e}")

        # हर 90 सेकंड (1.5 मिनट) में पिंग करेगा ताकि 15 मिनट वाला स्लीप टाइमर कभी चालू ही न हो
        time.sleep(90)


threading.Thread(target=keep_alive, daemon=True).start()

# ============================================================
# 3. TELEGRAM SETTINGS
# ============================================================
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
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False


active_trades = {}
sent_alerts = {}


def is_duplicate_alert(symbol, alert_type, cooldown_minutes=45):
    key = f"{symbol}_{alert_type}"
    now = time.time()
    if key in sent_alerts and (now - sent_alerts[key] < cooldown_minutes * 60):
        return True
    sent_alerts[key] = now
    return False


# ============================================================
# 4. WATCHLIST (ACCURATE MCX & NSE TICKERS)
# ============================================================
WATCHLIST = {
    # NSE STOCKS (₹ INR Direct)
    "PNB.NS": {"name": "PNB (NSE)", "factor": 1.0},
    "GAIL.NS": {"name": "GAIL (NSE)", "factor": 1.0},
    "IOC.NS": {"name": "IOC (NSE)", "factor": 1.0},
    "FEDERALBNK.NS": {"name": "FEDERAL BANK (NSE)", "factor": 1.0},
    "ASHOKLEY.NS": {"name": "ASHOK LEYLAND (NSE)", "factor": 1.0},
    "BPCL.NS": {"name": "BPCL (NSE)", "factor": 1.0},
    "NTPC.NS": {"name": "NTPC (NSE)", "factor": 1.0},
    "PFC.NS": {"name": "PFC (NSE)", "factor": 1.0},
    "BHEL.NS": {"name": "BHEL (NSE)", "factor": 1.0},
    "SBIN.NS": {"name": "SBI (NSE)", "factor": 1.0},
    # COMMODITIES (MCX Scaled Equivalent)
    "GC=F": {"name": "GOLD 10G (MCX Est. ₹)", "factor": 30.0},
    "SI=F": {"name": "SILVER 1KG (MCX Est. ₹)", "factor": 2700.0},
    "CL=F": {"name": "CRUDE OIL (MCX Est. ₹)", "factor": 83.5},
    "NG=F": {"name": "NATURAL GAS (MCX Est. ₹)", "factor": 83.5},
}


# ============================================================
# 5. INDICATOR CALCULATIONS
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

    avg_gain = gain.ewm(
        alpha=1 / window, adjust=False, min_periods=window
    ).mean()
    avg_loss = loss.ewm(
        alpha=1 / window, adjust=False, min_periods=window
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_atr(df, window=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return true_range.ewm(
        alpha=1 / window, adjust=False, min_periods=window
    ).mean()


def is_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    current_time = now.time()
    return current_time.hour >= 9 and current_time.hour <= 23


def bullish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    return (row["Close"] > row["Open"]) and (
        abs(row["Close"] - row["Open"]) / candle_range >= 0.50
    )


def bearish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    return (row["Close"] < row["Open"]) and (
        abs(row["Close"] - row["Open"]) / candle_range >= 0.50
    )


# ============================================================
# 6. SCAN MARKETS
# ============================================================
def scan_markets():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    })

    for ticker, info in WATCHLIST.items():
        display_name = info["name"]
        factor = info["factor"]

        try:
            ticker_obj = yf.Ticker(ticker, session=session)
            df = ticker_obj.history(
                period="5d", interval="5m", auto_adjust=False, prepost=False
            )

            if df.empty or len(df) < 50:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna(subset=["Open", "High", "Low", "Close"])

            df["Open"] = df["Open"] * factor
            df["High"] = df["High"] * factor
            df["Low"] = df["Low"] * factor
            df["Close"] = df["Close"] * factor

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

            if display_name in active_trades:
                trade = active_trades[display_name]
                trade_type = trade["type"]
                target_p = trade["target"]
                sl_p = trade["sl"]

                if trade_type == "BUY":
                    if close >= target_p:
                        send_telegram(
                            f"🎉 *TARGET HIT! PROFIT BOOKED* 🎉\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 *Asset:* `{display_name}`\n"
                            f"💰 *Entry:* `₹{trade['entry']:.2f}`\n"
                            f"🎯 *Target Hit:* `₹{close:.2f}`\n"
                            f"✅ *Profit:* `+₹{close - trade['entry']:.2f}`"
                        )
                        del active_trades[display_name]
                        continue
                    elif close <= sl_p:
                        send_telegram(
                            f"🛑 *STOP LOSS HIT! TRADE CLOSED* 🛑\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 *Asset:* `{display_name}`\n"
                            f"💰 *Entry:* `₹{trade['entry']:.2f}`\n"
                            f"🔻 *SL Hit:* `₹{close:.2f}`\n"
                            f"⚠️ *Loss:* `-₹{trade['entry'] - close:.2f}`"
                        )
                        del active_trades[display_name]
                        continue

                elif trade_type == "SELL":
                    if close <= target_p:
                        send_telegram(
                            f"🎉 *TARGET HIT! PROFIT BOOKED* 🎉\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 *Asset:* `{display_name}`\n"
                            f"💰 *Entry:* `₹{trade['entry']:.2f}`\n"
                            f"🎯 *Target Hit:* `₹{close:.2f}`\n"
                            f"✅ *Profit:* `+₹{trade['entry'] - close:.2f}`"
                        )
                        del active_trades[display_name]
                        continue
                    elif close >= sl_p:
                        send_telegram(
                            f"🛑 *STOP LOSS HIT! TRADE CLOSED* 🛑\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"📌 *Asset:* `{display_name}`\n"
                            f"💰 *Entry:* `₹{trade['entry']:.2f}`\n"
                            f"🔻 *SL Hit:* `₹{close:.2f}`\n"
                            f"⚠️ *Loss:* `-₹{close - trade['entry']:.2f}`"
                        )
                        del active_trades[display_name]
                        continue

            bullish_cross = prev_ema9 <= prev_ema21 and ema9 > ema21
            bearish_cross = prev_ema9 >= prev_ema21 and ema9 < ema21
            above_vwap = close > vwap
            below_vwap = close < vwap
            bullish_rsi = 54 <= rsi <= 68
            bearish_rsi = 32 <= rsi <= 46
            volume_confirmed = volume >= volume_ma * 1.20
            bullish_confirmed = bullish_candle(latest)
            bearish_confirmed = bearish_candle(latest)
            bullish_trend = ema9 > ema21 and close > ema9
            bearish_trend = ema9 < ema21 and close < ema9

            buy_score = sum([
                above_vwap,
                bullish_cross * 2,
                bullish_trend,
                bullish_rsi,
                volume_confirmed,
                bullish_confirmed,
            ])
            sell_score = sum([
                below_vwap,
                bearish_cross * 2,
                bearish_trend,
                bearish_rsi,
                volume_confirmed,
                bearish_confirmed,
            ])

            sl_points = max(atr * 1.20, close * 0.004)
            target_points = sl_points * 2

            if (
                buy_score >= 6
                and above_vwap
                and bullish_trend
                and bullish_rsi
                and volume_confirmed
                and bullish_confirmed
            ):
                if not is_duplicate_alert(display_name, "BUY"):
                    sl = round(close - sl_points, 2)
                    target = round(close + target_points, 2)
                    active_trades[display_name] = {
                        "type": "BUY",
                        "entry": close,
                        "sl": sl,
                        "target": target,
                    }

                    message = (
                        "🟢 *STRONG BUY ALERT (INR ₹)*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{display_name}`\n"
                        f"💰 *Entry Price:* `₹{close:.2f}`\n"
                        f"📊 *VWAP:* `₹{vwap:.2f}` Above ✅\n"
                        f"📈 *RSI:* `{rsi:.2f}`\n\n"
                        f"🎯 *Target:* `₹{target:.2f}` (+₹{target - close:.2f})\n"
                        f"🛑 *Stop Loss:* `₹{sl:.2f}` (-₹{close - sl:.2f})\n"
                        f"⚖️ *Risk/Reward:* 1:2\n"
                        f"⭐ *Score:* `{buy_score}/7`\n\n"
                        "🔄 *Bot tracking Target & SL Hit!*"
                    )
                    send_telegram(message)

            elif (
                sell_score >= 6
                and below_vwap
                and bearish_trend
                and bearish_rsi
                and volume_confirmed
                and bearish_confirmed
            ):
                if not is_duplicate_alert(display_name, "SELL"):
                    sl = round(close + sl_points, 2)
                    target = round(close - target_points, 2)
                    active_trades[display_name] = {
                        "type": "SELL",
                        "entry": close,
                        "sl": sl,
                        "target": target,
                    }

                    message = (
                        "🔴 *STRONG SELL ALERT (INR ₹)*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{display_name}`\n"
                        f"💰 *Entry Price:* `₹{close:.2f}`\n"
                        f"📊 *VWAP:* `₹{vwap:.2f}` Below 🔻\n"
                        f"📉 *RSI:* `{rsi:.2f}`\n\n"
                        f"🎯 *Target:* `₹{target:.2f}` (-₹{close - target:.2f})\n"
                        f"🛑 *Stop Loss:* `₹{sl:.2f}` (+₹{sl - close:.2f})\n"
                        f"⚖️ *Risk/Reward:* 1:2\n"
                        f"⭐ *Score:* `{buy_score}/7`\n\n"
                        "🔄 *Bot tracking Target & SL Hit!*"
                    )
                    send_telegram(message)

            time.sleep(1.5)

        except Exception as e:
            print(f"[ERROR] {ticker}: {e}")


# ============================================================
# 7. MAIN LOOP
# ============================================================
send_telegram("🚀 *100% NON-STOP KEEP-ALIVE BOT ACTIVATED*")

while True:
    try:
        now_ist = datetime.now(IST)
        print(
            f"[{now_ist.strftime('%H:%M:%S')} IST] Scanning Indian Stocks &"
            " Commodities..."
        )

        if is_market_open():
            scan_markets()
        else:
            print("Outside market hours.")

        time.sleep(180)

    except Exception as e:
        print(f"[MAIN LOOP ERROR] {e}")
        time.sleep(30)
