# backend/youtube_handler.py

import re
import traceback
from typing import Optional, Dict, Any
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
    VideoUnavailable,
    TooManyRequests,
    IpBlocked,
    RequestBlocked
)

def extract_video_id(url: str) -> Optional[str]:
    """YouTube URL-லிருந்து video ID எடுக்க"""
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_youtube_transcript(video_url: str, lang: str = 'ta') -> Dict[str, Any]:
    """
    YouTube video-ன் transcript-ஐ எடுக்க.
    Fail ஆனால் fallback message தரும்.
    """
    video_id = extract_video_id(video_url)
    
    if not video_id:
        return {
            "success": False,
            "error": "❌ சரியான YouTube இணைப்பு அல்ல",
            "transcript": None
        }

    try:
        # 1. முதலில் கேட்ட மொழியில் முயற்சி
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # மொழி priority: கேட்ட மொழி → English → auto-generated → எதுவும் கிடைத்தாலும்
        try:
            transcript = transcript_list.find_transcript([lang])
        except NoTranscriptFound:
            try:
                transcript = transcript_list.find_transcript(['en'])
            except NoTranscriptFound:
                # Auto-generated கூட எடுக்க முயற்சி
                transcript = transcript_list.find_generated_transcript([lang, 'en'])
        
        # Fetch transcript
        raw_transcript = transcript.fetch()
        
        if not raw_transcript:
            raise CouldNotRetrieveTranscript(video_id)
        
        # Text-ஆக மாற்று
        full_text = " ".join([entry['text'] for entry in raw_transcript])
        
        return {
            "success": True,
            "error": None,
            "transcript": full_text,
            "language": transcript.language,
            "is_generated": transcript.is_generated,
            "video_id": video_id
        }

    except TranscriptsDisabled:
        return {
            "success": False,
            "error": "❌ இந்த வீடியோவில் subtitles முடக்கப்பட்டுள்ளன. வீடியோ உரிமையாளர் captions அனுமதிக்கவில்லை.",
            "transcript": None,
            "video_id": video_id
        }
    
    except NoTranscriptFound:
        return {
            "success": False,
            "error": "❌ இந்த வீடியோவில் transcript கிடைக்கவில்லை. CC (captions) இல்லாத வீடியோக்களுக்கு summary எடுக்க முடியாது.",
            "transcript": None,
            "video_id": video_id
        }
    
    except (TooManyRequests, IpBlocked, RequestBlocked):
        return {
            "success": False,
            "error": "⚠️ YouTube-லிருந்து தற்காலிகமாக தடை பெற்றுள்ளோம். சிறிது நேரம் கழித்து முயற்சிக்கவும்.",
            "transcript": None,
            "video_id": video_id
        }
    
    except VideoUnavailable:
        return {
            "success": False,
            "error": "❌ இந்த வீடியோ கிடைக்கவில்லை. Private அல்லது Deleted ஆகிவிட்டதாக இருக்கலாம்.",
            "transcript": None,
            "video_id": video_id
        }
    
    except Exception as e:
        # XML parser error (no element found) இங்கே catch ஆகும்
        error_msg = str(e)
        if "no element found" in error_msg:
            return {
                "success": False,
                "error": "❌ YouTube transcript காலியாக வந்துள்ளது. இந்த வீடியோவில் usable captions இல்லை அல்லது YouTube-ன் API-ல் மாற்றம் ஏற்பட்டுள்ளது.",
                "transcript": None,
                "video_id": video_id
            }
        
        return {
            "success": False,
            "error": f"❌ Transcript பிழை: {error_msg}",
            "transcript": None,
            "video_id": video_id
        }


# ==================== SUMMARIZE ENDPOINT ====================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class SummarizeRequest(BaseModel):
    url: str
    target_lang: str = 'ta'
    link_type: str = 'youtube'

@router.post("/summarize_link")
async def summarize_link(req: SummarizeRequest):
    if req.link_type.lower() == 'youtube':
        result = get_youtube_transcript(req.url, req.target_lang)
        
        if not result["success"]:
            # Backend error-ஆக அனுப்பாமல், UI-ல் காட்ட வசதியாக JSON-ல் அனுப்பவும்
            return {
                "success": False,
                "summary": result["error"],
                "video_id": result.get("video_id")
            }
        
        # AI-க்கு அனுப்பி summary எடுக்க
        transcript = result["transcript"]
        summary = await generate_ai_summary(transcript, req.target_lang)
        
        return {
            "success": True,
            "summary": summary,
            "language": result["language"],
            "is_generated": result["is_generated"]
        }
    
    # Website/Twitter handling...
    else:
        # Existing website logic
        pass


async def generate_ai_summary(text: str, lang: str) -> str:
    """AI-க்கு transcript அனுப்பி summary எடுக்க"""
    # உங்கள் existing AI logic
    # OpenAI / Gemini / Local model
    max_chars = 8000  # Token limit-க்குள் இருக்க
    truncated = text[:max_chars]
    
    prompt = f"""
பின்வரும் YouTube வீடியோ transcript-ஐ {lang} மொழியில் சுருக்கமாக விளக்கவும்:

{truncated}

முக்கியமான புள்ளிகள்:
1. முதன்மையான கருத்து என்ன?
2. முக்கியமான தகவல்கள் என்ன?
3. முடிவுரை என்ன?
"""
    # AI call செய்து return செய்யவும்
    return "AI summary here..."