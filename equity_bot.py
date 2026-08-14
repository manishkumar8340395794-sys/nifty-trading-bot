import os
import requests
import yfinance as yf
from datetime import datetime, date
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

def get_current_expiry():
    """महीने के आखिरी गुरुवार (Expiry) की तारीख निकालता है"""
    today = date.today()
    year = today.year
    month = today.month
    
    # महीने का आखिरी दिन
    last_day = calendar.monthrange(year, month)[1]
    
    # आखिरी गुरुवार ढूंढना
    for day in range(last_day, 0, -1):
        d = date(year, month, day)
        if d.weekday() == 3: # 3 = Thursday
            if d < today:
                if month == 12:
                    month = 1
                    year += 1
                else:
                    month += 1
                return get_current_expiry()
            
            angel_fmt = d.strftime("%d-%b-%Y").upper() # Ex: 27-AUG-2026
            fivep_fmt = d.strftime("%d %b %Y").upper() # Ex: 27 AUG 2026
            return angel_fmt, fivep_fmt

def safe_extract_val(val):
    """Pandas Series / Float conversion issue fix"""
    try:
        if hasattr(val, 'iloc'):
            val = val.iloc[-1]
        if hasattr(val, 'item'):
            val = val.item()
        return float(val)
    except Exception:
        return None

def run_equity_fno_bot():
    expiry_dates = get_current_expiry()
    if not expiry_dates:
        angel_exp, fivep_exp = "EXPIRY", "EXPIRY"
    else:
        angel_exp, fivep_exp = expiry_dates

    # Nifty 50, Bank Nifty & Major Sectoral Stocks List
    stocks = {
        # --- INDICES ---
        "NIFTY": {"ticker": "^NSEI", "step": 50, "is_fno": True},
        "BANKNIFTY": {"ticker": "^NSEBANK", "step": 100, "is_fno": True},

        # --- IT SECTOR ---
        "TCS": {"ticker": "TCS.NS", "step": 50, "is_fno": True},
        "INFY": {"ticker": "INFY.NS", "step": 20, "is_fno": True},
        "WIPRO": {"ticker": "WIPRO.NS", "step": 10, "is_fno": True},
        "HCLTECH": {"ticker": "HCLTECH.NS", "step": 20, "is_fno": True},
        "TECHM": {"ticker": "TECHM.NS", "step": 20, "is_fno": True},

        # --- BANKING & FINANCE ---
        "HDFCBANK": {"ticker": "HDFCBANK.NS", "step": 20, "is_fno": True},
        "ICICIBANK": {"ticker": "ICICIBANK.NS", "step": 20, "is_fno": True},
        "SBIN": {"ticker": "SBIN.NS", "step": 10, "is_fno": True},
        "KOTAKBANK": {"ticker": "KOTAKBANK.NS", "step": 20, "is_fno": True},
        "AXISBANK": {"ticker": "AXISBANK.NS", "step": 20, "is_fno": True},

        # --- CHEMICAL SECTOR ---
        "SRF": {"ticker": "SRF.NS", "step": 50, "is_fno": True},
        "AARTIIND": {"ticker": "AARTIIND.NS", "step": 10, "is_fno": True},
        "ATUL": {"ticker": "ATUL.NS", "step": 100, "is_fno": True},
        "DEEPAKNTR": {"ticker": "DEEPAKNTR.NS", "step": 20, "is_fno": True},
        "UPL": {"ticker": "UPL.NS", "step": 10, "is_fno": True},

        # --- AUTO SECTOR ---
        "MARUTI": {"ticker": "MARUTI.NS", "step": 100, "is_fno": True},
        "M&M": {"ticker": "M&M.NS", "step": 20, "is_fno": True},
        "TATAMOTORS": {"ticker": "TATAMOTORS.NS", "step": 10, "is_fno": True},

        # --- PHARMA & METALS ---
        "SUNPHARMA": {"ticker": "SUNPHARMA.NS", "step": 20, "is_fno": True},
        "TATASTEEL": {"ticker": "TATASTEEL.NS", "step": 2.5, "is_fno": True},
        "RELIANCE": {"ticker": "RELIANCE.NS", "step": 20, "is_fno": True}
    }

    print("Scanning Market with Multi-Timeframe Analysis...")

    for name, config in stocks.items():
        try:
            ticker = config["ticker"]

            # 1. Daily Trend Analysis
            df_daily = yf.download(ticker, period="30d", interval="1d", progress=False)
            if df_daily.empty or len(df_daily) < 20:
                continue

            close_series = df_daily['Close']
            daily_close = safe_extract_val(close_series.iloc[-1])
            daily_sma20 = safe_extract_val(close_series.rolling(20).mean().iloc[-1])

            if daily_close is None or daily_sma20 is None:
                continue

            macro_trend = "BULLISH" if daily_close > daily_sma20 else "BEARISH"

            # 2. 15-Min VWAP Trigger
            df_15m = yf.download(ticker, period="5d", interval="15m", progress=False)
            if df_15m.empty:
                continue

            close_15m = safe_extract_val(df_15m['Close'].iloc[-1])
            if close_15m is None:
                continue

            vol = df_15m['Volume']
            high = df_15m['High']
            low = df_15m['Low']
            close = df_15m['Close']

            # VWAP Calculation Safely
            tot_vol = safe_extract_val(vol.sum())
            if tot_vol and tot_vol > 0:
                vwap_val = ((vol * (high + low + close) / 3).sum()) / vol.sum()
                vwap = safe_extract_val(vwap_val)
            else:
                vwap = safe_extract_val(df_15m['Close'].rolling(10).mean().iloc[-1])

            if vwap is None:
                continue

            # Signal Logic
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
            swing_target = close_15m * (1.05 if signal == "BUY" else 0.95)
            swing_sl = close_15m * (0.97 if signal == "BUY" else 1.03)

            strike = int(round(close_15m / config["step"]) * config["step"])
            option_type = "CE" if signal == "BUY" else "PE"

            search_angel_opt = f"{name} {angel_exp} {strike} {option_type}"
            search_5p_opt = f"{name} {fivep_exp} {strike} {option_type}"
            search_angel_fut = f"{name} {angel_exp} FUT"

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
📱 <b>F&O SEARCH DETAILS (Angel One):</b>
• <b>Option:</b> <code>{search_angel_opt}</code>
• <b>Future:</b> <code>{search_angel_fut}</code>

📱 <b>F&O SEARCH DETAILS (5Paisa):</b>
• <b>Option:</b> <code>{search_5p_opt}</code>
━━━━━━━━━━━━━━━━━━
🛡️ <i>Execute after market confirmation. Paper trade first.</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

    print("✅ Scanning Completed!")

if __name__ == "__main__":
    run_equity_fno_bot()
