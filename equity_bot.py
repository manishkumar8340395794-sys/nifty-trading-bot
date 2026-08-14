import yfinance as yf
import pandas as pd
import requests
import datetime

# ==========================================
# 1. TELEGRAM SETTINGS
# ==========================================
TELEGRAM_BOT_TOKEN = "आपका_बॉट_टोकन_यहाँ_डालें"
TELEGRAM_CHAT_ID = "आपका_चैट_आईडी_यहाँ_डालें"

# ==========================================
# 2. STOCK UNIVERSE (Indices & Nifty Stocks)
# ==========================================
master_dict = {
    # INDICES
    "NIFTY_50": {"ticker": "^NSEI"},
    "BANK_NIFTY": {"ticker": "^NSEBANK"},
    
    # HEAVYWEIGHTS & SECTORS
    "RELIANCE": {"ticker": "RELIANCE.NS"},
    "HDFCBANK": {"ticker": "HDFCBANK.NS"},
    "ICICIBANK": {"ticker": "ICICIBANK.NS"},
    "SBIN": {"ticker": "SBIN.NS"},
    "PNB": {"ticker": "PNB.NS"},
    "TCS": {"ticker": "TCS.NS"},
    "INFY": {"ticker": "INFY.NS"},
    "WIPRO": {"ticker": "WIPRO.NS"},
    "AARTIIND": {"ticker": "AARTIIND.NS"},
    "SRF": {"ticker": "SRF.NS"},
    "DEEPAKNTR": {"ticker": "DEEPAKNTR.NS"},
    "TATAMOTORS": {"ticker": "TATAMOTORS.NS"},
    "TATASTEEL": {"ticker": "TATASTEEL.NS"},
    "LT": {"ticker": "LT.NS"},
    "ITC": {"ticker": "ITC.NS"}
}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message: {e}")

# ==========================================
# 3. INDICATORS CALCULATIONS
# ==========================================
def calculate_indicators(df):
    # 9 EMA & 21 EMA
    df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean() # Big Trend
    
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Average True Range (ATR for Safe Stop Loss)
    df['TR'] = pd.concat([
        df['High'] - df['Low'],
        abs(df['High'] - df['Close'].shift()),
        abs(df['Low'] - df['Close'].shift())
    ], axis=1).max(axis=1)
    df['ATR'] = df['TR'].rolling(window=14).mean()
    
    return df

# ==========================================
# 4. MULTI-TIMEFRAME ANALYSIS ENGINE
# ==========================================
def analyze_stock(stock_name, ticker):
    stock = yf.Ticker(ticker)
    
    # 1. 📈 Daily Data Fetch (For Main Trend Analysis)
    df_daily = stock.history(period="60d", interval="1d")
    if df_daily.empty or len(df_daily) < 30:
        return
    df_daily = calculate_indicators(df_daily)
    
    daily_last = df_daily.iloc[-1]
    is_daily_bullish = daily_last['Close'] > daily_last['EMA_50']  # Price 50 EMA के ऊपर है
    is_daily_bearish = daily_last['Close'] < daily_last['EMA_50']  # Price 50 EMA के नीचे है
    
    # 2. ⚡ 15-Minute Data Fetch (For Intraday Entry)
    df_15m = stock.history(period="5d", interval="15m")
    if df_15m.empty or len(df_15m) < 25:
        return
    df_15m = calculate_indicators(df_15m)
    
    m15_last = df_15m.iloc[-1]
    m15_prev = df_15m.iloc[-2]
    
    current_price = round(m15_last['Close'], 2)
    rsi_15m = round(m15_last['RSI'], 2)
    atr = round(m15_last['ATR'], 2)
    
    # --- A. INTRADAY BUY CALL (Only if Daily Trend is UP) ---
    if is_daily_bullish:
        if (m15_prev['EMA_9'] <= m15_prev['EMA_21']) and (m15_last['EMA_9'] > m15_last['EMA_21']) and (rsi_15m > 55):
            stop_loss = round(current_price - (1.5 * atr), 2)
            target = round(current_price + (3.0 * atr), 2)
            
            msg = f"🚀 **INTRADAY BUY CALL (BULLISH)** 🚀\n\n"
            msg += f"📌 **Stock:** {stock_name}\n"
            msg += f"💰 **Entry Price:** ₹{current_price}\n"
            msg += f"🛑 **Safe Stop Loss:** ₹{stop_loss}\n"
            msg += f"🎯 **Target Price:** ₹{target}\n\n"
            msg += f"📊 **Reason:** Daily Chart Trend UP + 15M EMA Crossover Breakout\n"
            msg += f"📈 **RSI:** {rsi_15m}\n"
            send_telegram_message(msg)
            return

    # --- B. INTRADAY SELL CALL (Only if Daily Trend is DOWN) ---
    if is_daily_bearish:
        if (m15_prev['EMA_9'] >= m15_prev['EMA_21']) and (m15_last['EMA_9'] < m15_last['EMA_21']) and (rsi_15m < 45):
            stop_loss = round(current_price + (1.5 * atr), 2)
            target = round(current_price - (3.0 * atr), 2)
            
            msg = f"📉 **INTRADAY SELL CALL (BEARISH)** 📉\n\n"
            msg += f"📌 **Stock:** {stock_name}\n"
            msg += f"💰 **Entry Price:** ₹{current_price}\n"
            msg += f"🛑 **Safe Stop Loss:** ₹{stop_loss}\n"
            msg += f"🎯 **Target Price:** ₹{target}\n\n"
            msg += f"📊 **Reason:** Daily Chart Trend DOWN + 15M EMA Breakdown\n"
            msg += f"📉 **RSI:** {rsi_15m}\n"
            send_telegram_message(msg)
            return

    # --- C. SWING TRADE CALL (Daily Chart Breakout) ---
    # अगर Daily Chart पर बड़ा ब्रेकआउट हुआ हो (फॉर 2-7 डेज होल्डिंग)
    daily_prev = df_daily.iloc[-2]
    if (daily_prev['EMA_9'] <= daily_prev['EMA_21']) and (daily_last['EMA_9'] > daily_last['EMA_21']) and (daily_last['RSI'] > 60):
        stop_loss = round(current_price - (2.0 * atr), 2)
        target = round(current_price + (5.0 * atr), 2)
        
        msg = f"💎 **SWING TRADE CALL (2-7 DAYS)** 💎\n\n"
        msg += f"📌 **Stock:** {stock_name}\n"
        msg += f"💰 **Buying Zone:** ₹{current_price}\n"
        msg += f"🛑 **Swing Stop Loss:** ₹{stop_loss}\n"
        msg += f"🎯 **Swing Target:** ₹{target}\n\n"
        msg += f"📊 **Reason:** Strong Daily Chart Momentum Breakout\n"
        send_telegram_message(msg)

# ==========================================
# 5. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    print(f"[{datetime.datetime.now()}] 🔄 Scanning Market with Multi-Timeframe Analysis...")
    for stock_name, info in master_dict.items():
        try:
            analyze_stock(stock_name, info["ticker"])
        except Exception as e:
            print(f"Error scanning {stock_name}: {e}")
    print("✅ Scanning Completed!")
