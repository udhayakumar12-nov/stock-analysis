from google import genai
from google.genai import types
from io import BytesIO
from PIL import Image

class ImageService:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.0-flash"  # or gemini-1.5-flash
    
    async def translate_image(self, image_bytes: bytes, target_lang: str) -> str:
        """Extract text from image and translate to target language"""
        try:
            image = Image.open(BytesIO(image_bytes))
            
            prompt = f"""
            1. Extract ALL text visible in this image
            2. Translate the extracted text to {target_lang} language
            3. Provide both original and translated text
            4. If it's a financial document/stock chart, explain the key numbers
            
            Format:
            Original: [extracted text]
            Translation: [translated text]
            Summary: [brief explanation]
            """
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, image]
            )
            return response.text
        except Exception as e:
            return f"⚠️ Image processing error: {str(e)}"
    
    async def analyze_chart(self, image_bytes: bytes) -> str:
        """Analyze stock chart image"""
        try:
            image = Image.open(BytesIO(image_bytes))
            
            prompt = """
            Analyze this stock chart image. Provide:
            1. Trend direction (Bullish/Bearish/Sideways)
            2. Key support and resistance levels
            3. Pattern recognition (if any)
            4. Short term outlook
            
            Respond in the user's language.
            """
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, image]
            )
            return response.text
        except Exception as e:
            return f"⚠️ Chart analysis error: {str(e)}"