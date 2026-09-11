# services/groq_manager.py
import httpx
import json
import asyncio
import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

try:
    from config import GROQ_KEYS
    print(f"✅ Config-லிருந்து {len(GROQ_KEYS)} API Keys ஏற்றப்பட்டன.")
except ImportError:
    GROQ_KEYS = []
    print("❌ Config.py-ல் Keys எதுவும் கிடைக்கவில்லை!")

class GroqManager:
    def __init__(self, api_keys: List[str] = None):
        self.api_keys = api_keys if api_keys else GROQ_KEYS
        self.current_index = 0
        self.key_status = {key: {'valid': True, 'last_used': None, 'cooldown_until': None} for key in self.api_keys}
        self.model = "qwen/qwen3.6-27b"
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"
        self.max_retries = len(self.api_keys) if self.api_keys else 1
        self._lock = asyncio.Lock()

        if not self.api_keys:
            print("❌ எச்சரிக்கை: API Keys எதுவும் அமைக்கப்படவில்லை!")

    def _get_next_key(self) -> Optional[str]:
        now = datetime.now()
        start_index = self.current_index
        
        for attempt in range(len(self.api_keys)):
            idx = (start_index + attempt) % len(self.api_keys)
            key = self.api_keys[idx]
            status = self.key_status.get(key, {})
            if not status.get('valid', True):
                continue
            cooldown_until = status.get('cooldown_until')
            if cooldown_until and now < cooldown_until:
                continue
            self.key_status[key]['last_used'] = now
            self.current_index = (idx + 1) % len(self.api_keys)
            return key
        
        for key, status in self.key_status.items():
            if status.get('valid', True):
                cooldown_until = status.get('cooldown_until')
                if not cooldown_until or now >= cooldown_until:
                    return key
        return None

    def _mark_key_failed(self, key: str):
        self.key_status[key]['valid'] = False
        self.key_status[key]['cooldown_until'] = datetime.now() + timedelta(minutes=5)

    def _mark_key_success(self, key: str):
        self.key_status[key]['valid'] = True
        self.key_status[key]['cooldown_until'] = None

    def _clean_response(self, text: str) -> str:
        """ Safely remove thinking process without truncating the actual output """
        if not text:
            return ""
            
        # 1. Remove XML style thinking tags (<think>...</think>)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 2. Remove DeepSeek / Qwen reasoning prefix up to the actual Tamil/English content
        thinking_patterns = [
            r"Here'?s a thinking process:.*?(?=\n\n|\n\*|\n#)",
            r"^Here'?s a thinking process:.*?\n",
            r"Identify Key Components.*?\n",
            r"Translate/Adapt.*?\n",
            r"Check Constraints.*?\n"
        ]
        
        for pattern in thinking_patterns:
            text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)
            
        # 3. If there is leftover reasoning content, start directly from the first bold title or header
        match = re.search(r'(\*\*|#)', text)
        if match and match.start() > 0:
            preface = text[:match.start()]
            if any(k in preface.lower() for k in ["thinking", "process", "components", "translate"]):
                text = text[match.start():]

        # 4. Cleanup HTML tags and excessive spacing
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.2,
        max_tokens: int = 4096,  # Increased from 2000 to prevent text truncation
        max_retries: Optional[int] = None,
        clean_response: bool = True
    ) -> str:
        if not self.api_keys:
            return "❌ API Keys எதுவும் அமைக்கப்படவில்லை. config.py-ல் GROQ_KEYS-ஐ சரிபார்க்கவும்."

        retry_count = 0
        max_attempts = max_retries or self.max_retries

        async with httpx.AsyncClient(timeout=120.0) as client:
            while retry_count < max_attempts:
                async with self._lock:
                    key = self._get_next_key()
                if not key:
                    await asyncio.sleep(2)
                    retry_count += 1
                    continue

                try:
                    response = await client.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {key}", 
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": self.model, 
                            "messages": messages, 
                            "temperature": temperature, 
                            "max_tokens": max_tokens
                        }
                    )

                    if response.status_code == 200:
                        self._mark_key_success(key)
                        data = response.json()
                        content = data["choices"][0]["message"]["content"]
                        
                        if clean_response:
                            content = self._clean_response(content)
                        
                        return content
                    else:
                        self._mark_key_failed(key)
                        retry_count += 1
                        await asyncio.sleep(1)
                        continue

                except Exception:
                    self._mark_key_failed(key)
                    retry_count += 1
                    await asyncio.sleep(1)
                    continue

            return "❌ மன்னிக்கவும், தற்சமயம் சேவையை வழங்க முடியவில்லை. சற்று நேரம் கழித்து மீண்டும் முயற்சிக்கவும்."
        
    async def ask_agent_with_real_data(self, query: str, user_language: str, stock_data: Optional[Dict] = None) -> str:
        data_context = ""
        if stock_data:
            # NOTE: keys here must match what stock_service.fetch_stock_data() actually
            # returns ('price', 'pe', 'dividendYield', ...) — mismatched keys silently
            # produced "None" values that the model would then print verbatim.
            price = stock_data.get('price', stock_data.get('current_price', 'N/A'))
            pe = stock_data.get('pe', stock_data.get('pe_ratio', 'N/A'))
            eps = stock_data.get('eps', 'N/A')
            div_yield = stock_data.get('dividendYield', stock_data.get('dividend_yield', 'N/A'))
            high_52 = stock_data.get('fiftyTwoWeekHigh', 'N/A')
            low_52 = stock_data.get('fiftyTwoWeekLow', 'N/A')

            data_context = f"""
STRICT REAL-TIME STOCK DATA (USE THESE EXACT FIGURES, DO NOT WRITE "None"):
- Symbol: {stock_data.get('symbol')}
- Current Live Price: ₹{price}
- P/E Ratio: {pe}
- EPS (TTM): ₹{eps}
- Dividend Yield: {div_yield}
- 52-Week High/Low: ₹{high_52} / ₹{low_52}
"""

        system_prompt = f"""You are an advanced Real-Time Financial & Investment Analyst AI.

CRITICAL INSTRUCTIONS:
1. RESPONSE LANGUAGE: You MUST respond STRICTLY in the target language requested by the user: '{user_language}'.
2. ACCURACY & REAL DATA: {"Use the real-time stock data provided below. DO NOT fabricate old prices." if data_context else "NO LIVE DATA WAS PROVIDED for this query. You MUST NOT state any specific price, P/E ratio, market cap, or other numeric figure from memory/training data, since it will be stale or wrong. Instead, clearly tell the user you don't have live figures for this and answer only the non-numeric, conceptual parts of their question."}
3. NO THINKING PROCESS: Do NOT output any reasoning steps, preface, or system tags. Start directly with the markdown response.
4. STRUCTURE: Use Markdown formatting with bold headers and clear bullet points.
"""

        user_prompt = f"User Query: {query}\n"
        if data_context:
            user_prompt += f"\nLive Market Context:\n{data_context}"

        return await self.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1
        )

    # Alias Method for backward compatibility
    async def ask_agent(self, query: str, user_language: str = "English", stock_data: Optional[Dict] = None) -> str:
        return await self.ask_agent_with_real_data(query, user_language, stock_data)

# =====================================================================
# Global Variables & Startup Functions
# =====================================================================

groq_manager: Optional[GroqManager] = None
groq_manager_instance: Optional[GroqManager] = None

def init_groq_manager(api_keys: List[str] = None):
    global groq_manager, groq_manager_instance
    keys = api_keys if api_keys else GROQ_KEYS
    groq_manager = GroqManager(keys)
    groq_manager_instance = groq_manager
    print(f"✅ GroqManager வெற்றிகரமாக {len(keys)} Keys-உடன் Initialize செய்யப்பட்டது.")

def get_groq_manager() -> GroqManager:
    global groq_manager
    if groq_manager is None:
        init_groq_manager()
    return groq_manager