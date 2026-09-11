import os
import re
import io
import requests
from bs4 import BeautifulSoup
from groq import Groq
from PIL import Image

# புதிய Gemini SDK இறக்குமதி
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

# Stock Service இறக்குமதி
try:
    from stock_service import StockService, FAST_SYMBOL_MAP
except ImportError:
    StockService = None
    FAST_SYMBOL_MAP = {}

# Config இறக்குமதி
try:
    import config
    GROQ_KEYS = getattr(config, 'GROQ_KEYS', [])
    GROQ_API_KEY = getattr(config, 'GROQ_API_KEY', '')
    GEMINI_API_KEY = getattr(config, 'GEMINI_API_KEY', '')
except ImportError:
    GROQ_KEYS = []
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Gemini Client Initialization (New SDK Format)
gemini_client = None
if GEMINI_API_KEY and genai:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"⚠️ Gemini Client Initialization Error: {e}")

# ⚠️ மாற்றப்படவில்லை - அதே model
GROQ_MODEL = 'qwen/qwen3.8-27b'

LANG_NAMES = {
    'ta': 'Tamil', 'hi': 'Hindi', 'en': 'English', 'kn': 'Kannada',
    'mr': 'Marathi', 'te': 'Telugu', 'ml': 'Malayalam', 'bn': 'Bengali',
    'gu': 'Gujarati', 'or': 'Odia', 'as': 'Assamese', 'pa': 'Punjabi',
    'ur': 'Urdu', 'sa': 'Sanskrit', 'ne': 'Nepali',
}

def clean_key(key_str: str) -> str:
    """API Key-இல் உள்ள தேவையற்ற Quotes/Spaces-ஐ அகற்றும்"""
    if not key_str:
        return ""
    match = re.search(r'gsk_[A-Za-z0-9]+', str(key_str))
    if match:
        return match.group(0)
    return ""

def extract_working_keys():
    """config.py-இல் உள்ள அனைத்து Format-களில் இருந்தும் சுத்தமான API Keys-ஐ மட்டும் எடுக்கும்"""
    keys = []
    if isinstance(GROQ_KEYS, list):
        for item in GROQ_KEYS:
            cleaned = clean_key(item)
            if cleaned and cleaned not in keys:
                keys.append(cleaned)

    if isinstance(GROQ_API_KEY, str):
        cleaned = clean_key(GROQ_API_KEY)
        if cleaned and cleaned not in keys:
            keys.append(cleaned)

    return keys

def fetch_url_content(url: str) -> str:
    """URL-லிருந்து நேரலை உரையை மட்டும் பிரித்தெடுக்கும் செயல்பாடு"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            response.encoding = response.apparent_encoding or 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                script.extract()
            paragraphs = soup.find_all(['p', 'h1', 'h2', 'h3'])
            text = ' '.join([p.get_text().strip() for p in paragraphs if p.get_text().strip()])
            return text[:4000]
        return ""
    except Exception as e:
        print(f"URL Fetch Error: {e}")
        return ""

def generate_stock_analysis(stock_data: dict, lang: str = 'ta') -> str:
    """உள்ளூர் / அடிப்படை பங்குச் சந்தை தரவை பகுப்பாய்வு செய்யும் சேவை"""
    target_language = LANG_NAMES.get(lang, 'Tamil')

    if not stock_data or "error" in stock_data:
        return f"பங்கு பகுப்பாய்வு செய்ய முடியவில்லை: {stock_data.get('error', 'தரவு கிடைக்கவில்லை') if stock_data else 'தரவு கிடைக்கவில்லை'}"

    symbol = stock_data.get('symbol', 'N/A')
    name = stock_data.get('company_name', stock_data.get('name', 'N/A'))
    currency = stock_data.get('currency', 'INR')
    curr_symbol = '$' if currency == 'USD' else '₹' if currency == 'INR' else f"{currency} "

    price = stock_data.get('price', 'N/A')
    pe = stock_data.get('pe', stock_data.get('p_e', 'N/A'))
    peg = stock_data.get('peg', 'N/A')
    eps = stock_data.get('eps', 'N/A')
    nav = stock_data.get('nav', 'N/A')
    div_yield = stock_data.get('dividendYield', stock_data.get('dividend_yield', 'N/A'))
    high_52 = stock_data.get('fiftyTwoWeekHigh', stock_data.get('fifty_two_week_high', 'N/A'))
    low_52 = stock_data.get('fiftyTwoWeekLow', stock_data.get('fifty_two_week_low', 'N/A'))
    roe = stock_data.get('roe', 'N/A')
    roce = stock_data.get('roce', 'N/A')
    sector = stock_data.get('sector', 'N/A')
    market_cap = stock_data.get('marketCap', stock_data.get('market_cap', 'N/A'))
    fcf = stock_data.get('freeCashFlow', 'N/A')

    system_prompt = f"""
    You are an expert real-time stock analyst. Using ONLY the LIVE stock market data provided below,
    write a high-quality analysis. NEVER state that you don't have real-time data. Write ENTIRELY in {target_language} (lang: {lang}).

    LIVE MARKET DATA:
    - Company Name: {name} ({symbol})
    - Currency: {currency}
    - Current Price: {curr_symbol}{price}
    - P/E Ratio: {pe} | PEG Ratio: {peg}
    - EPS (TTM): {curr_symbol}{eps} | NAV: {curr_symbol}{nav}
    - Dividend Yield: {div_yield}
    - 52-Week High: {curr_symbol}{high_52} | 52-Week Low: {curr_symbol}{low_52}
    - ROE: {roe}% | ROCE: {roce}%
    - Market Cap: {market_cap} | Free Cash Flow: {fcf}
    - Sector: {sector}

    Provide sections: Market Summary, Fundamental Strength, Valuation & Outlook, Risk Disclaimer.
    """

    api_keys = extract_working_keys()
    if api_keys:
        for key in api_keys:
            try:
                client = Groq(api_key=key, timeout=25.0)
                completion = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": system_prompt}],
                    temperature=0.2,
                    max_tokens=2048,
                )
                res = completion.choices[0].message.content
                if res:
                    return res
            except Exception:
                continue

    return f"""📊 **{name} ({symbol}) - சந்தை பகுப்பாய்வு**

