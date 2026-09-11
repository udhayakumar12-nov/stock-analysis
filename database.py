import os

# Supabase லைப்ரரி சரிபார்த்தல்
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://tvkveuuvlsxmgtzuwjtm.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "sb_secret_pIp8rwLhiK-u9TJ62Cg48w_1dHct4Yf")

# ==================== SECTOR ALIAS MAP (NEW) ====================
# ✅ புதியது: Yahoo Finance-இன் உண்மையான GICS sector taxonomy உங்கள்
# Tamil/logical sector-key உடன் எப்போதும் ஒத்துப்போகாது.
# எ.கா: NTPC / POWERGRID / TATAPOWER -> Yahoo sector = "Utilities"
#       ONGC / RELIANCE            -> Yahoo sector = "Energy"
# "Energy" அல்லது "Power" எனக் கேட்கும்போது, இரண்டு sector பெயர்களையும்
# OR-ஆகத் தேடும்படி அமைக்கப்பட்டுள்ளது. இதுவே "power sector stocks" கேட்டால்
# தவறான/தொடர்பில்லாத பங்குகள் வந்த முக்கியக் காரணம்.
SECTOR_ALIASES = {
    "energy": ["Energy", "Utilities"],
    "power": ["Energy", "Utilities"],
    "power & energy": ["Energy", "Utilities"],
    "oil & gas": ["Energy"],
    "utilities": ["Utilities"],
    "technology": ["Technology"],
    "it": ["Technology"],
    "financial services": ["Financial Services"],
    "banking": ["Financial Services"],
    "telecom": ["Communication Services"],
    "telecommunication": ["Communication Services"],
    "healthcare": ["Healthcare"],
    "pharma": ["Healthcare"],
    "consumer cyclical": ["Consumer Cyclical"],
    "automobile": ["Consumer Cyclical"],
    "consumer defensive": ["Consumer Defensive"],
    "fmcg": ["Consumer Defensive"],
    "basic materials": ["Basic Materials"],
    "metals": ["Basic Materials"],
    "steel": ["Basic Materials"],
    "industrials": ["Industrials"],
    "manufacturing": ["Industrials"],
    "real estate": ["Real Estate"],
}


