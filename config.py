import os
from dotenv import load_dotenv

# .env கோப்பின் துல்லியமான பாதையைக் கண்டறிந்து load செய்கிறது
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=env_path)

# 1. Environment Variables - Supabase & API Keys
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# 2. Model Name Configuration
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

# 3. Dynamic Groq Keys Loading (1 முதல் 51 வரை தானாக லோட் செய்யும்)
GROQ_KEYS = []
for i in range(1, 52):
    key = os.getenv(f"GROQ_API_KEY_{i}")
    if key and key.strip():  # Key காலியாக இல்லாமல் இருந்தால் மட்டுமே சேர்க்கும்
        GROQ_KEYS.append(key.strip())
        # தனித்தனியாக அணுக வேண்டிய சூழ்நிலை இருந்தால் அதற்கான Variable dynamic-ஆக உருவாக்கப்படுகிறது
        globals()[f"GROQ_API_KEY_{i}"] = key.strip()

# 4. Main.py மற்றும் பிற சேவைகளுக்கான Verification Log
if GROQ_KEYS:
    print(f"✅ Config.py-ல் வெற்றிகரமாக {len(GROQ_KEYS)} Groq Keys லோட் செய்யப்பட்டன!")
else:
    print("❌ Config.py-ல் Keys எதுவும் கிடைக்கவில்லை! (.env கோப்பைச் சரிபார்க்கவும்)")