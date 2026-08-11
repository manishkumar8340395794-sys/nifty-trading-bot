import os
import time
import requests
import http.server
import socketserver
import threading

# ============================================================
# 1. RENDER PORT & HEALTH SERVER (Render को चालू रखने के लिए)
# ============================================================
PORT = int(os.environ.get("PORT", 10000))

def run_server():
    class HealthHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    try:
        with socketserver.TCPServer(("", PORT), HealthHandler) as httpd:
            print(f"Health Server running on port {PORT}")
            httpd.serve_forever()
    except Exception as e:
        print(f"Server Error: {e}")

threading.Thread(target=run_server, daemon=True).start()

# ============================================================
# 2. टेलीग्राम बोट सेटिंग्स (एकदम सही आईडी के साथ)
# ============================================================
TELEGRAM_BOT_TOKEN = "8993254284:AAGs5LwFD5PD0UMViDpDd8OY35IOSTMwyNE"
TELEGRAM_CHAT_ID = "5660614483"  # सही 10 अंकों की चैट आईडी

def send_test_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        print("Telegram Response:", response.json())
        return response.json()
    except Exception as e:
        print("Error sending message:", e)
        return None

# ============================================================
# 3. मुख्य एग्जीक्यूशन
# ============================================================
if __name__ == "__main__":
    print("Testing Telegram Connection...")
    
    # 1. सर्वर चालू होते ही मैसेज भेजेगा
    msg = "🎉 *बधाई हो! आपका टेलीग्राम बोट अब पूरी तरह सही कनेक्ट हो गया है।*"
    send_test_message(msg)
    
    # 2. हर 1 मिनट में मैसेज भेजता रहेगा ताकि कन्फर्म हो जाए
    counter = 1
    while True:
        time.sleep(60)
        send_test_message(f"🔔 *टेस्ट मैसेज नंबर #{counter}* (बोट एकदम सही काम कर रहा है)")
        counter += 1
