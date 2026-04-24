"""Book metadata fetching from multiple sources."""
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import logging
import asyncio
import re

_LOGGER = logging.getLogger(__name__)

# Timeout pro jednotlivé zdroje (sekundy)
_SOURCE_TIMEOUT = 6
# Celkový timeout pro gather všech zdrojů
_TOTAL_TIMEOUT = 8

# Mapování jazykových kódů na české názvy
_LANG_MAP = {
    "cs": "Čeština", "sk": "Slovenština", "en": "Angličtina",
    "de": "Němčina", "fr": "Francouzština", "pl": "Polština",
    "es": "Španělština", "it": "Italština", "ru": "Ruština",
    "pt": "Portugalština", "nl": "Holandština", "la": "Latina",
    "und": "", "mul": "Vícejazyčné",
}


def _normalize_language(lang_code: str | None) -> str:
    """Convert ISO 639 language code to Czech name."""
    if not lang_code:
        return ""
    code = lang_code.strip().lower()[:2]
    return _LANG_MAP.get(code, lang_code)


async def fetch_book_metadata(hass, isbn: str) -> dict | None:
    """Fetch book metadata from all sources in parallel, merge results.
    
    Returns merged dict or None if no source found anything.
    All sources run in parallel with individual timeouts.
    The total operation is capped at _TOTAL_TIMEOUT seconds.
    """
    isbn = re.sub(r'[- ]', '', isbn)
    if not isbn:
        return None

    session = async_get_clientsession(hass)

    # Spustíme všechny zdroje paralelně
    results = await asyncio.wait_for(
        asyncio.gather(
            _safe_fetch("Google Books", fetch_google_books, session, isbn),
            _safe_fetch("Open Library", fetch_open_library, session, isbn),
            _safe_fetch("Knihovny.cz", fetch_knihovny_cz, session, isbn),
        ),
        timeout=_TOTAL_TIMEOUT,
    )

    # Filtrujeme platné výsledky
    valid = [r for r in results if r is not None]
    if not valid:
        _LOGGER.warning("Bookcase: No metadata found for ISBN %s from any source", isbn)
        return None

    _LOGGER.info(
        "Bookcase: Got %d/%d results for ISBN %s",
        len(valid), len(results), isbn
    )

    return _merge_results(isbn, valid)


async def _safe_fetch(name: str, fn, session, isbn: str) -> dict | None:
    """Wrap a fetch function with timeout and error handling."""
    try:
        result = await asyncio.wait_for(fn(session, isbn), timeout=_SOURCE_TIMEOUT)
        if result and result.get("title"):
            _LOGGER.debug("Bookcase: %s returned data for ISBN %s", name, isbn)
            return result
        # Zdroj odpověděl ale nic nenašel – to je OK, ne error
        return None
    except asyncio.TimeoutError:
        _LOGGER.debug("Bookcase: %s timed out for ISBN %s", name, isbn)
        return None
    except Exception as err:
        _LOGGER.debug("Bookcase: %s failed for ISBN %s: %s", name, isbn, err)
        return None


