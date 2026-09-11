import yfinance as yf
import sys
import re
from pathlib import Path

# Project Root மற்றும் Current Directory இரண்டையும் Python Path-இல் சேர்க்கிறோம்
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.append(str(CURRENT_DIR))

# Safe Import Logic for SupabaseManager
SupabaseManager = None
try:
    # 1. Try importing from Root (database.py at root)
    from database import SupabaseManager
except ModuleNotFoundError:
    try:
        # 2. Try importing from services folder (services/database.py)
        from services.database import SupabaseManager
    except ModuleNotFoundError:
        print("⚠️ Warning: SupabaseManager (database.py) could not be loaded. Running without Database cache.")

# Fast-lookup Map with expanded global stocks
FAST_SYMBOL_MAP = {
    # India - IT
    'infosys': 'INFY.NS', 'tcs': 'TCS.NS', 'wipro': 'WIPRO.NS', 'hcltech': 'HCLTECH.NS', 'techm': 'TECHM.NS',
    
    # India - Banking & Financials
    'hdfc': 'HDFCBANK.NS', 'hdfcbank': 'HDFCBANK.NS', 'icici': 'ICICIBANK.NS', 'sbi': 'SBIN.NS', 'sbin': 'SBIN.NS',
    
    # India - Energy, Auto & Others
    'reliance': 'RELIANCE.NS', 'itc': 'ITC.NS', 'tatamotors': 'TATAMOTORS.NS', 'tata motors': 'TATAMOTORS.NS', 
    'adani': 'ADANIPORTS.NS', 'maruti': 'MARUTI.NS',
    
    # US Giants
    'apple': 'AAPL', 'microsoft': 'MSFT', 'google': 'GOOGL', 'alphabet': 'GOOGL',
    'amazon': 'AMZN', 'tesla': 'TSLA', 'nvidia': 'NVDA', 'meta': 'META',
    
    # China / Hong Kong
    'alibaba': 'BABA', 'tencent': '0700.HK', 'meituan': '3690.HK', 'baidu': 'BIDU', 
    'xiaomi': '1810.HK', 'jd': 'JD', 'pinduoduo': 'PDD',
    
    # Japan
    'toyota': '7203.T', 'sony': '6758.T', 'keyence': '6861.T', 'softbank': '9984.T', 'tokyo electron': '8035.T',
    
    # Germany
    'sap': 'SAP.DE', 'siemens': 'SIE.DE', 'volkswagen': 'VOW3.DE', 'allianz': 'ALV.DE', 'basf': 'BAS.DE',
    
    # Brazil
    'petrobras': 'PETR4.SA', 'vale': 'VALE3.SA', 'itau': 'ITUB4.SA', 'nu bank': 'NU', 'ambev': 'ABEV3.SA',
    
    # South Korea
    'samsung': '005930.KS', 'sk hynix': '000660.KS', 'hyundai': '005380.KS', 'naver': '035420.KS', 'lg energy': '373220.KS'
}

SECTOR_KEYWORDS = [
    "it", "tech", "technology", "pharma", "pharmaceuticals", "health", "healthcare",
    "bank", "banking", "finance", "auto", "automobile", "fmcg", "energy", "power",
    "china", "chinese", "japan", "japanese", "germany", "german", "brazil", "brazilian", "korea", "korean",
    "மருந்து", "வங்கி", "ஐடி", "நிதி", "ஆற்றல்", "நுகர்வோர்"
]

def detect_symbol_in_text(text: str) -> str:
    if not text:
        return ""
        
    clean_text = text.lower().strip()

    for name, symbol in FAST_SYMBOL_MAP.items():
        if name in clean_text:
            return symbol

    if any(keyword == clean_text or f" {keyword} " in f" {clean_text} " for keyword in SECTOR_KEYWORDS):
        return ""

    try:
        words = clean_text.split()
        query = words[0] if len(words) > 0 else clean_text
        search_results = yf.Search(query, max_results=3).quotes
        
        if search_results:
            return search_results[0].get('symbol', '')
    except Exception:
        pass

    return ""

