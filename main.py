import time
import requests
import pandas as pd
import yfinance as yf

TELEGRAM_BOT_TOKEN = "8993254284:AAGs5LwFD5PD0UMViDpDd8OY35IOSTMwyNE"
TELEGRAM_CHAT_ID = "5660614483"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")

send_telegram("🚀 *Render Bot Active!* Listening for Intraday Nifty Signals...")
print("Bot Started on Render Server...")

def run_scanner():
    print("Scanning market...")
    # Intraday scanning logic runs here

while True:
    run_scanner()
    time.sleep(900)  # Every 15 minutes
