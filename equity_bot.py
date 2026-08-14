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
                # अगर इस महीने की एक्सपायरी बीत गई है तो अगले महीने की एक्सपायरी
                if month == 12:
                    month = 1
                    year += 1
                else:
                    month += 1
                return get_current_expiry()
            
            angel_fmt = d.strftime("%d-%b-%Y").upper() # Ex: 27-AUG-2026
            fivep_fmt = d.strftime("%d %b %Y").upper() # Ex: 27 AUG 2026
            return angel_fmt, fivep_fmt

def run_equity_fno_bot():
    angel_exp, fivep_exp = get_current_expiry()

    # Nifty 50, Bank Nifty & Major Sectoral Stocks List
    stocks = {
        # --- INDICES ---
        "NIFTY": {"ticker": "^NSEI", "step": 50, "is_fno": True, "type": "INDEX"},
        "BANKNIFTY": {"ticker": "^NSEBANK", "step": 100, "is_fno": True, "type": "INDEX"},

        # --- IT SECTOR ---
        "TCS": {"ticker": "TCS.NS", "step": 50, "is_fno": True, "type": "EQUITY"},
        "INFY": {"ticker": "INFY.NS", "step": 20, "is_fno": True, "type": "EQUITY"},
        "WIPRO": {"ticker": "WIPRO.NS", "step": 10, "is_fno": True, "type": "EQUITY"},
        "HCLTECH": {"ticker": "HCLTECH.NS", "step": 20, "is_fno": True, "type": "EQUITY"},
        "TECHM": {"ticker": "TECHM.NS", "step": 20, "is_fno": True, "type": "EQUITY"},

        # --- BANKING & FINANCE ---
        "HDFCBANK": {"ticker": "HDFCBANK.NS", "step": 20, "is_fno": True, "type": "EQUITY"},
        "ICICIBANK": {"ticker": "ICICIBANK.NS", "step": 20, "is_fno": True, "type": "EQUITY"},
        "SBIN": {"ticker": "SBIN.NS", "step": 10, "is_fno": True, "type": "EQUITY"},
        "KOTAKBANK": {"ticker": "KOTAKBANK.NS", "step": 20, "is_fno": True, "type": "EQUITY"},
        "AXISBANK": {"ticker": "AXISBANK.NS", "step": 20, "is_fno": True, "type": "EQUITY"},

        # --- CHEMICAL SECTOR ---
        "SRF": {"ticker": "SRF.NS", "step": 50, "is_fno": True, "type": "EQUITY"},
        "AARTIIND": {"ticker": "AARTIIND.NS", "step": 10, "is_fno": True, "type": "EQUITY"},
        "ATUL": {"ticker": "ATUL.NS", "step": 100, "is_fno": True, "type": "EQUITY"},
        "DEEPAKNTR": {"ticker": "DEEPAKNTR.NS", "step": 20, "is_fno": True, "type": "EQUITY"},
        "UPL": {"ticker": "UPL.NS", "step": 10, "is_fno": True, "type": "EQUITY"},

        # --- AUTO SECTOR ---
        "TATAMOTORS": {"ticker": "TATAMOTORS.NS", "step": 10, "is_fno": True, "type": "EQUITY"},
        "MARUTI": {"ticker": "MARUTI.NS", "step": 100, "is_fno": True, "type": "EQUITY"},
        "M&M": {"ticker": "M&M.NS", "step": 20, "is_fno": True, "type": "EQUITY"},

        # --- PHARMA & METALS ---
        "SUNPHARMA": {"ticker": "SUNPHARMA.NS", "step": 20, "is_fno": True, "type": "EQUITY"},
        "TATASTEEL": {"ticker": "TATASTEEL.NS", "step": 2.5, "is_fno": True, "type": "EQUITY"},
        "RELIANCE": {"ticker": "RELIANCE.NS", "step": 20, "is_fno": True, "type": "EQUITY"}
    }

    for name, config in stocks.items():
        try:
            ticker = config["ticker"]

            # 1. Daily Trend Analysis
            df_daily = yf.download(ticker, period="30d", interval="1d", progress=False)
            if df_daily.empty:
                continue

            daily_close = float(df_daily['Close'].iloc[-1].item() if hasattr(df_daily['Close'].iloc[-1], 'item') else df_daily['Close'].iloc[-1])
            daily_sma20 = float(df_daily['Close'].rolling(20).mean().iloc[-1].item() if hasattr(df_daily['Close'].rolling(20).mean().iloc[-1], 'item') else df_daily['Close'].rolling(20).mean().iloc[-1])
            macro_trend = "BULLISH" if daily_close > daily_sma20 else "BEARISH"

            # 2. 15-Min VWAP Trigger
            df_15m = yf.download(ticker, period="5d", interval="15m", progress=False)
            if df_15m.empty:
                continue

            close_15m = float(df_15m['Close'].iloc[-1].item() if hasattr(df_15m['Close'].iloc[-1], 'item') else df_15m['Close'].iloc[-1])
            vol = df_15m['Volume']
            high = df_15m['High']
            low = df_15m['Low']
            close = df_15m['Close']

            # Check for non-zero volume (Indices like Nifty don't have direct volume in yfinance)
            if vol.sum() > 0:
                vwap = float(((vol * (high + low + close) / 3).sum() / vol.sum()).item() if hasattr(((vol * (high + low + close) / 3).sum() / vol.sum()), 'item') else ((vol * (high + low + close) / 3).sum() / vol.sum()))
            else:
                vwap = float(df_15m['Close'].rolling(10).mean().iloc[-1].item() if hasattr(df_15m['Close'].rolling(10).mean().iloc[-1], 'item') else df_15m['Close'].rolling(10).mean().iloc[-1])

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

if __name__ == "__main__":
    run_equity_fno_bot()
