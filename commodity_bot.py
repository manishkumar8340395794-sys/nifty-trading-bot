import os
import requests
import yfinance as yf
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

active_trades = {}

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
    # MCX Commodities Configuration
    # is_option_available: False (केवल फ्यूचर सिग्नल देगा, जैसे Aluminium)
    commodities = {
        "CRUDEOIL": {"ticker": "CL=F", "factor": 86.5, "strike_step": 50, "opt_exp_angel": "17-AUG-26", "fut_exp_angel": "19-AUG-26", "opt_exp_5p": "17 AUG 2026", "fut_exp_5p": "19 AUG 2026", "prem_pct": 0.022, "has_option": True},
        "NATURALGAS": {"ticker": "NG=F", "factor": 95.3, "strike_step": 5, "opt_exp_angel": "24-AUG-26", "fut_exp_angel": "26-AUG-26", "opt_exp_5p": "24 AUG 2026", "fut_exp_5p": "26 AUG 2026", "prem_pct": 0.029, "has_option": True},
        "GOLD": {"ticker": "GC=F", "factor": 86.5, "strike_step": 100, "opt_exp_angel": "27-AUG-26", "fut_exp_angel": "05-OCT-26", "opt_exp_5p": "27 AUG 2026", "fut_exp_5p": "05 OCT 2026", "prem_pct": 0.015, "has_option": True},
        "SILVER": {"ticker": "SI=F", "factor": 86.5, "strike_step": 500, "opt_exp_angel": "27-AUG-26", "fut_exp_angel": "05-SEP-26", "opt_exp_5p": "27 AUG 2026", "fut_exp_5p": "05 SEP 2026", "prem_pct": 0.020, "has_option": True},
        "COPPER": {"ticker": "HG=F", "factor": 185.0, "strike_step": 5, "opt_exp_angel": "25-AUG-26", "fut_exp_angel": "31-AUG-26", "opt_exp_5p": "25 AUG 2026", "fut_exp_5p": "31 AUG 2026", "prem_pct": 0.020, "has_option": True},
        "ZINC": {"ticker": "ZNC=F", "factor": 86.5, "strike_step": 1, "opt_exp_angel": "", "fut_exp_angel": "31-AUG-26", "opt_exp_5p": "", "fut_exp_5p": "31 AUG 2026", "prem_pct": 0.0, "has_option": False},
        "ALUMINIUM": {"ticker": "ALI=F", "factor": 86.5, "strike_step": 1, "opt_exp_angel": "", "fut_exp_angel": "31-AUG-26", "opt_exp_5p": "", "fut_exp_5p": "31 AUG 2026", "prem_pct": 0.0, "has_option": False}
    }

    for name, config in commodities.items():
        try:
            ticker = config["ticker"]
            
            # Daily Trend
            df_daily = yf.download(ticker, period="30d", interval="1d", progress=False)
            if df_daily.empty:
                continue
                
            daily_close = float(df_daily['Close'].iloc[-1].item() if hasattr(df_daily['Close'].iloc[-1], 'item') else df_daily['Close'].iloc[-1])
            daily_sma20 = float(df_daily['Close'].rolling(20).mean().iloc[-1].item() if hasattr(df_daily['Close'].rolling(20).mean().iloc[-1], 'item') else df_daily['Close'].rolling(20).mean().iloc[-1])
            macro_trend = "BULLISH" if daily_close > daily_sma20 else "BEARISH"

            # 15-Min Candle Data
            df_15m = yf.download(ticker, period="5d", interval="15m", progress=False)
            if df_15m.empty:
                continue
                
            close_15m_usd = float(df_15m['Close'].iloc[-1].item() if hasattr(df_15m['Close'].iloc[-1], 'item') else df_15m['Close'].iloc[-1])
            vol = df_15m['Volume']
            high = df_15m['High']
            low = df_15m['Low']
            close = df_15m['Close']
            vwap_usd = float(((vol * (high + low + close) / 3).sum() / vol.sum()).item() if hasattr(((vol * (high + low + close) / 3).sum() / vol.sum()), 'item') else ((vol * (high + low + close) / 3).sum() / vol.sum()))

            close_inr = close_15m_usd * config["factor"]

            # Signal Logic
            signal = None
            if macro_trend == "BULLISH" and close_15m_usd > vwap_usd:
                signal = "BUY"
            elif macro_trend == "BEARISH" and close_15m_usd < vwap_usd:
                signal = "SELL"

            if not signal:
                continue

            emoji = "🟢" if signal == "BUY" else "🔴"

            # अगर Option उपलब्ध है (जैसे Crude oil, NatGas)
            if config["has_option"]:
                est_option_premium = close_inr * config["prem_pct"]
                strike = int(round(close_inr / config["strike_step"]) * config["strike_step"])
                option_type = "CE" if signal == "BUY" else "PE"

                opt_target = est_option_premium * 1.25
                opt_sl = est_option_premium * 0.85

                search_angel_opt = f"{name} {config['opt_exp_angel']} {strike} {option_type}"
                search_angel_fut = f"{name} {config['fut_exp_angel']}"
                search_5p_opt = f"{name} {config['opt_exp_5p']} {strike} {option_type}"
                search_5p_fut = f"{name} {config['fut_exp_5p']} FUT"

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
            # अगर केवल Future उपलब्ध है (जैसे Aluminium, Zinc)
            else:
                fut_target = close_inr * (1.015 if signal == "BUY" else 0.985)
                fut_sl = close_inr * (0.992 if signal == "BUY" else 1.008)

                search_angel_fut = f"{name} {config['fut_exp_angel']}"
                search_5p_fut = f"{name} {config['fut_exp_5p']} FUT"

                msg = f"""
{emoji} <b>MCX COMMODITY FUTURE {signal} SIGNAL</b>
━━━━━━━━━━━━━━━━━━
📊 <b>Overall Day Trend:</b> {macro_trend}
⏱️ <b>Trigger:</b> 15-Min VWAP Aligned
📌 <b>MCX Future Price:</b> ₹{close_inr:.2f}
━━━━━━━━━━━━━━━━━━
📱 <b>ANGEL ONE / 5PAISA SEARCH:</b>
• <b>Future Search:</b> <code>{search_angel_fut}</code>
• <b>Action:</b> {signal}
• <b>Entry Price:</b> ₹{close_inr:.2f}
• <b>Target:</b> ₹{fut_target:.2f}
• <b>Stop Loss:</b> ₹{fut_sl:.2f}
━━━━━━━━━━━━━━━━━━
🛡️ <i>Daily Trend matched. Paper trade first.</i>
"""
            send_telegram_message(msg)

        except Exception as e:
            print(f"Error scanning {name}: {e}")

if __name__ == "__main__":
    run_commodity_bot()
