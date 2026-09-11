import yfinance as yf
import pandas as pd
from supabase import create_client, Client
import time
from datetime import datetime

# 1. Supabase Credentials
SUPABASE_URL = "https://tvkveuuvlsxmgtzuwjtm.supabase.co"
SUPABASE_KEY = "sb_secret_pIp8rwLhiK-u9TJ62Cg48w_1dHct4Yf"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. 1,000+ இந்திய பங்குகளைத் தானாகப் பெறுதல் (Dynamic Fetch)
# ==========================================
def get_indian_tickers():
    print("📥 Nifty 500 & MidSmallCap பட்டியலை இணையத்திலிருந்து பெறுகிறது...")
    try:
        # Nifty 500 CSV மூலம் 500 பங்குகளின் Tickers பெறப்படுகிறது
        url_nifty500 = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        df = pd.read_csv(url_nifty500)
        indian_symbols = [f"{symbol}.NS" for symbol in df['Symbol'].tolist()]
        print(f"✅ Nifty 500-லிருந்து {len(indian_symbols)} பங்குகள் பெறப்பட்டன!")
        return indian_symbols
    except Exception as e:
        print(f"⚠️ Dynamic Fetch தோல்வி, fallback பட்டியலைப் பயன்படுத்துகிறது: {e}")
        # எமர்ஜென்சி Backup பட்டியல்
        return [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "INFY.NS", "ITC.NS", "SBIN.NS",
            "LTIM.NS", "LT.NS", "HINDUNILVR.NS", "AXISBANK.NS", "KOTAKBANK.NS", "SUNPHARMA.NS", "TATAMOTORS.NS",
            "MARUTI.NS", "NTPC.NS", "ULTRACEMCO.NS", "TITAN.NS", "POWERGRID.NS", "BAJFINANCE.NS", "M&M.NS",
            "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS", "TATASTEEL.NS", "ASIANPAINT.NS", "HCLTECH.NS",
            "NESTLEIND.NS", "BAJAJFINSV.NS", "GRASIM.NS", "ONGC.NS", "TECHM.NS", "WIPRO.NS", "JSWSTEEL.NS",
            "BRITANNIA.NS", "HDFCLIFE.NS", "SBILIFE.NS", "DRREDDY.NS", "EICHERMOT.NS", "TATACONSUM.NS",
            "DIVISLAB.NS", "CIPLA.NS", "APOLLOHOSP.NS", "HEROMOTOCO.NS", "BPCL.NS", "BEL.NS", "TRENT.NS",
            "VBL.NS", "HAL.NS", "DLF.NS", "CHOLAFIN.NS", "SIEMENS.NS", "PIDILITIND.NS", "ABB.NS", "IOC.NS"
        ]

# ==========================================
# 3. Global Stocks Map
# ==========================================
GLOBAL_STOCKS_MAP = {
    "India": get_indian_tickers(),
    "USA": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "V", "UNH", "PG", "HD", "MA", "BAC", "XOM", "DIS", "PFE", "KO", "CSCO"],
    "China": ["0700.HK", "9988.HK", "3690.HK", "0941.HK", "1398.HK", "0939.HK", "2318.HK", "1810.HK", "9888.HK", "1211.HK"],
    "Japan": ["7203.T", "6758.T", "9984.T", "6861.T", "8306.T", "7267.T", "6501.T", "7751.T", "8035.T", "4063.T"],
    "Germany": ["SAP.DE", "SIE.DE", "ALV.DE", "DT.DE", "VOW3.DE", "MBG.DE", "BMW.DE", "BAS.DE", "BAYN.DE", "ADS.DE"],
    "Brazil": ["VALE3.SA", "PETR4.SA", "ITUB4.SA", "BBDC4.SA", "ABEV3.SA", "BBAS3.SA", "WEGE3.SA", "RENT3.SA"],
    "Taiwan": ["2330.TW", "2454.TW", "2317.TW", "2308.TW", "2382.TW", "2881.TW", "2882.TW", "2412.TW"],
    "South Korea": ["005930.KS", "000660.KS", "005380.KS", "005935.KS", "068270.KS", "000270.KS", "051910.KS", "035420.KS"]
}

