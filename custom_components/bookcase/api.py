import aiohttp
import logging
import asyncio
import re

_LOGGER = logging.getLogger(__name__)

async def fetch_book_metadata(isbn: str):
    """Fetch book metadata from multiple sources and merge them for maximum robustness."""
    # Clean ISBN
    isbn = re.sub(r'[- ]', '', isbn)
    
    results = await asyncio.gather(
        fetch_open_library(isbn),
        fetch_google_books(isbn),
        fetch_knihovny_cz(isbn),
        fetch_obalky_knih(isbn),
        return_exceptions=True
    )

    merged = {
        "isbn": isbn,
        "title": None,
        "subtitle": None,
        "authors": [],
        "publishers": [],
        "publish_date": None,
        "languages": [],
        "cover_url": None,
        "pages": None,
        "url": None,
        "subjects": [],
        "description": None
    }

    # Step 1: Aggregate all textual data
    for res in results:
        if not res or isinstance(res, Exception):
            continue
        
        if not merged["title"] or len(merged["title"]) < 3:
            merged["title"] = res.get("title")
        if not merged["subtitle"]:
            merged["subtitle"] = res.get("subtitle")

        for author in res.get("authors", []):
            if author and author not in merged["authors"]:
                merged["authors"].append(author)

        for pub in res.get("publishers", []):
            if pub and pub not in merged["publishers"]:
                merged["publishers"].append(pub)

        if not merged["publish_date"]:
            merged["publish_date"] = res.get("publish_date")
        
        res_pages = res.get("pages")
        if res_pages and (not merged["pages"] or res_pages > merged["pages"]):
            merged["pages"] = res_pages

        for sub in res.get("subjects", []):
            if sub and sub not in merged["subjects"]:
                merged["subjects"].append(sub)
        
        if not merged["url"]:
            merged["url"] = res.get("url")
        
        if not merged["description"] or len(res.get("description", "")) > len(merged["description"]):
            merged["description"] = res.get("description")

    # Step 2: Robust Cover Selection
    # We collect all possible covers and pick the best one
    covers = []
    for res in results:
        if not res or isinstance(res, Exception): continue
        url = res.get("cover_url")
        if url:
            # Score the cover source
            score = 10
            if "obalkyknih.cz" in url: score = 100 # High quality for CZ
            if "knihovny.cz" in url: score = 90
            if "google" in url and "zoom=1" not in url: score = 80
            if "openlibrary" in url: score = 70
            covers.append((score, url))
    
    if covers:
        # Sort by score descending and pick best
        covers.sort(key=lambda x: x[0], reverse=True)
        merged["cover_url"] = covers[0][1]

    if not merged["title"]:
        # Last resort: Try title search if ISBN gave nothing (though we need title for that)
        # For now, if ISBN fails, we return None
        return None

    return merged

async def fetch_open_library(isbn: str):
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    key = f"ISBN:{isbn}"
                    if key in data:
                        b = data[key]
                        return {
                            "title": b.get("title"),
                            "subtitle": b.get("subtitle"),
                            "authors": [a.get("name") for a in b.get("authors", [])],
                            "publishers": [p.get("name") for p in b.get("publishers", [])],
                            "publish_date": b.get("publish_date"),
                            "cover_url": b.get("cover", {}).get("large"),
                            "pages": b.get("number_of_pages"),
                            "url": b.get("url"),
                            "subjects": [s.get("name") for s in b.get("subjects", [])[:5]]
                        }
    except Exception: pass
    return None

async def fetch_google_books(isbn: str):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("totalItems", 0) > 0:
                        i = data["items"][0]["volumeInfo"]
                        # Try to get a high-res cover
                        links = i.get("imageLinks", {})
                        cover_url = links.get("extraLarge") or links.get("large") or links.get("medium") or links.get("thumbnail")
                        if cover_url and cover_url.startswith("http://"):
                            cover_url = cover_url.replace("http://", "https://")
                        return {
                            "title": i.get("title"),
                            "subtitle": i.get("subtitle"),
                            "authors": i.get("authors", []),
                            "publishers": [i.get("publisher")] if i.get("publisher") else [],
                            "publish_date": i.get("publishedDate"),
                            "cover_url": cover_url,
                            "pages": i.get("pageCount"),
                            "url": i.get("infoLink"),
                            "subjects": i.get("categories", []),
                            "description": i.get("description")
                        }
    except Exception: pass
    return None

async def fetch_knihovny_cz(isbn: str):
    url = f"https://www.knihovny.cz/api/v1/search?q=isbn:{isbn}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("resultCount", 0) > 0:
                        r = data["records"][0]
                        return {
                            "title": r.get("title"),
                            "authors": list(r.get("authors", {}).get("primary", {}).keys()),
                            "publishers": list(r.get("authors", {}).get("secondary", {}).keys()),
                            "publish_date": r.get("publicationDate"),
                            "cover_url": f"https://www.knihovny.cz/Cover/Show?id={r.get('id')}&size=large",
                            "url": f"https://www.knihovny.cz/Record/{r.get('id')}",
                            "subjects": [s[0] for s in r.get("subjects", [])[:5]]
                        }
    except Exception: pass
    return None

async def fetch_obalky_knih(isbn: str):
    """Specialized service for Czech book covers."""
    url = f"https://www.obalkyknih.cz/api/books?query=isbn:{isbn}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        # ObalkyKnih returns a dict where keys are ISBNs
                        for key in data:
                            b = data[key]
                            if b.get("cover_url"):
                                return {
                                    "cover_url": b.get("cover_url"),
                                    "title": b.get("title")
                                }
    except Exception: pass
    return None