def get_global_symbol(symbol: str) -> str:
    if not symbol:
        return ""
        
    symbol = symbol.strip().upper()

    global_suffixes = ['.NS', '.BO', '.HK', '.SS', '.SZ', '.DE', '.F', '.T', '.SA', '.KS', '.KQ', '.L', '.TW']
    if any(symbol.endswith(ext) for ext in global_suffixes) or '^' in symbol or '-' in symbol:
        return symbol

    for name, mapped_symbol in FAST_SYMBOL_MAP.items():
        if symbol == name.upper() or symbol == mapped_symbol.upper():
            return mapped_symbol

    try:
        test_ticker = yf.Ticker(symbol)
        if test_ticker.info and test_ticker.info.get('regularMarketPrice'):
            return symbol
    except Exception:
        pass

    return f"{symbol}.NS"

def fetch_stock_data(symbol: str) -> dict:
    if not symbol:
        return {"error": "செல்லுபடியாகும் பங்கு குறியீடு (Symbol) வழங்கப்படவில்லை."}

    formatted_symbol = get_global_symbol(symbol)
    ticker_obj = yf.Ticker(formatted_symbol)
    info = ticker_obj.info or {}

    if not info or not (info.get('currentPrice') or info.get('regularMarketPrice')):
        if formatted_symbol.endswith('.NS'):
            fallback_symbol = formatted_symbol.replace('.NS', '.BO')
            ticker_obj = yf.Ticker(fallback_symbol)
            info = ticker_obj.info or {}
            if info:
                formatted_symbol = fallback_symbol

    if not info or not (info.get('currentPrice') or info.get('regularMarketPrice')):
        try:
            search_res = yf.Search(symbol, max_results=1).quotes
            if search_res:
                formatted_symbol = search_res[0].get('symbol')
                ticker_obj = yf.Ticker(formatted_symbol)
                info = ticker_obj.info or {}
        except Exception:
            pass

    if not info or not (info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')):
        return {"error": f"'{symbol}' நிறுவனத்திற்கான தரவுகள் சந்தையில் கிடைக்கவில்லை அல்லது தவறான குறியீடு."}

    try:
        current = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose') or 0
        previous = info.get('previousClose') or info.get('regularMarketPreviousClose') or 0
        change_pct = round(((current - previous) / previous) * 100, 2) if current and previous else 0

        market_cap = info.get('marketCap', 'N/A')
        shares_outstanding = info.get('sharesOutstanding', 0)
        total_assets = info.get('totalAssets', 0)
        total_debt = info.get('totalDebt', 0)
        nav = (total_assets - total_debt) / shares_outstanding if shares_outstanding else 0

        div_yield = info.get('dividendYield', 0.0)
        div_yield_pct = f"{round(div_yield * 100, 2)}%" if isinstance(div_yield, (int, float)) and div_yield < 1.0 else f"{round(div_yield, 2)}%" if isinstance(div_yield, (int, float)) else "N/A"

        pe = round(info.get('trailingPE', 0), 2) if info.get('trailingPE') else 'N/A'
        forward_pe = round(info.get('forwardPE', 0), 2) if info.get('forwardPE') else 'N/A'
        peg = round(info.get('pegRatio', 0), 2) if info.get('pegRatio') else 'N/A'
        roe = round(info.get('returnOnEquity', 0) * 100, 2) if info.get('returnOnEquity') else 'N/A'
        roce = round(info.get('returnOnAssets', 0) * 100, 2) if info.get('returnOnAssets') else 'N/A'
        fcf = info.get('freeCashflow', 'N/A')
        currency = info.get('currency', 'USD')
        currency_symbol = '₹' if currency == 'INR' else '$'

        roe_str = f"{roe}%" if roe != 'N/A' else 'N/A'
        roce_str = f"{roce}%" if roce != 'N/A' else 'N/A'

        if fcf != 'N/A' and isinstance(fcf, (int, float)):
            fcf_formatted = f"{currency_symbol} {fcf / 1e7:.2f} கோடி" if currency == 'INR' else f"{currency_symbol} {fcf / 1e9:.2f} B"
            fcf_text = f"மேலும், {fcf_formatted} மதிப்பிலான சுதந்திர பணப்புழக்கம் நிறுவனத்திற்கு நிதி ரீதியான வலிமையை வழங்குகிறது."
        else:
            fcf_text = "நிறுவனத்தின் பணப்புழக்கம் நிதி ரீதியான தன்மையை நிர்ணயிக்கிறது."

        if pe != 'N/A':
            if isinstance(peg, (int, float)) and peg > 1.5:
                peg_analysis = f"PEG விகிதம் {peg} ஆக இருப்பது, பங்கு சற்றே உயர் மதிப்பீட்டில் உள்ளதைக் காட்டுகிறது."
            elif isinstance(peg, (int, float)) and peg <= 1.5:
                peg_analysis = f"PEG விகிதம் {peg} ஆக இருப்பது, நல்ல வளர்ச்சி வாய்ப்புடன் நியாயமான மதிப்பீட்டில் உள்ளதைக் காட்டுகிறது."
            else:
                peg_analysis = "PEG விகிதம் கிடைக்கப்பெறவில்லை."

            if forward_pe != 'N/A' and isinstance(forward_pe, (int, float)) and isinstance(pe, (int, float)) and forward_pe < pe:
                fpe_analysis = f"இருப்பினும், எதிர்கால P/E {forward_pe} ஆகக் குறைவது அடுத்தடுத்த காலங்களில் வருவாய் வளர்ச்சி மேம்படும் என்பதைக் காட்டுகிறது."
            elif forward_pe != 'N/A':
                fpe_analysis = f"எதிர்கால P/E {forward_pe} ஆக உள்ளது."
            else:
                fpe_analysis = ""

            valuation_analysis_text = f"நிறுவனத்தின் P/E விகிதம் {pe} ஆக இருப்பது நியாயமான மதிப்பீட்டைக் குறிக்கிறது. {peg_analysis} {fpe_analysis}"
        else:
            valuation_analysis_text = "நிறுவனத்தின் P/E தரவுகள் கிடைக்கப்பெறவில்லை."

        analysis_summary = f"""ROE {roe_str} மற்றும் ROCE {roce_str} என்பது நிறுவனம் தனது முதலீடுகளைக்கொண்டு சிறப்பான முறையில் லாபத்தைப் பெருக்குகிறது என்பதைக் காட்டுகிறது. {fcf_text}

மதிப்பீடு மற்றும் எதிர்நோக்கு:
- P/E விகிதம்: {pe}
- PEG விகிதம்: {peg}
- எதிர்கால P/E (Forward PE): {forward_pe}

{valuation_analysis_text}

அபாய எச்சரிக்கை:
இந்தப் பகுப்பாய்வு அறிக்கை நேரலைத் தரவுகளின் அடிப்படையில் மட்டுமே உருவாக்கப்பட்டுள்ளது. இது நேரடியாக முதலீட்டுப் பரிந்துரை அல்ல. பங்குச் சந்தை முதலீடுகள் அபாயங்களுக்கு உட்பட்டவை."""

        return {
            "symbol": formatted_symbol,
            "ticker": symbol.upper(),
            "name": info.get('longName', info.get('shortName', symbol.upper())),
            "company_name": info.get('longName', info.get('shortName', symbol.upper())),
            "currency": currency,
            "exchange": info.get('exchange', 'N/A'),
            "country": info.get('country', 'N/A'),
            "price": round(current, 2) if isinstance(current, (int, float)) else 'N/A',
            "previousClose": round(previous, 2) if isinstance(previous, (int, float)) else 'N/A',
            "changePercent": change_pct,
            "fiftyTwoWeekHigh": info.get('fiftyTwoWeekHigh', 'N/A'),
            "fiftyTwoWeekLow": info.get('fiftyTwoWeekLow', 'N/A'),
            "pe": pe,
            "forwardPe": forward_pe,
            "peg": peg,
            "eps": round(info.get('trailingEps', 0), 2) if info.get('trailingEps') else 'N/A',
            "nav": round(nav, 2) if isinstance(nav, (int, float)) and nav != 0 else 'N/A',
            "marketCap": market_cap,
            "freeCashFlow": fcf,
            "roe": roe,
            "roce": roce,
            "dividendYield": div_yield_pct,
            "sector": info.get('sector', 'N/A'),
            "industry": info.get('industry', 'N/A'),
            "summary": info.get('longBusinessSummary', 'N/A'),
            "analysis_summary": analysis_summary
        }

    except Exception as e:
        return {"error": f"தரவு எடுப்பதில் பிழை ஏற்பட்டது: {str(e)}"}

def get_competitors(sector: str, current_symbol: str) -> list:
    sector_competitors = {
        "Technology": ["INFY.NS", "TCS.NS", "WIPRO.NS", "AAPL", "MSFT", "NVDA", "0700.HK", "SAP.DE", "005930.KS"],
        "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "JPM", "BAC", "ITUB4.SA"],
        "Healthcare": ["SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "PFE", "JNJ"],
        "Consumer Electronics": ["AAPL", "SONY", "6758.T", "6861.T", "005930.KS", "1810.HK"],
        "Automotive": ["TATAMOTORS.NS", "MARUTI.NS", "TSLA", "7203.T", "VOW3.DE", "005380.KS"],
        "Energy": ["RELIANCE.NS", "PETR4.SA", "XOM", "CVX"],
    }
    
    competitors = sector_competitors.get(sector, ["INFY.NS", "TCS.NS", "AAPL", "MSFT", "RELIANCE.NS"])
    return [comp for comp in competitors if comp.upper() != current_symbol.upper()][:4]

get_live_stock_data = fetch_stock_data

class StockService:
    def __init__(self):
        self.db = None
        if SupabaseManager is not None:
            try:
                self.db = SupabaseManager()
            except Exception as e:
                print(f"⚠️ Supabase Init Failed: {e}")

    def fetch_and_cache_stock(self, symbol: str) -> dict:
        data = fetch_stock_data(symbol)
        
        if data and "error" not in data:
            market_cap_val = data.get("marketCap")
            fcf_val = data.get("freeCashFlow")
            
            stock_record = {
                "symbol": data.get("symbol"),
                "name": data.get("name"),
                "country": data.get("country"),
                "exchange": data.get("exchange"),
                "sector": data.get("sector"),
                "industry": data.get("industry"),
                "price": data.get("price") if data.get("price") != 'N/A' else None,
                "pe_ratio": data.get("pe") if data.get("pe") != 'N/A' else None,
                "peg_ratio": data.get("peg") if data.get("peg") != 'N/A' else None,
                "market_cap_cr": round(market_cap_val / 1e7, 2) if isinstance(market_cap_val, (int, float)) else None,
                "free_cashflow_cr": round(fcf_val / 1e7, 2) if isinstance(fcf_val, (int, float)) else None,
            }
            
            if self.db and hasattr(self.db, 'supabase') and self.db.supabase:
                try:
                    self.db.supabase.table("global_stocks").upsert(stock_record).execute()
                except Exception as e:
                    print(f"⚠️ Supabase Caching Error: {e}")
                
        return data

    def get_stock_details(self, symbol: str) -> dict:
        data = self.fetch_and_cache_stock(symbol)
        if "error" in data:
            return data
            
        market_cap_val = data.get("marketCap")
        fcf_val = data.get("freeCashFlow")
        
        market_cap_cr = (market_cap_val / 1e7) if isinstance(market_cap_val, (int, float)) else 0
        free_cashflow_cr = (fcf_val / 1e7) if isinstance(fcf_val, (int, float)) else 0
        
        return {
            "symbol": data.get("symbol"),
            "name": data.get("name"),
            "price": data.get("price"),
            "pe_ratio": data.get("pe"),
            "peg_ratio": data.get("peg"),
            "debt_to_equity": 0,
            "market_cap_cr": round(market_cap_cr, 2),
            "free_cashflow_cr": round(free_cashflow_cr, 2),
            "sector": data.get("sector"),
            "country": data.get("country"),
            "summary": data.get("summary"),
            "analysis_summary": data.get("analysis_summary")
        }

    def analyze_quarterly_results(self, symbol: str) -> dict:
        try:
            formatted_symbol = get_global_symbol(symbol)
            ticker = yf.Ticker(formatted_symbol)
            income_stmt = ticker.quarterly_income_stmt

            if income_stmt is None or income_stmt.empty:
                if self.db and hasattr(self.db, 'get_latest_quarterly_report'):
                    cached_report = self.db.get_latest_quarterly_report(formatted_symbol)
                    if cached_report:
                        return cached_report
                return {"error": "Quarterly data unavailable currently."}

            latest_date = income_stmt.columns[0]
            prev_date = income_stmt.columns[1] if len(income_stmt.columns) > 1 else None

            rev_current = income_stmt.loc['Total Revenue'][latest_date] if 'Total Revenue' in income_stmt.index else 0
            rev_prev = income_stmt.loc['Total Revenue'][prev_date] if prev_date and 'Total Revenue' in income_stmt.index else 0

            net_inc_current = income_stmt.loc['Net Income'][latest_date] if 'Net Income' in income_stmt.index else 0
            net_inc_prev = income_stmt.loc['Net Income'][prev_date] if prev_date and 'Net Income' in income_stmt.index else 0

            rev_growth_qoq = ((rev_current - rev_prev) / rev_prev * 100) if rev_prev else 0
            profit_growth_qoq = ((net_inc_current - net_inc_prev) / net_inc_prev * 100) if net_inc_prev else 0

            sentiment = "NEUTRAL"
            if rev_growth_qoq > 5 and profit_growth_qoq > 10:
                sentiment = "BULLISH"
            elif rev_growth_qoq < -5 or profit_growth_qoq < -10:
                sentiment = "BEARISH"

            report = {
                "symbol": formatted_symbol,
                "quarter_year": str(latest_date.date()),
                "report_date": str(latest_date.date()),
                "revenue": round(rev_current / 1e7, 2),
                "net_profit": round(net_inc_current / 1e7, 2),
                "operating_margin_pct": round((net_inc_current / rev_current * 100), 2) if rev_current else 0,
                "key_highlights": f"Revenue QoQ Growth: {round(rev_growth_qoq, 2)}%, Profit QoQ Growth: {round(profit_growth_qoq, 2)}%",
                "sentiment": sentiment
            }

            if self.db and hasattr(self.db, 'save_quarterly_report'):
                self.db.save_quarterly_report(report)
            return report

        except Exception as e:
            return {"error": f"Error analyzing quarterly earnings: {str(e)}"}

    def screen_global_stocks(self, country=None, sector=None, max_pe=None, min_market_cap=None):
        results = []
        
        if hasattr(self, 'db') and self.db and hasattr(self.db, 'supabase') and self.db.supabase:
            try:
                query = self.db.supabase.table("global_stocks").select("*")
                
                if country:
                    query = query.ilike("country", f"%{country}%")
                if sector:
                    query = query.ilike("sector", f"%{sector}%")
                if max_pe:
                    query = query.lte("pe_ratio", float(max_pe))
                if min_market_cap:
                    query = query.gte("market_cap_cr", float(min_market_cap))
                    
                response = query.execute()
                if response.data:
                    return response.data
            except Exception as e:
                print(f"⚠️ Supabase Screener Error: {e}")

        sample_tickers = [
            "INFY.NS", "TCS.NS", "HDFCBANK.NS", "RELIANCE.NS", "TATAMOTORS.NS",
            "AAPL", "NVDA", "MSFT", "GOOGL", "AMZN",
            "0700.HK", "3690.HK", "1810.HK", "BABA",
            "7203.T", "6758.T", "6861.T",
            "SAP.DE", "SIE.DE", "VOW3.DE",
            "PETR4.SA", "VALE3.SA", "ITUB4.SA",
            "005930.KS", "000660.KS", "005380.KS"
        ]
        
        for symbol in sample_tickers:
            try:
                stock_info = self.fetch_and_cache_stock(symbol)
                
                if not stock_info or "error" in stock_info:
                    continue
                    
                if country and country.lower() not in stock_info.get("country", "").lower():
                    continue
                    
                if sector and sector.lower() not in stock_info.get("sector", "").lower():
                    continue
                    
                pe = stock_info.get("pe")
                if max_pe and (pe == 'N/A' or pe is None or float(pe) > float(max_pe)):
                    continue
                    
                results.append(stock_info)

            except Exception:
                continue

        return results