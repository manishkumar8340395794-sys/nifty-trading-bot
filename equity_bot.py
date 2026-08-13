import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np

# Telegram Configurations
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

SYMBOLS = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "SENSEX": "^BSESN",
    "NIFTY IT": "^CNXIT",
    "NTPC": "NTPC.NS"
}

# Trade state tracker
trade_state = {symbol: {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0} for symbol in SYMBOLS}

def send_telegram(message):
    if TELEGRAM_TOKEN and CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"})
        except Exception as e:
            print(f"Telegram error: {e}")

def calculate_supertrend(df, period=10, multiplier=3):
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # ATR calculation
    price_diff1 = high - low
    price_diff2 = abs(high - close.shift())
    price_diff3 = abs(low - close.shift())
    true_range = pd.concat([price_diff1, price_diff2, price_diff3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (high + low) / 2
    final_upperband = hl2 + (multiplier * atr)
    final_lowerband = hl2 - (multiplier * atr)
    
    supertrend = [True] * len(df)
    
    for i in range(1, len(df)):
        if close.iloc[i] > final_upperband.iloc[i-1]:
            supertrend[i] = True
        elif close.iloc[i] < final_lowerband.iloc[i-1]:
            supertrend[i] = False
        else:
            supertrend[i] = supertrend[i-1]
            if supertrend[i] and final_lowerband.iloc[i] < final_lowerband.iloc[i-1]:
                final_lowerband.iloc[i] = final_lowerband.iloc[i-1]
            if not supertrend[i] and final_upperband.iloc[i] > final_upperband.iloc[i-1]:
                final_upperband.iloc[i] = final_upperband.iloc[i-1]
                
    df['Supertrend'] = supertrend
    df['ATR'] = atr
    return df

def calculate_adx(df, length=14):
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    up = high - high.shift(1)
    down = low.shift(1) - low
    
    plus_dm = np.where((up > down) & (up > 0), up, 0)
    minus_dm = np.where((down > up) & (down > 0), down, 0)
    
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.rolling(length).mean()
    plus_di = 100 * (pd.Series(plus_dm).rolling(length).mean() / atr)
    minus_di = 100 * (pd.Series(minus_dm).rolling(length).mean() / atr)
    
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    df['ADX'] = dx.rolling(length).mean()
    return df

def analyze():
    global trade_state
    
    for name, ticker in SYMBOLS.items():
        try:
            data = yf.download(ticker, period="5d", interval="15m", progress=False)
            if data.empty or len(data) < 50:
                continue
                
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
                
            df = calculate_supertrend(data)
            df = calculate_adx(df)
            df['EMA200'] = df['Close'].ewm(span=200, adjust=False).mean()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            current_price = float(curr['Close'])
            atr = float(curr['ATR'])
            
            state = trade_state[name]
            
            # 1. Exit Tracking
            if state['status'] == 'BUY':
                if current_price >= state['target']:
                    send_telegram(f"🎯 *TARGET HIT - {name}*\n\n💰 Exit: ₹{current_price:.2f}\n🎉 Profit Booked!")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue
                elif current_price <= state['sl']:
                    send_telegram(f"❌ *STOP LOSS HIT - {name}*\n\n🔻 Exit: ₹{current_price:.2f}")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue

            elif state['status'] == 'SELL':
                if current_price <= state['target']:
                    send_telegram(f"🎯 *TARGET HIT - {name}*\n\n💰 Exit: ₹{current_price:.2f}\n🎉 Profit Booked!")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue
                elif current_price >= state['sl']:
                    send_telegram(f"❌ *STOP LOSS HIT - {name}*\n\n🔺 Exit: ₹{current_price:.2f}")
                    trade_state[name] = {'status': 'NONE', 'entry': 0, 'sl': 0, 'target': 0}
                    continue

            # 2. Strict Entry Conditions (Supertrend + ADX > 20 + EMA 200)
            strong_trend = curr['ADX'] > 20
            
            buy_signal = (
                prev['Supertrend'] == False and curr['Supertrend'] == True and
                current_price > curr['EMA200'] and strong_trend
            )
            
            sell_signal = (
                prev['Supertrend'] == True and curr['Supertrend'] == False and
                current_price < curr['EMA200'] and strong_trend
            )
            
            # 3. Execution
            if state['status'] == 'NONE':
                if buy_signal:
                    sl = current_price - (1.8 * atr)
                    target = current_price + (3.6 * atr)  # 1:2 R:R Ratio
                    
                    trade_state[name] = {'status': 'BUY', 'entry': current_price, 'sl': sl, 'target': target}
                    
                    msg = (f"🟢 *HIGH ACCURACY BUY - {name}*\n\n"
                           f"📌 *Entry:* ₹{current_price:.2f}\n"
                           f"🎯 *Target:* ₹{target:.2f}\n"
                           f"🛑 *Stop Loss:* ₹{sl:.2f}\n"
                           f"📊 *ADX Trend Strength:* {curr['ADX']:.1f} (Strong)")
                    send_telegram(msg)
                    
                elif sell_signal:
                    sl = current_price + (1.8 * atr)
                    target = current_price - (3.6 * atr)
                    
                    trade_state[name] = {'status': 'SELL', 'entry': current_price, 'sl': sl, 'target': target}
                    
                    msg = (f"🔴 *HIGH ACCURACY SELL - {name}*\n\n"
                           f"📌 *Entry:* ₹{current_price:.2f}\n"
                           f"🎯 *Target:* ₹{target:.2f}\n"
                           f"🛑 *Stop Loss:* ₹{sl:.2f}\n"
                           f"📊 *ADX Trend Strength:* {curr['ADX']:.1f} (Strong)")
                    send_telegram(msg)

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    analyze()
