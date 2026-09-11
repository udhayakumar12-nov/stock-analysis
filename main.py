import os
import re
import json
import sys
from typing import Optional
from fastapi import FastAPI, Query, Form, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from supabase import create_client, Client

# Services Imports
import services.groq_manager as groq_module
from services.stock_service import fetch_stock_data, get_competitors, get_global_symbol, get_live_stock_data, detect_symbol_in_text
from services.news_service import fetch_stock_news, fetch_quarterly_results
from services.link_service import LinkService
from services.ticker_service import get_live_tickers

# AI Service Import (URL analysis, Stock analysis, Camera/Document OCR & AIAgent)
try:
    from services.ai_service import (
        generate_stock_analysis, 
        analyze_url_content, 
        translate_camera_image, 
        translate_uploaded_document,
        AIAgent
    )
except ImportError:
    generate_stock_analysis = None
    analyze_url_content = None
    translate_camera_image = None
    translate_uploaded_document = None
    AIAgent = None

# Config Import
try:
    from config import GROQ_KEYS, GEMINI_API_KEY, BACKEND_URL, SUPABASE_URL, SUPABASE_KEY
    print(f"✅ Loaded {len(GROQ_KEYS)} Groq keys from config.py")
except ImportError:
    GROQ_KEYS = []
    GEMINI_API_KEY = ""
    BACKEND_URL = "http://localhost:8000"
    SUPABASE_URL = "https://tvkveuuvlsxmgtzuwjtm.supabase.co"
    SUPABASE_KEY = "sb_secret_pIp8rwLhiK-u9TJ62Cg48w_1dHct4Yf"

app = FastAPI(title="Stock Analyzer & Content Intelligence API", version="2.0")

# Supabase Client Initialization
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase Client Connected Successfully in main.py")
except Exception as e:
    supabase = None
    print(f"⚠️ Supabase Connection Warning: {e}")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    keys = GROQ_KEYS if GROQ_KEYS else []
    groq_module.init_groq_manager(keys)
    
    # LinkService
    app.state.link_service = LinkService(groq_module.groq_manager)
    print("✅ LinkService initialized")

    # AIAgent
    if AIAgent:
        app.state.ai_agent = AIAgent()
        print("✅ AIAgent initialized")
    else:
        app.state.ai_agent = None

@app.get("/")
def root():
    return {
        "message": "Stock Analyzer & Content API is running!",
        "version": "2.0",
        "status": "success",
        "groq_keys_loaded": len(GROQ_KEYS),
        "groq_manager_ready": groq_module.groq_manager is not None,
        "ai_agent_ready": app.state.ai_agent is not None,
        "supabase_ready": supabase is not None
    }

# ==================== NEW SMART ROUTER FOR CHAT & LINKS ====================

@app.post("/analyze")
async def analyze_request(payload: dict):
    user_input = payload.get("message", "").strip()
    lang = payload.get("lang", "ta")
    stock_data = payload.get("stock_data")
    
    if user_input.startswith("http://") or user_input.startswith("https://"):
        if analyze_url_content:
            return {"response": analyze_url_content(user_input, lang=lang)}
        return {"response": "❌ URL பகுப்பாய்வு சேவை தற்காலிகமாக இயக்கத்தில் இல்லை."}
        
    if stock_data and generate_stock_analysis:
        return {"response": generate_stock_analysis(stock_data, lang=lang)}

    return {"response": "தயவுசெய்து சரியான பங்கு குறியீட்டை அல்லது இணையதள லிங்க்கை வழங்கவும்."}

# ==================== EXISTING STOCK ENDPOINTS ====================

