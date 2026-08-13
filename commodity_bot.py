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

            # USD to MCX Conversion Logic
            if name == "CRUDEOIL":
                close_inr = close_15m_usd * 86.5
                strike = int(round(close_inr / 50) * 50)
                
                exp_angel_opt = "17-AUG-26"
                exp_angel_fut = "19-AUG-26"
                exp_5p_opt = "17 AUG 2026"
                exp_5p_fut = "19 AUG 2026"
                
                est_option_premium = close_inr * 0.022
            elif name == "NATURALGAS":
                close_inr = close_15m_usd * 95.3
                strike = int(round(close_inr / 5) * 5)
                
                exp_angel_opt = "24-AUG-26"
                exp_angel_fut = "26-AUG-26"
                exp_5p_opt = "24 AUG 2026"
                exp_5p_fut = "26 AUG 2026"
                
                est_option_premium = close_inr * 0.029

            option_type = "CE" if signal == "BUY" else "PE"
            emoji = "🟢" if signal == "BUY" else "🔴"

            # Target & Stop Loss Calculation
            opt_target = est_option_premium * 1.25
            opt_sl = est_option_premium * 0.85

            # Formats for Angel One
            search_angel_opt = f"{name} {exp_angel_opt} {strike} {option_type}"
            search_angel_fut = f"{name} {exp_angel_fut}"

            # Formats for 5paisa
            search_5p_opt = f"{name} {exp_5p_opt} {strike} {option_type}"
            search_5p_fut = f"{name} {exp_5p_fut} FUT"

            msg = f"""
{emoji} <b>MCX COMMODITY {signal} SIGNAL</b>
━━━━━━━━━━━━━━━━━━
📊 <b>Overall Day Trend:</b> {macro_trend}
⏱️ <b>Trigger:</b> 15-Min VWAP Aligned
📌 <b>MCX Spot Price:</b> ₹{close_inr:.2f}
━━━━━━━━━━━━━━━━━━
📱 <b>ANGEL ONE DETAILS:</b>
• <b>Option Search:</b> <code>{search_angel_opt}</code>
• <b>Future Search:</b> <code>{search_angel_fut}</code>
• <b>Buy Price:</b> ₹{est_option_premium:.2f}
• <b>Target:</b> ₹{opt_target:.2f}
• <b>Stop Loss:</b> ₹{opt_sl:.2f}
━━━━━━━━━━━━━━━━━━
📱 <b>5PAISA DETAILS:</b>
• <b>Option Search:</b> <code>{search_5p_opt}</code>
• <b>Future Search:</b> <code>{search_5p_fut}</code>
• <b>Buy Price:</b> ₹{est_option_premium:.2f}
• <b>Target:</b> ₹{opt_target:.2f}
• <b>Stop Loss:</b> ₹{opt_sl:.2f}
━━━━━━━━━━━━━━━━━━
🛡️ <i>Daily Trend matched. Paper trade first.</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

if __name__ == "__main__":
    run_commodity_bot()
