import os
import requests
import yfinance as yf
from datetime import datetime, date, timedelta
import calendar

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

def get_fno_expiries():
    """NSE/Angel One/5Paisa के लिए एकदम सही एक्सपायरी फॉर्मेट निकालता है"""
    today = date.today()
    
    # Stock Monthly Expiry (Month's Last Thursday)
    year, month = today.year, today.month
    last_day = calendar.monthrange(year, month)[1]
    last_thursday = None
    for day in range(last_day, 0, -1):
        d = date(year, month, day)
        if d.weekday() == 3: # Thursday
            last_thursday = d
            break
            
    if last_thursday < today:
        month = 1 if month == 12 else month + 1
        year = year + 1 if month == 1 else year
        last_day = calendar.monthrange(year, month)[1]
        for day in range(last_day, 0, -1):
            d = date(year, month, day)
            if d.weekday() == 3:
                last_thursday = d
                break

    # Angel One Format: "27AUG26" or "27 AUG"
    stock_exp_angel = last_thursday.strftime("%d%b%y").upper() 
    stock_exp_simple = last_thursday.strftime("%d %b").upper()
    
    return stock_exp_angel, stock_exp_simple

def safe_extract_val(val):
    try:
        if hasattr(val, 'iloc'):
            val = val.iloc[-1]
        if hasattr(val, 'item'):
            val = val.item()
        return float(val)
    except Exception:
        return None

def run_equity_fno_bot():
    stock_exp_angel, stock_exp_simple = get_fno_expiries()

    # Broad Stocks & Indices Config
    stocks = {
        # --- INDICES ---
        "NIFTY": {"ticker": "^NSEI", "step": 50},
        "BANKNIFTY": {"ticker": "^NSEBANK", "step": 100},

        # --- IT SECTOR ---
        "TCS": {"ticker": "TCS.NS", "step": 50},
        "INFY": {"ticker": "INFY.NS", "step": 20},
        "WIPRO": {"ticker": "WIPRO.NS", "step": 5},
        "HCLTECH": {"ticker": "HCLTECH.NS", "step": 20},

        # --- BANKING ---
        "HDFCBANK": {"ticker": "HDFCBANK.NS", "step": 20},
        "ICICIBANK": {"ticker": "ICICIBANK.NS", "step": 10},
        "SBIN": {"ticker": "SBIN.NS", "step": 10},
        "AXISBANK": {"ticker": "AXISBANK.NS", "step": 10},

        # --- CHEMICAL & AUTO ---
        "SRF": {"ticker": "SRF.NS", "step": 50},
        "AARTIIND": {"ticker": "AARTIIND.NS", "step": 10},
        "DEEPAKNTR": {"ticker": "DEEPAKNTR.NS", "step": 20},
        "MARUTI": {"ticker": "MARUTI.NS", "step": 100},
        "M&M": {"ticker": "M&M.NS", "step": 20},
        "TATAMOTORS": {"ticker": "TATAMOTORS.NS", "step": 10},

        # --- OTHERS ---
        "RELIANCE": {"ticker": "RELIANCE.NS", "step": 20},
        "TATASTEEL": {"ticker": "TATASTEEL.NS", "step": 2}
    }

    print("Scanning Equity & F&O Market...")

    for name, config in stocks.items():
        try:
            ticker = config["ticker"]

            # 1. Daily Trend (Unadjusted price for accurate Spot level)
            df_daily = yf.download(ticker, period="40d", interval="1d", auto_adjust=False, progress=False)
            if df_daily.empty or len(df_daily) < 20:
                continue

            close_series = df_daily['Close']
            daily_close = safe_extract_val(close_series.iloc[-1])
            daily_sma20 = safe_extract_val(close_series.rolling(20).mean().iloc[-1])

            if daily_close is None or daily_sma20 is None:
                continue

            macro_trend = "BULLISH" if daily_close > daily_sma20 else "BEARISH"

            # 2. 15-Min VWAP Trigger
            df_15m = yf.download(ticker, period="5d", interval="15m", auto_adjust=False, progress=False)
            if df_15m.empty:
                continue

            close_15m = safe_extract_val(df_15m['Close'].iloc[-1])
            if close_15m is None:
                continue

            vol = df_15m['Volume']
            high = df_15m['High']
            low = df_15m['Low']
            close = df_15m['Close']

            tot_vol = safe_extract_val(vol.sum())
            if tot_vol and tot_vol > 0:
                vwap_val = ((vol * (high + low + close) / 3).sum()) / vol.sum()
                vwap = safe_extract_val(vwap_val)
            else:
                vwap = safe_extract_val(df_15m['Close'].rolling(10).mean().iloc[-1])

            if vwap is None:
                continue

            # Signal Generation
            signal = None
            if macro_trend == "BULLISH" and close_15m > vwap:
                signal = "BUY"
            elif macro_trend == "BEARISH" and close_15m < vwap:
                signal = "SELL"

            if not signal:
                continue

            emoji = "🟢" if signal == "BUY" else "🔴"

            # Targets & Stop Loss
            intra_target = close_15m * (1.01 if signal == "BUY" else 0.99)
            intra_sl = close_15m * (0.995 if signal == "BUY" else 1.005)
            swing_target = close_15m * (1.04 if signal == "BUY" else 0.96)
            swing_sl = close_15m * (0.98 if signal == "BUY" else 1.02)

            # Rounding to Strike Price
            strike = int(round(close_15m / config["step"]) * config["step"])
            option_type = "CE" if signal == "BUY" else "PE"

            # Perfect Search Strings for Brokers
            angel_search = f"{name} {stock_exp_angel} {strike} {option_type}" # Ex: HDFCBANK 27AUG26 1700 PE
            easy_search = f"{name} {strike} {option_type}"                  # Ex: HDFCBANK 1700 PE (Angel/5Paisa Direct)

            msg = f"""
{emoji} <b>NSE EQUITY / F&O {signal} SIGNAL</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Stock/Index:</b> {name}
📊 <b>Daily Trend:</b> {macro_trend}
⏱️ <b>Trigger:</b> 15-Min VWAP Aligned
💰 <b>Current Spot Price:</b> ₹{close_15m:.2f}
━━━━━━━━━━━━━━━━━━
🎯 <b>INTRADAY CALL (Cash):</b>
• <b>Action:</b> {signal}
• <b>Target:</b> ₹{intra_target:.2f}
• <b>Stop Loss:</b> ₹{intra_sl:.2f}

📈 <b>SWING CALL (Short Term):</b>
• <b>Action:</b> {signal}
• <b>Target:</b> ₹{swing_target:.2f}
• <b>Stop Loss:</b> ₹{swing_sl:.2f}
━━━━━━━━━━━━━━━━━━
🔍 <b>HOW TO SEARCH IN ANGEL ONE / 5PAISA:</b>
• <b>Direct Search:</b> <code>{easy_search}</code>
• <b>Full Contract Name:</b> <code>{angel_search}</code>
━━━━━━━━━━━━━━━━━━
🛡️ <i>Execute after market confirmation. Paper trade first.</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

    print("✅ Equity Scanning Completed Successfully!")

if __name__ == "__main__":
    run_equity_fno_bot()