class SupabaseManager:
    def __init__(self):
        if SUPABASE_AVAILABLE and SUPABASE_URL and SUPABASE_KEY:
            try:
                self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            except Exception as e:
                print(f"⚠️ Supabase Client Initialization Error: {e}")
                self.client = None
        else:
            self.client = None
            if not SUPABASE_AVAILABLE:
                print("⚠️ Warning: 'supabase' package is not installed. Run 'pip install supabase'.")

    # 1. பங்குகளின் தரவைச் சேமிக்க அல்லது புதுப்பிக்க (Upsert)
    def upsert_stocks(self, stocks_data: list):
        if not self.client:
            print("⚠️ Supabase இணைப்பு செயல்படவில்லை.")
            return None
        try:
            response = self.client.table("global_stocks").upsert(stocks_data).execute()
            return response
        except Exception as e:
            print(f"Error upserting stocks: {e}")
            return None

    # 2. குறிப்பிட்ட ஒரு நிறுவனத்தைத் தேட (e.g. Apple, AAPL, TCS)
    def get_stock_by_symbol_or_name(self, query_text: str):
        """
        நிறுவனத்தின் பெயர் (Name) அல்லது குறியீடு (Symbol) மூலம் நேரடியாக தேடும் முறை.
        DEFAULT P/E எதுவும் பயன்படுத்தப்படாது.
        """
        if not self.client or not query_text:
            return []
        try:
            clean_query = query_text.strip()

            res = self.client.table("global_stocks")\
                .select("*")\
                .or_(f"symbol.ilike.%{clean_query}%,name.ilike.%{clean_query}%")\
                .limit(10)\
                .execute()

            return res.data or []
        except Exception as e:
            print(f"Error fetching specific stock ({query_text}): {e}")
            return []

    # 3. திரையிடல் (Dynamic Screening Query)
    def screen_stocks(
        self, 
        country: str = None, 
        sector: str = None, 
        industry: str = None,
        max_pe: float = None,       # பயனர் அனுப்பும் P/E மட்டுமே எடுத்துக்கொள்ளப்படும்
        min_pe: float = None,       # குறைந்தபட்ச P/E
        max_peg: float = None, 
        max_pb: float = None, 
        max_debt: float = None, 
        min_fcf: float = None,
        limit: int = 50
    ):
        """
        பயனர் வெளிப்படையாகக் கேட்கும் வடிகட்டிகளுக்கு (Filters) ஏற்ப மட்டுமே இயங்கும்.
        Null sector/industry/country தரவுகளைத் தவிர்த்துத் துல்லியமான முடிவுகளைத் தரும்.

        ✅ திருத்தப்பட்டது:
        - sector filter இப்போது SECTOR_ALIASES மூலம் Yahoo Finance-இன்
          உண்மையான sector பெயர்களையும் (Utilities vs Energy) OR-ஆகத் தேடும்.
        - country filter NULL-ஐத் தவிர்த்து strict-ஆக apply செய்யப்படும்.
        - Debug log சேர்க்கப்பட்டுள்ளது - எதிர்காலத்தில் "filter apply ஆகவில்லை"
          போன்ற பிழைகளை உடனே கண்டறிய உதவும்.
        """
        if not self.client:
            print("⚠️ Supabase இணைப்பு செயல்படவில்லை.")
            return []
        try:
            query = self.client.table("global_stocks").select("*")

            # ✅ Sector filter - alias-mapped OR search
            if sector:
                sector_key = sector.strip().lower()
                aliases = SECTOR_ALIASES.get(sector_key, [sector])
                or_clause = ",".join([f"sector.ilike.%{a}%" for a in aliases])
                query = query.not_.is_("sector", None).or_(or_clause)

            if industry:
                query = query.not_.is_("industry", None).ilike("industry", f"%{industry}%")

            # ✅ Country filter - NULL தவிர்த்து, strict ஆக apply
            if country:
                query = query.not_.is_("country", None).ilike("country", f"%{country}%")

            # நிதி விகிதங்கள் (பயனர் தந்தால் மட்டுமே வடிகட்டும்)
            if max_pe is not None:
                query = query.lte("pe_ratio", max_pe).gt("pe_ratio", 0)
            if min_pe is not None:
                query = query.gte("pe_ratio", min_pe)
            if max_peg is not None:
                query = query.lte("peg_ratio", max_peg).gt("peg_ratio", 0)
            if max_pb is not None:
                query = query.lte("pb_ratio", max_pb).gt("pb_ratio", 0)
            if max_debt is not None:
                query = query.lte("debt_to_equity", max_debt)
            if min_fcf is not None:
                query = query.gte("free_cashflow_cr", min_fcf)

            # சந்தை மதிப்பின்படி வரிசைப்படுத்துதல்
            res = query.order("market_cap_cr", ascending=False).limit(limit).execute()
            rows = res.data or []

            # ✅ புதிய debug log
            print(f"🔍 screen_stocks filters -> country={country!r}, sector={sector!r}, "
                  f"max_pe={max_pe} | rows_returned={len(rows)}")

            return rows
        except Exception as e:
            print(f"Error querying stocks: {e}")
            return []

    # 4. காலாண்டு அறிக்கையை சேமித்தல்
    def save_quarterly_report(self, report_data: dict):
        if not self.client:
            print("⚠️ Supabase இணைப்பு செயல்படவில்லை.")
            return None
        try:
            return self.client.table("quarterly_reports").insert(report_data).execute()
        except Exception as e:
            print(f"Error saving quarterly report: {e}")
            return None

    # 5. பங்குகளின் அண்மைக்கால காலாண்டு அறிக்கையை எடுத்தல்
    def get_latest_quarterly_report(self, symbol: str):
        if not self.client:
            print("⚠️ Supabase இணைப்பு செயல்படவில்லை.")
            return None
        try:
            res = self.client.table("quarterly_reports")\
                .select("*")\
                .eq("symbol", symbol)\
                .order("report_date", desc=True)\
                .limit(1)\
                .execute()
            return res.data[0] if res.data else None
        except Exception as e:
            print(f"Error fetching report: {e}")
            return None