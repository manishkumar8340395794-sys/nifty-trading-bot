import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np

# Telegram Configurations
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# Tickers to monitor (Nifty 50, Bank Nifty, Sensex, IT Sector)
SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTY IT": "^CNXIT"
}

# Global dictionary to track active trade state
# Format: {symbol: {'status': 'BUY'/'SELL'/'NONE', 'entry': price, 'sl': price, 'target': price}}
trade_state = {symbol: {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0} for symbol in SYMBOLS}

def send_telegram(message):
    if TELEGRAM_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
        except Exception as e:
            print(f"Telegram error: {e}")

def calculate_indicators(df):
    # EMA 20, 50, 200
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # RSI (14)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR for dynamic Stop-Loss and Target calculation
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    return df

def analyze_and_trade():
    global trade_state
    
    for name, ticker in SYMBOLS.items():
        try:
            # Fetch 15-minute timeframe data
            data = yf.download(ticker, period="5d", interval="15m", progress=False)
            if data.empty or len(data) < 200:
                continue
            
            # Fix multi-index columns if returned by yfinance
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
                
            df = calculate_indicators(data)
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            current_price = float(curr['Close'])
            atr = float(curr['ATR'])
            
            state = trade_state[name]
            
            # --- 1. Check Active Trade for Target or Stop Loss ---
            if state['status'] == 'BUY':
                if current_price >= state['target']:
                    send_telegram(f"🎯 *TARGET HIT - {name}*\n\n"
                                  f"📈 Status: Target Completed\n"
                                  f"💰 Exit Price: ₹{current_price:.2f}\n"
                                  f"🎉 Profit Booked!")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue
                elif current_price <= state['sl']:
                    send_telegram(f"❌ *STOP LOSS HIT - {name}*\n\n"
                                  f"📉 Status: Exit Trade\n"
                                  f"🔻 Exit Price: ₹{current_price:.2f}")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue

            elif state['status'] == 'SELL':
                if current_price <= state['target']:
                    send_telegram(f"🎯 *TARGET HIT - {name}*\n\n"
                                  f"📉 Status: Target Completed\n"
                                  f"💰 Exit Price: ₹{current_price:.2f}\n"
                                  f"🎉 Profit Booked!")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue
                elif current_price >= state['sl']:
                    send_telegram(f"❌ *STOP LOSS HIT - {name}*\n\n"
                                  f"📈 Status: Exit Trade\n"
                                  f"🔺 Exit Price: ₹{current_price:.2f}")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue

            # --- 2. Signal Generation Filters (High Accuracy) ---
            # BUY Condition:
            # 1. Price above EMA 200 (Strong Uptrend)
            # 2. EMA 20 crosses above EMA 50
            # 3. RSI between 50 and 68 (Strong Momentum without being Overbought)
            buy_condition = (
                current_price > curr['EMA200'] and
                prev['EMA20'] <= prev['EMA50'] and curr['EMA20'] > curr['EMA50'] and
                50 < curr['RSI'] < 68
            )

            # SELL Condition:
            # 1. Price below EMA 200 (Strong Downtrend)
            # 2. EMA 20 crosses below EMA 50
            # 3. RSI between 32 and 50 (Strong Bearish Momentum)
            sell_condition = (
                current_price < curr['EMA200'] and
                prev['EMA20'] >= prev['EMA50'] and curr['EMA20'] < curr['EMA50'] and
                32 < curr['RSI'] < 50
            )

            # --- 3. Execute Only If No Active Trade Exists (No Repetition) ---
            if state['status'] == 'NONE':
                if buy_condition:
                    sl = current_price - (1.5 * atr)
                    target = current_price + (3.0 * atr) # 1:2 Risk-Reward Ratio
                    
                    trade_state[name] = {
                        'status': 'BUY',
                        'entry': current_price,
                        'sl': sl,
                        'target': target
                    }
                    
                    msg = (f"🚀 *HIGH ACCURACY BUY CALL - {name}*\n\n"
                           f"📊 *Entry Price:* ₹{current_price:.2f}\n"
                           f"🎯 *Target:* ₹{target:.2f}\n"
                           f"🛑 *Stop Loss:* ₹{sl:.2f}\n"
                           f"📈 *Trend:* Strong Bullish (EMA 200 + RSI {curr['RSI']:.1f})\n"
                           f"⚙️ *Risk/Reward:* 1:2")
                    send_telegram(msg)

                elif sell_condition:
                    sl = current_price + (1.5 * atr)
                    target = current_price - (3.0 * atr) # 1:2 Risk-Reward Ratio
                    
                    trade_state[name] = {
                        'status': 'SELL',
                        'entry': current_price,
                        'sl': sl,
                        'target': target
                    }
                    
                    msg = (f"🔻 *HIGH ACCURACY SELL CALL - {name}*\n\n"
                           f"📊 *Entry Price:* ₹{current_price:.2f}\n"
                           f"🎯 *Target:* ₹{target:.2f}\n"
                           f"🛑 *Stop Loss:* ₹{sl:.2f}\n"
                           f"📉 *Trend:* Strong Bearish (EMA 200 + RSI {curr['RSI']:.1f})\n"
                           f"⚙️ *Risk/Reward:* 1:2")
                    send_telegram(msg)

        except Exception as e:
            print(f"Error processing {name}: {e}")

if __name__ == "__main__":
    analyze_and_trade()
