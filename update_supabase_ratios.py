import time
import requests
import concurrent.futures
import pandas as pd
import yfinance as yf
import io
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

# Supabase Connection
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase Client Connected!")
except Exception as e:
    print(f"❌ Supabase Connection Error: {e}")
    exit()

# ------------------------------------------------------------------
# LIVE FX Normalization Helpers (Base Currency -> INR Crores)
# ------------------------------------------------------------------

# நேரலை FX விகிதங்களைச் சேமிக்க உலகளாவிய கேச் (Cache)
FX_CACHE = {'INR': 1.0}

def get_live_fx_to_inr(currency: str) -> float:
    """
    Yahoo Finance மூலம் நேரலை நாணய மாற்று விகிதத்தை (INR-க்கு) எடுக்கும்.
    """
    if not currency or not isinstance(currency, str):
        return 83.5  # Fallback rate

    curr = currency.upper().strip()
    
    if curr in FX_CACHE:
        return FX_CACHE[curr]

    try:
        pair_symbol = f"{curr}INR=X"
        fx_data = yf.Ticker(pair_symbol)
        price = fx_data.info.get('regularMarketPrice') or fx_data.info.get('previousClose')
        
        if price and isinstance(price, (int, float)) and price > 0:
            FX_CACHE[curr] = price
            print(f"🔱 Live FX Fetched: 1 {curr} = {price:.2f} INR")
            return price
    except Exception as e:
        print(f"⚠️ FX Fetch error for {curr}: {e}")

    fallback_rates = {
        'USD': 94.0, 'EUR': 98.5, 'GBP': 115.0, 
        'JPY': 0.58, 'HKD': 12.0, 'BRL': 16.5, 'KRW': 0.065
    }
    return fallback_rates.get(curr, 83.5)


def calculate_mcap_cr(mcap_raw, currency):
    """
    Normalizes local currency market capitalization into INR Crores using live rates.
    """
    if not isinstance(mcap_raw, (int, float)):
        return None

    currency = (currency or 'USD').upper()
    fx_rate = get_live_fx_to_inr(currency)
    mcap_inr = mcap_raw * fx_rate
    return round(mcap_inr / 1e7, 2)


# ------------------------------------------------------------------
# DYNAMIC TICKER GENERATOR
# ------------------------------------------------------------------
def get_all_listed_tickers() -> list:
    all_tickers = set()
    print("🔍 Generating comprehensive list of all listed companies across target countries...")

    # 1. 🇮🇳 INDIA (NSE)
    try:
        nse_url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(nse_url, headers=headers, timeout=10)
        if res.status_code == 200:
            # 🔥 pd.compat.StringIO-க்கு பதிலாக io.StringIO பயன்படுத்தப்பட்டுள்ளது
            df_nse = pd.read_csv(io.StringIO(res.text))
            nse_symbols = [f"{sym}.NS" for sym in df_nse['SYMBOL'].dropna().unique()]
            all_tickers.update(nse_symbols)
            print(f"  🇮🇳 Loaded {len(nse_symbols)} Indian stocks (NSE)")
    except Exception as e:
        print(f"  ⚠️ India NSE fetch warning: {e}")

    # 2. 🇺🇸 UNITED STATES (SEC JSON API)
    try:
        us_url = "https://www.sec.gov/files/company_tickers.json"
        headers = {'User-Agent': 'FinancialApp admin@mycompany.com'}
        res = requests.get(us_url, headers=headers, timeout=10)
        if res.status_code == 200:
            us_data = res.json()
            us_symbols = [str(item['ticker']).strip().upper() for item in us_data.values() if '^' not in str(item['ticker']) and '.' not in str(item['ticker'])]
            all_tickers.update(us_symbols)
            print(f"  🇺🇸 Loaded {len(us_symbols)} US stocks")
    except Exception as e:
        print(f"  ⚠️ US fetch warning: {e}")

    # 3. 🇨🇳 CHINA & HONG KONG (.HK)
    try:
        hk_symbols = [f"{str(i).zfill(4)}.HK" for i in range(1, 3000)]
        all_tickers.update(hk_symbols)
        print(f"  🇨🇳 Loaded {len(hk_symbols)} Hong Kong listed tickers")
    except Exception as e:
        print(f"  ⚠️ HK fetch warning: {e}")

    # 4. 🇯🇵 JAPAN (.T)
    try:
        jp_symbols = [f"{i}.T" for i in range(1301, 9999, 3)]
        all_tickers.update(jp_symbols)
        print(f"  🇯🇵 Generated Tokyo Stock Exchange tickers")
    except Exception as e:
        print(f"  ⚠️ Japan fetch warning: {e}")

    # 5. 🇩🇪 GERMANY (.DE)
    try:
        de_url = "https://raw.githubusercontent.com/stefan-j/stock-market-germany/master/data/dax.csv"
        df_de = pd.read_csv(de_url)
        de_symbols = [f"{sym}.DE" for sym in df_de['Ticker'].dropna().unique()]
        all_tickers.update(de_symbols)
        print(f"  🇩🇪 Loaded {len(de_symbols)} German equities")
    except Exception:
        fallback_de = ["ADS.DE", "ALV.DE", "BAS.DE", "BAYN.DE", "BMW.DE", "MBG.DE", "SAP.DE", "SIE.DE", "VOW3.DE"]
        all_tickers.update(fallback_de)
        print(f"  🇩🇪 Loaded German fallback tickers")

    # 6. 🇧🇷 BRAZIL (.SA)
    try:
        br_symbols = [
            "VALE3.SA", "PETR4.SA", "ITUB4.SA", "PETR3.SA", "BBDC4.SA", "BBAS3.SA", 
            "WEGE3.SA", "ABEV3.SA", "ITSA4.SA", "RENT3.SA", "B3SA3.SA", "SUZB3.SA"
        ]
        all_tickers.update(br_symbols)
        print(f"  🇧🇷 Loaded {len(br_symbols)} Brazilian tickers")
    except Exception as e:
        print(f"  ⚠️ Brazil fetch warning: {e}")

    # 7. 🇰🇷 SOUTH KOREA (.KS)
    try:
        fallback_kr = [f"{str(i).zfill(6)}.KS" for i in range(5930, 95000, 100)]
        all_tickers.update(fallback_kr)
        print(f"  🇰🇷 Loaded South Korean tickers")
    except Exception as e:
        print(f"  ⚠️ South Korea fetch warning: {e}")

    print(f"\n📊 Total Unique Global Tickers Queue: {len(all_tickers)}\n")
    return list(all_tickers)


