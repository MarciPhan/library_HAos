import logging
import asyncio
import aiohttp

from .const import (
    WIKI_SEARCH_URL, 
    WIKI_SUMMARY_URL, 
    MOISTURE_HEURISTICS
)

class WikipediaAPI:
    """Client for Wikipedia API."""

    def __init__(self, session: aiohttp.ClientSession, lang: str = "en"):
        """Initialize."""
        self.session = session
        self.lang = lang
        self.search_url = f"https://{lang}.wikipedia.org/w/api.php"
        self.summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"

    async def search_plants(self, query: str):
        """Search for plants on Wikipedia."""
        params = {
            "action": "opensearch",
            "search": query,
            "limit": 10,
            "namespace": 0,
            "format": "json"
        }
        try:
            async with asyncio.timeout(10):
                response = await self.session.get(self.search_url, params=params)
                if response.status == 200:
                    result = await response.json()
                    # OpenSearch returns [query, titles, summaries, links]
                    titles = result[1]
                    return [{"pid": t, "alias": t, "display_pid": t, "source": "wikipedia"} for t in titles]
                return []
        except Exception as err:
            _LOGGER.error("Error searching Wikipedia (%s): %s", self.lang, err)
            return []

    async def get_plant_detail(self, title: str):
        """Get details for a specific plant from Wikipedia."""
        url = f"{self.summary_url}{title.replace(' ', '_')}"
        try:
            async with asyncio.timeout(10):
                response = await self.session.get(url)
                if response.status == 200:
                    data = await response.json()
                    extract = data.get("extract", "")
                    
                    # Heuristic care analysis
                    min_moist = self._heuristic_analysis(extract)
                    
                    return {
                        "pid": title,
                        "display_pid": title,
                        "description": extract,
                        "image_url": data.get("thumbnail", {}).get("source"),
                        "min_soil_moist": min_moist,
                        "source": "wikipedia"
                    }
                return None
        except Exception as err:
            _LOGGER.error("Error getting Wikipedia detail for %s: %s", title, err)
            return None

    def _heuristic_analysis(self, text: str) -> int:
        """Estimate moisture needs from text."""
        text = text.lower()
        score = 30 # Default medium
        matches = 0
        
        for keyword, value in MOISTURE_HEURISTICS.items():
            if keyword in text:
                score += value
                matches += 1
                
        if matches > 0:
            return round(score / (matches + 1)) # Weighted average with default
            
        return 30