def _merge_results(isbn: str, results: list[dict]) -> dict:
    """Merge metadata from multiple sources into one rich record."""
    merged = {
        "isbn": isbn,
        "title": None,
        "subtitle": None,
        "authors": [],
        "publishers": [],
        "publish_date": None,
        "cover_url": None,
        "pages": None,
        "description": None,
        "language": None,
        "genres": [],
        "url": None,
    }

    for res in results:
        # Titul – preferujeme delší (pravděpodobně kompletní)
        res_title = res.get("title")
        if res_title and (not merged["title"] or len(res_title) > len(merged["title"])):
            merged["title"] = res_title

        # Podnázev – první nalezený
        if not merged["subtitle"] and res.get("subtitle"):
            merged["subtitle"] = res["subtitle"]

        # Popis – preferujeme delší
        res_desc = res.get("description", "")
        if res_desc and (not merged["description"] or len(res_desc) > len(merged["description"] or "")):
            merged["description"] = res_desc

        # Autoři – deduplikujeme
        for author in res.get("authors", []):
            if author and author not in merged["authors"]:
                merged["authors"].append(author)

        # Nakladatelé – deduplikujeme
        for pub in res.get("publishers", []):
            if pub and pub not in merged["publishers"]:
                merged["publishers"].append(pub)

        # Rok vydání – první nalezený
        if not merged["publish_date"] and res.get("publish_date"):
            merged["publish_date"] = res["publish_date"]

        # Počet stran – preferujeme větší (přesnější)
        res_pages = res.get("pages")
        if res_pages and (not merged["pages"] or res_pages > merged["pages"]):
            merged["pages"] = res_pages

        # Jazyk – první nalezený (neprázdný)
        if not merged["language"] and res.get("language"):
            merged["language"] = res["language"]

        # Žánry – deduplikujeme
        for genre in res.get("genres", []):
            if genre and genre not in merged["genres"]:
                merged["genres"].append(genre)

        # URL odkaz na knihu – první nalezený
        if not merged["url"] and res.get("url"):
            merged["url"] = res["url"]

    # Obálka – prioritizace podle kvality zdroje
    cover_candidates = []
    for res in results:
        url = res.get("cover_url")
        if url:
            score = 10  # default
            if "googleapis.com" in url or "books.google" in url:
                # Google Books má nejspolehlivější obálky
                score = 100 if "zoom=1" not in url else 80
            elif "openlibrary.org" in url:
                score = 70
            elif "knihovny.cz" in url:
                # Knihovny.cz často vrací placeholder PNG
                score = 30
            cover_candidates.append((score, url))

    # Fallback: přímý Open Library cover URL (existuje vždy, i když API nevrátilo data)
    cover_candidates.append((20, f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"))

    if cover_candidates:
        cover_candidates.sort(key=lambda x: x[0], reverse=True)
        merged["cover_url"] = cover_candidates[0][1]

    return merged


# ──────────────────────────────────────────────
# Jednotlivé zdroje
# ──────────────────────────────────────────────

async def fetch_google_books(session, isbn: str) -> dict | None:
    """Google Books API – nejbohatší zdroj metadat."""
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        if data.get("totalItems", 0) == 0:
            return None

        info = data["items"][0]["volumeInfo"]
        links = info.get("imageLinks", {})
        cover = links.get("extraLarge") or links.get("large") or links.get("medium") or links.get("thumbnail")
        if cover and cover.startswith("http://"):
            cover = cover.replace("http://", "https://", 1)

        return {
            "title": info.get("title"),
            "subtitle": info.get("subtitle"),
            "authors": info.get("authors", []),
            "cover_url": cover,
            "pages": info.get("pageCount"),
            "description": info.get("description"),
            "publish_date": info.get("publishedDate"),
            "publishers": [info["publisher"]] if info.get("publisher") else [],
            "language": _normalize_language(info.get("language")),
            "genres": info.get("categories", []),
            "url": info.get("infoLink"),
        }


async def fetch_open_library(session, isbn: str) -> dict | None:
    """Open Library API."""
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data"
    async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        key = f"ISBN:{isbn}"
        if key not in data:
            return None

        b = data[key]

        # Subjects jako žánry
        genres = []
        for s in b.get("subjects", []):
            name = s.get("name") if isinstance(s, dict) else str(s)
            if name and name not in genres:
                genres.append(name)

        return {
            "title": b.get("title"),
            "subtitle": b.get("subtitle"),
            "authors": [a.get("name") for a in b.get("authors", []) if a.get("name")],
            "cover_url": b.get("cover", {}).get("large") or b.get("cover", {}).get("medium"),
            "pages": b.get("number_of_pages"),
            "publish_date": b.get("publish_date"),
            "publishers": [p.get("name") for p in b.get("publishers", []) if p.get("name")],
            "genres": genres[:5],  # Omezíme na 5 nejdůležitějších
            "url": b.get("url"),
        }


async def fetch_knihovny_cz(session, isbn: str) -> dict | None:
    """Knihovny.cz API – správný ISN search."""
    url = f"https://www.knihovny.cz/api/v1/search?lookfor={isbn}&type=ISN"
    async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        count = data.get("resultCount", 0)
        if count == 0 or count > 50:
            # 0 = nic nenalezeno, >50 = příliš obecný výsledek (špatný query)
            return None

        r = data["records"][0]
        authors_dict = r.get("authors", {}).get("primary", {})
        # primary může být dict nebo list (prázdný)
        if isinstance(authors_dict, list):
            authors_dict = {}

        # Žánry z subjects – každý subject je list stringů, bereme první
        genres = []
        for subj in r.get("subjects", []):
            if isinstance(subj, list) and subj:
                name = subj[0]
                if name and name not in genres:
                    genres.append(name)

        # Jazyky
        langs = r.get("languages", [])
        language = _normalize_language(langs[0]) if langs else ""

        return {
            "title": r.get("title"),
            "authors": list(authors_dict.keys()) if authors_dict else [],
            "cover_url": f"https://www.knihovny.cz/Cover/Show?id={r.get('id')}&size=large" if r.get("id") else None,
            "publish_date": r.get("publicationDate"),
            "publishers": [],
            "language": language,
            "genres": genres[:5],
            "url": f"https://www.knihovny.cz/Record/{r.get('id')}" if r.get("id") else None,
        }
