import os
import requests
import yfinance as yf
from datetime import datetime, date
import calendar
import time
import logging

logging.getLogger('yfinance').setLevel(logging.CRITICAL)

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

# सक्रिय ट्रेड्स को स्टोर करने के लिए (Active Positions Storage)
active_positions = {}

def get_fno_month():
    today = date.today()
    return today.strftime("%b").upper()

def safe_extract_val(val):
    try:
        if hasattr(val, 'iloc'):
            val = val.iloc[-1]
        if hasattr(val, 'item'):
            val = val.item()
        return float(val)
    except Exception:
        return None

def fetch_live_price(ticker):
    """हर कुछ सेकंड में लाइव प्राइस लाने का फ़ंक्शन"""
    try:
        df = yf.Ticker(ticker).history(period="1d", interval="1m", auto_adjust=False)
        if not df.empty:
            return safe_extract_val(df['Close'].iloc[-1])
    except Exception:
        pass
    return None

def track_live_positions():
    """सक्रिय ट्रेड्स की हर 10 सेकंड में चेकिंग"""
    global active_positions
    if not active_positions:
        return

    print("🔍 Tracking active positions live...")
    for symbol, trade in list(active_positions.items()):
        current_price = fetch_live_price(trade["ticker"])
        if current_price is None:
            continue

        # Target Check
        if (trade["signal"] == "BUY" and current_price >= trade["target"]) or \
           (trade["signal"] == "SELL" and current_price <= trade["target"]):
            
            msg = f"""
🎯 <b>TARGET ACHIEVED ALERT!</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Stock:</b> {symbol}
📊 <b>Type:</b> {trade['signal']}
💰 <b>Entry Price:</b> ₹{trade['entry']:.2f}
🚀 <b>Current Price:</b> ₹{current_price:.2f}
🎯 <b>Target Price:</b> ₹{trade['target']:.2f}
✅ <i>Profit booked successfully!</i>
"""
            send_telegram_message(msg)
            del active_positions[symbol]  # ट्रेड क्लोज कर दें

        # Stop Loss Check
        elif (trade["signal"] == "BUY" and current_price <= trade["sl"]) or \
             (trade["signal"] == "SELL" and current_price >= trade["sl"]):
            
            msg = f"""
🚨 <b>STOP LOSS HIT ALERT!</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Stock:</b> {symbol}
📊 <b>Type:</b> {trade['signal']}
💰 <b>Entry Price:</b> ₹{trade['entry']:.2f}
🔻 <b>Current Price:</b> ₹{current_price:.2f}
🛑 <b>Stop Loss Price:</b> ₹{trade['sl']:.2f}
⚠️ <i>Exit position immediately to prevent losses!</i>
"""
            send_telegram_message(msg)
            del active_positions[symbol]  # ट्रेड क्लोज कर दें

def scan_for_new_signals():
    """नये सिग्नल्स खोजना"""
    month_name = get_fno_month()
    stocks = {
        "TATASTEEL": {"ticker": "TATASTEEL.NS", "step": 2, "approx_premium_pct": 0.02},
        "SBIN": {"ticker": "SBIN.NS", "step": 10, "approx_premium_pct": 0.018},
        "RELIANCE": {"ticker": "RELIANCE.NS", "step": 20, "approx_premium_pct": 0.015}
    }

    for name, config in stocks.items():
        if name in active_positions:
            continue  # अगर इसका ट्रेड पहले से एक्टिव है तो दुबारा सिग्नल न बनाएँ

        try:
            ticker = config["ticker"]
            df_15m = yf.Ticker(ticker).history(period="5d", interval="15m", auto_adjust=False)
            if df_15m.empty:
                continue

            close_15m = safe_extract_val(df_15m['Close'].iloc[-1])
            if close_15m is None:
                continue

            vol = df_15m['Volume']
            high = df_15m['High']
            low = df_15m['Low']
            close = df_15m['Close']
            vwap = safe_extract_val(((vol * (high + low + close) / 3).sum()) / vol.sum())

            if vwap is None:
                continue

            signal = "BUY" if close_15m > vwap else "SELL"
            emoji = "🟢" if signal == "BUY" else "🔴"

            intra_target = close_15m * (1.01 if signal == "BUY" else 0.99)
            intra_sl = close_15m * (0.995 if signal == "BUY" else 1.005)

            # पोजीशन को लाइव ट्रैकिंग सूची में जोड़ें
            active_positions[name] = {
                "ticker": ticker,
                "signal": signal,
                "entry": close_15m,
                "target": intra_target,
                "sl": intra_sl
            }

            msg = f"""
{emoji} <b>NEW {signal} SIGNAL GENERATED</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Stock:</b> {name}
💰 <b>Entry Spot Price:</b> ₹{close_15m:.2f}
🎯 <b>Target:</b> ₹{intra_target:.2f}
🛑 <b>Stop Loss:</b> ₹{intra_sl:.2f}
⚡ <i>Live Real-Time Monitoring Started...</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

# Continuous Live Execution Loop
if __name__ == "__main__":
    print("🚀 LIVE REAL-TIME TRACKER RUNNING...")
    scan_counter = 0

    while True:
        try:
            # 1. हर 10 सेकंड में एक्टिव पोजीशन्स का रेट लाइव चेक करो
            track_live_positions()

            # 2. हर 5 मिनट (300 सेकंड) में नये मार्केट सिग्नल्स स्कैन करो
            if scan_counter % 30 == 0:
                scan_for_new_signals()

            scan_counter += 1
            time.sleep(10)  # 10 सेकंड का डिले

        except KeyboardInterrupt:
            print("Bot stopped by user.")
            break
        except Exception as e:
            print(f"Live Tracking Error: {e}")
            time.sleep(10)
