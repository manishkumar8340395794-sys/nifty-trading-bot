import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

def get_mcx_expiry_format():
    now = datetime.now()
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    return f"{months[now.month - 1]}{now.strftime('%y')}"

def run_commodity_bot():
    commodities = {
        "CRUDEOIL": "CL=F",
        "NATURALGAS": "NG=F",
        "GOLD": "GC=F",
        "SILVER": "SI=F"
    }
    
    expiry = get_mcx_expiry_format()

    for name, ticker in commodities.items():
        try:
            # 1. Daily Trend Calculation
            df_daily = yf.download(ticker, period="30d", interval="1d", progress=False)
            if df_daily.empty:
                continue
                
            daily_close = df_daily['Close'].iloc[-1].item() if hasattr(df_daily['Close'].iloc[-1], 'item') else float(df_daily['Close'].iloc[-1])
            daily_sma20 = df_daily['Close'].rolling(20).mean().iloc[-1].item() if hasattr(df_daily['Close'].rolling(20).mean().iloc[-1], 'item') else float(df_daily['Close'].rolling(20).mean().iloc[-1])
            
            macro_trend = "BULLISH" if daily_close > daily_sma20 else "BEARISH"

            # 2. 15-Minute Entry Calculation
            df_15m = yf.download(ticker, period="5d", interval="15m", progress=False)
            if df_15m.empty:
                continue
                
            close_15m = df_15m['Close'].iloc[-1].item() if hasattr(df_15m['Close'].iloc[-1], 'item') else float(df_15m['Close'].iloc[-1])
            
            vol = df_15m['Volume']
            high = df_15m['High']
            low = df_15m['Low']
            close = df_15m['Close']
            vwap = ((vol * (high + low + close) / 3).sum() / vol.sum())
            vwap = vwap.item() if hasattr(vwap, 'item') else float(vwap)

            # 3. Signal Filtering
            signal = None
            if macro_trend == "BULLISH" and close_15m > vwap:
                signal = "BUY"
            elif macro_trend == "BEARISH" and close_15m < vwap:
                signal = "SELL"

            if not signal:
                continue

            emoji = "🟢" if signal == "BUY" else "🔴"
            strike = round(close_15m / 50) * 50
            option_type = "CE" if signal == "BUY" else "PE"

            target = close_15m * 1.012 if signal == "BUY" else close_15m * 0.988
            sl = close_15m * 0.994 if signal == "BUY" else close_15m * 1.006

            msg = f"""
{emoji} <b>MCX COMMODITY {signal} SIGNAL</b>
━━━━━━━━━━━━━━━━━━
📊 <b>Overall Day Trend:</b> {macro_trend}
⏱️ <b>Trigger:</b> 15-Min VWAP Aligned
🏷️ <b>Category:</b> <b>INTRADAY / MCX POSITIONAL</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Asset:</b> {name}
🔍 <b>Angel One Search:</b> <code>{name} {expiry} FUT</code>
💡 <b>Option Buyers:</b> <code>{name} {strike} {option_type}</code>
━━━━━━━━━━━━━━━━━━
💰 <b>Entry:</b> ₹{close_15m:.2f}
🎯 <b>Target:</b> ₹{target:.2f}
🛑 <b>Stop Loss:</b> ₹{sl:.2f}
━━━━━━━━━━━━━━━━━━
🛡️ <i>Daily Trend matched. Paper trade first.</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

if __name__ == "__main__":
    run_commodity_bot()
