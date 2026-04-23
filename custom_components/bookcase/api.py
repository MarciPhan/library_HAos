from homeassistant.helpers.aiohttp_client import async_get_clientsession
import logging
import asyncio
import re

_LOGGER = logging.getLogger(__name__)

async def fetch_book_metadata(hass, isbn: str, fast=True):
    """Fetch book metadata. 
    If fast=True, returns the first result that responds.
    If fast=False, waits for all results and merges them for maximum detail.
    """
    isbn = re.sub(r'[- ]', '', isbn)
    session = async_get_clientsession(hass)
    
    tasks = [
        fetch_google_books(session, isbn),
        fetch_knihovny_cz(session, isbn),
        fetch_obalky_knih(session, isbn),
        fetch_open_library(session, isbn),
    ]
    
    if fast:
        try:
            # Try to get AT LEAST one result quickly
            done, pending = await asyncio.wait([asyncio.create_task(t) for t in tasks], timeout=2.5, return_when=asyncio.FIRST_COMPLETED)
            for task in pending: task.cancel()
            for task in done:
                res = task.result()
                if res and res.get("title"): return res
        except Exception: pass
        return None
    else:
        # Full merge mode
        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = [r for r in results if r and not isinstance(r, Exception)]
        
        if not valid_results: return None
        
        merged = {
            "isbn": isbn, "title": None, "subtitle": None, "authors": [], "publishers": [],
            "publish_date": None, "cover_url": None, "pages": None, "url": None, "description": None
        }

        for res in valid_results:
            if not merged["title"] or len(merged["title"]) < 3: merged["title"] = res.get("title")
            if not merged.get("description") or len(res.get("description", "")) > len(merged.get("description", "")):
                merged["description"] = res.get("description")
            
            for author in res.get("authors", []):
                if author and author not in merged["authors"]: merged["authors"].append(author)
            
            for pub in res.get("publishers", []):
                if pub and pub not in merged["publishers"]: merged["publishers"].append(pub)
            
            if not merged["publish_date"]: merged["publish_date"] = res.get("publish_date")
            if res.get("pages") and (not merged["pages"] or res.get("pages") > merged["pages"]):
                merged["pages"] = res.get("pages")

        # Better cover logic
        covers = []
        for res in valid_results:
            url = res.get("cover_url")
            if url:
                score = 10
                if "obalkyknih.cz" in url: score = 100
                if "knihovny.cz" in url: score = 90
                if "google" in url and "zoom=1" not in url: score = 80
                covers.append((score, url))
        if covers:
            covers.sort(key=lambda x: x[0], reverse=True)
            merged["cover_url"] = covers[0][1]

        return merged

async def fetch_open_library(session, isbn: str):
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                key = f"ISBN:{isbn}"
                if key in data:
                    b = data[key]
                    return {
                        "title": b.get("title"),
                        "authors": [a.get("name") for a in b.get("authors", [])],
                        "cover_url": b.get("cover", {}).get("large"),
                        "pages": b.get("number_of_pages"),
                        "publish_date": b.get("publish_date"),
                        "publishers": [p.get("name") for p in b.get("publishers", [])]
                    }
    except Exception: pass
    return None

async def fetch_google_books(session, isbn: str):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("totalItems", 0) > 0:
                    i = data["items"][0]["volumeInfo"]
                    links = i.get("imageLinks", {})
                    cover_url = links.get("extraLarge") or links.get("large") or links.get("thumbnail")
                    if cover_url and cover_url.startswith("http://"): cover_url = cover_url.replace("http://", "https://")
                    return {
                        "title": i.get("title"),
                        "authors": i.get("authors", []),
                        "cover_url": cover_url,
                        "pages": i.get("pageCount"),
                        "description": i.get("description"),
                        "publish_date": i.get("publishedDate"),
                        "publishers": [i.get("publisher")] if i.get("publisher") else []
                    }
    except Exception: pass
    return None

async def fetch_knihovny_cz(session, isbn: str):
    url = f"https://www.knihovny.cz/api/v1/search?q=isbn:{isbn}"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("resultCount", 0) > 0:
                    r = data["records"][0]
                    return {
                        "title": r.get("title"),
                        "authors": list(r.get("authors", {}).get("primary", {}).keys()),
                        "cover_url": f"https://www.knihovny.cz/Cover/Show?id={r.get('id')}&size=large",
                        "publish_date": r.get("publicationDate")
                    }
    except Exception: pass
    return None

async def fetch_obalky_knih(session, isbn: str):
    url = f"https://www.obalkyknih.cz/api/books?query=isbn:{isbn}"
    try:
        async with session.get(url, timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if data:
                    for key in data:
                        b = data[key]
                        if b.get("cover_url"):
                            return {
                                "cover_url": b.get("cover_url"),
                                "title": b.get("title")
                            }
    except Exception: pass
    return None
