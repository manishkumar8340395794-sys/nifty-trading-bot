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

def get_fno_expiries():
    """NSE Expiry Format"""
    today = date.today()
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

    stock_exp_angel = last_thursday.strftime("%d%b%y").upper() 
    return stock_exp_angel

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
    stock_exp_angel = get_fno_expiries()

    stocks = {
        # --- INDICES ---
        "NIFTY": {"ticker": "^NSEI", "step": 50, "approx_premium_pct": 0.008},
        "BANKNIFTY": {"ticker": "^NSEBANK", "step": 100, "approx_premium_pct": 0.008},

        # --- IT SECTOR ---
        "TCS": {"ticker": "TCS.NS", "step": 50, "approx_premium_pct": 0.015},
        "INFY": {"ticker": "INFY.NS", "step": 20, "approx_premium_pct": 0.015},
        "WIPRO": {"ticker": "WIPRO.NS", "step": 5, "approx_premium_pct": 0.02},
        "HCLTECH": {"ticker": "HCLTECH.NS", "step": 20, "approx_premium_pct": 0.015},

        # --- BANKING ---
        "HDFCBANK": {"ticker": "HDFCBANK.NS", "step": 20, "approx_premium_pct": 0.015},
        "ICICIBANK": {"ticker": "ICICIBANK.NS", "step": 10, "approx_premium_pct": 0.015},
        "SBIN": {"ticker": "SBIN.NS", "step": 10, "is_fno": True, "approx_premium_pct": 0.018},
        "AXISBANK": {"ticker": "AXISBANK.NS", "step": 10, "approx_premium_pct": 0.015},

        # --- CHEMICAL & AUTO ---
        "SRF": {"ticker": "SRF.NS", "step": 50, "approx_premium_pct": 0.02},
        "AARTIIND": {"ticker": "AARTIIND.NS", "step": 10, "approx_premium_pct": 0.02},
        "DEEPAKNTR": {"ticker": "DEEPAKNTR.NS", "step": 20, "approx_premium_pct": 0.02},
        "MARUTI": {"ticker": "MARUTI.NS", "step": 100, "approx_premium_pct": 0.013},
        "M&M": {"ticker": "M&M.NS", "step": 20, "approx_premium_pct": 0.015},
        "TATAMOTORS": {"ticker": "TATAMOTORS.NS", "step": 10, "approx_premium_pct": 0.02},

        # --- OTHERS ---
        "RELIANCE": {"ticker": "RELIANCE.NS", "step": 20, "approx_premium_pct": 0.015},
        "TATASTEEL": {"ticker": "TATASTEEL.NS", "step": 2, "approx_premium_pct": 0.02}
    }

    print("Scanning Equity & F&O Market...")

    for name, config in stocks.items():
        try:
            ticker = config["ticker"]

            # 1. Daily Trend
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

            # Cash/Equity Targets & SL
            intra_target = close_15m * (1.01 if signal == "BUY" else 0.99)
            intra_sl = close_15m * (0.995 if signal == "BUY" else 1.005)

            # Option Calculations (CE for BUY, PE for SELL)
            strike = int(round(close_15m / config["step"]) * config["step"])
            option_type = "CE" if signal == "BUY" else "PE"
            easy_search = f"{name} {strike} {option_type}"

            # Estimated Premium Calculation (ATM Price Estimation)
            est_premium = close_15m * config.get("approx_premium_pct", 0.015)
            opt_buy_range = f"₹{est_premium * 0.95:.1f} - ₹{est_premium * 1.05:.1f}"
            opt_target = est_premium * 1.30  # +30% Target
            opt_sl = est_premium * 0.85      # -15% Stop Loss

            msg = f"""
{emoji} <b>NSE EQUITY / F&O {signal} SIGNAL</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Stock/Index:</b> {name}
📊 <b>Daily Trend:</b> {macro_trend}
⏱️ <b>Trigger:</b> 15-Min VWAP Aligned
💰 <b>Current Spot Price:</b> ₹{close_15m:.2f}
━━━━━━━━━━━━━━━━━━
🎯 <b>INTRADAY CASH CALL:</b>
• <b>Action:</b> {signal}
• <b>Target:</b> ₹{intra_target:.2f}
• <b>Stop Loss:</b> ₹{intra_sl:.2f}

🔥 <b>F&O OPTION TRADE ({option_type}):</b>
• <b>Search Broker:</b> <code>{easy_search}</code>
• <b>Est. Entry Price:</b> Buy around {opt_buy_range}
• <b>Option Target (+30%):</b> ₹{opt_target:.2f}
• <b>Option Stop Loss (-15%):</b> ₹{opt_sl:.2f}
━━━━━━━━━━━━━━━━━━
🛡️ <i>Option Targets rely on Option Premium movements. Risk management is key.</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

    print("✅ F&O Signal Bot Ran Successfully!")

if __name__ == "__main__":
    run_equity_fno_bot()
