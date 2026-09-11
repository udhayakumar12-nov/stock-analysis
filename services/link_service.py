# services/link_service.py
import httpx
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
import re
import asyncio
import json

class LinkService:
    def __init__(self, groq_mgr):
        self.groq = groq_mgr
    
    def _get_lang_name(self, lang_code: str) -> str:
        """Convert language code to full name for AI prompt"""
        lang_map = {
            'ta': 'Tamil', 
            'hi': 'Hindi', 
            'en': 'English', 
            'kn': 'Kannada',
            'mr': 'Marathi', 
            'te': 'Telugu', 
            'ml': 'Malayalam', 
            'bn': 'Bengali',
            'gu': 'Gujarati', 
            'or': 'Odia', 
            'as': 'Assamese',
            'pa': 'Punjabi', 
            'ur': 'Urdu', 
            'sa': 'Sanskrit',
            'sd': 'Sindhi', 
            'ne': 'Nepali', 
            'bodo': 'Bodo',
            'dogri': 'Dogri', 
            'ks': 'Kashmiri', 
            'konkani': 'Konkani',
            'santali': 'Santali', 
            'mai': 'Maithili'
        }
        return lang_map.get(lang_code, 'Tamil')

    async def _extract_article_content(self, html_content: str, url: str) -> dict:
        """Extract clean article content with title and body"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript", "form", "button"]):
                element.decompose()
            
            # Get title
            title = "No Title"
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()
            
            # Try to find article title from meta tags
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()
            
            # Try to find main article content
            article_content = None
            
            # Method 1: Look for article tag
            article = soup.find('article')
            if article:
                article_content = article
            
            # Method 2: Look for main content divs
            if not article_content:
                for selector in ['main', '.article-body', '.story-body', '.content-body', '.post-content', '.article-content', '.entry-content', '.story-content']:
                    content_div = soup.select_one(selector)
                    if content_div:
                        article_content = content_div
                        break
            
            # Method 3: Look for div with most text
            if not article_content:
                max_text_length = 0
                best_div = None
                for div in soup.find_all(['div', 'section']):
                    text = div.get_text(separator=' ', strip=True)
                    if len(text) > 500 and len(text) > max_text_length:
                        max_text_length = len(text)
                        best_div = div
                if best_div:
                    article_content = best_div
            
            # Method 4: Use body as fallback
            if not article_content:
                article_content = soup.body
            
            # Extract text
            if article_content:
                text = article_content.get_text(separator='\n', strip=True)
            else:
                text = soup.get_text(separator='\n', strip=True)
            
            # Clean up text
            lines = [line.strip() for line in text.splitlines() if line.strip() and len(line.strip()) > 10]
            
            # Filter out noisy lines
            filtered_lines = []
            for line in lines:
                # Skip lines that look like navigation or metadata
                if any(skip in line.lower() for skip in ['cookie', 'privacy', 'subscribe', 'newsletter', 'follow', 'share', 'search', 'login', 'sign up', 'register']):
                    continue
                # Skip very short lines
                if len(line) < 20:
                    continue
                filtered_lines.append(line)
            
            content = '\n'.join(filtered_lines)
            
            # If content is too short, use raw text
            if len(content) < 500:
                content = soup.get_text(separator=' ', strip=True)
                # Remove repeated patterns
                content = re.sub(r'\s+', ' ', content)
            
            return {
                'title': title,
                'content': content[:6000]  # Limit for AI processing
            }
            
        except Exception as e:
            print(f"Error extracting content: {e}")
            return {
                'title': 'Error Extracting Content',
                'content': html_content[:3000]
            }

    async def summarize_website(self, url: str, target_lang: str) -> str:
        """Fetch and summarize website content"""
        try:
            # Add http:// if no protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                
                # Check if it's HTML content
                content_type = resp.headers.get('content-type', '')
                if 'text/html' not in content_type:
                    return f"⚠️ இந்த URL HTML உள்ளடக்கத்தை கொண்டிருக்கவில்லை. Content-Type: {content_type}"
                
                # Extract article content
                article_data = await self._extract_article_content(resp.text, url)
                title = article_data['title']
                content = article_data['content']
                
                print(f"📰 Extracted: Title='{title}', Content Length={len(content)}")
                
                if len(content) < 100:
                    return f"⚠️ இணையதளத்தில் இருந்து போதுமான தரவு பெற முடியவில்லை. உள்ளடக்கம்: {len(content)} எழுத்துக்கள் மட்டுமே கிடைத்தது."
                
                lang_name = self._get_lang_name(target_lang)
                
                # Construct the prompt with actual content
                user_prompt = f"""தலைப்பு: {title}

இந்த செய்தியை/கட்டுரையை {lang_name} மொழியில் முழுமையாக சுருக்கமாக்குங்கள்:

{content[:4000]}"""

                messages = [
                    {
                        "role": "system", 
                        "content": f"""You are a professional news summarizer.

