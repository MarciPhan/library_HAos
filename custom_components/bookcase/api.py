import aiohttp
import logging
import asyncio

_LOGGER = logging.getLogger(__name__)

async def fetch_book_metadata(isbn: str):
    """Fetch book metadata from multiple sources and merge them."""
    results = await asyncio.gather(
        fetch_open_library(isbn),
        fetch_google_books(isbn),
        fetch_knihovny_cz(isbn),
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

    for res in results:
        if not res or isinstance(res, Exception):
            continue
        
        # Title & Subtitle (take first non-null)
        if not merged["title"] or merged["title"] == "Unknown":
            merged["title"] = res.get("title")
        if not merged["subtitle"]:
            merged["subtitle"] = res.get("subtitle")

        # Authors (merge lists)
        for author in res.get("authors", []):
            if author not in merged["authors"]:
                merged["authors"].append(author)

        # Publishers (merge lists)
        for pub in res.get("publishers", []):
            if pub not in merged["publishers"]:
                merged["publishers"].append(pub)

        # Dates & Pages (take maximum or first)
        if not merged["publish_date"]:
            merged["publish_date"] = res.get("publish_date")
        if not merged["pages"] or (res.get("pages") and res.get("pages") > merged["pages"]):
            merged["pages"] = res.get("pages")

        # Cover (prefer larger or first)
        if not merged["cover_url"]:
            merged["cover_url"] = res.get("cover_url")
        elif "google" in merged["cover_url"] and "knihovny" in (res.get("cover_url") or ""):
            # Prefer Knihovny.cz covers as they are often better for Czech books
            merged["cover_url"] = res.get("cover_url")

        # Subjects
        for sub in res.get("subjects", []):
            if sub not in merged["subjects"]:
                merged["subjects"].append(sub)
        
        if not merged["url"]:
            merged["url"] = res.get("url")
        
        if not merged["description"]:
            merged["description"] = res.get("description")

    if not merged["title"]:
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
                        cover_url = i.get("imageLinks", {}).get("thumbnail")
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
