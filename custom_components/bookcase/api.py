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
    original_query = isbn.strip()
    normalized_isbn = re.sub(r'[- ]', '', original_query)
    
    session = async_get_clientsession(hass)

    # Spustíme všechny zdroje paralelně
    results = await asyncio.wait_for(
        asyncio.gather(
            _safe_fetch("Google Books", fetch_google_books, session, normalized_isbn),
            _safe_fetch("Open Library", fetch_open_library, session, normalized_isbn),
            _safe_fetch("Knihovny.cz", fetch_knihovny_cz, session, normalized_isbn, original_query),
            _safe_fetch("ObalkyKnih", fetch_obalkyknih_cz, session, normalized_isbn),
            _safe_fetch("Didasko.cz", fetch_didasko_cz, session, normalized_isbn),
            _safe_fetch("Databáze knih", fetch_databazeknih_cz, session, original_query),
            _safe_fetch("NKP", fetch_nkp_cz, session, original_query),
            _safe_fetch("Martinus", fetch_martinus_cz, session, normalized_isbn, original_query),
        ),
        timeout=_TOTAL_TIMEOUT,
    )

    # Filtrujeme platné výsledky
    valid = [r for r in results if r is not None]
    if not valid:
        _LOGGER.warning("Bookcase: No metadata found for query '%s' from any source", original_query)
        return None

    _LOGGER.info(
        "Bookcase: Got %d/%d results for query '%s'",
        len(valid), len(results), original_query
    )

    return _merge_results(normalized_isbn, valid)


async def _safe_fetch(name: str, fn, session, *args) -> dict | None:
    """Wrap a fetch function with timeout and error handling."""
    # Pro logování použijeme první argument z args (což je obvykle ISBN)
    query = args[0] if args else "unknown"
    try:
        result = await asyncio.wait_for(fn(session, *args), timeout=_SOURCE_TIMEOUT)
        if result and (result.get("title") or result.get("cover_url")):
            _LOGGER.debug("Bookcase: %s returned data for %s", name, query)
            return result
        return None
    except asyncio.TimeoutError:
        _LOGGER.debug("Bookcase: %s timed out for %s", name, query)
        return None
    except Exception as err:
        _LOGGER.debug("Bookcase: %s failed for %s: %s", name, query, err)
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
        # ISBN – pokud jsme hledali podle názvu nebo máme kratší verzi, preferujeme delší nalezené ISBN
        res_isbn = res.get("isbn")
        if res_isbn and (not merged["isbn"] or not any(c.isdigit() for c in merged["isbn"]) or len(res_isbn) > len(merged["isbn"])):
            merged["isbn"] = res_isbn

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

    # Pokud titul obsahuje dvojtečku a podnázev je prázdný, rozdělíme ho
    if merged["title"] and ":" in merged["title"] and not merged["subtitle"]:
        parts = merged["title"].split(":", 1)
        merged["title"] = parts[0].strip()
        merged["subtitle"] = parts[1].strip()

    # Obálka – prioritizace podle kvality zdroje
    cover_candidates = []
    for res in results:
        url = res.get("cover_url")
        if url:
            score = 10  # default
            if "obalkyknih.cz" in url:
                score = 110 # ObalkyKnih (české) mají nejvyšší prioritu pro lokální knihy
            elif "databazeknih.cz" in url:
                score = 120 # Databáze knih má často nejhezčí fotky
            elif "martinus.cz" in url or "martinus.sk" in url:
                score = 105
            elif "googleapis.com" in url or "books.google" in url:
                # Google Books má velmi spolehlivé obálky
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


async def fetch_obalkyknih_cz(session, isbn: str) -> dict | None:
    """Stahuje obálku z HTML obalkyknih.cz (API nefunguje spolehlivě z klienta bez registrace)."""
    url = f"https://www.obalkyknih.cz/view?isbn={isbn}"
    async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
        if resp.status != 200:
            return None
        text = await resp.text()
        
        # Extrahuje link na velkou obálku
        match = re.search(r'<link\s+rel=["\']previewimage["\']\s+href=["\']([^"\']+)["\']', text, re.IGNORECASE)
        if match:
            cover_url = match.group(1)
            if cover_url.startswith("//"):
                cover_url = "https:" + cover_url
            elif cover_url.startswith("/"):
                cover_url = "https://www.obalkyknih.cz" + cover_url
            
            # Pokud našel obálku, vrátíme alespoň cover a title
            # Můžeme přidat i prázdný zbytek
            return {
                "cover_url": cover_url,
                "title": "Nalezeno v ObálkyKnih" # Tím zabráníme aby funkce vrátila None sice bez validního textu, ale _safe_fetch to zahodí bez titlu
            }
        return None


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