CRITICAL INSTRUCTIONS:
1. Respond ONLY in {lang_name} language
2. Do NOT include ANY thinking process, tags (<think>, </think>, etc.)
3. Do NOT include ANY code blocks or markdown
4. Provide a CLEAN, WELL-STRUCTURED response
5. Use {lang_name} script and language only
6. Provide a detailed summary with:
   - Headline/Title
   - Main summary (2-3 paragraphs)
   - Key details in bullet points (use • or 1., 2., 3.)
   - Current status or conclusion
7. Keep the summary comprehensive but concise
8. Use proper {lang_name} grammar and script"""
                    },
                    {
                        "role": "user", 
                        "content": user_prompt
                    }
                ]
                
                result = await self.groq.chat_completion(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=700,
                    clean_response=True
                )
                
                # Verify the result is not empty or just the thinking process
                if not result or len(result.strip()) < 10:
                    return f"⚠️ சுருக்கம் உருவாக்க முடியவில்லை. மீண்டும் முயற்சிக்கவும்."
                
                # Check if result contains thinking tags
                if '<think>' in result or '</think>' in result or 'thinking process' in result.lower():
                    # Try one more time with stricter instructions
                    messages[0]['content'] = f"""You are a professional news summarizer. 
                    
CRITICAL WARNING: 
- DO NOT include ANY thinking process or tags
- Respond ONLY with the final summary in {lang_name} language
- If you start with "Here's a thinking process", STOP and start over
- Provide ONLY the summary, nothing else

Guidelines for summary:
1. Headline/Title
2. Main summary (2-3 paragraphs)
3. Key details (bullet points)
4. Conclusion

Use proper {lang_name} grammar and script."""
                    
                    result = await self.groq.chat_completion(
                        messages=messages,
                        temperature=0.2,
                        max_tokens=700,
                        clean_response=True
                    )
                
                return result
                
        except httpx.TimeoutException:
            return "⚠️ இணையதளத்துடன் இணைப்பு தாமதமாகிறது. மீண்டும் முயற்சிக்கவும்."
        except httpx.HTTPStatusError as e:
            return f"⚠️ HTTP பிழை: {e.response.status_code} - {e.response.reason_phrase}"
        except Exception as e:
            return f"⚠️ இணையதள சுருக்கம் பிழை: {str(e)}"
    
    async def summarize_youtube(self, video_url: str, target_lang: str) -> str:
        """Get YouTube transcript and summarize"""
        try:
            # Extract video ID
            patterns = [
                r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[&?]|$)',
                r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
                r'(?:embed\/)([0-9A-Za-z_-]{11})',
                r'(?:shorts\/)([0-9A-Za-z_-]{11})',
            ]
            
            vid = None
            for pattern in patterns:
                match = re.search(pattern, video_url)
                if match:
                    vid = match.group(1)
                    break
            
            if not vid:
                return "⚠️ சரியான YouTube URL அல்ல. URL-ஐ சரிபார்க்கவும்."
            
            # Try to get transcript
            transcript_text = None
            
            # Try with default languages first
            try:
                transcript = YouTubeTranscriptApi.get_transcript(vid)
                transcript_text = ' '.join([t['text'] for t in transcript])
            except Exception as e:
                print(f"Default transcript failed: {e}")
                
                # Try to list available transcripts
                try:
                    transcript_list = YouTubeTranscriptApi.list_transcripts(vid)
                    available_langs = []
                    
                    for t in transcript_list:
                        available_langs.append(t.language_code)
                    
                    if available_langs:
                        for lang in available_langs:
                            try:
                                transcript = YouTubeTranscriptApi.get_transcript(vid, languages=[lang])
                                transcript_text = ' '.join([t['text'] for t in transcript])
                                break
                            except:
                                continue
                except Exception as e:
                    print(f"Transcript listing failed: {e}")
            
            # Try auto-generated transcripts
            if not transcript_text:
                langs = ['en', 'hi', 'ta', 'te', 'ml', 'kn', 'bn', 'mr', 'gu', 'or', 'as', 'pa', 'ur']
                for lang in langs:
                    try:
                        transcript = YouTubeTranscriptApi.get_transcript(vid, languages=[lang])
                        transcript_text = ' '.join([t['text'] for t in transcript])
                        break
                    except:
                        continue
            
            if not transcript_text:
                return "⚠️ வீடியோவில் subtitle/transcript இல்லை. தயவுசெய்து வேறு வீடியோவை முயற்சிக்கவும்."
            
            # Limit transcript length
            if len(transcript_text) > 8000:
                transcript_text = transcript_text[:8000]
            
            lang_name = self._get_lang_name(target_lang)
            
            messages = [
                {
                    "role": "system", 
                    "content": f"""You are a professional video content summarizer.

