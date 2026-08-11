import os
import time
import requests
import yfinance as yf

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# TATAMOTORS.NS को हटा दिया गया है ताकि लूप न अटके
STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LTIM.NS", "LT.NS",
    "AXISBANK.NS", "KOTAKBANK.NS", "HINDUNILVR.NS", "BAJFINANCE.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS"
]

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def run_bot():
    print("Running Equity Bot...")
    signals = []
    
    for symbol in STOCKS:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="5d", interval="15m", timeout=5)
            
            if df.empty or len(df) < 2:
                print(f"No data for {symbol}")
                continue
                
            last_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            pct_change = ((last_close - prev_close) / prev_close) * 100
            
            print(f"{symbol}: {last_close:.2f} ({pct_change:.2f}%)")
            
            # Simple condition for test signal
            if abs(pct_change) >= 1.5:
                direction = "🚀 BUY/BULLISH" if pct_change > 0 else "🔻 SELL/BEARISH"
                signals.append(f"{direction} Signal for *{symbol}*\nPrice: ₹{last_close:.2f} ({pct_change:+.2f}%)")
                
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            
    if signals:
        full_msg = "📊 *NSE EQUITY SIGNALS*\n\n" + "\n\n".join(signals)
        send_telegram_message(full_msg)
    else:
        print("No signals triggered.")
        # Send test status message on first run
        send_telegram_message("✅ *Equity Bot Test Run Complete!*\nSystem is running fine and active.")

if __name__ == "__main__":
    run_bot()
