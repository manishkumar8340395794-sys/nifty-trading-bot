import os
import time
import requests
from datetime import datetime
from SmartApi import SmartConnect
import pyotp

# GitHub Secrets से एंजल वन के क्रेडेंशियल्स प्राप्त करना
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram Error: {e}")

def initialize_angel_one():
    """Angel One SmartAPI में लॉगिन करना"""
    try:
        smart_api = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smart_api.generateSession(CLIENT_ID, PASSWORD, totp)
        
        if data['status']:
            print("✅ Angel One SmartAPI Login Successful!")
            return smart_api
        else:
            print(f"❌ Angel One Login Failed: {data['message']}")
            return None
    except Exception as e:
        print(f"❌ Exception during Angel One Login: {e}")
        return None

def fetch_live_market_data(smart_api, exchange, tradingsymbol, symboltoken):
    """Angel One से सीधे लाइव LTP और मार्केट डेटा खींचना"""
    try:
        data = smart_api.ltpData(exchange, tradingsymbol, symboltoken)
        if data and data.get('status'):
            return float(data['data']['ltp'])
    except Exception as e:
        print(f"Error fetching LTP for {tradingsymbol}: {e}")
    return None

def run_angel_bot():
    smart_api = initialize_angel_one()
    if not smart_api:
        send_telegram_message("⚠️ <b>Angel One API Login Failed!</b> Please check credentials.")
        return

    # स्टॉक टोकन लिस्ट (Angel One NSE Tokens)
    watch_list = [
        {"name": "TATASTEEL", "symbol": "TATASTEEL-EQ", "token": "3499", "exchange": "NSE"},
        {"name": "SBIN", "symbol": "SBIN-EQ", "token": "3045", "exchange": "NSE"},
        {"name": "RELIANCE", "symbol": "RELIANCE-EQ", "token": "2885", "exchange": "NSE"},
        {"name": "INFY", "symbol": "INFY-EQ", "token": "1594", "exchange": "NSE"}
    ]

    print("Fetching Live Data directly from Angel One Server...")

    for item in watch_list:
        ltp = fetch_live_market_data(smart_api, item["exchange"], item["symbol"], item["token"])
        if ltp:
            print(f"Real-time LTP for {item['name']} from Angel One: ₹{ltp}")
            
            # सैंपल सिग्नल अलर्ट
            msg = f"""
📡 <b>ANGEL ONE SMART-API LIVE DATA</b>
━━━━━━━━━━━━━━━━━━
📌 <b>Stock:</b> {item['name']}
💰 <b>Angel One Live Price (LTP):</b> ₹{ltp:.2f}
⏱️ <b>Time:</b> {datetime.now().strftime('%H:%M:%S')}
✅ <i>Directly fetched from Angel One Server</i>
"""
            send_telegram_message(msg)
        else:
            print(f"Failed to fetch live data for {item['name']}")

    # Session Logout
    try:
        smart_api.terminateSession(CLIENT_ID)
    except Exception:
        pass

if __name__ == "__main__":
    run_angel_bot()
        
