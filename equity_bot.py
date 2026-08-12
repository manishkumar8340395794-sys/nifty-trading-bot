import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import pytz

# Telegram Credentials (Strip whitespace to avoid 404 errors)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Default fallback credentials if needed
if not TELEGRAM_BOT_TOKEN:
    TELEGRAM_BOT_TOKEN = "8303140788:AAGE7DE1bhttDpRVB4GtoErn4kyDqemJ-Ns"
if not TELEGRAM_CHAT_ID:
    TELEGRAM_CHAT_ID = "5660614483"

IST = pytz.timezone('Asia/Kolkata')

# Watchlist for scanning
SYMBOLS = [
    "^NSEI", "^NSEBANK", "^BSESN", "^CNXIT",
    "SBIN.NS", "PNB.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "GAIL.NS", "IOC.NS", "BPCL.NS", "NTPC.NS", "PFC.NS",
    "BHEL.NS", "ASHOKLEY.NS", "TATAMOTORS.NS", "RELIANCE.NS",
    "TCS.NS", "INFY.NS"
]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
    except Exception as e:
        print(f"[Telegram Error]: {e}")

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

def scan_symbol(symbol):
    try:
        df = yf.download(symbol, period="5d", interval="5m", progress=False)
        if df.empty or len(df) < 200:
            return None

        # Flatten MultiIndex columns if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # VWAP
        v = df['Volume']
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (tp * v).cumsum() / v.cumsum()
        
        df['RSI'] = calculate_rsi(df['Close'])
        df['ATR'] = calculate_atr(df)
        df['Vol_MA'] = df['Volume'].rolling(20).mean()

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(latest['Close'])
        ema9 = float(latest['EMA9'])
        ema21 = float(latest['EMA21'])
        ema200 = float(latest['EMA200'])
        vwap = float(latest['VWAP'])
        rsi = float(latest['RSI'])
        atr = float(latest['ATR'])
        vol = float(latest['Volume'])
        vol_ma = float(latest['Vol_MA'])

        # --- HIGH ACCURACY HIGH FILTER CONDITIONS ---
        # 1. Trend Filter: Must be above 200 EMA for BUY, below 200 EMA for SELL
        # 2. RSI Filter: Avoid buying overbought (>65) or selling oversold (<35)
        # 3. Volume Filter: Current volume > 1.2x Volume MA
        
        signal = None
        
        # BUY SIGNAL
        if (close > ema200 and 
            ema9 > ema21 and prev['EMA9'] <= prev['EMA21'] and 
            close > vwap and 
            48 <= rsi <= 65 and 
            vol > 1.2 * vol_ma):
            signal = "BUY"

        # SELL SIGNAL
        elif (close < ema200 and 
              ema9 < ema21 and prev['EMA9'] >= prev['EMA21'] and 
              close < vwap and 
              35 <= rsi <= 52 and 
              vol > 1.2 * vol_ma):
            signal = "SELL"

        if signal:
            # Safer Stoploss using 1.5x ATR
            sl_dist = round(1.5 * atr, 2)
            
            if signal == "BUY":
                entry = close
                sl = round(entry - sl_dist, 2)
                target = round(entry + (1.5 * sl_dist), 2)
                emoji = "🟢 *SAFE BUY ALERT*"
            else:
                entry = close
                sl = round(entry + sl_dist, 2)
                target = round(entry - (1.5 * sl_dist), 2)
                emoji = "🔴 *SAFE SELL ALERT*"

            clean_name = symbol.replace(".NS", "").replace("^", "")
            
            msg = (
                f"{emoji}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📌 *Asset:* `{clean_name}`\n"
                f"💰 *Price:* `{entry:.2f}`\n"
                f"📊 *Trend (200 EMA):* {'ABOVE ✅' if close > ema200 else 'BELOW 🔻'}\n"
                f"📈 *RSI:* `{rsi:.1f}` | *VWAP:* `{vwap:.2f}`\n"
                f"🔊 *Volume Surge:* Confirmed ✅\n\n"
                f"🎯 *Entry:* `{entry:.2f}`\n"
                f"🎯 *Target (1:1.5):* `{target:.2f}`\n"
                f"🛑 *Safe Stop Loss:* `{sl:.2f}`\n\n"
                f"⚠️ *Always trade with proper risk management.*"
            )
            return msg

    except Exception as e:
        print(f"Error scanning {symbol}: {e}")
    
    return None

def main():
    print(f"[{datetime.now(IST)}] Starting Filtered Market Scan...")
    alerts = []
    
    for sym in SYMBOLS:
        print(f"Scanning: {sym}")
        alert = scan_symbol(sym)
        if alert:
            alerts.append(alert)

    if alerts:
        for a in alerts:
            send_telegram(a)
    else:
        print("No high-probability setups found.")

if __name__ == "__main__":
    main()
