# backend/app.py (உதாரணம்)

from fastapi import FastAPI
import yfinance as yf
import requests

app = FastAPI()

@app.get("/analyze_stock")
async def analyze_stock(symbol: str, lang: str = 'ta'):
    # 1. Yahoo Finance-லிருந்து நேரடி தரவு
    ticker = yf.Ticker(symbol)
    info = ticker.info
    hist = ticker.history(period="5d")
    
    # 2. NSE India FII/DII தரவு (scraping அல்லது API)
    # https://www.nseindia.com/api/fiidiiTradeReact
    
    # 3. இந்த தரவை AI-க்கு அனுப்புவதற்கு முன் prompt-ல் சேர்க்கவும்
    real_time_context = f"""
    Current Price: {info.get('currentPrice')}
    Previous Close: {info.get('previousClose')}
    PE: {info.get('trailingPE')}
    Market Cap: {info.get('marketCap')}
    """
    
    # 4. AI-க்கு அனுப்பும்போது "Use ONLY the above data" என்று கட்டாயப்படுத்தவும்
    
    return {
        "name": info.get('longName'),
        "price": info.get('currentPrice'),
        "changePercent": round(
            ((info.get('currentPrice',0) - info.get('previousClose',0)) 
             / info.get('previousClose',1)) * 100, 2
        ),
        "pe": info.get('trailingPE'),
        "pb": info.get('priceToBook'),
        "marketCap": info.get('marketCap'),
        "aiAnalysis": generate_ai_analysis(real_time_context, lang)
    }