async def fetch_knihovny_cz(session, isbn: str, original_query: str = "") -> dict | None:
    """Knihovny.cz API – správný ISN search + AllFields fallback pro staré kódy."""
    # 1. Zkusíme ISN search (ISBN/ISSN)
    url = f"https://www.knihovny.cz/api/v1/search?lookfor={isbn}&type=ISN"
    async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
        if resp.status == 200:
            data = await resp.json()
            if data.get("resultCount", 0) > 0:
                return await _parse_knihovny_record(session, data["records"][0])

    # 2. Fallback: Citované AllFields vyhledávání pro staré publikace (např. "23-058-65")
    if original_query and original_query != isbn:
        quoted = f'"{original_query}"'
        url = f"https://www.knihovny.cz/api/v1/search?lookfor={quoted}&type=AllFields"
        async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("resultCount", 0) > 0:
                    return await _parse_knihovny_record(session, data["records"][0])
    return None


async def _parse_knihovny_record(session, r: dict) -> dict:
    """Parse common Knihovny.cz record format."""
    authors_dict = r.get("authors", {}).get("primary", {})
    if isinstance(authors_dict, list): authors_dict = {}

    genres = []
    for subj in r.get("subjects", []):
        if isinstance(subj, list) and subj:
            name = subj[0]
            if name and name not in genres: genres.append(name)

    langs = r.get("languages", [])
    language = _normalize_language(langs[0]) if langs else ""
    
    publish_date = r.get("publicationDate")
    publishers = []
    pages = None
    
    record_id = r.get("id")
    if record_id:
        xml_url = f"https://www.knihovny.cz/Record/{record_id}/Export?style=MARCXML"
        try:
            async with session.get(xml_url, timeout=5) as xml_resp:
                if xml_resp.status == 200:
                    xml = await xml_resp.text()
                    if not publish_date:
                        y = re.search(r'<subfield code="c">.*?(\d{4}).*?</subfield>', xml)
                        if y: publish_date = y.group(1)
                    p = re.search(r'<datafield tag="26[04]".*?code="b">([^<]+)</subfield>', xml, re.DOTALL)
                    if p: publishers.append(p.group(1).strip(" ,:;/"))
                    pg = re.search(r'<subfield code="a">.*?(\d+)\s*s\..*?</subfield>', xml)
                    if pg: pages = int(pg.group(1))
        except: pass

    return {
        "title": r.get("title"),
        "authors": list(authors_dict.keys()) if authors_dict else [],
        "cover_url": f"https://www.knihovny.cz/Cover/Show?id={record_id}&size=large" if record_id else None,
        "publish_date": publish_date,
        "publishers": publishers,
        "pages": pages,
        "language": language,
        "genres": genres[:5],
        "url": f"https://www.knihovny.cz/Record/{record_id}" if record_id else None,
    }


