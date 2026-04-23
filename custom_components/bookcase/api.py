import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

async def fetch_book_metadata(isbn: str):
    """Fetch book metadata from Open Library API."""
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status != 200:
                    _LOGGER.error("Error fetching book metadata: %s", response.status)
                    return None
                
                data = await response.json()
                key = f"ISBN:{isbn}"
                
                if key not in data:
                    _LOGGER.warning("Book with ISBN %s not found in Open Library", isbn)
                    return None
                
                book_info = data[key]
                return {
                    "isbn": isbn,
                    "title": book_info.get("title", "Unknown Title"),
                    "subtitle": book_info.get("subtitle"),
                    "authors": [author.get("name") for author in book_info.get("authors", [])],
                    "publishers": [pub.get("name") for pub in book_info.get("publishers", [])],
                    "publish_date": book_info.get("publish_date"),
                    "languages": [lang.get("name") for lang in book_info.get("languages", [])],
                    "cover_url": book_info.get("cover", {}).get("large"),
                    "pages": book_info.get("number_of_pages"),
                    "url": book_info.get("url"),
                    "subjects": [sub.get("name") for sub in book_info.get("subjects", [])[:5]]  # Limit to 5 genres
                }
        except Exception as e:
            _LOGGER.error("Exception while fetching book metadata: %s", e)
            return None
