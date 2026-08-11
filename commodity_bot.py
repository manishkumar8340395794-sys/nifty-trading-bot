import http.server
import os
import socketserver
import threading
import time
from datetime import datetime

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
        print("[Telegram] ERROR: Bot token missing.")
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
            print("[Telegram] Commodity Alert Sent Successfully.")
            return True
        return False
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False


# ============================================================
# 5. COOLDOWN & ACTIVE TRADES ENGINE
# ============================================================

sent_alerts = {}
active_trades = {}


def is_duplicate_alert(symbol, alert_type, cooldown_minutes=45):
    key = f"{symbol}_{alert_type}"
    now = time.time()

    if key in sent_alerts:
        elapsed = (now - sent_alerts[key]) / 60
        if elapsed < cooldown_minutes:
            print(
                f"[SKIP] {symbol} ({alert_type}) blocked by cooldown ({int(cooldown_minutes - elapsed)} min left)"
            )
            return True

    sent_alerts[key] = now
    return False


# ============================================================
# 6. COMMODITY WATCHLIST (MCX / INTERNATIONAL FUTURES)
# ============================================================

WATCHLIST = {
    "GC=F": "GOLD (MCX / International)",
    "SI=F": "SILVER (MCX / International)",
    "CL=F": "CRUDE OIL",
    "NG=F": "NATURAL GAS",
    "HG=F": "COPPER",
}


# ============================================================
# 7. MCX MARKET HOURS CHECK
# ============================================================


def is_commodity_market_open():
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday & Sunday Closed
        return False
    current_time = now.time()
    # MCX Hours: Morning 09:00 AM to Night 11:30 PM (or 11:55 PM) IST
    return (current_time.hour == 9 and current_time.minute >= 0) or (
        9 < current_time.hour < 23
    ) or (current_time.hour == 23 and current_time.minute <= 30)


# ============================================================
# 8. TECHNICAL INDICATORS
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

    vwap = cumulative_pv / (cumulative_volume + 1e-9)
    return vwap.fillna(data["Close"])


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


def bullish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    body = abs(row["Close"] - row["Open"])
    return row["Close"] > row["Open"] and (body / candle_range) >= 0.50


def bearish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    body = abs(row["Close"] - row["Open"])
    return row["Close"] < row["Open"] and (body / candle_range) >= 0.50


# ============================================================
# 9. COMMODITY SCANNER & TRADE TRACKER
# ============================================================


