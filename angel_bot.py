import os
import requests
import pyotp
from SmartApi import SmartConnect

# Github Secrets से क्रेडेंशियल्स प्राप्त करना
API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID")
PASSWORD = os.environ.get("ANGEL_PASSWORD")
PIN = os.environ.get("ANGEL_PIN")
TOTP_KEY = os.environ.get("ANGEL_TOTP_KEY")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram(message):
    if TELEGRAM_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})

def run_bot():
    try:
        # Angel One SmartAPI लॉगिन
        smart_api = SmartConnect(api_key=API_KEY)
        
        # लॉगिन/सेशन
        data = smart_api.generateSession(CLIENT_ID, PASSWORD, PIN)
        
        if data['status']:
            msg = "✅ *Angel One SmartAPI सफलतापूर्वक कनेक्ट हो गया है!*"
            print(msg)
            send_telegram(msg)
        else:
            print("लॉगिन असफल:", data['message'])
            send_telegram(f"❌ *Angel One लॉगिन असफल:* {data['message']}")
            
    except Exception as e:
        print("एरर:", str(e))
        send_telegram(f"⚠️ *बॉट एरर:* {str(e)}")

if __name__ == "__main__":
    run_bot()