# ------------------------------------------------------------------
# SINGLE TICKER FETCH WORKER (Safe Rate Limited)
# ------------------------------------------------------------------
def fetch_single_ticker(symbol: str):
    try:
        time.sleep(0.3)  # Block ஆகாமல் இருக்க சிறு தாமதம்
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}

        price = info.get('currentPrice') or info.get('regularMarketPrice')
        company_name = info.get('longName') or info.get('shortName')

        if not price and not company_name:
            return None

        currency = info.get('currency', 'USD')
        mcap_raw = info.get('marketCap')
        market_cap_cr = calculate_mcap_cr(mcap_raw, currency)

        inst_holding = info.get('heldPercentInstitutions')
        fii_holding = round(inst_holding * 100, 2) if isinstance(inst_holding, (int, float)) else None

        return {
            "symbol": symbol,
            "name": company_name or symbol,
            "sector": info.get('sector'),
            "industry": info.get('industry'),
            "country": info.get('country'),
            "price": round(price, 2) if isinstance(price, (int, float)) else None,
            "pb_ratio": round(info.get('priceToBook'), 2) if isinstance(info.get('priceToBook'), (int, float)) else None,
            "pe_ratio": round(info.get('trailingPE'), 2) if isinstance(info.get('trailingPE'), (int, float)) else None,
            "peg_ratio": round(info.get('pegRatio'), 2) if isinstance(info.get('pegRatio'), (int, float)) else None,
            "market_cap_cr": market_cap_cr,
            "fii_holding": fii_holding
        }
    except Exception:
        return None


# ------------------------------------------------------------------
# PIPELINE EXECUTION
# ------------------------------------------------------------------
def fetch_and_update_all_stocks():
    existing_symbols = set()
    try:
        # Supabase Pagination மூலம் அனைத்து 14,000+ பங்குகளையும் எடுக்கிறோம்
        page_size = 1000
        start = 0
        while True:
            res = supabase.table("global_stocks").select("symbol").range(start, start + page_size - 1).execute()
            data = res.data or []
            if not data:
                break
            for item in data:
                if item.get('symbol'):
                    existing_symbols.add(item['symbol'].upper())
            start += page_size

        print(f"📦 Currently in Supabase DB: {len(existing_symbols)} stocks")
    except Exception as e:
        print(f"⚠️ Could not query existing stocks: {e}")

    # அனைத்து உலகளாவிய பங்குகளையும் எடுத்தல்
    all_market_tickers = get_all_listed_tickers()
    
    # 🔥 ஏற்கனவே DB-யில் உள்ள பங்குகளைத் தவிர்த்து, மீதமுள்ளவை மட்டும் வடிகட்டப்படுகின்றன
    tickers_to_process = [sym for sym in all_market_tickers if sym.upper() not in existing_symbols]
    
    print(f"🚀 Found {len(all_market_tickers)} total tickers.")
    print(f"🎯 Remaining tickers to fetch: {len(tickers_to_process)} companies...\n")

    if not tickers_to_process:
        print("🎉 All companies are already fetched and up to date!")
        return

    batch_size = 30
    buffer_records = []
    processed_count = 0
    MAX_WORKERS = 3

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ticker = {executor.submit(fetch_single_ticker, sym): sym for sym in tickers_to_process}

        for future in concurrent.futures.as_completed(future_to_ticker):
            processed_count += 1
            symbol = future_to_ticker[future]
            try:
                record = future.result()
                if record:
                    buffer_records.append(record)
                    print(f"[{processed_count}/{len(tickers_to_process)}] 🟢 Fetched: {symbol}")
                else:
                    print(f"[{processed_count}/{len(tickers_to_process)}] ⚪ Skipped: {symbol}")
            except Exception as err:
                print(f"[{processed_count}/{len(tickers_to_process)}] 🔴 Error on {symbol}: {err}")

            if len(buffer_records) >= batch_size:
                try:
                    supabase.table("global_stocks").upsert(buffer_records).execute()
                    print(f"\n💾 Saved {len(buffer_records)} stocks to Supabase.\n")
                    buffer_records.clear()
                except Exception as batch_err:
                    print(f"❌ Batch Upsert Error: {batch_err}")
                    buffer_records.clear()

    if buffer_records:
        try:
            supabase.table("global_stocks").upsert(buffer_records).execute()
            print(f"\n💾 Saved remaining {len(buffer_records)} stocks.")
        except Exception as batch_err:
            print(f"❌ Final Batch Upsert Error: {batch_err}")

    print("\n🎉 Remaining market synchronization completed!")
if __name__ == "__main__":
    fetch_and_update_all_stocks()