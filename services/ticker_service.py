import yfinance as yf
from typing import Dict

def get_live_tickers() -> Dict:
    """Fetch live commodity and forex data"""
    try:
        # Gold (GC=F), Silver (SI=F), Crude Oil (CL=F), USD/INR (INR=X)
        tickers = {
            'gold': 'GC=F',
            'silver': 'SI=F', 
            'crude_oil': 'CL=F',
            'usd_inr': 'INR=X',
            'btc_usd': 'BTC-USD'
        }
        
        result = {}
        for name, symbol in tickers.items():
            try:
                t = yf.Ticker(symbol)
                info = t.info
                hist = t.history(period="2d")
                
                current = info.get('regularMarketPrice', info.get('previousClose', 0))
                prev = info.get('previousClose', 0)
                
                change = 0
                if current and prev:
                    change = round(((current - prev) / prev) * 100, 2)
                
                result[name] = {
                    "price": round(current, 2) if current else 'N/A',
                    "change": change,
                    "currency": info.get('currency', 'USD'),
                    "name": info.get('shortName', name)
                }
            except:
                result[name] = {"error": "Data unavailable"}
        
        return result
    except Exception as e:
        return {"error": str(e)}