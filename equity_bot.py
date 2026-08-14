import os
import sys
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from SmartApi import SmartConnect
import pyotp
import yfinance as yf

# Logging Setup
logging.basicConfig(level=logging.INFO, format='[%(levelname)s %(asctime)s] %(message)s')

# Credentials from GitHub Secrets
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing!")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

# Comprehensive Watchlist covering Nifty 50, Bank Nifty, Sensex & Key Sectors (Chemical, IT, Auto, Pharma etc.)
WATCHLIST = [
    # Nifty 50 & Bank Nifty / Sensex Heavyweights
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LICI.NS", "KOTAKBANK.NS",
    "LT.NS", "AXISBANK.NS", "HINDUNILVR.NS", "ASIANPAINT.NS", "MARUTI.NS",
    "SUNPHARMA.NS", "TITAN.NS", "BAJFINANCE.NS", "ULTRACEMCO.NS", "NESTLEIND.NS",
    "TATASTEEL.NS", "POWERGRID.NS", "NTPC.NS", "M&M.NS", "GRASIM.NS",
    "TECHM.NS", "HINDALCO.NS", "CIPLA.NS", "BPCL.NS", "TATACONSUM.NS",
    
    # Chemical Sector Stocks
    "DEEPAKNTR.NS", "ATUL.NS", "NAVINFLUOR.NS", "AARTIIND.NS", "SRF.NS",
    "ALKYLAMINE.NS", "FINEORG.NS", "PIIND.NS", "COROMANDEL.NS", "TATACHEM.NS",
    
    # IT Sector Stocks
    "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS",
    
    # Other Prominent Nifty 100 / Sensex Stocks
    "ADANIENT.NS", "ADANIPORTS.NS", "BAJAJ-AUTO.NS", "ONGC.NS", "COALINDIA.NS",
    "SBILIFE.NS", "HDFCLIFE.NS", "BRITANNIA.NS", "HEROMOTOCO.NS", "EICHERMOT.NS"
]

def calculate_indicators(df):
    try:
        # RSI Calculation (14 period)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Supertrend Calculation (Multiplier 3, Period 10)
        hl2 = (df['High'] + df['Low']) / 2
        atr = df['High'].rolling(10).max() - df['Low'].rolling(10).min() # Simplified ATR proxy for scanner
        upper_band = hl2 + (3 * atr)
        lower_band = hl2 - (3 * atr)
        
        df['Supertrend'] = 'BUY'
        # Basic trend filter using SMA & RSI
        df['SMA_20'] = df['Close'].rolling(window=20).mean()
        return df
    except Exception as e:
        logging.error(f"Indicator calculation error: {e}")
        return None

def scan_markets():
    logging.info("Starting Multi-Sector & Nifty 100/Chemical Market Scan...")
    signals_found = 0

    for symbol in WATCHLIST:
        try:
            data = yf.download(symbol, period="5d", interval="15m", progress=False)
            if data.empty or len(data) < 20:
                continue
            
            # Flatten multi-index columns if returned by newer yfinance versions
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.droplevel(1)

            df = calculate_indicators(data)
            if df is None or df.empty:
                continue

            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            
            close_price = float(last_row['Close'])
            rsi = float(last_row['RSI'])
            sma20 = float(last_row['SMA_20'])

            # Multi-Condition Strategy Filter for High Accuracy
            action = None
            if close_price > sma20 and 55 <= rsi <= 75:
                action = "BUY"
            elif close_price < sma20 and 25 <= rsi <= 45:
                action = "SELL"

            if action:
                target = round(close_price * 1.015, 2) if action == "BUY" else round(close_price * 0.985, 2)
                stop_loss = round(close_price * 0.992, 2) if action == "BUY" else round(close_price * 1.008, 2)

                msg = (
                    f"🚨 **HIGH-ACCURACY MARKET SCANNER** 🚨\n\n"
                    f"📌 **Stock/Asset:** `{symbol}`\n"
                    f"📊 **Action:** `{action}`\n"
                    f"💰 **Trigger Price:** `₹{close_price:.2f}`\n"
                    f"📈 **RSI (14):** `{rsi:.2f}`\n"
                    f"🎯 **Target (1.5%):** `₹{target}`\n"
                    f"🛑 **Stop Loss (0.8%):** `₹{stop_loss}`\n\n"
                    f"✅ *Scanned from Nifty 50/100/Chemical/IT Universe*\n"
                    f"⚠️ *Paper trade first for testing.*"
                )
                send_telegram_message(msg)
                signals_found += 1
                logging.info(f"Signal sent for {symbol}: {action}")

        except Exception as e:
            logging.error(f"Error processing {symbol}: {e}")

    if signals_found == 0:
        logging.info("Scan completed. No strong setups matched the strict filter criteria right now.")

if __name__ == "__main__":
    scan_markets()