CRITICAL INSTRUCTIONS:
1. Respond ONLY in {lang_name} language
2. Do NOT include ANY thinking process, tags, or code blocks
3. Provide a CLEAN summary with:
   - Main topic/theme
   - Key points covered (bullet points)
   - Important takeaways
   - Any conclusions
4. Use proper {lang_name} grammar and script"""
                },
                {
                    "role": "user", 
                    "content": f"""இந்த YouTube வீடியோவை {lang_name} மொழியில் சுருக்கமாக்குங்கள்:

வீடியோ ID: {vid}

Transcription:
{transcript_text}"""
                }
            ]
            
            result = await self.groq.chat_completion(
                messages=messages,
                temperature=0.3,
                max_tokens=500,
                clean_response=True
            )
            
            return result
            
        except Exception as e:
            return f"⚠️ YouTube சுருக்கம் பிழை: {str(e)}"
    
    async def summarize_tweet(self, tweet_url: str, target_lang: str) -> str:
        """Scrape public tweet and summarize"""
        try:
            # Clean URL
            if 'x.com' in tweet_url:
                tweet_url = tweet_url.replace('x.com', 'twitter.com')
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(tweet_url, headers=headers)
                resp.raise_for_status()
                
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Extract tweet text using multiple methods
                tweet_text = None
                author = None
                
                # Method 1: Open Graph
                meta_og = soup.find('meta', property='og:description')
                if meta_og and meta_og.get('content'):
                    tweet_text = meta_og['content']
                
                # Method 2: Twitter card
                if not tweet_text:
                    meta_twitter = soup.find('meta', attrs={'name': 'twitter:description'})
                    if meta_twitter and meta_twitter.get('content'):
                        tweet_text = meta_twitter['content']
                
                # Method 3: Title
                if not tweet_text:
                    title = soup.find('title')
                    if title:
                        tweet_text = title.get_text()
                        tweet_text = re.sub(r'\s*[-|]\s*(Twitter|X|𝕏)\s*', '', tweet_text)
                
                # Method 4: Tweet article
                if not tweet_text:
                    article = soup.find('article')
                    if article:
                        tweet_text = article.get_text(separator=' ', strip=True)
                        tweet_text = tweet_text[:1000]
                
                # Method 5: Data attribute
                if not tweet_text:
                    tweet_div = soup.find('div', attrs={'data-testid': 'tweetText'})
                    if tweet_div:
                        tweet_text = tweet_div.get_text(strip=True)
                
                # Method 6: Regex on all text
                if not tweet_text or len(tweet_text) < 10:
                    all_text = soup.get_text(separator=' ', strip=True)
                    tweet_pattern = r'(?:^|\s)[@#][\w]+\s+.*?(?=(?:\.\s|$))'
                    matches = re.findall(tweet_pattern, all_text)
                    if matches:
                        tweet_text = matches[0]
                
                # Extract author
                author_meta = soup.find('meta', property='og:title')
                if author_meta and author_meta.get('content'):
                    author_text = author_meta['content']
                    username_match = re.search(r'@(\w+)', author_text)
                    if username_match:
                        author = username_match.group(1)
                
                if not tweet_text or len(tweet_text) < 5:
                    return "⚠️ Twitter/X-இருந்து tweet text பெற முடியவில்லை."
                
                # Clean text
                tweet_text = re.sub(r'\s+', ' ', tweet_text).strip()
                
                lang_name = self._get_lang_name(target_lang)
                
                prompt = f"Tweet Text:\n{tweet_text[:2000]}"
                if author:
                    prompt = f"Author: @{author}\n\n{prompt}"
                
                messages = [
                    {
                        "role": "system", 
                        "content": f"""You are a professional social media analyst.

CRITICAL INSTRUCTIONS:
1. Respond ONLY in {lang_name} language
2. Do NOT include ANY thinking process, tags, or code blocks
3. Provide a clean analysis with:
   - Main message/claim
   - Context and implications
   - Key impact
4. Use proper {lang_name} grammar and script"""
                    },
                    {
                        "role": "user", 
                        "content": f"""இந்த Tweet-ஐ {lang_name} மொழியில் பகுப்பாய்வு செய்து சுருக்கமாக்குங்கள்:

{prompt}"""
                    }
                ]
                
                result = await self.groq.chat_completion(
                    messages=messages,
                    temperature=0.3,
                    max_tokens=400,
                    clean_response=True
                )
                
                return result
                
        except httpx.TimeoutException:
            return "⚠️ Twitter/X உடன் இணைப்பு தாமதமாகிறது."
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return "⚠️ Tweet கிடைக்கவில்லை. இது நீக்கப்பட்டிருக்கலாம் அல்லது தனிப்பட்டதாக இருக்கலாம்."
            return f"⚠️ Twitter/X பிழை: {e.response.status_code}"
        except Exception as e:
            return f"⚠️ Twitter/X சுருக்கம் பிழை: {str(e)}"