# ==========================================
# 4. Bulk Upload Logic
# ==========================================
def start_massive_upload():
    print("🚀 1,000+ பங்குகள் பதிவேற்றத் தொடங்குகின்றன...\n")
    
    total_success = 0
    total_errors = 0

    for country, symbols in GLOBAL_STOCKS_MAP.items():
        print(f"\n📁 நாடு: {country} (மொத்தம்: {len(symbols)} பங்குகள்)")

        for index, symbol in enumerate(symbols, 1):
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info or {}

                price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
                if not price:
                    print(f"  [{index}/{len(symbols)}] ⚠️ Skipping {symbol}: No Price Data")
                    continue

                is_inr = symbol.endswith('.NS') or symbol.endswith('.BO')
                mcap = info.get('marketCap', 0)
                mcap_cr = round((mcap / 1e7) if is_inr else (mcap / 1e6), 2)
                fcf = info.get('freeCashflow', 0)
                fcf_cr = round((fcf / 1e7) if is_inr else (fcf / 1e6), 2)

                inst_holding = info.get('heldPercentInstitutions')
                inst_holding_pct = round(inst_holding * 100, 2) if inst_holding else None

                # 1. global_stocks Data Payload
                global_stock_payload = {
                    "symbol": symbol,
                    "name": info.get('longName', info.get('shortName', symbol)),
                    "country": country,
                    "exchange": info.get('exchange', 'NSE' if is_inr else 'GLOBAL'),
                    "sector": info.get('sector', 'N/A'),
                    "industry": info.get('industry', 'N/A'),
                    "price": round(price, 2),
                    "pe_ratio": round(info.get('trailingPE'), 2) if info.get('trailingPE') else None,
                    "peg_ratio": round(info.get('pegRatio'), 2) if info.get('pegRatio') else None,
                    "debt_to_equity": round(info.get('debtToEquity'), 2) if info.get('debtToEquity') else None,
                    "market_cap_cr": mcap_cr,
                    "free_cashflow_cr": fcf_cr,
                    "institutional_holding_pct": inst_holding_pct,
                    "revenue_growth_pct": round(info.get('revenueGrowth', 0) * 100, 2) if info.get('revenueGrowth') else None,
                    "last_updated": datetime.now().isoformat()
                }

                # Supabase Upsert global_stocks
                supabase.table("global_stocks").upsert(global_stock_payload).execute()

                # 2. quarterly_reports Data Payload (Q1-2027 Financials)
                q_stmt = ticker.quarterly_income_stmt
                if q_stmt is not None and not q_stmt.empty:
                    latest_date = q_stmt.columns[0]
                    revenue = q_stmt.loc['Total Revenue'][latest_date] if 'Total Revenue' in q_stmt.index else 0
                    net_profit = q_stmt.loc['Net Income'][latest_date] if 'Net Income' in q_stmt.index else 0

                    rev_cr = round((revenue / 1e7) if is_inr else (revenue / 1e6), 2)
                    profit_cr = round((net_profit / 1e7) if is_inr else (net_profit / 1e6), 2)

                    quarterly_payload = {
                        "symbol": symbol,
                        "quarter_year": "Q1-2027",
                        "report_date": "2026-06-30",
                        "revenue": rev_cr,
                        "net_profit": profit_cr,
                        "eps": round(info.get('trailingEps', 0), 2),
                        "operating_margin_pct": round((profit_cr / rev_cr * 100), 2) if rev_cr else 0,
                        "key_highlights": "Q1 FY2027 Official Financial Performance Report",
                        "sentiment": "Positive" if profit_cr > 0 else "Neutral"
                    }

                    # Supabase Upsert quarterly_reports
                    supabase.table("quarterly_reports").upsert(quarterly_payload).execute()

                print(f"  [{index}/{len(symbols)}] ✅ Saved: {symbol:12} | P/E: {global_stock_payload['pe_ratio']} | Q1-2027 Updated")
                total_success += 1

            except Exception as e:
                print(f"  [{index}/{len(symbols)}] ❌ Error uploading {symbol}: {e}")
                total_errors += 1

            # yfinance IP Rate limit தவிர்க்க சிறிய இடைவெளி
            time.sleep(0.2)

    print(f"\n🎉 அனைத்துப் பணிகளும் முடிந்தன! வெற்றி: {total_success} | தோல்வி: {total_errors}")

if __name__ == "__main__":
    start_massive_upload()