def scan_commodities():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        )
    })

    for ticker, display_name in WATCHLIST.items():
        try:
            print(f"Scanning Commodity: {display_name}")
            ticker_obj = yf.Ticker(ticker, session=session)
            df = ticker_obj.history(
                period="5d", interval="5m", auto_adjust=False, prepost=False
            )

            if df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            if len(df) < 50:
                continue

            if "Volume" not in df.columns or df["Volume"].sum() == 0:
                df["Volume"] = 1000

            # Calculation
            df["VWAP"] = calculate_vwap(df)
            df["RSI"] = calculate_rsi(df["Close"])
            df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
            df["ATR"] = calculate_atr(df)
            df["Volume_MA"] = df["Volume"].rolling(20).mean().fillna(100)

            latest = df.iloc[-2]
            prev = df.iloc[-3]

            close = float(latest["Close"])
            high = float(latest["High"])
            low = float(latest["Low"])
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
            # A. TARGET / STOP LOSS TRACKER FOR COMMODITY TRADES
            # ----------------------------------------------------
            if display_name in active_trades:
                trade = active_trades[display_name]

                # BUY Trade Check
                if trade["type"] == "BUY":
                    if high >= trade["target"]:
                        msg = (
                            "🔥 *COMMODITY TARGET ACHIEVED!* 🎉\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"🛢️ *Asset:* `{display_name}`\n"
                            f"🚀 *Entry:* `{trade['entry']:.2f}`\n"
                            f"🎯 *Target Hit:* `{trade['target']:.2f}`\n"
                            f"💰 *Profit Points:* `+{trade['target'] - trade['entry']:.2f}`"
                        )
                        send_telegram(msg)
                        del active_trades[display_name]

                    elif low <= trade["sl"]:
                        msg = (
                            "🛑 *COMMODITY STOP LOSS HIT!* ⚠️\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"🛢️ *Asset:* `{display_name}`\n"
                            f"🚀 *Entry:* `{trade['entry']:.2f}`\n"
                            f"🛑 *SL Hit:* `{trade['sl']:.2f}`\n"
                            f"📉 *Loss Points:* `-{trade['entry'] - trade['sl']:.2f}`"
                        )
                        send_telegram(msg)
                        del active_trades[display_name]

                # SELL Trade Check
                elif trade["type"] == "SELL":
                    if low <= trade["target"]:
                        msg = (
                            "🔥 *COMMODITY TARGET ACHIEVED!* 🎉\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"🛢️ *Asset:* `{display_name}`\n"
                            f"📉 *Entry:* `{trade['entry']:.2f}`\n"
                            f"🎯 *Target Hit:* `{trade['target']:.2f}`\n"
                            f"💰 *Profit Points:* `+{trade['entry'] - trade['target']:.2f}`"
                        )
                        send_telegram(msg)
                        del active_trades[display_name]

                    elif high >= trade["sl"]:
                        msg = (
                            "🛑 *COMMODITY STOP LOSS HIT!* ⚠️\n"
                            "━━━━━━━━━━━━━━━━━━━━\n"
                            f"🛢️ *Asset:* `{display_name}`\n"
                            f"📉 *Entry:* `{trade['entry']:.2f}`\n"
                            f"🛑 *SL Hit:* `{trade['sl']:.2f}`\n"
                            f"📉 *Loss Points:* `-{trade['sl'] - trade['entry']:.2f}`"
                        )
                        send_telegram(msg)
                        del active_trades[display_name]

            # ----------------------------------------------------
            # B. STRICT STRATEGY & SCORE SYSTEM
            # ----------------------------------------------------
            bullish_cross = prev_ema9 <= prev_ema21 and ema9 > ema21
            bearish_cross = prev_ema9 >= prev_ema21 and ema9 < ema21
            above_vwap = close > vwap
            below_vwap = close < vwap

            # Strict RSI Rules
            bullish_rsi = 54 <= rsi <= 68
            bearish_rsi = 32 <= rsi <= 46

            # Volume & Candle Ratio
            volume_confirmed = volume >= volume_ma * 1.20
            bullish_confirmed = bullish_candle(latest)
            bearish_confirmed = bearish_candle(latest)

            # Trend Confirmation
            bullish_trend = ema9 > ema21 and close > ema9
            bearish_trend = ema9 < ema21 and close < ema9

            # Score Calculation
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

            # ATR Risk Management
            sl_points = max(atr * 1.20, close * 0.004)
            target_points = sl_points * 2

            # ----------------------------------------------------
            # C. SIGNAL GENERATION (STRICT 6/7 FILTER)
            # ----------------------------------------------------
            strong_buy = (
                buy_score >= 6
                and above_vwap
                and bullish_trend
                and bullish_rsi
                and volume_confirmed
                and bullish_confirmed
            )
            strong_sell = (
                sell_score >= 6
                and below_vwap
                and bearish_trend
                and bearish_rsi
                and volume_confirmed
                and bearish_confirmed
            )

            if strong_buy:
                if not is_duplicate_alert(display_name, "BUY"):
                    sl = close - sl_points
                    target = close + target_points
                    risk = close - sl
                    reward = target - close

                    active_trades[display_name] = {
                        "type": "BUY",
                        "entry": close,
                        "target": target,
                        "sl": sl,
                    }

                    message = (
                        "🟢 *STRONG COMMODITY BUY SIGNAL*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🛢️ *Asset:* `{display_name}`\n"
                        f"💰 *Price:* `{close:.2f}`\n"
                        f"📊 *VWAP:* `{vwap:.2f}` (Above ✅)\n"
                        f"📈 *RSI:* `{rsi:.2f}`\n"
                        f"📈 *EMA 9:* `{ema9:.2f}` | *EMA 21:* `{ema21:.2f}`\n"
                        f"🔊 *Volume:* 1.2x Confirmed ✅\n"
                        f"🕯️ *Candle:* Bullish Body ✅\n\n"
                        f"🎯 *Entry:* `{close:.2f}`\n"
                        f"🎯 *Target:* `{target:.2f}` (+{reward:.2f})\n"
                        f"🛑 *Stop Loss:* `{sl:.2f}` (-{risk:.2f})\n"
                        f"⚖️ *Risk/Reward:* 1:2\n"
                        f"⭐ *Score:* `{buy_score}/7`\n\n"
                        "⚠️ *Verify MCX charts before executing trade.*"
                    )
                    send_telegram(message)

            elif strong_sell:
                if not is_duplicate_alert(display_name, "SELL"):
                    sl = close + sl_points
                    target = close - target_points
                    risk = sl - close
                    reward = close - target

                    active_trades[display_name] = {
                        "type": "SELL",
                        "entry": close,
                        "target": target,
                        "sl": sl,
                    }

                    message = (
                        "🔴 *STRONG COMMODITY SELL SIGNAL*\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        f"🛢️ *Asset:* `{display_name}`\n"
                        f"💰 *Price:* `{close:.2f}`\n"
                        f"📊 *VWAP:* `{vwap:.2f}` (Below 🔻)\n"
                        f"📉 *RSI:* `{rsi:.2f}`\n"
                        f"📈 *EMA 9:* `{ema9:.2f}` | *EMA 21:* `{ema21:.2f}`\n"
                        f"🔊 *Volume:* 1.2x Confirmed ✅\n"
                        f"🕯️ *Candle:* Bearish Body ✅\n\n"
                        f"🎯 *Entry:* `{close:.2f}`\n"
                        f"🎯 *Target:* `{target:.2f}` (-{reward:.2f})\n"
                        f"🛑 *Stop Loss:* `{sl:.2f}` (+{risk:.2f})\n"
                        f"⚖️ *Risk/Reward:* 1:2\n"
                        f"⭐ *Score:* `{sell_score}/7`\n\n"
                        "⚠️ *Verify MCX charts before executing trade.*"
                    )
                    send_telegram(message)

            time.sleep(1)

        except Exception as e:
            print(f"[Error scanning {display_name}] {e}")


# ============================================================
# 10. MAIN EXECUTION LOOP
# ============================================================

if __name__ == "__main__":
    print("Initializing Commodity Application...")

    send_telegram(
        "🛢️ *MCX COMMODITY SCANNER ACTIVATED!*\n\n"
        "📊 Timeframe: 5 Minutes\n"
        "📈 Strategy: VWAP + EMA 9/21 + RSI + ATR\n"
        "🕒 Market Hours: 09:00 AM to 11:30 PM IST\n"
        "🎯 Tracker: Live Target & Stop Loss Hit Engine\n"
        "⭐ Strict Score Filter: 6/7 Required\n\n"
        "Commodity scanner is active."
    )

    while True:
        try:
            now_ist = datetime.now(IST)
            current_time = now_ist.strftime("%H:%M:%S")

            print("\n==============================================")
            print(f"[{current_time} IST] Scanning Commodity Markets...")

            if is_commodity_market_open():
                scan_commodities()
            else:
                print("MCX Market is currently CLOSED.")

            print("Next scan after 180 seconds...")
            time.sleep(180)

        except KeyboardInterrupt:
            print("Commodity scanner stopped.")
            break
        except Exception as e:
            print(f"[MAIN LOOP ERROR] {e}")
            time.sleep(30)
