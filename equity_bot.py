import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf

# ============================================================
# 1. TELEGRAM SETTINGS (Environment Variables / Secrets)
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

IST = pytz.timezone("Asia/Kolkata")


# ============================================================
# 2. TELEGRAM FUNCTION
# ============================================================


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] ERROR: Token or Chat ID missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()

        if result.get("ok"):
            print("[Telegram] Message sent successfully.")
            return True
        return False
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False


# ============================================================
# 3. WATCHLIST (NSE INDICES + STOCKS + COMMODITIES)
# ============================================================

WATCHLIST = {
    # Indices
    "^NSEI": "NIFTY 50",
    "^NSEBANK": "BANK NIFTY",
    "^BSESN": "SENSEX",
    "^CNXIT": "NIFTY IT",
    # Top NSE Stocks
    "SBIN.NS": "SBI",
    "PNB.NS": "PNB",
    "HDFCBANK.NS": "HDFC BANK",
    "ICICIBANK.NS": "ICICI BANK",
    "GAIL.NS": "GAIL",
    "IOC.NS": "IOC",
    "BPCL.NS": "BPCL",
    "NTPC.NS": "NTPC",
    "PFC.NS": "PFC",
    "BHEL.NS": "BHEL",
    "ASHOKLEY.NS": "ASHOK LEYLAND",
    "TATAMOTORS.NS": "TATA MOTORS",
    "RELIANCE.NS": "RELIANCE",
    "TCS.NS": "TCS",
    "INFY.NS": "INFOSYS",
    # Commodities
    "GC=F": "GOLD",
    "SI=F": "SILVER",
    "CL=F": "CRUDE OIL",
    "NG=F": "NATURAL GAS",
}


# ============================================================
# 4. TECHNICAL INDICATORS
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
# 5. MARKET SCANNER ENGINE
# ============================================================


def scan_markets():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        )
    })

    signals_found = 0

    for ticker, display_name in WATCHLIST.items():
        try:
            print(f"Scanning: {display_name}")
            ticker_obj = yf.Ticker(ticker, session=session)

            # Strict 5-second timeout to prevent lag on symbols like TATAMOTORS
            df = ticker_obj.history(
                period="5d",
                interval="5m",
                auto_adjust=False,
                prepost=False,
                timeout=5,
            )

            if df.empty:
                print(f"No data found for {display_name}, skipping.")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            if len(df) < 50:
                continue

            if "Volume" not in df.columns or df["Volume"].sum() == 0:
                df["Volume"] = 1000

            # Technical Calculations
            df["VWAP"] = calculate_vwap(df)
            df["RSI"] = calculate_rsi(df["Close"])
            df["EMA_9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["EMA_21"] = df["Close"].ewm(span=21, adjust=False).mean()
            df["ATR"] = calculate_atr(df)
            df["Volume_MA"] = df["Volume"].rolling(20).mean().fillna(100)

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

            # Strategy & Logic Verification
            bullish_cross = prev_ema9 <= prev_ema21 and ema9 > ema21
            bearish_cross = prev_ema9 >= prev_ema21 and ema9 < ema21
            above_vwap = close > vwap
            below_vwap = close < vwap

            # Strict RSI Rules
            bullish_rsi = 54 <= rsi <= 68
            bearish_rsi = 32 <= rsi <= 46

            # Volume & Candle Confirmation
            volume_confirmed = volume >= volume_ma * 1.20
            bullish_confirmed = bullish_candle(latest)
            bearish_confirmed = bearish_candle(latest)

            # Trend Confirmation
            bullish_trend = ema9 > ema21 and close > ema9
            bearish_trend = ema9 < ema21 and close < ema9

            # Score Calculations (Out of 7)
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

            # Risk Management
            sl_points = max(atr * 1.20, close * 0.004)
            target_points = sl_points * 2

            # Signal Filtering Logic (Strict 6/7 Filter)
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
                sl = close - sl_points
                target = close + target_points
                risk = close - sl
                reward = target - close

                message = (
                    "🟢 *STRONG BUY ALERT*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 *Asset:* `{display_name}`\n"
                    f"💰 *Price:* `{close:.2f}`\n"
                    f"📊 *VWAP:* `{vwap:.2f}` (Above ✅)\n"
                    f"📈 *RSI:* `{rsi:.2f}`\n"
                    f"📈 *EMA 9:* `{ema9:.2f}` | *EMA 21:* `{ema21:.2f}`\n"
                    f"🔊 *Volume:* Confirmed ✅\n"
                    f"🕯️ *Candle:* Bullish ✅\n\n"
                    f"🎯 *Entry:* `{close:.2f}`\n"
                    f"🎯 *Target:* `{target:.2f}` (+{reward:.2f})\n"
                    f"🛑 *Stop Loss:* `{sl:.2f}` (-{risk:.2f})\n"
                    f"⚖️ *Risk/Reward:* 1:2\n"
                    f"⭐ *Score:* `{buy_score}/7`\n\n"
                    "⚠️ *Verify market conditions before trading.*"
                )
                send_telegram(message)
                signals_found += 1

            elif strong_sell:
                sl = close + sl_points
                target = close - target_points
                risk = sl - close
                reward = close - target

                message = (
                    "🔴 *STRONG SELL ALERT*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"📌 *Asset:* `{display_name}`\n"
                    f"💰 *Price:* `{close:.2f}`\n"
                    f"📊 *VWAP:* `{vwap:.2f}` (Below 🔻)\n"
                    f"📉 *RSI:* `{rsi:.2f}`\n"
                    f"📈 *EMA 9:* `{ema9:.2f}` | *EMA 21:* `{ema21:.2f}`\n"
                    f"🔊 *Volume:* Confirmed ✅\n"
                    f"🕯️ *Candle:* Bearish ✅\n\n"
                    f"🎯 *Entry:* `{close:.2f}`\n"
                    f"🎯 *Target:* `{target:.2f}` (-{reward:.2f})\n"
                    f"🛑 *Stop Loss:* `{sl:.2f}` (+{risk:.2f})\n"
                    f"⚖️ *Risk/Reward:* 1:2\n"
                    f"⭐ *Score:* `{sell_score}/7`\n\n"
                    "⚠️ *Verify market conditions before trading.*"
                )
                send_telegram(message)
                signals_found += 1

        except Exception as e:
            print(f"[Error scanning {display_name}]: {e}")

    if signals_found == 0:
        print("Scan finished. No 6/7 score setup detected right now.")
        send_telegram(
            "✅ *NSE Equity Scanner Execution Complete*\nNo high-probability"
            " setups (6/7 score) detected at this moment."
        )


# ============================================================
# 6. MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    now_ist = datetime.now(IST)
    print(
        f"[{now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST] Starting Market Scan..."
    )
    scan_markets()
    print("Scan completed successfully.")
