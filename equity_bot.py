from datetime import datetime
import json
import os
import time

import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf

# ============================================================
# CONFIG & ENVIRONMENT
# ============================================================

IST = pytz.timezone("Asia/Kolkata")

ALERT_COOLDOWN_MINUTES = 45
CACHE_FILE = "sent_alerts.json"

# Telegram Credentials (Environment Secrets + Fallback)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

if not TELEGRAM_BOT_TOKEN:
    TELEGRAM_BOT_TOKEN = "8303140788:AAHvS4sT5c1_5dOexKxN8Y025k3R8d26q60"

if not TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = "5660614483"


# ============================================================
# TELEGRAM ALERT SYSTEM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM ERROR] Token or Chat ID missing.")
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
            print("[TELEGRAM] Alert sent successfully.")
            return True
        print(f"[TELEGRAM ERROR] {result}")
        return False
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False


# ============================================================
# DUPLICATE ALERT PROTECTION (JSON CACHE)
# ============================================================

def load_sent_alerts():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_sent_alerts(alerts):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(alerts, f)
    except Exception as e:
        print(f"[CACHE ERROR] Could not save cache: {e}")


def is_duplicate_alert(symbol, alert_type):
    key = f"{symbol}_{alert_type}"
    now = time.time()
    sent_alerts = load_sent_alerts()

    if key in sent_alerts:
        elapsed = now - sent_alerts[key]
        if elapsed < (ALERT_COOLDOWN_MINUTES * 60):
            return True

    sent_alerts[key] = now
    save_sent_alerts(sent_alerts)
    return False


# ============================================================
# WATCHLIST (STOCKS, INDEXES, COMMODITIES)
# ============================================================

WATCHLIST = {
    # NSE STOCKS
    "PNB.NS": "PNB",
    "GAIL.NS": "GAIL",
    "IOC.NS": "IOC",
    "FEDERALBNK.NS": "FEDERAL BANK",
    "ASHOKLEY.NS": "ASHOK LEYLAND",
    "BPCL.NS": "BPCL",
    "NTPC.NS": "NTPC",
    "PFC.NS": "PFC",
    "BHEL.NS": "BHEL",
    "SBIN.NS": "SBI",

    # INDEXES
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "^CNXIT": "NIFTY IT",
    "^BSESN": "SENSEX",

    # COMMODITIES
    "GC=F": "GOLD",
    "SI=F": "SILVER",
    "CL=F": "CRUDE OIL",
    "NG=F": "NATURAL GAS",
}

INDEX_SYMBOLS = {
    "^NSEI",
    "^NSEBANK",
    "^CNXIT",
    "^BSESN",
}


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_atr(df, window=14):
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def calculate_vwap(df):
    data = df.copy()
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    data.index = data.index.tz_convert(IST)

    typical_price = (data["High"] + data["Low"] + data["Close"]) / 3
    volume = data["Volume"].fillna(0)
    session = data.index.date

    cumulative_pv = (typical_price * volume).groupby(session).cumsum()
    cumulative_volume = volume.groupby(session).cumsum()

    return cumulative_pv / (cumulative_volume + 1e-9)


# ============================================================
# CANDLE PATTERN CONFIRMATION
# ============================================================

def bullish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    body = abs(row["Close"] - row["Open"])
    body_ratio = body / candle_range
    close_position = (row["Close"] - row["Low"]) / candle_range
    return row["Close"] > row["Open"] and body_ratio >= 0.50 and close_position >= 0.65


def bearish_candle(row):
    candle_range = row["High"] - row["Low"]
    if candle_range <= 0:
        return False
    body = abs(row["Close"] - row["Open"])
    body_ratio = body / candle_range
    close_position = (row["High"] - row["Close"]) / candle_range
    return row["Close"] < row["Open"] and body_ratio >= 0.50 and close_position >= 0.65


# ============================================================
# DATA CLEANING
# ============================================================

def clean_data(df):
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]
    if not all(column in df.columns for column in required):
        return pd.DataFrame()

    df = df[required]
    df.dropna(subset=["Open", "High", "Low", "Close"], inplace=True)
    return df


