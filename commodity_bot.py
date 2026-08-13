import os
import requests
import yfinance as yf
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

def run_commodity_bot():
    commodities = {
        "CRUDEOIL": "CL=F",
        "NATURALGAS": "NG=F"
    }

    for name, ticker in commodities.items():
        try:
            # 1. Fetch Daily Data (1D) for Overall Trend
            df_daily = yf.download(ticker, period="30d", interval="1d", progress=False)
            if df_daily.empty:
                continue
                
            daily_close = float(df_daily['Close'].iloc[-1].item() if hasattr(df_daily['Close'].iloc[-1], 'item') else df_daily['Close'].iloc[-1])
            daily_sma20 = float(df_daily['Close'].rolling(20).mean().iloc[-1].item() if hasattr(df_daily['Close'].rolling(20).mean().iloc[-1], 'item') else df_daily['Close'].rolling(20).mean().iloc[-1])
            
            macro_trend = "BULLISH" if daily_close > daily_sma20 else "BEARISH"

            # 2. Fetch 15-Minute Data
            df_15m = yf.download(ticker, period="5d", interval="15m", progress=False)
            if df_15m.empty:
                continue
                
            close_15m_usd = float(df_15m['Close'].iloc[-1].item() if hasattr(df_15m['Close'].iloc[-1], 'item') else df_15m['Close'].iloc[-1])
            
            vol = df_15m['Volume']
            high = df_15m['High']
            low = df_15m['Low']
            close = df_15m['Close']
            vwap_usd = float(((vol * (high + low + close) / 3).sum() / vol.sum()).item() if hasattr(((vol * (high + low + close) / 3).sum() / vol.sum()), 'item') else ((vol * (high + low + close) / 3).sum() / vol.sum()))

            # Signal Logic
            signal = None
            if macro_trend == "BULLISH" and close_15m_usd > vwap_usd:
                signal = "BUY"
            elif macro_trend == "BEARISH" and close_15m_usd < vwap_usd:
                signal = "SELL"

            if not signal:
                continue

            # Correct USD to MCX INR Conversion & Strike Logic
            if name == "CRUDEOIL":
                close_inr = close_15m_usd * 86.5
                strike = int(round(close_inr / 50) * 50)
                expiry_opt = "17-AUG-26"
                expiry_fut = "19-AUG-26"
            elif name == "NATURALGAS":
                # Correct factor to match MCX price (~264 INR)
                close_inr = close_15m_usd * 95.3
                strike = int(round(close_inr / 5) * 5)
                expiry_opt = "24-AUG-26"
                expiry_fut = "26-AUG-26"

            option_type = "CE" if signal == "BUY" else "PE"
            emoji = "🟢" if signal == "BUY" else "🔴"

            target_inr = close_inr * 1.012 if signal == "BUY" else close_inr * 0.988
            sl_inr = close_inr * 0.994 if signal == "BUY" else close_inr * 1.006

            search_fut = f"{name} {expiry_fut}"
            search_opt = f"{name} {expiry_opt} {strike} {option_type}"

            msg = f"""
{emoji} <b>MCX COMMODITY {signal} SIGNAL</b>
━━━━━━━━━━━━━━━━━━
📊 <b>Overall Day Trend:</b> {macro_trend} 📈
⏱️ <b>Trigger:</b> 15-Min VWAP Aligned
🏷️ <b>Category:</b> <b>INTRADAY / MCX POSITIONAL</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Asset:</b> {name}
🔍 <b>Angel One Search:</b> <code>{search_fut}</code>
💡 <b>Option Buyers:</b> <code>{search_opt}</code>
━━━━━━━━━━━━━━━━━━
💰 <b>Entry:</b> ₹{close_inr:.2f}
🎯 <b>Target:</b> ₹{target_inr:.2f}
🛑 <b>Stop Loss:</b> ₹{sl_inr:.2f}
━━━━━━━━━━━━━━━━━━
🛡️ <i>Daily Trend matched. Paper trade first.</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

if __name__ == "__main__":
    run_commodity_bot()
