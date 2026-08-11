from datetime import datetime
import http.server
import os
import socketserver
import threading
import time
import numpy as np
import pandas as pd
import pytz
import requests
import yfinance as yf

# =========================================================
# 1. RENDER PORT & HEALTH SERVER (NON-BLOCKING)
# =========================================================
PORT = int(os.environ.get("PORT", 10000))

class HealthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is Running 24/7!")

    def log_message(self, format, *args):
        pass

def run_server():
    try:
        with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
            print(f"[HEALTH SERVER STARTED ON PORT {PORT}]")
            httpd.serve_forever()
    except Exception as e:
        print(f"[Health Server Error]: {e}")

# Server in background
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# =========================================================
# 2. INTERNAL AUTO KEEP-ALIVE
# =========================================================
def keep_alive():
    time.sleep(10)
    local_url = f"http://127.0.0.1:{PORT}"
    while True:
        try:
            res = requests.get(local_url, timeout=5)
            print(f"[{datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%H:%M:%S')}] Internal Ping Status: {res.status_code}")
        except Exception as e:
            print(f"[Keep-Alive Note]: {e}")
        time.sleep(90)

ping_thread = threading.Thread(target=keep_alive, daemon=True)
ping_thread.start()

# =========================================================
# 3. TELEGRAM SETTINGS
# =========================================================
TELEGRAM_BOT_TOKEN = "8993254284:AAGs..."  # अपना पूरा सही टोकन यहाँ डालें
TELEGRAM_CHAT_ID = "5660614483"             # आपकी चैट आईडी
IST = pytz.timezone("Asia/Kolkata")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False

# =========================================================
# 4. WATCHLIST & SCANNER
# =========================================================
WATCHLIST = {
    "SBIN.NS": {"name": "SBI (NSE)"},
    "PNB.NS": {"name": "PNB (NSE)"},
    "GAIL.NS": {"name": "GAIL (NSE)"},
    "IOC.NS": {"name": "IOC (NSE)"},
    "FEDERALBNK.NS": {"name": "FEDERAL BANK"},
    "ASHOKLEY.NS": {"name": "ASHOK LEYLAND"}
}

def scan_markets():
    for ticker, info in WATCHLIST.items():
        try:
            df = yf.download(ticker, period="2d", interval="5m", progress=False)
            if not df.empty:
                last_price = round(df['Close'].iloc[-1], 2)
                print(f"Checking {info['name']}: ₹{last_price}")
        except Exception as e:
            print(f"Error scanning {ticker}: {e}")

# =========================================================
# 5. MAIN LOOP
# =========================================================
print("Starting Main Market Scanner Loop...")
send_telegram("🚀 *100% NON-STOP TRADING BOT STARTED & SCANNING MARKETS!*")

while True:
    try:
        now_ist = datetime.now(IST)
        print(f"[{now_ist.strftime('%Y-%m-%d %H:%M:%S')}] Scanning Markets...")
        scan_markets()
    except Exception as e:
        print(f"[MAIN LOOP ERROR] {e}")
    
    time.sleep(180)  # हर 3 मिनट में मार्केट स्कैन करेगा