# ============================================================
# CHATGPT SCORING LOGIC ENGINE
# ============================================================

def analyze_asset(ticker, name, session):
    try:
        print(f"[SCAN] {name} ({ticker})...")
        obj = yf.Ticker(ticker, session=session)
        df = obj.history(period="5d", interval="5m", auto_adjust=False, prepost=False)

        df = clean_data(df)

        if df.empty or len(df) < 60:
            print(f" └─ {name}: Insufficient candle data.")
            return

        # Indicators
        df["VWAP"] = calculate_vwap(df)
        df["RSI"] = calculate_rsi(df["Close"])
        df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
        df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
        df["ATR"] = calculate_atr(df)
        df["VolumeMA"] = df["Volume"].rolling(20).mean()

        # Last completed candle
        latest = df.iloc[-2]
        previous = df.iloc[-3]

        close = float(latest["Close"])
        vwap = float(latest["VWAP"])
        rsi = float(latest["RSI"])
        ema9 = float(latest["EMA9"])
        ema21 = float(latest["EMA21"])
        prev_ema9 = float(previous["EMA9"])
        prev_ema21 = float(previous["EMA21"])
        atr = float(latest["ATR"])
        volume = float(latest["Volume"])
        volume_ma = float(latest["VolumeMA"])

        values = [close, vwap, rsi, ema9, ema21, prev_ema9, prev_ema21, atr, volume_ma]
        if any(np.isnan(x) for x in values):
            print(f" └─ {name}: NaN indicator values.")
            return

        # Technical Conditions
        above_vwap = close > vwap
        below_vwap = close < vwap
        bullish_cross = prev_ema9 <= prev_ema21 and ema9 > ema21
        bearish_cross = prev_ema9 >= prev_ema21 and ema9 < ema21
        bullish_trend = ema9 > ema21 and close > ema9
        bearish_trend = ema9 < ema21 and close < ema9
        bullish_rsi = 54 <= rsi <= 68
        bearish_rsi = 32 <= rsi <= 46
        volume_ok = volume >= volume_ma * 1.20
        bullish_confirmed = bullish_candle(latest)
        bearish_confirmed = bearish_candle(latest)

        # Chat GPT Score Criteria (Max 7)
        buy_score = 0
        sell_score = 0

        if above_vwap: buy_score += 1
        if bullish_cross: buy_score += 2
        if bullish_trend: buy_score += 1
        if bullish_rsi: buy_score += 1
        if volume_ok: buy_score += 1
        if bullish_confirmed: buy_score += 1

        if below_vwap: sell_score += 1
        if bearish_cross: sell_score += 2
        if bearish_trend: sell_score += 1
        if bearish_rsi: sell_score += 1
        if volume_ok: sell_score += 1
        if bearish_confirmed: sell_score += 1

        print(f" └─ Price: {close:.2f} | RSI: {rsi:.2f} | BUY Score: {buy_score}/7 | SELL Score: {sell_score}/7")

        # Stop-Loss & Target
        sl_distance = max(atr * 1.20, close * 0.004)
        target_distance = sl_distance * 2

        buy_setup = (
            buy_score >= 6
            and above_vwap
            and bullish_trend
            and bullish_rsi
            and volume_ok
            and bullish_confirmed
        )

        sell_setup = (
            sell_score >= 6
            and below_vwap
            and bearish_trend
            and bearish_rsi
            and volume_ok
            and bearish_confirmed
        )

        # 🟢 BUY SIGNAL
        if buy_setup:
            if not is_duplicate_alert(name, "BUY"):
                sl = close - sl_distance
                target = close + target_distance

                if ticker in INDEX_SYMBOLS:
                    message = (
                        "🟢 *INDEX OPTIONS SETUP*\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Index:* `{name}`\n"
                        "📈 *Bias:* BULLISH\n"
                        "🎯 *Option:* BUY CE\n\n"
                        f"📍 *Underlying Price:* `{close:.2f}`\n"
                        f"📊 *VWAP:* `{vwap:.2f}` ✅\n"
                        f"📈 *RSI:* `{rsi:.2f}`\n"
                        f"📈 *EMA9:* `{ema9:.2f}`\n"
                        f"📉 *EMA21:* `{ema21:.2f}`\n"
                        "🔊 *Volume:* Confirmed ✅\n\n"
                        f"🎯 *Underlying Target:* `{target:.2f}`\n"
                        f"🛑 *Underlying SL:* `{sl:.2f}`\n"
                        "⚖️ *RR:* 1:2\n"
                        f"⭐ *Score:* `{buy_score}/7`"
                    )
                else:
                    message = (
                        "🟢 *BUY ALERT*\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{name}`\n"
                        f"💰 *Price:* `{close:.2f}`\n"
                        f"📊 *VWAP:* `{vwap:.2f}` ✅\n"
                        f"📈 *RSI:* `{rsi:.2f}`\n"
                        f"📈 *EMA9:* `{ema9:.2f}`\n"
                        f"📉 *EMA21:* `{ema21:.2f}`\n"
                        "🔊 *Volume:* Confirmed ✅\n\n"
                        f"🎯 *Target:* `{target:.2f}`\n"
                        f"🛑 *SL:* `{sl:.2f}`\n"
                        "⚖️ *RR:* 1:2\n"
                        f"⭐ *Score:* `{buy_score}/7`"
                    )
                send_telegram(message)

        # 🔴 SELL SIGNAL
        elif sell_setup:
            if not is_duplicate_alert(name, "SELL"):
                sl = close + sl_distance
                target = close - target_distance

                if ticker in INDEX_SYMBOLS:
                    message = (
                        "🔴 *INDEX OPTIONS SETUP*\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Index:* `{name}`\n"
                        "📉 *Bias:* BEARISH\n"
                        "🎯 *Option:* BUY PE\n\n"
                        f"📍 *Underlying Price:* `{close:.2f}`\n"
                        f"📊 *VWAP:* `{vwap:.2f}` 🔻\n"
                        f"📉 *RSI:* `{rsi:.2f}`\n"
                        f"📈 *EMA9:* `{ema9:.2f}`\n"
                        f"📉 *EMA21:* `{ema21:.2f}`\n"
                        "🔊 *Volume:* Confirmed ✅\n\n"
                        f"🎯 *Underlying Target:* `{target:.2f}`\n"
                        f"🛑 *Underlying SL:* `{sl:.2f}`\n"
                        "⚖️ *RR:* 1:2\n"
                        f"⭐ *Score:* `{sell_score}/7`"
                    )
                else:
                    message = (
                        "🔴 *SELL ALERT*\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        f"📌 *Asset:* `{name}`\n"
                        f"💰 *Price:* `{close:.2f}`\n"
                        f"📊 *VWAP:* `{vwap:.2f}` 🔻\n"
                        f"📉 *RSI:* `{rsi:.2f}`\n"
                        f"📈 *EMA9:* `{ema9:.2f}`\n"
                        f"📉 *EMA21:* `{ema21:.2f}`\n"
                        "🔊 *Volume:* Confirmed ✅\n\n"
                        f"🎯 *Target:* `{target:.2f}`\n"
                        f"🛑 *SL:* `{sl:.2f}`\n"
                        "⚖️ *RR:* 1:2\n"
                        f"⭐ *Score:* `{sell_score}/7`"
                    )
                send_telegram(message)

    except Exception as e:
        print(f"[ANALYSIS ERROR] {ticker}: {e}")


# ============================================================
# MAIN ENTRY POINT FOR GITHUB ACTIONS
# ============================================================

def main():
    now = datetime.now(IST)
    print("==========================================")
    print(f"Scanner Execution Time: [{now.strftime('%d-%m-%Y %H:%M:%S')} IST]")
    print("==========================================")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    })

    for ticker, name in WATCHLIST.items():
        analyze_asset(ticker, name, session)
        time.sleep(1)

    print("\n[Scan Completed Successfully]")

if __name__ == "__main__":
    main()
