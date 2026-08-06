import http.server
import os
import socketserver
import threading
import time
import pandas as pd
import requests
import yfinance as yf


# Render Port Binding के लिए Dummy Web Server
def run_server():
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()


threading.Thread(target=run_server, daemon=True).start()

# Telegram Credentials
TELEGRAM_BOT_TOKEN = "8993254284:AAGs..."
TELEGRAM_CHAT_ID = "5660614483"


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram error: {e}")


send_telegram("🚀 *Render Bot Active & Running!*")
print("Bot Started on Render Server...")


def run_scanner():
    print("Scanning market...")


while True:
    run_scanner()
    time.sleep(60)