async def fetch_nkp_cz(session, query: str) -> dict | None:
    """Národní knihovna ČR – Aleph X-Server."""
    # Pro jistotu zkusíme citované vyhledávání pro ne-ISBN kódy
    req = f'"{query}"' if "-" in query else query
    url = f"https://aleph.nkp.cz/X?op=find&code=WRD&request={req}"
    try:
        async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
            if resp.status != 200: return None
            text = await resp.text()
            
        set_entry = re.search(r'<set_number>(\d+)</set_number>.*?<no_records>(\d+)</no_records>', text, re.DOTALL)
        if not set_entry or int(set_entry.group(2)) == 0: return None
        
        set_num = set_entry.group(1)
        present_url = f"https://aleph.nkp.cz/X?op=present&set_number={set_num}&set_entry=000000001&format=marc"
        async with session.get(present_url, timeout=_SOURCE_TIMEOUT) as resp:
            if resp.status != 200: return None
            marc = await resp.text()
            
        # Velmi hrubý MARC parser přes regexy
        def get_field(tag, sub=""):
            m = re.search(f'<varfield id="{tag}"[^>]*>(.*?)</varfield>', marc, re.DOTALL)
            if not m: return ""
            if not sub: return m.group(1).replace('<subfield label="', '$$').replace('">', '').replace('</subfield>', '')
            sm = re.search(f'<subfield label="{sub}">(.*?)</subfield>', m.group(1))
            return sm.group(1).strip() if sm else ""

        title = get_field("245", "a").strip(" /:,")
        author = get_field("100", "a").strip(" ,")
        publisher = get_field("260", "b").strip(" ,:") or get_field("264", "b").strip(" ,:")
        year = re.search(r'\d{4}', get_field("260", "c") or get_field("264", "c"))
        pages = re.search(r'(\d+)\s*s\.', get_field("300", "a"))
        sysid = re.search(r'<doc_number>(\d+)</doc_number>', marc)

        if not title: return None
        return {
            "title": title,
            "authors": [author] if author else [],
            "publishers": [publisher] if publisher else [],
            "publish_date": year.group(0) if year else None,
            "pages": int(pages.group(1)) if pages else None,
            "url": f"https://aleph.nkp.cz/F/?func=direct&doc_number={sysid.group(1)}&local_base=NKC" if sysid else None,
        }
    except: return None


async def fetch_databazeknih_cz(session, query: str) -> dict | None:
    """Databazeknih.cz – nejlepší český komunitní web."""
    url = f"https://www.databazeknih.cz/search?q={query}"
    try:
        async with session.get(url, timeout=_SOURCE_TIMEOUT, allow_redirects=True) as resp:
            if resp.status != 200: return None
            text = await resp.text()
            # Pokud nás to hodilo rovnou na knihu (přesměrování při přesné shodě)
            final_url = str(resp.url)
            
        if "/knihy/" not in final_url and "/prehled-knihy/" not in final_url:
            # Jsme na výsledcích hledání – zkusíme vzít první odkaz
            match = re.search(r'href=["\'](https://www.databazeknih.cz/(?:prehled-knihy|knihy)/[^"\']+)["\']', text)
            if not match: return None
            url = match.group(1)
            async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
                if resp.status != 200: return None
                text = await resp.text()
        
        title_match = re.search(r'<h1[^>]* itemprop="name">([^<]+)</h1>', text)
        if not title_match: title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', text)
        
        author_match = re.search(r'<a[^>]+ itemprop="author">([^<]+)</a>', text)
        desc_match = re.search(r'<p id="short_desc"[^>]*>(.*?)</p>', text, re.DOTALL)
        img_match = re.search(r'<img[^>]+class="kniha_img"[^>]+src="([^"]+)"', text)
        
        # Detaily v pravém sloupci
        pages = re.search(r'Po\u010det stran:.*?(\d+)', text)
        year = re.search(r'Rok vyd\u00e1n\u00ed:.*?(\d{4})', text)
        publisher = re.search(r'Nakladatelstv\u00ed:.*?<a[^>]+>([^<]+)</a>', text)
        isbn_match = re.search(r'ISBN:.*?([0-9- ]{10,20})', text)

        return {
            "title": title_match.group(1).strip() if title_match else None,
            "authors": [author_match.group(1).strip()] if author_match else [],
            "description": re.sub(r'<[^>]+>', '', desc_match.group(1)).strip() if desc_match else None,
            "cover_url": img_match.group(1) if img_match else None,
            "pages": int(pages.group(1)) if pages else None,
            "publish_date": year.group(0) if year else None,
            "publishers": [publisher.group(1).strip()] if publisher else [],
            "isbn": re.sub(r'[- ]', '', isbn_match.group(1)) if isbn_match else None,
            "url": final_url if "/knihy/" in final_url else url
        }
    except: return None


