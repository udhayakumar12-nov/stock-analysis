import httpx
from bs4 import BeautifulSoup
from typing import List, Dict
import feedparser
import yfinance as yf

async def fetch_stock_news(symbol: str, company_name: str) -> List[Dict]:
    """Fetch latest news about company from multiple sources"""
    news_items = []
    
    # 1. Google News RSS (Global)
    try:
        query = f"{company_name} stock OR {symbol} share price"
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:5]:
            news_items.append({
                "title": entry.title,
                "link": entry.link,
                "published": entry.published,
                "source": entry.source.title if 'source' in entry else 'Google News'
            })
    except Exception as e:
        print(f"Google News error: {e}")
    
    # 2. Yahoo Finance News
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        for item in news[:5]:
            news_items.append({
                "title": item.get('title', ''),
                "link": item.get('link', ''),
                "published": item.get('providerPublishTime', ''),
                "source": item.get('publisher', 'Yahoo Finance')
            })
    except Exception as e:
        print(f"Yahoo News error: {e}")
    
    # 3. Financial Times (Global)
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.ft.com/search?q={company_name}",
                timeout=10.0
            )
            soup = BeautifulSoup(response.text, 'html.parser')
            for article in soup.select('div.o-teaser')[ :3]:
                title_elem = article.select_one('h3.o-teaser__heading a')
                if title_elem:
                    news_items.append({
                        "title": title_elem.text.strip(),
                        "link": "https://www.ft.com" + title_elem.get('href', ''),
                        "published": "",
                        "source": "Financial Times"
                    })
    except Exception as e:
        print(f"FT error: {e}")
    
    # Remove duplicates
    unique = []
    seen_titles = set()
    for item in news_items:
        title = item.get('title', '')[:50]
        if title not in seen_titles:
            seen_titles.add(title)
            unique.append(item)
    
    return unique[:10]

async def fetch_quarterly_results(symbol: str) -> Dict:
    """Fetch quarterly results data"""
    try:
        ticker = yf.Ticker(symbol)
        financials = ticker.quarterly_financials
        if financials is not None and not financials.empty:
            latest = financials.iloc[:, 0]
            return {
                "quarter": str(financials.columns[0]),
                "revenue": latest.get('Total Revenue', 'N/A'),
                "netIncome": latest.get('Net Income', 'N/A'),
                "eps": latest.get('Basic EPS', 'N/A'),
            }
        return {"error": "காலாண்டு தரவுகள் கிடைக்கவில்லை"}
    except Exception as e:
        return {"error": str(e)}