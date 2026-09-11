from supabase import create_client, Client
import yfinance as yf

SUPABASE_URL = "https://tvkveuuvlsxmgtzuwjtm.supabase.co"
SUPABASE_KEY = "sb_secret_pIp8rwLhiK-u9TJ62Cg48w_1dHct4Yf"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def quick_test_upload():
    test_symbols = ["ITC.NS", "RELIANCE.NS"]
    
    for symbol in test_symbols:
        print(f"🔄 Fetching data for {symbol}...")
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        price = info.get('currentPrice') or info.get('regularMarketPrice') or 400.0
        
        data = {
            "symbol": symbol,
            "name": info.get('longName', symbol),
            "country": "India",
            "exchange": "NSE",
            "sector": info.get('sector', 'FMCG'),
            "price": float(price),
            "pe_ratio": float(info.get('trailingPE', 20.0)) if info.get('trailingPE') else 20.0
        }
        
        # Insert or Update
        res = supabase.table("global_stocks").upsert(data).execute()
        print(f"✅ Uploaded {symbol} successfully!")

if __name__ == "__main__":
    quick_test_upload()