async def fetch_martinus_cz(session, isbn: str, query: str = "") -> dict | None:
    """Martinus.cz – velký český e-shop."""
    q = isbn if len(isbn) >= 10 else query
    url = f"https://www.martinus.cz/vyhledavani?q={q}"
    try:
        async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
            if resp.status != 200: return None
            text = await resp.text()
            final_url = str(resp.url)
            
        if "/produkty/" not in final_url:
            # Zkusíme najít první produkt v seznamu
            match = re.search(r'href=["\'](/produkty/[^"\']+)["\']', text)
            if not match: return None
            url = "https://www.martinus.cz" + match.group(1)
            async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
                if resp.status != 200: return None
                text = await resp.text()
        else:
            url = final_url

        title = re.search(r'<h1[^>]*>([^<]+)</h1>', text)
        author = re.search(r'<li class="product-detail__author">.*?<a[^>]*>([^<]+)</a>', text, re.DOTALL)
        img = re.search(r'<img[^>]+class="product-detail__image"[^>]+src="([^"]+)"', text)
        pages = re.search(r'Po\u010det stran:.*?(\d+)', text)
        year = re.search(r'Rok vyd\u00e1n\u00ed:.*?(\d{4})', text)
        
        return {
            "title": title.group(1).strip() if title else None,
            "authors": [author.group(1).strip()] if author else [],
            "cover_url": img.group(1) if img else None,
            "pages": int(pages.group(1)) if pages else None,
            "publish_date": year.group(0) if year else None,
            "isbn": re.sub(r'[- ]', '', isbn_match.group(1)) if isbn_match else None,
            "url": url
        }
    except: return None


async def fetch_didasko_cz(session, isbn: str) -> dict | None:
    """Scrapuje obchod Didasko.cz pro jejich specifické knihy."""
    url = f"https://didasko.cz/?s={isbn}&post_type=product"
    async with session.get(url, timeout=_SOURCE_TIMEOUT) as resp:
        if resp.status != 200: return None
        text = await resp.text()
        
    links = set(re.findall(r'href="(https://didasko.cz/obchod/[^/"]+/)"', text))
    links = [l for l in links if "feed" not in l and "page" not in l][:5]
    
    for link in links:
        async with session.get(link, timeout=_SOURCE_TIMEOUT) as resp:
            if resp.status == 200:
                ptext = await resp.text()
                
                # Zkontrolovat, zda ISBN sedí
                isbn_match = re.search(r'<li class="isbn[^>]+>.*?<span class="attribute-value">([^<]+)</span>', ptext, re.IGNORECASE | re.DOTALL)
                if not isbn_match: continue
                found_isbn = re.sub(r'[- ]', '', isbn_match.group(1))
                if found_isbn != isbn: continue
                
                # Máme produkt
                title_match = re.search(r'<h1 class="product_title entry-title">([^<]+)</h1>', ptext)
                title = title_match.group(1).replace("&#8211;", "-").strip() if title_match else None
                
                img_match = re.search(r'<img[^>]+src="([^"]+)"[^>]*class="[^"]*wp-post-image', ptext)
                cover_url = img_match.group(1) if img_match else None
                
                author_match = re.search(r'<li class="autor[^>]+>.*?<span class="attribute-value">([^<]+)</span>', ptext, re.IGNORECASE | re.DOTALL)
                author = author_match.group(1).strip() if author_match else None
                
                pages_match = re.search(r'<li class="pocet-stran[^>]+>.*?<span class="attribute-value">([^<]+)</span>', ptext, re.IGNORECASE | re.DOTALL)
                pages = int(pages_match.group(1)) if pages_match else None
                
                year_match = re.search(r'<li class="rok-vydani[^>]+>.*?<span class="attribute-value">([^<]+)</span>', ptext, re.IGNORECASE | re.DOTALL)
                year = year_match.group(1).strip() if year_match else None
                
                pub_match = re.search(r'<li class="vydavatel[^>]+>.*?<span class="attribute-value">([^<]+)</span>', ptext, re.IGNORECASE | re.DOTALL)
                publisher = pub_match.group(1).strip() if pub_match else None
                
                return {
                    "title": title,
                    "authors": [author] if author else [],
                    "cover_url": cover_url,
                    "pages": pages,
                    "publish_date": year,
                    "publishers": [publisher] if publisher else [],
                    "url": link
                }
    return None