• **தற்போதைய விலை:** {curr_symbol}{price}
• **P/E விகிதம்:** {pe} | **PEG விகிதம்:** {peg}
• **EPS:** {curr_symbol}{eps} | **NAV:** {curr_symbol}{nav}
• **டிவிடெண்ட் ஈட்டம்:** {div_yield}
• **52 வார உச்சம் / குறைந்தபட்சம்:** {curr_symbol}{high_52} / {curr_symbol}{low_52}
• **ROE / ROCE:** {roe}% / {roce}%
• **துறை:** {sector}"""

def generate_global_stock_analysis(stock_data: dict, lang: str = 'ta') -> str:
    """சர்வதேச பங்குச் சந்தை தரவுகளை உயர்தர தொழில்முறை நிதி அறிக்கையாக மாற்றி வழங்கும் செயல்பாடு."""
    target_language = LANG_NAMES.get(lang, 'Tamil')

    if not stock_data or "error" in stock_data:
        return f"பங்கு பகுப்பாய்வு செய்ய முடியவில்லை: {stock_data.get('error', 'தரவு கிடைக்கவில்லை') if stock_data else 'தரவு கிடைக்கவில்லை'}"

    symbol = stock_data.get('symbol', 'N/A')
    name = stock_data.get('company_name', stock_data.get('name', 'N/A'))
    currency = stock_data.get('currency', 'USD')
    country = stock_data.get('country', 'Global')

    curr_map = {'USD': '$', 'INR': '₹', 'EUR': '€', 'JPY': '¥', 'BRL': 'R$', 'HKD': 'HK$'}
    curr_symbol = curr_map.get(currency, f"{currency} ")

    price = stock_data.get('price', 'N/A')
    pe = stock_data.get('pe', 'N/A')
    peg = stock_data.get('peg', 'N/A')
    eps = stock_data.get('eps', 'N/A')
    div_yield = stock_data.get('dividendYield', 'N/A')
    high_52 = stock_data.get('fiftyTwoWeekHigh', 'N/A')
    low_52 = stock_data.get('fiftyTwoWeekLow', 'N/A')
    roe = stock_data.get('roe', 'N/A')
    sector = stock_data.get('sector', 'N/A')
    market_cap = stock_data.get('marketCap', 'N/A')

    system_prompt = f"""
    You are an elite Institutional Global Equity Research Analyst. 
    Write a detailed stock report in {target_language} (language code: {lang}).
    NEVER claim you lack real-time data. You HAVE the live numbers below.

    LIVE MARKET DATA:
    - Company: {name} ({symbol})
    - Country: {country} | Currency: {currency}
    - Price: {curr_symbol}{price} | P/E: {pe} | PEG: {peg}
    - EPS: {curr_symbol}{eps} | Dividend Yield: {div_yield}
    - 52-Week Range: {curr_symbol}{low_52} - {curr_symbol}{high_52}
    - ROE: {roe}% | Sector: {sector} | Market Cap: {market_cap}
    """

    api_keys = extract_working_keys()
    if api_keys:
        for key in api_keys:
            try:
                client = Groq(api_key=key, timeout=25.0)
                completion = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": system_prompt}],
                    temperature=0.2,
                    max_tokens=2048,
                )
                res = completion.choices[0].message.content
                if res:
                    return res
            except Exception:
                continue

    return f"🌐 **{name} ({symbol}) - {country}**\n\n• தற்போதைய விலை: {curr_symbol}{price}\n• P/E விகிதம்: {pe}\n• ROE: {roe}%\n• 52 வார வரம்பு: {curr_symbol}{low_52} - {curr_symbol}{high_52}"

def analyze_url_content(url: str, lang: str = 'ta') -> str:
    """இணையதள லிங்க்கில் உள்ள தரவைப் படித்து முழுமையாகப் பயன்பாட்டு மொழிக்கு நேரடியாக மொழியாக்கம் செய்து வழங்கும் செயல்பாடு."""
    target_language = LANG_NAMES.get(lang, 'Tamil')
    url_text = fetch_url_content(url)

    if not url_text:
        return "இணையதள லிங்க்கிலிருந்து உரையைப் பிரித்தெடுக்க முடியவில்லை. தயவுசெய்து சரியான லிங்க் தானா என்பதைச் சரிபார்க்கவும்."

    # Prompt-இல் 'No Disclaimer' மற்றும் 'Direct Translation' கட்டுப்பாடுகள் சேர்க்கப்பட்டுள்ளன
    system_prompt = f"""
    You are a professional full-text translator.
    Your task is to provide a COMPLETE, FAITHFUL, and ACCURATE TRANSLATION of the provided webpage content into {target_language} (Language code: {lang}).

    STRICT RULES (MUST FOLLOW):
    1. STRICTLY DO NOT add any disclaimers like "I am an AI", "I don't have real-time data", or "This is for informational purposes only".
    2. DO NOT omit any key details, quotes, or statements from the source text.
    3. Translate the entire news/content into {target_language} clearly and accurately while maintaining a natural flow.
    4. Structure the translated response clearly using the following format in {target_language}:

       📰 **முழுமையான செய்தி / நிகழ்வு**
       (Provide the full translated core story here, covering all facts, statements, and quotes mentioned in the original text)

       📌 **முக்கியச் செய்திகள் & மேற்கோள்கள் (Key Highlights & Statements)**
       (List down all important facts, minister/official statements, and key bullet points)

       💡 **பின்னணி மற்றும் சூழல் (Context)**
       (Summarize the event background clearly without adding external AI warnings)

    WEBPAGE CONTENT TO TRANSLATE:
    {url_text}
    """

    api_keys = extract_working_keys()
    if api_keys:
        for key in api_keys:
            try:
                client = Groq(api_key=key, timeout=30.0)
                completion = client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[{"role": "user", "content": system_prompt}],
                    temperature=0.1,  # துல்லியமான மொழிபெயர்ப்பிற்கு 0.1 மிகச் சிறந்தது
                    max_tokens=3500,  # பெரிய செய்தியையும் முழுமையாக மொழியாக்கம் செய்ய அதிக டோக்கன்கள்
                )
                res = completion.choices[0].message.content
                if res:
                    return res
            except Exception as e:
                print(f"Groq Translation Error: {e}")
                continue

    return f"இணைப்பிலிருந்து பெறப்பட்ட தரவு:\n\n{url_text[:500]}..."

# ==================== CAMERA OCR & DOCUMENT TRANSLATION ====================

def translate_camera_image(image_bytes: bytes, lang: str = 'ta') -> str:
    """கேமரா புகைப்படங்கள் அல்லது படக் கோப்புகளில் உள்ள உரையைப் படித்துத் தேர்வுசெய்த மொழியில் மொழிபெயர்க்கும்."""
    if not gemini_client:
        return "❌ Gemini API Key கிடைக்கவில்லை. config.py கோப்பில் GEMINI_API_KEY என்பதைச் சரிபார்க்கவும்."

    target_language = LANG_NAMES.get(lang, 'Tamil')

    try:
        image = Image.open(io.BytesIO(image_bytes))

        prompt = f"""
        Read all the visible text in this image accurately, then translate it completely into {target_language} (language code: {lang}).

        FORMAT:
        - 📝 **கண்டறியப்பட்ட உரை (Extracted Text)**
        - 🔤 **மொழிபெயர்ப்பு ({target_language} Translation)**
        """

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt, image]
        )
        return response.text if response.text else "படத்திலிருந்து உரையைப் படிக்க முடியவில்லை."
    except Exception as e:
        return f"❌ படத்தைப் பகுப்பாய்வு செய்வதில் பிழை ஏற்பட்டது: {str(e)}"

def translate_uploaded_document(file_bytes: bytes, filename: str, lang: str = 'ta') -> str:
    """PDF, Word (DOCX) மற்றும் TXT கோப்புகளை உள்ளூர் மொழியில் மொழிபெயர்க்கும் செயல்பாடு."""
    if not gemini_client:
        return "❌ Gemini API Key கிடைக்கவில்லை. config.py கோப்பில் GEMINI_API_KEY என்பதைச் சரிபார்க்கவும்."

    target_language = LANG_NAMES.get(lang, 'Tamil')
    ext = os.path.splitext(filename)[1].lower()

    try:
        if ext == '.pdf':
            pdf_part = types.Part.from_bytes(
                data=file_bytes,
                mime_type="application/pdf"
            )
            prompt = f"Translate the text content of this PDF file accurately into {target_language}. Maintain structured headings and bullet points."

            response = gemini_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=[pdf_part, prompt]
            )
            return response.text if response.text else "PDF கோப்பில் உரை எதுவும் காணப்படவில்லை."

        else:
            text_content = file_bytes.decode('utf-8', errors='ignore')
            if not text_content.strip():
                return "கோப்பில் படிப்பதற்கான உரை எதுவும் இல்லை."

            prompt = f"Translate the following document content into {target_language}:\n\n{text_content[:8000]}"
            response = gemini_client.models.generate_content(
                model='gemini-2.0-flash',
                contents=prompt
            )
            return response.text if response.text else "மொழிபெயர்ப்பு தோல்வியடைந்தது."

    except Exception as e:
        return f"❌ ஆவணத்தை மொழிபெயர்ப்பதில் பிழை ஏற்பட்டது: {str(e)}"

# ==================== ADVANCED MULTI-SECTOR AI AGENT CLASS ====================

def _kw_match(text: str, keywords) -> bool:
    """
    ✅ புதிய helper function.
    'w in text' (substring) என்பதற்குப் பதிலாக \\b...\\b (word boundary)
    பயன்படுத்தி, "list" -க்குள் "it" போன்ற தற்செயலான பொருத்தங்களைத் தவிர்க்கிறது.
    English மற்றும் Tamil இரண்டு மொழிகளுக்கும் வேலை செய்யும்.
    """
    for w in keywords:
        try:
            pattern = r'\b' + re.escape(w) + r'\b'
            if re.search(pattern, text, flags=re.UNICODE | re.IGNORECASE):
                return True
        except re.error:
            if w in text:
                return True
    return False


def _extract_number_near_keyword(text: str, keyword_pattern: str):
    """
    ✅ புதிய helper function.
    "30 pe", "pe 30", "pe < 30", "pe under 30", "pe below 30" - இந்த
    அனைத்து pattern-களிலிருந்தும் எண்ணை (number) சரியாக பிரித்தெடுக்கும்.
    """
    # Pattern 1: எண் முதலில், keyword பின்னால் (e.g. "30 pe", "30pe")
    m = re.search(r'(\d+(?:\.\d+)?)\s*(?:' + keyword_pattern + r')', text)
    if m:
        return float(m.group(1))

    # Pattern 2: keyword முதலில், எண் பின்னால் - "under/below/less than/<" உடன் அல்லது இல்லாமல்
    m = re.search(
        r'(?:' + keyword_pattern + r')\s*(?:ratio)?\s*(?:is\s*)?(?:under|below|less\s*than|<|=|:)?\s*(\d+(?:\.\d+)?)',
        text
    )
    if m:
        return float(m.group(1))

    return None


# ==================== LIVE WEB SCREENING FALLBACK (NEW) ====================
# Local ticker-list / DB screener இரண்டும் தரவு தராதபோது, Screener.in-இன் public
# "query screen" URL-ஐப் பயன்படுத்தி நேரலையாகத் தேடி, அந்தத் தரவை Groq-க்கு
# அனுப்பி பகுப்பாய்வு செய்யும் fallback. ஏற்கனவே உள்ள fetch_url_content(),
# extract_working_keys(), GROQ_MODEL-ஐயே மறுபயன்படுத்துகிறது.

SECTOR_SCREENER_QUERY_MAP = {
    "Technology": 'Sector = "IT - Software"',
    "Energy": 'Sector = "Power Generation & Distribution"',
    "Oil & Gas": '(Sector = "Refineries" OR Sector = "Oil Drilling And Exploration")',
    "Telecom": 'Sector = "Telecom Services"',
    "Healthcare": 'Sector = "Pharmaceuticals"',
    "Financial Services": '(Sector = "Private Sector Bank" OR Sector = "Public Sector Bank" OR Sector = "Finance")',
    "Consumer Cyclical": 'Sector = "Automobile"',
    "Consumer Defensive": 'Sector = "FMCG"',
    "Basic Materials": '(Sector = "Iron & Steel" OR Sector = "Mining")',
    "Industrials": 'Sector = "Industrial Machinery"',
    "Real Estate": 'Sector = "Real Estate"',
    "PSU": 'Sector = "PSU"',
}

def _build_screener_url(sector_key, max_pe: float) -> str:
    """Screener.in-இன் login தேவையில்லாத 'query screen' URL உருவாக்குதல்."""
    from urllib.parse import quote
    query_parts = [f"Price to Earning < {max_pe}"]
    sector_clause = SECTOR_SCREENER_QUERY_MAP.get(sector_key)
    if sector_clause:
        query_parts.append(sector_clause)
    query_str = " AND ".join(query_parts)
    return f"https://www.screener.in/screen/raw/?query={quote(query_str)}"

def screen_stocks_via_web(sector_key, sector_name_ta: str, max_pe: float, lang: str = 'ta'):
    """
    ✅ புதிய function. Local ticker/DB தரவு கிடைக்காதபோது அழைக்கப்படும் fallback:
    1. Screener.in-இல் இருந்து நேரலையாக உரையை scrape செய்யும்.
    2. அந்த உரையை மட்டுமே ஆதாரமாக வைத்து Groq மூலம் கட்டமைக்கப்பட்ட பட்டியலாகத் தரும்.
    3. தரவு போதுமானதாக இல்லை எனில் None திருப்பும் (caller அடுத்த fallback-க்குச் செல்லும்).

    ⚠️ Screener.in-இன் Terms of Service-ஐ சரிபார்த்துக் கொள்ளவும்; production-இல்
    response-ஐ சிறிது நேரம் cache செய்வது பரிந்துரைக்கப்படுகிறது.
    """
    url = _build_screener_url(sector_key, max_pe)
    page_text = fetch_url_content(url)

    if not page_text or len(page_text.strip()) < 100:
        return None

    target_language = LANG_NAMES.get(lang, 'Tamil')

    system_prompt = f"""
    You are a financial-data extraction assistant. Below is REAL text just scraped
    from a live stock-screener webpage (screener.in), already filtered server-side for:
    Sector related to "{sector_name_ta}" AND P/E ratio < {max_pe}.

    CRITICAL RULES:
    1. Do NOT say you lack live/real-time data — this text IS live, scraped moments ago.
    2. List ONLY company names, symbols, P/E ratio and price that ACTUALLY appear in
       the text below. Never invent or estimate numbers.
    3. If the text does not clearly contain a list of companies with numbers, say so
       honestly in {target_language} and point the user to the source URL instead of
       guessing.
    4. Respond entirely in {target_language} (lang: {lang}) as a clean bullet list.

    SOURCE URL: {url}

    SCRAPED PAGE TEXT:
    {page_text}
    """

    api_keys = extract_working_keys()
    for key in api_keys:
        try:
            client = Groq(api_key=key, timeout=25.0)
            completion = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": system_prompt}],
                temperature=0.1,
                max_tokens=1500,
            )
            res = completion.choices[0].message.content
            if res:
                return res + f"\n\n🔗 மூலம்: {url}"
        except Exception:
            continue

    return None


class AIAgent:
    def __init__(self):
        if StockService:
            try:
                self.stock_service = StockService()
            except Exception:
                self.stock_service = None
        else:
            self.stock_service = None

        # ✅ அனைத்துத் துறைகளுக்குமான Tickers
        # புதிதாகச் சேர்க்கப்பட்டவை: Telecom, Oil & Gas, Industrials/Manufacturing, PSU
        # Financial Services-இல் NBFC keywords சேர்க்கப்பட்டுள்ளது (தனி ticker தேவையில்லை,
        # ஏனெனில் NBFC என்பது Financial Services-இன் உட்பிரிவு)
        self.SECTOR_TICKERS = {
            "Energy": {
                "name_ta": "மின்சாரம் மற்றும் ஆற்றல் (Power & Energy)",
                "keywords": ["power", "energy", "electricity", "மின்சாரம்", "மின்சாரத் துறை", "ஆற்றல்", "எரிசக்தி", "மின் உற்பத்தி"],
                "tickers": ["NTPC.NS", "POWERGRID.NS", "TATAPOWER.NS", "NHPC.NS", "SJVN.NS", "CESC.NS", "TORNTPOWER.NS", "RELIANCE.NS", "ADANIPOWER.NS", "ADANIGREEN.NS"]
            },
            "Oil & Gas": {
                "name_ta": "எண்ணெய் மற்றும் எரிவாயு (Oil & Gas)",
                "keywords": ["oil", "gas", "petroleum", "எண்ணெய்", "எரிவாயு", "பெட்ரோலியம்"],
                "tickers": ["ONGC.NS", "IOC.NS", "BPCL.NS", "HPCL.NS", "GAIL.NS", "OIL.NS", "RELIANCE.NS", "MRPL.NS"]
            },
            "Telecom": {
                "name_ta": "தொலைத்தொடர்பு (Telecom)",
                "keywords": ["telecom", "telecommunication", "தொலைத்தொடர்பு", "டெலிகாம்"],
                "tickers": ["BHARTIARTL.NS", "IDEA.NS", "TATACOMM.NS", "INDUSTOWER.NS", "MTNL.NS", "RAILTEL.NS"]
            },
            "Healthcare": {
                "name_ta": "ஃபார்மா / ஹெல்த்கேர் (Pharma & Healthcare)",
                "keywords": ["pharma", "pharmaceuticals", "health", "healthcare", "மருந்து", "பார்மா"],
                "tickers": ["SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "LUPIN.NS", "AUROPHARMA.NS", "TORNTPHARM.NS", "DIVISLAB.NS", "BIOCON.NS"]
            },
            "Technology": {
                "name_ta": "ஐடி / தகவல் தொழில்நுட்பம் (IT & Technology)",
                "keywords": ["it", "tech", "technology", "தகவல் தொழில்நுட்பம்", "ஐடி", "மென்பொருள்"],
                "tickers": ["INFY.NS", "TCS.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTIM.NS", "COFORGE.NS", "PERSISTENT.NS"]
            },
            "Financial Services": {
                "name_ta": "வங்கி மற்றும் நிதி (Banking, Finance & NBFC)",
                "keywords": ["bank", "banking", "finance", "financial", "nbfc", "வங்கி", "நிதி", "பங்கிங்", "என்பிஎப்சி"],
                "tickers": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "BAJFINANCE.NS", "MUTHOOTFIN.NS", "CHOLAFIN.NS", "SHRIRAMFIN.NS", "LICHSGFIN.NS"]
            },
            "Consumer Cyclical": {
                "name_ta": "ஆட்டோமொபைல் / வாகனம் (Automobile)",
                "keywords": ["auto", "automobile", "வாகனம்", "ஆட்டோ", "மோட்டார்"],
                "tickers": ["TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS", "TVSMOTOR.NS", "EICHERMOT.NS"]
            },
            "Consumer Defensive": {
                "name_ta": "நுகர்வோர் பொருட்கள் (FMCG)",
                "keywords": ["fmcg", "consumer", "நுகர்வோர்", "உணவு", "சோப்பு", "itc"],
                "tickers": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS", "DABUR.NS", "MARICO.NS"]
            },
            "Basic Materials": {
                "name_ta": "உலோகம், சுரங்கம் மற்றும் நிலக்கரி (Metals, Mining & Coal)",
                "keywords": ["metal", "steel", "mining", "coal", "உலோகம்", "இரும்பு", "ஸ்டீல்", "நிலக்கரி"],
                "tickers": ["TATASTEEL.NS", "JSL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "COALINDIA.NS", "NMDC.NS", "VEDL.NS", "SAIL.NS"]
            },
            "Industrials": {
                "name_ta": "உற்பத்தி / தொழில்துறை (Manufacturing & Industrials)",
                "keywords": ["manufacturing", "industrial", "industrials", "உற்பத்தி", "தொழில்துறை"],
                "tickers": ["LT.NS", "SIEMENS.NS", "ABB.NS", "BHEL.NS", "CUMMINSIND.NS", "HAVELLS.NS", "THERMAX.NS"]
            },
            "Real Estate": {
                "name_ta": "ரியல் எஸ்டேட் மற்றும் கட்டுமானம் (Real Estate & Infrastructure)",
                "keywords": ["realty", "real estate", "construction", "ரியல் எஸ்டேட்", "கட்டுமானம்", "வீடு"],
                "tickers": ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "LODHA.NS", "PRESTIGE.NS"]
            },
            "PSU": {
                "name_ta": "அரசுத்துறை நிறுவனங்கள் (PSU Stocks)",
                "keywords": ["psu", "public sector", "அரசுத்துறை", "பொதுத்துறை"],
                "tickers": ["NTPC.NS", "ONGC.NS", "COALINDIA.NS", "SAIL.NS", "BHEL.NS", "IOC.NS", "GAIL.NS",
                            "POWERGRID.NS", "BPCL.NS", "HPCL.NS", "SBIN.NS", "BANKBARODA.NS", "PNB.NS"]
            },
        }

    def extract_sector_info(self, query_lower: str):
        """
        ✅ திருத்தப்பட்டது: substring match -> word-boundary match (_kw_match)
        தமிழ் மற்றும் ஆங்கில வார்த்தைகளில் இருந்து துறையைத் துல்லியமாக அடையாளம் காணும் செயல்பாடு
        """
        for sec_key, sec_data in self.SECTOR_TICKERS.items():
            if _kw_match(query_lower, sec_data["keywords"]):
                return sec_key, sec_data["name_ta"], sec_data["tickers"]

        return None, "அனைத்து முக்கியத் துறைகள்", []

    def _detect_symbol(self, query: str) -> str:
        """
        ✅ புதிய method - இதுவரை இந்த class-இல் இல்லாததால் AttributeError
        ஏற்படுத்திய பிழை இப்போது சரி செய்யப்பட்டது.
        stock_service.py-இல் ஏற்கனவே உள்ள detect_symbol() / detect_symbol_in_text()
        logic-ஐயே மறுபயன்படுத்துகிறது - புதிய தேடல் logic எதுவும் இல்லை.
        """
        if not self.stock_service:
            return ""
        try:
            if hasattr(self.stock_service, 'detect_symbol'):
                return self.stock_service.detect_symbol(query) or ""
        except Exception:
            pass
        try:
            from stock_service import detect_symbol_in_text
            return detect_symbol_in_text(query) or ""
        except Exception:
            return ""

    def process_query(self, query: str, lang: str = 'ta') -> str:
        """பயனர் கேட்க்கும் கேள்விக்கான முதன்மை கையாளும் செயல்பாடு"""
        return self.process_user_query(query, lang)

    def process_user_query(self, query: str, lang: str = 'ta') -> str:
        if not self.stock_service:
            return "❌ StockService சரியாக இணைக்கப்படவில்லை அல்லது கிடைக்கவில்லை."

        query_lower = query.lower()

        # ---------------------------------------------------------
        # 1. காலாண்டு முடிவுகள் பகுப்பாய்வு (Quarterly Results Query)
        # ---------------------------------------------------------
        if _kw_match(query_lower, ["quarterly", "காலாண்டு", "results", "முடிவுகள்", "earnings"]):
            symbol = self._detect_symbol(query)
            if symbol:
                stock_data = self.stock_service.fetch_data(symbol) if hasattr(self.stock_service, 'fetch_data') else self.stock_service.get_stock_details(symbol)
                if stock_data and "error" not in stock_data:
                    return generate_stock_analysis(stock_data, lang=lang)
                return self._handle_quarterly_analysis(symbol)

        # ---------------------------------------------------------
        # 2. துறை சார்ந்த வடிகட்டி & Screener (Sector / Metric Screening Query)
        # ✅ புதிய sector keywords (telecom, oil, gas, nbfc, psu, manufacturing, industrial)
        #    சேர்க்கப்பட்டு, word-boundary match பயன்படுத்தப்படுகிறது.
        # ---------------------------------------------------------
        screening_keywords = [
            "screen", "stocks", "பங்குகள்", "small cap", "small-cap", "mid cap", "mid-cap",
            "p/e", "pe", "peg", "sector", "துறை", "நிறுவனங்கள்",
            "மருந்து", "வங்கி", "ஐடி", "மின்சாரம்", "ஆற்றல்", "power",
            "telecom", "தொலைத்தொடர்பு", "oil", "gas", "எண்ணெய்", "எரிவாயு",
            "nbfc", "என்பிஎப்சி", "psu", "அரசுத்துறை",
            "manufacturing", "industrial", "உற்பத்தி", "தொழில்துறை",
            "steel", "coal", "நிலக்கரி", "list", "list out",
        ]
        if _kw_match(query_lower, screening_keywords):
            return self._handle_sector_screening(query, query_lower, lang=lang)

        # ---------------------------------------------------------
        # 3. தனிப்பட்ட பங்கின் விவரம் (Single Stock Detailed Analysis)
        # ---------------------------------------------------------
        symbol = self._detect_symbol(query)
        if symbol:
            stock_data = self.stock_service.fetch_data(symbol) if hasattr(self.stock_service, 'fetch_data') else self.stock_service.get_stock_details(symbol)
            if stock_data and "error" not in stock_data:
                return generate_stock_analysis(stock_data, lang=lang)

        # ---------------------------------------------------------
        # 4. பொதுவான பங்குகளின் பெயர் கேட்கப்பட்டால் (Fallback Search)
        # ---------------------------------------------------------
        for symbol_key in ["NTPC", "TATAPOWER", "POWERGRID", "ITC", "TCS", "INFY", "RELIANCE", "HDFCBANK"]:
            if symbol_key.lower() in query_lower:
                full_sym = f"{symbol_key}.NS"
                stock_data = self.stock_service.fetch_data(full_sym) if hasattr(self.stock_service, 'fetch_data') else self.stock_service.get_stock_details(full_sym)
                if stock_data and "error" not in stock_data:
                    return generate_stock_analysis(stock_data, lang=lang)

        return "மன்னிக்கவும், தாங்கள் கேட்ட பங்கின் விவரங்கள் சரியாகத் தொடர்புகொள்ள முடியவில்லை. தயவுசெய்து பங்கின் சரியான பெயர் (எ.கா: NTPC, Tata Power, TCS) அல்லது துறையைக் (எ.கா: Electric stocks P/E < 40) குறிப்பிட்டு மீண்டும் கேட்கவும்."

    def _handle_sector_screening(self, query_raw: str, query_lower: str, lang: str = 'ta') -> str:
        """
        ✅ திருத்தப்பட்டது:
        - PE எண் extract செய்யும் regex "under/below/less than/<" எல்லா pattern-களையும் பிடிக்கும்
        - PEG, Market Cap filter-க்கான hooks சேர்க்கப்பட்டுள்ளன
        - country="USA" (இந்தியா அல்லாத நாடு) கேட்கும்போது, தவறாக இந்திய பங்குகளைத்
          திருப்பாமல் தெளிவான செய்தி தரும்
        """
        is_india = _kw_match(query_lower, ["india", "இந்திய", "indian"])
        is_usa = _kw_match(query_lower, ["usa", "us stocks", "america", "அமெரிக்கா"])
        country = "India" if is_india else ("USA" if is_usa else None)

        sector_key, sector_name_ta, fallback_tickers = self.extract_sector_info(query_lower)

        # ✅ PE, PEG வரம்பு பிரித்தெடுத்தல் (பல வகையான வாக்கிய அமைப்புகளையும் பிடிக்கும்)
        max_pe = _extract_number_near_keyword(query_lower, r'pe|p/e|பி\s*/\s*ஈ')
        max_pe = max_pe if max_pe is not None else 40

        max_peg = _extract_number_near_keyword(query_lower, r'peg')
        # max_peg கிடைக்கவில்லை என்றால் filter செய்யப்படாது (None)

        # ⚠️ fallback ticker-கள் தற்போது இந்திய பங்குகள் (.NS) மட்டுமே.
        # country="USA" எனக் கேட்டால், தவறான இந்திய தரவைத் தராமல் தெளிவாகச் சொல்கிறோம்.
        if country == "USA" and not (hasattr(self.stock_service, 'screen_global_stocks')):
            return ("🌐 தற்போது அமெரிக்க (USA) பங்குகளுக்கான நேரலை screening இந்த சேவையில் "
                    "கிடைக்கவில்லை. இது இந்திய (NSE/BSE) பங்குகளுக்கு மட்டுமே ஆதரவளிக்கிறது.")

        stocks_list = []

        # 1. DB Screener சோதனை
        if hasattr(self.stock_service, 'screen_global_stocks'):
            try:
                db_results = self.stock_service.screen_global_stocks(
                    country=country, sector=sector_key, max_pe=max_pe
                )
                if db_results:
                    stocks_list = db_results
            except Exception as e:
                print(f"DB Screener Error: {e}")

        # 2. StockService நேரலை தேடல் (Safely Extracted Values)
        if not stocks_list and fallback_tickers:
            for ticker in fallback_tickers:
                try:
                    data = self.stock_service.fetch_data(ticker) if hasattr(self.stock_service, 'fetch_data') else self.stock_service.get_stock_details(ticker)
                    if data and "error" not in data:
                        raw_pe = data.get('pe') or data.get('pe_ratio') or data.get('p_e') or data.get('trailingPE')
                        raw_peg = data.get('peg') or data.get('peg_ratio')

                        try:
                            pe_float = float(raw_pe)
                        except (ValueError, TypeError):
                            continue

                        if pe_float <= 0 or pe_float > max_pe:
                            continue

                        if max_peg is not None:
                            try:
                                peg_float = float(raw_peg)
                                if peg_float > max_peg:
                                    continue
                                data['peg'] = peg_float
                            except (ValueError, TypeError):
                                # PEG தரவு இல்லாத பங்குகளை PEG filter கேட்கும்போது தவிர்க்கிறோம்
                                continue

                        data['pe'] = pe_float
                        stocks_list.append(data)
                except Exception:
                    continue

        # 3. ✅ புதிய fallback: local ticker/DB தரவு கிடைக்காவிட்டால், Screener.in-இல்
        #    இருந்து நேரலையாகத் தேடி (web scrape) பதில் தர முயற்சி
        if not stocks_list:
            web_result = screen_stocks_via_web(sector_key, sector_name_ta, max_pe, lang=lang)
            if web_result:
                return web_result

        if not stocks_list:
            return f"🔍 **பகுப்பாய்வு முடிவு ({sector_name_ta}):**\n\nதற்போது {sector_name_ta} துறையில் P/E விகிதம் {max_pe}-க்குக் கீழ் உள்ள பங்குகள் நேரலை வடிகட்டலில் கண்டறியப்படவில்லை (local மற்றும் web தேடல் இரண்டும் தோல்வியடைந்தது). தயவுசெய்து P/E வரம்பை அதிகரித்து முயற்சிக்கவும்."

        # நேரலைத் தரவை வெளியீடாகத் தருதல்
        response = f"🎯 **{sector_name_ta} துறையில் P/E < {max_pe}"
        if max_peg is not None:
            response += f", PEG < {max_peg}"
        response += " கொண்ட பங்குகள்:**\n\n"

        for s in stocks_list[:10]:
            name = s.get('name') or s.get('company_name') or s.get('symbol', 'N/A')
            sym = str(s.get('symbol', '')).replace('.NS', '').replace('.BO', '')
            price = s.get('price', 'N/A')
            pe = s.get('pe', 'N/A')
            peg = s.get('peg') or s.get('peg_ratio', 'N/A')
            mcap = s.get('marketCap') or s.get('market_cap', 'N/A')

            response += f"• **{name} ({sym})**\n"
            response += f"   - தற்போதைய விலை: ₹ {price}\n"
            response += f"   - P/E விகிதம்: {pe}\n"
            response += f"   - PEG விகிதம்: {peg}\n"
            response += f"   - சந்தை மதிப்பு: {mcap}\n\n"

        return response

    def _handle_quarterly_analysis(self, symbol: str, lang: str = 'ta') -> str:
        """yfinance/StockService வழியாக சமீபத்திய காலாண்டு அறிக்கையைப் பெற்று AI மூலம் பகுப்பாய்வு செய்யும் செயல்பாடு"""
        target_language = LANG_NAMES.get(lang, 'Tamil')
        clean_symbol = symbol.replace('.NS', '').replace('.BO', '')

        quarterly_data_str = ""

        try:
            if hasattr(self.stock_service, 'get_quarterly_financials'):
                q_df = self.stock_service.get_quarterly_financials(symbol)
                if q_df is not None and not q_df.empty:
                    quarterly_data_str = q_df.to_string()
            else:
                import yfinance as yf
                ticker = yf.Ticker(symbol if '.' in symbol else f"{symbol}.NS")
                q_df = ticker.quarterly_financials
                if q_df is not None and not q_df.empty:
                    quarterly_data_str = q_df.iloc[:, :2].to_string()
        except Exception as e:
            print(f"Quarterly Fetch Error: {e}")

        if quarterly_data_str:
            system_prompt = f"""
            You are a senior Financial Analyst. Below is the recent quarterly financial statement (income statement) for {clean_symbol}.
            Analyze these quarterly results and generate a clear, structured financial summary in {target_language} (lang: {lang}).

            FINANCIAL DATA:
            {quarterly_data_str}

            REQUIRED STRUCTURE:
            📰 **{clean_symbol} - சமீபத்திய காலாண்டு அறிக்கைப் பகுப்பாய்வு**
            • 💰 **வருவாய் (Total Revenue):** [கடைசி இரு காலாண்டுகளின் ஒப்பீடு]
            • 📈 **நிகர லாபம் (Net Income / Profit):** [வளர்ச்சி / வீழ்ச்சி விவரம்]
            • 📊 **இயக்க லாபம் (Operating Revenue/Expenses):** [முக்கிய அவதானிப்புகள்]
            • 💡 **AI மதிப்பீடு (Key Takeaways):** [நிறுவனத்தின் தற்போதைய நிதி நிலைமை பற்றிய சுருக்கம்]
            """

            api_keys = extract_working_keys()
            if api_keys:
                for key in api_keys:
                    try:
                        client = Groq(api_key=key, timeout=25.0)
                        completion = client.chat.completions.create(
                            model=GROQ_MODEL,
                            messages=[{"role": "user", "content": system_prompt}],
                            temperature=0.2,
                            max_tokens=2048,
                        )
                        res = completion.choices[0].message.content
                        if res:
                            return res
                    except Exception:
                        continue

        if hasattr(self.stock_service, 'analyze_quarterly_results'):
            q_data = self.stock_service.analyze_quarterly_results(symbol)
            if q_data and "error" not in q_data:
                return (
                    f"📰 **{clean_symbol} - சமீபத்திய காலாண்டு முடிவுகள் பகுப்பாய்வு ({q_data.get('quarter_year', 'Latest')}):**\n\n"
                    f"• **மொத்த வருவாய் (Revenue):** ₹{q_data.get('revenue', 'N/A')} கோடி\n"
                    f"• **நிகர லாபம் (Net Profit):** ₹{q_data.get('net_profit', 'N/A')} கோடி\n"
                    f"• **இயக்க லாப வரம்பு (Operating Margin):** {q_data.get('operating_margin_pct', 'N/A')}%\n"
                    f"• **வளர்ச்சி சிறப்பம்சங்கள்:** {q_data.get('key_highlights', 'நேர்மறையான வளர்ச்சி')}\n"
                    f"• **சந்தை மனநிலை (Sentiment):** {q_data.get('sentiment', 'Bullish')}\n\n"
                    f"**AI பகுப்பாய்வு:** நிறுவனம் {q_data.get('sentiment', 'சீரான')} போக்கில் இயங்கி வருகிறது."
                )

        return f"❌ '{clean_symbol}' நிறுவனத்திற்கான சமீபத்திய காலாண்டு அறிக்கை விவரங்களை நேரலையாகப் பெற முடியவில்லை."