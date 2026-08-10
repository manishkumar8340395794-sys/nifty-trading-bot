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
        time.sleep(600)
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
TELEGRAM_BOT_TOKEN = "8993254284:AAGs5LwFD5PD0UMViDpDd8OY35lOSTMwyNE"
TELEGRAM_CHAT_ID = "5660614483"
IST = pytz.timezone("Asia/Kolkata")


# ============================================================
# 4. TELEGRAM FUNCTION
# ============================================================
def send_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
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


# ============================================================
# 5. ACTIVE TRADES TRACKER (FOR SL / TARGET NOTIFICATION)
# ============================================================
active_trades = {}
sent_alerts = {}


def is_duplicate_alert(symbol, alert_type, cooldown_minutes=45):
    key = f"{symbol}_{alert_type}"
    now = time.time()
    if key in sent_alerts:
        if now - sent_alerts[key] < cooldown_minutes * 60:
            return True
    sent_alerts[key] = now
    return False


# ============================================================
# 6. INDIAN WATCHLIST (ALL RATES IN ₹ INR)
# ============================================================
WATCHLIST = {
    # NSE STOCKS (₹ INR)
    "PNB.NS": "PNB (NSE)",
    "GAIL.NS": "GAIL (NSE)",
    "IOC.NS": "IOC (NSE)",
    "FEDERALBNK.NS": "FEDERAL BANK (NSE)",
    "ASHOKLEY.NS": "ASHOK LEYLAND (NSE)",
    "BPCL.NS": "BPCL (NSE)",
    "NTPC.NS": "NTPC (NSE)",
    "PFC.NS": "PFC (NSE)",
    "BHEL.NS": "BHEL (NSE)",
    "SBIN.NS": "SBI (NSE)",
    # MCX COMMODITIES IN INDIAN RUPEES (₹ INR)
    "NATURALGAS1.MCX": "NATURAL GAS (MCX ₹)",
    "CRUDEOIL1.MCX": "CRUDE OIL (MCX ₹)",
    "SILVER1.MCX": "SILVER (MCX ₹)",
    "GOLD1.MCX": "GOLD (MCX ₹)",
}


# ============================================================
# 7. INDICATOR CALCULATIONS
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
# 8. SCAN MARKETS & TRACK ACTIVE POSITIONS
# ============================================================
def scan_markets():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    })

    for ticker, display_name in WATCHLIST.items():
        try:
            ticker_obj = yf.Ticker(ticker, session=session)
            df = ticker_obj.history(
                period="5d", interval="5m", auto_adjust=False, prepost=False
            )

            if df.empty:
                # Fallback for MCX ticker symbols if standard failed
                if ".MCX" in ticker:
                    alt_ticker = ticker.replace("1.MCX", "=F")
                    ticker_obj = yf.Ticker(alt_ticker, session=session)
                    df = ticker_obj.history(
                        period="5d",
                        interval="5m",
                        auto_adjust=False,
                        prepost=False,
                    )

            if df.empty or len(df) < 50:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna(subset=["Open", "High", "Low", "Close"])

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

            # ----------------------------------------------------
            # 8A. CHECK ACTIVE TRADES FOR SL / TARGET HIT
            # ----------------------------------------------------
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
                            f"✅ *Profit per share/lot:* `+₹{close - trade['entry']:.2f}`"
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
                            f"⚠️ *Loss per share/lot:* `-₹{trade['entry'] - close:.2f}`"
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
                            f"✅ *Profit per share/lot:* `+₹{trade['entry'] - close:.2f}`"
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
                            f"⚠️ *Loss per share/lot:* `-₹{close - trade['entry']:.2f}`"
                        )
                        del active_trades[display_name]
                        continue

            # ----------------------------------------------------
            # 8B. GENERATE NEW SIGNALS
            # ----------------------------------------------------
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

            # BUY ALERT
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
                        "🔄 *Bot will track & notify on Target or SL Hit!*"
                    )
                    send_telegram(message)

            # SELL ALERT
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
                        f"⭐ *Score:* `{sell_score}/7`\n\n"
                        "🔄 *Bot will track & notify on Target or SL Hit!*"
                    )
                    send_telegram(message)

            time.sleep(1.5)

        except Exception as e:
            print(f"[ERROR] {ticker}: {e}")


# ============================================================
# 9. STARTUP MESSAGE & MAIN LOOP
# ============================================================
send_telegram(
    "🚀 *INDIAN MARKET & COMMODITY SCANNER ACTIVATED!*\n\n"
    "🇮🇳 Currency: Indian Rupees (₹ INR / MCX)\n"
    "📊 Timeframe: 5 Minutes\n"
    "🎯 Auto Target & SL Tracker: ACTIVATED ✅\n\n"
    "Scanner is now live."
)

while True:
    try:
        now_ist = datetime.now(IST)
        current_time = now_ist.strftime("%H:%M:%S")

        print(
            f"[{current_time} IST] Scanning Indian Stocks & MCX Commodities..."
        )

        if is_market_open():
            scan_markets()
        else:
            print("Outside configured market window.")

        time.sleep(180)

    except Exception as e:
        print(f"[MAIN LOOP ERROR] {e}")
        time.sleep(30)