@app.get("/analyze_stock")
async def analyze_stock(symbol: str = Query(...), lang: str = Query("ta")):
    try:
        stock_data = fetch_stock_data(symbol)
        
        if not stock_data or "error" in stock_data:
            raise HTTPException(status_code=400, detail="Stock data not found")
            
        if generate_stock_analysis:
            analysis = generate_stock_analysis(stock_data, lang)
        else:
            manager = groq_module.get_groq_manager()
            query = f"Provide a complete stock analysis for {symbol}"
            analysis = await manager.ask_agent_with_real_data(
                query=query, 
                user_language=lang, 
                stock_data=stock_data
            )
        
        return {
            "status": "success",
            "stock_data": stock_data,
            "analysis": analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/symbol_search")
async def symbol_search(query: str):
    try:
        return {"symbol": get_global_symbol(query)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/stock_news")
async def stock_news(symbol: str, company: str = ""):
    return await fetch_stock_news(symbol, company)

@app.get("/quarterly_results")
async def quarterly_results(symbol: str):
    return await fetch_quarterly_results(symbol)

@app.get("/compare_stocks")
async def compare_stocks(symbols: str = Query(...)):
    sym_list = [s.strip() for s in symbols.split(",")]
    results = {}
    for sym in sym_list:
        results[sym] = fetch_stock_data(sym)
    return results

@app.get("/live_tickers")
async def live_tickers():
    return get_live_tickers()

# ==================== ADVANCED FILTERING & PARSING HELPERS ====================

# SQL-இல் உள்ள 11 துறைகளின் துல்லியமான பெயர் வரைபடம்
SECTOR_MAP = {
    "it": ["Technology"],
    "tech": ["Technology"],
    "technology": ["Technology"],
    "ஐடி": ["Technology"],
    "fmcg": ["Consumer Defensive"],
    "staples": ["Consumer Defensive"],
    "bank": ["Financial Services"],
    "banking": ["Financial Services"],
    "finance": ["Financial Services"],
    "financial": ["Financial Services"],
    "வங்கி": ["Financial Services"],
    "நிதி": ["Financial Services"],
    "power": ["Utilities", "Energy"],
    "utilities": ["Utilities"],
    "energy": ["Energy"],
    "ஆற்றல்": ["Utilities", "Energy"],
    "மின்சாரம்": ["Utilities", "Energy"],
    "auto": ["Consumer Cyclical"],
    "automobile": ["Consumer Cyclical"],
    "cyclical": ["Consumer Cyclical"],
    "pharma": ["Healthcare"],
    "healthcare": ["Healthcare"],
    "health": ["Healthcare"],
    "மருத்துவம்": ["Healthcare"],
    "metal": ["Basic Materials"],
    "materials": ["Basic Materials"],
    "basic materials": ["Basic Materials"],
    "உலோகம்": ["Basic Materials"],
    "telecom": ["Communication Services"],
    "communication": ["Communication Services"],
    "தொலைத்தொடர்பு": ["Communication Services"],
    "real estate": ["Real Estate"],
    "realty": ["Real Estate"],
    "ரியல் எஸ்டேட்": ["Real Estate"],
    "industrial": ["Industrials"],
    "industrials": ["Industrials"],
    "உற்பத்தி": ["Industrials"],
}

_STOCK_INTENT_KEYWORDS = [
    "pe", "p/e", "peg", "pb", "p/b", "holding", "holdings", "fii", "dii", "sector", "screen", 
    "stocks", "stock", "share", "shares", "market cap", "quarterly", "earnings", "dividend", "low pe",
    "பங்கு", "பங்குகள்", "பி/ஈ", "துறை", "காலாண்டு", "முடிவுகள்", "சந்தை மதிப்பு",
    "நிறுவனங்கள்", "வங்கி", "ஐடி", "மின்சாரம்", "ஆற்றல்", "தொலைத்தொடர்பு",
    "எண்ணெய்", "எரிவாயு", "என்பிஎப்சி", "nbfc", "psu", "அரசுத்துறை", "உற்பத்தி",
    "steel", "coal", "நிலக்கரி", "telecom", "oil", "gas", "us", "usa", "india", "indian"
]

# ✅ திருத்தப்பட்டது: "pe/peg/pb/fii/dii" போன்ற metric-words இனி gate
# ஆகாது — "tcs pe ratio" போன்ற single-stock கேள்விகளிலும் "pe" வார்த்தை
# இயல்பாக வரும் என்பதால், அதை bulk-intent எனத் தவறாகக் கருதிவிட்டது.
# இப்போது உண்மையான "பல பங்குகள்" (plural/list) signal words மட்டுமே
# bulk-screening-ஐத் தூண்டும்.
_BULK_LIST_KEYWORDS = [
    "stocks", "companies", "screen", "list", "list out", "sector",
    "பங்குகள்", "நிறுவனங்கள்", "துறை", "small cap", "mid cap",
]

def _has_keyword(text: str, keywords) -> bool:
    """✅ புதிய பொதுவான helper - word-boundary அடிப்படையிலான keyword match."""
    t = text.lower()
    for kw in keywords:
        try:
            if re.search(r'\b' + re.escape(kw) + r'\b', t, flags=re.UNICODE):
                return True
        except re.error:
            if kw in t:
                return True
    return False

def _is_stock_related(text: str) -> bool:
    return _has_keyword(text, _STOCK_INTENT_KEYWORDS)

def detect_requested_sector(query_text: str):
    q = query_text.lower()
    for key, sectors in SECTOR_MAP.items():
        if re.search(r'\b' + re.escape(key) + r'\b', q):
            return sectors
    return None

def detect_country_preference(query_text: str):
    q = query_text.lower()
    if re.search(r'\b(us|usa|american|united states|அமெரிக்க)\b', q):
        return "US"
    elif re.search(r'\b(india|indian|nifty|nse|bse|இந்திய|இந்தியா)\b', q):
        return "INDIA"
    elif re.search(r'\b(china|chinese|hong kong|hk|சீனா)\b', q):
        return "CHINA"
    elif re.search(r'\b(japan|japanese|tokyo|nikkei|ஜப்பான்)\b', q):
        return "JAPAN"
    elif re.search(r'\b(germany|german|dax|ஜெர்மனி)\b', q):
        return "GERMANY"
    elif re.search(r'\b(brazil|brazilian|bovespa|பிரேசில்)\b', q):
        return "BRAZIL"
    elif re.search(r'\b(korea|south korea|korean|kospi|கொரியா)\b', q):
        return "SOUTH_KOREA"
    return None

def extract_metric_value(query_text: str, keywords: list) -> Optional[float]:
    """
    ✅ திருத்தப்பட்டது: "pe under 25", "pe below 30" போன்ற "under/below/
    less than" பதங்களையும் இப்போது பிடிக்கும் (முன்பு "pe<25" style
    நேரடி proximity மட்டும் பிடித்தது; "pe under 25" தவறவிடப்பட்டது,
    தற்செயலாக வேறு எண்ணைப் பிடிக்கும் அபாயம் இருந்தது).
    """
    q = query_text.lower()
    for kw in keywords:
        kw_esc = re.escape(kw)
        # Pattern A: எண் முதலில், keyword பின்னால் (e.g. "25 pe", "25pe")
        m = re.search(r'(\d+(?:\.\d+)?)\s*' + kw_esc + r'\b', q)
        if m:
            return float(m.group(1))
        # Pattern B: keyword முதலில் - "under/below/less than/</=" உடன் அல்லது இல்லாமல்
        m = re.search(
            kw_esc + r'\s*(?:ratio)?\s*(?:is\s*)?(?:under|below|less\s*than|<=?|=)?\s*(\d+(?:\.\d+)?)',
            q
        )
        if m:
            return float(m.group(1))
    return None

def _fetch_all_global_stocks():
    """
    ✅ புதிய helper - CRITICAL FIX.
    Supabase/PostgREST ஒரு .execute() call-இல் DEFAULT-ஆக அதிகபட்சம் 1000
    rows மட்டுமே திருப்பும். update_script.py-இல் நீங்கள் pagination மூலம்
    14,000+ பங்குகளை DB-இல் சேர்க்கிறீர்கள் - ஆனால் இந்த /ai_agent
    endpoint pagination இல்லாமல் ஒரே .execute() அழைத்ததால், table 1000
    rows-க்கு மேல் வளர்ந்தவுடன் பெரும்பாலான பங்குகள் (குறிப்பாக insertion
    order-இல் பிந்தி வந்த Indian/NSE stocks) silently தவிர்க்கப்படும்.
    இதுவே "India/Power sector filter தவறாகக் காட்டுகிறது" எனும் பிழைக்கான
    மிக முக்கியமான காரணமாக இருக்கக்கூடும். update_script.py-இல் உள்ள
    pagination pattern-ஐயே இங்கும் பயன்படுத்துகிறோம்.
    """
    all_rows = []
    page_size = 1000
    start = 0
    while True:
        res = supabase.table("global_stocks") \
            .select("symbol, name, sector, price, pe_ratio, peg_ratio, pb_ratio, fii_holding, dii_holding, market_cap_cr") \
            .range(start, start + page_size - 1) \
            .execute()
        chunk = res.data or []
        if not chunk:
            break
        all_rows.extend(chunk)
        if len(chunk) < page_size:
            break
        start += page_size
    return all_rows

# ==================== REVISED AI AGENT ENDPOINT ====================

@app.post("/ai_agent")
async def ai_agent(query: str = Form(...), lang: str = Form("ta")):
    if groq_module.groq_manager is None:
        return {"response": "AI service not available"}

    try:
        clean_query = query.strip()

        # 1. URL Analysis
        if (clean_query.startswith("http://") or clean_query.startswith("https://")) and analyze_url_content:
            res = analyze_url_content(clean_query, lang=lang)
            return {"response": res}

        # ✅ 2. REGRESSION FIX + இப்போது மேலும் திருத்தப்பட்டது: ஒரு குறிப்பிட்ட
        # நிறுவனத்தின் பெயர்/Symbol கேட்கப்பட்டு, "stocks/companies/sector/list"
        # போன்ற உண்மையான bulk-list signal words இல்லையெனில் (metric words
        # "pe"/"peg" இருந்தாலும் சரி — "tcs pe ratio" இதற்கு உதாரணம்),
        # 300+ பங்குகளின் பட்டியலைக் காட்டாமல் அந்த ஒரு நிறுவனத்தின்
        # நேரடி பகுப்பாய்வையே தரும்.
        if not _has_keyword(clean_query, _BULK_LIST_KEYWORDS):
            symbol = detect_symbol_in_text(clean_query)
            if symbol:
                fetched = fetch_stock_data(symbol)
                if fetched and "error" not in fetched and generate_stock_analysis:
                    return {"response": generate_stock_analysis(fetched, lang=lang)}

        # 3. Supabase Data Retrieval Logic (Sector / Metric Screening)
        if supabase and _is_stock_related(clean_query):
            try:
                # ✅ pagination fix - இனி 1000 rows-க்கு மேலும் முழுமையாக search ஆகும்
                stocks_list = _fetch_all_global_stocks()

                if stocks_list:
                    pe_limit = extract_metric_value(clean_query, ["pe", "p/e"])
                    peg_limit = extract_metric_value(clean_query, ["peg", "peg ratio"])
                    pb_limit = extract_metric_value(clean_query, ["pb", "p/b", "pb ratio"])
                    fii_min = extract_metric_value(clean_query, ["fii", "fii holding", "fii holdings"])
                    dii_min = extract_metric_value(clean_query, ["dii", "dii holding", "dii holdings"])
                    mcap_min = extract_metric_value(clean_query, ["market cap", "mcap", "cap"])

                    # ✅ FIX: "top 5 power stocks under 30 pe" போன்ற வாக்கியங்களில்
                    # numbers[0] ("5") எடுத்தால் தவறு - அது count-ஐக் குறிக்கிறது,
                    # threshold அல்ல. numbers-இல் கடைசி எண்ணே பொதுவாக threshold
                    # ஆக இருக்கும் என்பதால் [-1]-ஐப் பயன்படுத்துகிறோம்.
                    if pe_limit is None and peg_limit is None and pb_limit is None and fii_min is None and dii_min is None and mcap_min is None:
                        numbers = re.findall(r'\b\d+(?:\.\d+)?\b', clean_query)
                        if numbers:
                            pe_limit = float(numbers[-1])
                        elif "low pe" in clean_query.lower() or "குறைந்த" in clean_query.lower():
                            pe_limit = 25.0

                    target_sectors = detect_requested_sector(clean_query)
                    target_country = detect_country_preference(clean_query)

                    # Filtering Logic
                    matched_stocks = []
                    for s in stocks_list:
                        sec = s.get("sector") or ""
                        sym = s.get("symbol") or ""
                        pe = s.get("pe_ratio")
                        peg = s.get("peg_ratio")
                        pb = s.get("pb_ratio")
                        fii = s.get("fii_holding")
                        dii = s.get("dii_holding")
                        mcap = s.get("market_cap_cr")

                        # Sector Check
                        sector_check = True
                        if target_sectors:
                            sector_check = any(ts.lower() == sec.lower() for ts in target_sectors)

                        # Country / Exchange Check using Yahoo Finance market suffixes
                        country_check = True

                        if target_country == "US":
                            country_check = not re.search(r'\.(NS|BO|HK|TW|T|SS|SZ|DE|F|SA|KS|KQ)$', sym, re.IGNORECASE)

                        elif target_country == "INDIA":
                            country_check = sym.upper().endswith(".NS") or sym.upper().endswith(".BO")

                        elif target_country == "CHINA":
                            country_check = bool(re.search(r'\.(HK|SS|SZ|TW)$', sym, re.IGNORECASE))

                        elif target_country == "JAPAN":
                            country_check = sym.upper().endswith(".T")

                        elif target_country == "GERMANY":
                            country_check = sym.upper().endswith(".DE") or sym.upper().endswith(".F")

                        elif target_country == "BRAZIL":
                            country_check = sym.upper().endswith(".SA")

                        elif target_country == "SOUTH_KOREA":
                            country_check = sym.upper().endswith(".KS") or sym.upper().endswith(".KQ")

                        # Numeric Checks
                        pe_check = True if pe_limit is None else (pe is not None and 0 < pe <= pe_limit)
                        peg_check = True if peg_limit is None else (peg is not None and 0 < peg <= peg_limit)
                        pb_check = True if pb_limit is None else (pb is not None and 0 < pb <= pb_limit)
                        fii_check = True if fii_min is None else (fii is not None and fii >= fii_min)
                        dii_check = True if dii_min is None else (dii is not None and dii >= dii_min)
                        mcap_check = True if mcap_min is None else (mcap is not None and mcap >= mcap_min)

                        if sector_check and country_check and pe_check and peg_check and pb_check and fii_check and dii_check and mcap_check:
                            matched_stocks.append(s)

                    if matched_stocks:
                        # ✅ புதியது: சந்தை மதிப்பின்படி வரிசைப்படுத்துதல் (பெரிய
                        # நிறுவனங்கள் முதலில் தெரிய) - முன்பு எந்த வரிசையும் இல்லை.
                        matched_stocks.sort(key=lambda x: x.get("market_cap_cr") or 0, reverse=True)

                        sector_title = f" ({', '.join(target_sectors)} துறை)" if target_sectors else ""
                        country_title = f" [{target_country}]" if target_country else ""
                        
                        filters_desc = []
                        if pe_limit: filters_desc.append(f"P/E < {pe_limit}")
                        if peg_limit: filters_desc.append(f"PEG < {peg_limit}")
                        if pb_limit: filters_desc.append(f"P/B < {pb_limit}")
                        if fii_min: filters_desc.append(f"FII > {fii_min}%")
                        if dii_min: filters_desc.append(f"DII > {dii_min}%")
                        if mcap_min: filters_desc.append(f"M.Cap > {mcap_min}Cr")

                        filter_str = ", ".join(filters_desc) if filters_desc else "அனைத்து"

                        output = f"📊 **Supabase தரவுத்தளத்திலிருந்து பெறப்பட்ட பங்குகள்{sector_title}{country_title} [{filter_str}]:**\n\n"
                        output += "| நிறுவனம் / Symbol | Sector | P/E | PEG | P/B | FII (%) | DII (%) | M.Cap (Cr) |\n"
                        output += "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n"
                        
                        for s in matched_stocks[:20]:
                            name = s.get('name') or s.get('symbol')
                            sec_val = s.get('sector') or '-'
                            pe_val = round(s.get('pe_ratio'), 2) if s.get('pe_ratio') is not None else '-'
                            peg_val = round(s.get('peg_ratio'), 2) if s.get('peg_ratio') is not None else '-'
                            pb_val = round(s.get('pb_ratio'), 2) if s.get('pb_ratio') is not None else '-'
                            fii_val = round(s.get('fii_holding'), 2) if s.get('fii_holding') is not None else '-'
                            dii_val = round(s.get('dii_holding'), 2) if s.get('dii_holding') is not None else '-'
                            mcap_val = round(s.get('market_cap_cr'), 2) if s.get('market_cap_cr') is not None else '-'

                            output += f"| **{name}** ({s['symbol']}) | {sec_val} | {pe_val} | {peg_val} | {pb_val} | {fii_val} | {dii_val} | {mcap_val} |\n"

                        output += f"\n\n*மொத்தம் {len(matched_stocks)} பங்குகள் கண்டறியப்பட்டுள்ளன.*"
                        return {"response": output}
                    else:
                        return {"response": "❌ மன்னிக்கும்! நீங்கள் கேட்ட அளவுகோல்களுக்கு ஏற்ப பங்குகள் எதுவும் Supabase தரவுத்தளத்தில் கண்டறியப்படவில்லை."}

            except Exception as db_err:
                print(f"⚠️ Supabase Retrieval Error: {db_err}")

        # 4. General Chat Fallback
        response = await groq_module.groq_manager.ask_agent(clean_query, lang, stock_data=None)
        return {"response": response}

    except Exception as e:
        return {"response": f"❌ Backend Error: {str(e)}"}

@app.post("/agent_chat")
async def agent_chat(query: str = Form(...)):
    if not app.state.ai_agent:
        return {"response": "❌ AIAgent சேவை இயக்கப்படவில்லை."}
    
    try:
        res = app.state.ai_agent.process_user_query(query)
        return {"response": res}
    except Exception as e:
        return {"response": f"❌ AIAgent பிழை: {str(e)}"}

@app.post("/analyze_stock_details")
async def analyze_stock_details(symbol: str = Form(...), stock_data: str = Form(...), lang: str = Form("ta")):
    try:
        data = json.loads(stock_data)
        
        if generate_stock_analysis:
            analysis = generate_stock_analysis(data, lang)
        elif groq_module.groq_manager:
            analysis = await groq_module.groq_manager.analyze_stock(symbol, data, lang)
        else:
            analysis = "AI service not available"
            
        return {"analysis": analysis}
    except Exception as e:
        return {"error": str(e)}

@app.post("/compare_stocks_ai")
async def compare_stocks_ai(stocks: str = Form(...), lang: str = Form("ta")):
    if groq_module.groq_manager is None:
        return {"comparison": "AI not available"}
    try:
        stocks_data = json.loads(stocks)
        comparison = await groq_module.groq_manager.compare_stocks(stocks_data, lang)
        return {"comparison": comparison}
    except Exception as e:
        return {"error": str(e)}

@app.post("/market_sentiment")
async def market_sentiment(market_data: str = Form(...), lang: str = Form("ta")):
    if groq_module.groq_manager is None:
        return {"sentiment": "AI not available"}
    try:
        sentiment = await groq_module.groq_manager.get_market_sentiment(market_data, lang)
        return {"sentiment": sentiment}
    except Exception as e:
        return {"error": str(e)}

# ==================== LINK SUMMARIZATION ====================

@app.post("/summarize_link")
async def summarize_link(
    url: str = Form(...), 
    target_lang: str = Form("ta"), 
    link_type: str = Form("website")
):
    try:
        service = app.state.link_service
        result = ""
        
        if link_type == "youtube":
            result = await service.summarize_youtube(url, target_lang)
        elif link_type == "twitter":
            result = await service.summarize_tweet(url, target_lang)
        else:
            result = await service.summarize_website(url, target_lang)
        
        if result.startswith("⚠️") or result.startswith("❌"):
            return {
                "success": False,
                "summary": result,
                "error": result
            }
        
        return {
            "success": True,
            "summary": result,
            "link_type": link_type,
            "target_lang": target_lang
        }
        
    except Exception as e:
        return {
            "success": False,
            "summary": f"❌ Error: {str(e)}",
            "error": str(e)
        }

# ==================== DOCUMENT TRANSLATION ====================

@app.post("/translate_camera_image")
async def api_translate_camera_image(
    file: UploadFile = File(...),
    lang: str = Form("ta")
):
    if not translate_camera_image:
        return {"success": False, "error": "Camera translation service unavailable"}

    try:
        contents = await file.read()
        result = translate_camera_image(contents, lang=lang)
        return {"success": True, "translation": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/translate_document_upload")
async def api_translate_document_upload(
    file: UploadFile = File(...),
    lang: str = Form("ta")
):
    if not translate_uploaded_document:
        return {"success": False, "error": "Document translation service unavailable"}

    try:
        contents = await file.read()
        result = translate_uploaded_document(contents, file.filename, lang=lang)
        return {"success": True, "translation": result, "filename": file.filename}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==================== CLI INTERFACE MAIN FUNCTION ====================

def main():
    if not AIAgent:
        print("❌ AIAgent வகுப்பு கிடைக்கவில்லை. services/ai_service.py கோப்பைச் சரிபார்க்கவும்.")
        return

    agent = AIAgent()
    print("🤖 AI Stock Intelligence System (Global + Supabase) தயார் நிலையில் உள்ளது!")
    print("விருப்பமான கேள்விகளைக் கேட்கவும்...\n")

    while True:
        try:
            user_input = input("பயனர்: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "முடிவு"]:
                print("👋 நன்றி! வெளியேறுகிறது...")
                break
            
            response = agent.process_user_query(user_input)
            print(f"\nAI: {response}\n" + "-"*50)
        except KeyboardInterrupt:
            print("\n👋 வெளியேறுகிறது...")
            break
        except Exception as e:
            print(f"\n❌ பிழை ஏற்பட்டது: {e}\n" + "-"*50)

if __name__ == "__main__":
    main()