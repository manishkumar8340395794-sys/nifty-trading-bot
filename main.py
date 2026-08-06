import http.server
import os
import socketserver
import threading
import time
import requests

# 1. Render Port Binding (Dummy Server)
def run_server():
    port = int(os.environ.get("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# 2. Telegram Credentials
TELEGRAM_BOT_TOKEN = "8993254284:AAGs5LwFD5PD0UMViDpDd8OY35lOSTMwyNE"
TELEGRAM_CHAT_ID = "5660614483"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload)
        print("Telegram Response:", res.json())
    except Exception as e:
        print(f"Telegram error: {e}")

# 3. Startup Notification
send_telegram("🚀 *Render Bot Active & Running Successfully!*")
print("Bot Started on Render Server...")

# 4. Main Scanning Loop
def run_scanner():
    print("Scanning market...")

while True:
    run_scanner()
    time.sleep(60)
