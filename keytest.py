import os
from dotenv import load_dotenv

load_dotenv()
raw_keys = os.getenv("GROQ_KEYS", "")
groq_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

print(f"ஏற்றப்பட்ட மொத்த Keys: {len(groq_keys)}")