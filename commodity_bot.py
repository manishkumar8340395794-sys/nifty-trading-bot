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
# CONFIGURATION
# ============================================================

IST = pytz.timezone("Asia/Kolkata")
ALERT_COOLDOWN_MINUTES = 30
CACHE_FILE = "sent_commodity_alerts.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

if not TELEGRAM_BOT_TOKEN:
    TELEGRAM_BOT_TOKEN = "8303140788:AAHvS4sT5c1_5dOexKxN8Y025k3R8d26q60"

if not TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = "5660614483"

# COMMODITY WATCHLIST (Yahoo Finance Symbols)
COMMODITIES = {
    "GC=F": "GOLD (MCX / COMEX)",
    "SI=F": "SILVER (MCX / COMEX)",
    "CL=F": "CRUDE OIL (MCX / WTI)",
    "NG=F": "NATURAL GAS (MCX)",
    "HG=F": "COPPER",
}

# ============================================================
# UTILITIES & TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TELEGRAM ERROR] Missing Token/Chat ID")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        return res.json().get("ok", False)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        print(f"[CACHE ERROR] {e}")


def is_duplicate(symbol, alert_type):
    key = f"{symbol}_{alert_type}"
    now = time.time()
    cache = load_cache()
    if key in cache and (now - cache[key]) < (ALERT_COOLDOWN_MINUTES * 60):
        return True
    cache[key] = now
    save_cache(cache)
    return False

# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_atr(df, period=14):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def calculate_vwap(df):
    data = df.copy()
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    data.index = data.index.tz_convert(IST)

    tp = (data["High"] + data["Low"] + data["Close"]) / 3
    vol = data["Volume"].fillna(0)
    cum_pv = (tp * vol).groupby(data.index.date).cumsum()
    cum_vol = vol.groupby(data.index.date).cumsum()
    return cum_pv / (cum_vol + 1e-9)


def calculate_supertrend(df, period=10, multiplier=3.0):
    atr = calculate_atr(df, period)
    hl2 = (df["High"] + df["Low"]) / 2

    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    upper_band = pd.Series(index=df.index, dtype=float)
    lower_band = pd.Series(index=df.index, dtype=float)
    trend = pd.Series(index=df.index, dtype=int)

    for i in range(len(df)):
        if i == 0:
            upper_band.iloc[i] = basic_upper.iloc[i]
            lower_band.iloc[i] = basic_lower.iloc[i]
            trend.iloc[i] = 1
            continue

        prev_close = df["Close"].iloc[i - 1]

        # Upper Band Calculation
        if (basic_upper.iloc[i] < upper_band.iloc[i - 1]) or (
            prev_close > upper_band.iloc[i - 1]
        ):
            upper_band.iloc[i] = basic_upper.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i - 1]

        # Lower Band Calculation
        if (basic_lower.iloc[i] > lower_band.iloc[i - 1]) or (
            prev_close < lower_band.iloc[i - 1]
        ):
            lower_band.iloc[i] = basic_lower.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i - 1]

        # Trend Determination
        if trend.iloc[i - 1] == 1:
            if df["Close"].iloc[i] < lower_band.iloc[i - 1]:
                trend.iloc[i] = -1
            else:
                trend.iloc[i] = 1
        else:
            if df["Close"].iloc[i] > upper_band.iloc[i - 1]:
                trend.iloc[i] = 1
            else:
                trend.iloc[i] = -1

    return trend, upper_band, lower_band

# ============================================================
# COMMODITY STRATEGY ENGINE
# ============================================================

def analyze_commodity(ticker, name, session):
    try:
        print(f"[SCAN COMMODITY] {name} ({ticker})...")
        obj = yf.Ticker(ticker, session=session)
        df = obj.history(period="5d", interval="15m", auto_adjust=False)

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        req = ["Open", "High", "Low", "Close", "Volume"]
        if df.empty or not all(c in df.columns for c in req) or len(df) < 50:
            print(f" └─ {name}: Insufficient data.")
            return

        df["VWAP"] = calculate_vwap(df)
        df["RSI"] = calculate_rsi(df["Close"])
        df["ATR"] = calculate_atr(df)
        df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
        df["Trend"], df["ST_Upper"], df["ST_Lower"] = calculate_supertrend(
            df, period=10, multiplier=3.0
        )

        latest = df.iloc[-2]  # Confirmed bar
        close = float(latest["Close"])
        vwap = float(latest["VWAP"])
        rsi = float(latest["RSI"])
        atr = float(latest["ATR"])
        ema50 = float(latest["EMA50"])
        st_trend = int(latest["Trend"])

        # Rules Matrix
        bullish = (
            st_trend == 1
            and close > vwap
            and close > ema50
            and 52 <= rsi <= 70
        )

        bearish = (
            st_trend == -1
            and close < vwap
            and close < ema50
            and 30 <= rsi <= 48
        )

        sl_distance = max(atr * 1.5, close * 0.005)
        tp_distance = sl_distance * 2.0  # 1:2 Risk-to-Reward

        if bullish and not is_duplicate(name, "BUY"):
            sl = close - sl_distance
            tp = close + tp_distance
            msg = (
                "🟡 *COMMODITY BUY SIGNAL*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🛢️ *Asset:* `{name}`\n"
                f"💰 *Entry:* `{close:.2f}`\n"
                f"📊 *VWAP:* `{vwap:.2f}` (Above) ✅\n"
                f"📈 *RSI:* `{rsi:.2f}`\n"
                f"⚡ *Supertrend:* BULLISH ✅\n\n"
                f"🎯 *Target (1:2):* `{tp:.2f}`\n"
                f"🛑 *Stop Loss:* `{sl:.2f}`"
            )
            send_telegram(msg)

        elif bearish and not is_duplicate(name, "SELL"):
            sl = close + sl_distance
            tp = close - tp_distance
            msg = (
                "🔴 *COMMODITY SELL SIGNAL*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🛢️ *Asset:* `{name}`\n"
                f"💰 *Entry:* `{close:.2f}`\n"
                f"📊 *VWAP:* `{vwap:.2f}` (Below) 🔻\n"
                f"📉 *RSI:* `{rsi:.2f}`\n"
                f"⚡ *Supertrend:* BEARISH 🔻\n\n"
                f"🎯 *Target (1:2):* `{tp:.2f}`\n"
                f"🛑 *Stop Loss:* `{sl:.2f}`"
            )
            send_telegram(msg)

    except Exception as e:
        print(f"[ERROR] {ticker}: {e}")


def main():
    now = datetime.now(IST)
    print(f"--- Commodity Scan Start [{now.strftime('%Y-%m-%d %H:%M:%S')}] ---")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    )

    for ticker, name in COMMODITIES.items():
        analyze_commodity(ticker, name, session)
        time.sleep(1)


if __name__ == "__main__":
    main()
