import logging
import uuid
import re
import homeassistant.util.dt as dt_util
import os
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from .const import DOMAIN, STATUS_TO_READ
from .api import fetch_book_metadata

_LOGGER = logging.getLogger(__name__)

class BookcasePanelView(HomeAssistantView):
    """View to serve the panel JavaScript file directly."""
    url = "/bookcase_static/panel.js"
    name = "api:bookcase:panel"
    requires_auth = False

    async def get(self, request):
        """Serve the panel.js file."""
        file_path = os.path.join(os.path.dirname(__file__), "www", "panel.js")
        if not os.path.exists(file_path):
            return aiohttp.web.Response(status=404)
        return aiohttp.web.FileResponse(file_path)

class BookcaseExportView(HomeAssistantView):
    """View to export the entire library as a CSV file."""
    url = "/bookcase_static/export.csv"
    name = "api:bookcase:export"
    requires_auth = False # Veřejné pro stažení z panelu

    def __init__(self, books):
        self.books = books

    async def get(self, request):
        """Generate and serve the CSV file."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        
        # Hlavička
        writer.writerow([
            "ID", "ISBN", "Titul", "Podnázev", "Autoři", "Nakladatel", 
            "Rok", "Jazyk", "Stran", "Kusů", "Stav", "Přečteno", 
            "Mé hodnocení", "Mé poznámky", "Půjčeno komu", "Termín vrácení"
        ])
        
        for book in self.books.values():
            loans = book.get("active_loans", [])
            loan_people = ", ".join([l.get("person", "") for l in loans])
            loan_dates = ", ".join([l.get("until", "") for l in loans])
            
            writer.writerow([
                book.get("id", ""),
                book.get("isbn", ""),
                book.get("title", ""),
                book.get("subtitle", ""),
                ", ".join(book.get("authors", [])),
                book.get("publisher", ""),
                book.get("year", ""),
                book.get("language", ""),
                book.get("page_count", 0),
                book.get("count", 1),
                book.get("status", ""),
                "Ano" if book.get("is_read") else "Ne",
                # Hodnocení a poznámky (pro jednoduchost bereme první nalezené nebo prázdné)
                next(iter(book.get("ratings_by", {}).values()), ""),
                next(iter(book.get("notes_by", {}).values()), ""),
                loan_people,
                loan_dates
            ])
            
        return aiohttp.web.Response(
            body=output.getvalue(),
            content_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="knihovnicka_export.csv"'}
        )


class BookcaseCoverView(HomeAssistantView):
    """View to serve and cache book covers."""
    url = "/bookcase_covers/{book_id}.jpg"
    name = "api:bookcase:cover"
    requires_auth = False # Veřejně dostupné pro panel

    def __init__(self, hass, books):
        self.hass = hass
        self.books = books
        # Cesta k obálkám v rámci www adresáře komponenty
        self.cover_dir = os.path.join(os.path.dirname(__file__), "www", "covers")
        if not os.path.exists(self.cover_dir):
            os.makedirs(self.cover_dir, exist_ok=True)

    async def post(self, request, book_id):
        """Upload a custom cover."""
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field.name != 'file':
                return aiohttp.web.Response(status=400, text="Expected 'file' field")
            
            file_path = os.path.join(self.cover_dir, f"{book_id}.jpg")
            
            # Přečteme data
            content = b""
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                content += chunk
            
            size = len(content)
            import time
            timestamp = int(time.time())
            
            # Uložíme soubor přes executor
            def save_file():
                if not os.path.exists(self.cover_dir):
                    os.makedirs(self.cover_dir, exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(content)
            
            await self.hass.async_add_executor_job(save_file)
            
            _LOGGER.info("Bookcase: Uploaded custom cover for %s (%d bytes)", book_id, size)
            
            # Nastavíme lokální odkaz s timestampem pro cache busting
            if book_id in self.books:
                self.books[book_id]["cover_url"] = f"/bookcase_covers/{book_id}.jpg?v={timestamp}"
                
                # Uložíme změnu do storage
                from homeassistant.helpers.storage import Store
                store = Store(self.hass, 1, "bookcase_data")
                data = await store.async_load() or {"books": {}}
                if "books" in data and book_id in data["books"]:
                    data["books"][book_id]["cover_url"] = self.books[book_id]["cover_url"]
                    await store.async_save(data)
            
            self.hass.bus.async_fire("bookcase_updated")
            return aiohttp.web.Response(status=200, text="OK")
        except Exception as e:
            _LOGGER.error("Bookcase: Upload failed for %s: %s", book_id, e)
            return aiohttp.web.Response(status=500, text=str(e))

    async def get(self, request, book_id):
        """Fetch and serve the cover."""
        file_path = os.path.join(self.cover_dir, f"{book_id}.jpg")
        
        # 1. Pokud existuje lokálně, servírujeme přímo
        if os.path.exists(file_path):
            return aiohttp.web.FileResponse(file_path)

        # 2. Pokud neexistuje, zkusíme najít URL obálky v datech
        book = self.books.get(book_id)
        if not book or not book.get("cover_url"):
            return aiohttp.web.Response(status=404)

        cover_url = book["cover_url"]
        
        # Ochrana proti nekonečné smyčce – pokud cover_url ukazuje zpět na nás, ale soubor nemáme
        if cover_url.startswith("/bookcase_covers/"):
            return aiohttp.web.Response(status=404)
        
        # 3. Stáhneme obálku s User-Agentem a podporou různých formátů
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(cover_url, timeout=15) as response:
                    if response.status == 200:
                        content = await response.read()
                        content_type = response.headers.get("Content-Type", "image/jpeg")
                        
                        # Uložíme přes executor
                        def save_cache():
                            with open(file_path, "wb") as f:
                                f.write(content)
                        await self.hass.async_add_executor_job(save_cache)
                        
                        return aiohttp.web.Response(body=content, content_type=content_type)
        except Exception as e:
            _LOGGER.error("Failed to fetch cover from %s: %s", cover_url, e)

        return aiohttp.web.Response(status=404)

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up Bookcase from a config entry."""
    _migrated_flag = False
    from homeassistant.helpers.storage import Store
    store = Store(hass, 1, "bookcase_data")
    data = await store.async_load() or {"books": {}}

    # 4. Sjednocení duplicitních ISBN a inicializace 'active_loans'
    isbn_map = {}
    to_delete = []
    
    # Pracujeme s kopií klíčů, protože budeme mazat
    all_book_ids = list(data.get("books", {}).keys())
    for book_id in all_book_ids:
        book = data["books"][book_id]
        
        # Inicializace active_loans, pokud chybí
        if "active_loans" not in book:
            book["active_loans"] = []
            # Pokud má kniha starý styl půjčení, převedeme ho
            if book.get("lent_to"):
                book["active_loans"].append({
                    "person": book["lent_to"],
                    "until": book.get("lent_until", ""),
                    "loaned_at": book.get("added_at", dt_util.now().isoformat())
                })
            _migrated_flag = True
        
        isbn = book.get("isbn")
        if not isbn: continue
        
        if isbn not in isbn_map:
            isbn_map[isbn] = book_id
        else:
            # Máme duplicitu! Sloučíme ji do původního záznamu (prvního nalezeného)
            target_id = isbn_map[isbn]
            target = data["books"][target_id]
            
            # Sečteme kusy
            target["count"] = target.get("count", 1) + book.get("count", 1)
            # Sloučíme půjčky
            target["active_loans"].extend(book.get("active_loans", []))
            # Sloučíme metadata (pokud cílový záznam něco nemá)
            for key in ["description", "subtitle", "cover_url", "genre"]:
                if not target.get(key) and book.get(key):
                    target[key] = book[key]
            # Sloučíme uživatelská data
            for key in ["ratings_by", "notes_by", "statuses_by"]:
                if key in book:
                    target.setdefault(key, {}).update(book[key])
            for user in book.get("read_by", []):
                if user not in target.setdefault("read_by", []):
                    target["read_by"].append(user)
            
            to_delete.append(book_id)
            _migrated_flag = True

    for book_id in to_delete:
        del data["books"][book_id]
        _LOGGER.info("Bookcase: Merged duplicate book record %s", book_id)
    
    if _migrated_flag:
        await store.async_save(data)
        _LOGGER.info("Bookcase: Data migration completed (duplicates merged, loans initialized)")

    async def handle_add_book(call: ServiceCall):
        query = call.data.get("isbn", "").strip()
        if not query:
            return

        # Normalizované ISBN pro kontrolu duplicit (odstranění mezer a pomlček)
        if query.startswith("http"):
            normalized_query = query
        else:
            normalized_query = re.sub(r'[- ]', '', query) if any(c.isdigit() for c in query) else query

        existing_id = None
        for bid, existing in data["books"].items():
            if existing.get("isbn") == normalized_query:
                existing_id = bid
                break

        if existing_id:
            # Už ji máme → jen navýšíme count
            data["books"][existing_id]["count"] = data["books"][existing_id].get("count", 1) + 1
            await store.async_save(data)
            hass.bus.async_fire("bookcase_updated")
            hass.bus.async_fire("bookcase_info", {"message": f"Přidán další výtisk: {data['books'][existing_id].get('title')}"})
            _LOGGER.info("Bookcase: Incremented count for ISBN %s", normalized_query)
            return

        # Nový dotaz → fetch z internetu
        try:
            book_data = await fetch_book_metadata(hass, query)
        except Exception as err:
            _LOGGER.error("Bookcase: Metadata fetch failed for query %s: %s", query, err)
            book_data = None

        book_id = str(uuid.uuid4())
        
        # Pokud jsme hledali podle názvu, zkusíme z metadat vytáhnout skutečné ISBN, pokud tam je
        final_isbn = book_data.get("isbn", normalized_query) if book_data else normalized_query

        new_book = {
            "id": book_id,
            "isbn": final_isbn,
            "title": book_data.get("title", f"Kniha: {query}") if book_data else f"Kniha: {query}",
            "subtitle": book_data.get("subtitle", "") if book_data else "",
            "authors": book_data.get("authors", []) if book_data else [],
            "publisher": book_data.get("publishers", [""])[0] if book_data and book_data.get("publishers") else "",
            "year": book_data.get("publish_date", "") if book_data else "",
            "language": book_data.get("language", "Čeština") if book_data else "Čeština",
            "page_count": book_data.get("pages", 0) if book_data else 0,
            "cover_url": book_data.get("cover_url", "") if book_data else "",
            "description": book_data.get("description", "") if book_data else "",
            "genre": book_data.get("genres", []) if book_data else [],
            "url": book_data.get("url", "") if book_data else "",
            "count": 1,
            "status": STATUS_TO_READ,
            "condition": "",
            "ratings_by": {},
            "notes_by": {},
            "statuses_by": {},
            "active_loans": [],
            "date_read": "",
            "added_at": dt_util.now().isoformat(),
            "read_by": [],
            "wishlist_by": []
        }

        data["books"][book_id] = new_book
        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        hass.bus.async_fire("bookcase_updated")
        _LOGGER.info("Bookcase: Added book '%s' (Query: %s, ISBN: %s)", new_book["title"], query, final_isbn)

    async def handle_add_book_manual(call: ServiceCall):
        book_id = str(uuid.uuid4())
        new_book = {
            "id": book_id,
            "isbn": call.data.get("isbn", ""),
            "title": call.data.get("title", "Nová kniha"),
            "subtitle": call.data.get("subtitle", ""),
            "authors": call.data.get("authors", []),
            "publisher": call.data.get("publisher", ""),
            "year": call.data.get("year", ""),
            "language": call.data.get("language", "Čeština"),
            "page_count": call.data.get("page_count", 0),
            "cover_url": call.data.get("cover_url", ""),
            "status": call.data.get("status", STATUS_TO_READ),
            "condition": call.data.get("condition", ""),
            "ratings_by": call.data.get("ratings_by", {}),
            "notes_by": call.data.get("notes_by", {}),
            "statuses_by": call.data.get("statuses_by", {}),
            "description": call.data.get("description", ""),
            "genre": call.data.get("genre", []),
            "url": call.data.get("url", ""),
            "count": call.data.get("count", 1),
            "date_read": call.data.get("date_read", ""),
            "added_at": dt_util.now().isoformat(),
            "read_by": call.data.get("read_by", []),
            "wishlist_by": call.data.get("wishlist_by", [])
        }
        data["books"][book_id] = new_book
        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        hass.bus.async_fire("bookcase_updated")

    async def handle_update_book(call: ServiceCall):
        book_id = call.data.get("book_id")
        if book_id not in data["books"]: return

        book = data["books"][book_id]
        old_lent_to = book.get("lent_to")
        
        # Klíče, které chceme slučovat (merge) místo prostého přepsání
        merge_keys = ["ratings_by", "notes_by", "statuses_by"]

        for key in ["status", "is_read", "date_read", "condition", "description", 
                    "lent_to", "lent_until", "count", "genre", "read_by", "wishlist_by", 
                    "title", "subtitle", "authors", "cover_url", "publisher", 
                    "year", "language", "page_count", "url", "isbn"] + merge_keys:
            if key in call.data:
                val = call.data[key]
                
                # Pokud se mění cover_url, smažeme lokální cache
                # Pokud se mění cover_url, smažeme lokální cache, ALE jen pokud nová adresa není ta lokální
                if key == "cover_url" and val != book.get("cover_url"):
                    # Pokud nová adresa nezačíná na náš lokální prefix, smažeme starý lokální soubor
                    if not val or not val.startswith("/bookcase_covers/"):
                        cover_path = os.path.join(os.path.dirname(__file__), "www", "covers", f"{book_id}.jpg")
                        if os.path.exists(cover_path):
                            try:
                                os.remove(cover_path)
                                _LOGGER.debug("Bookcase: Deleted cached cover for %s due to external URL change", book_id)
                            except Exception as e:
                                _LOGGER.error("Bookcase: Failed to delete cached cover %s: %s", cover_path, e)

                if key in merge_keys and isinstance(val, dict):
                    # Inteligentní merge: aktualizujeme pouze klíče (uživatele) přítomné v požadavku
                    if key not in book or not isinstance(book[key], dict):
                        book[key] = {}
                    book[key].update(val)
                else:
                    book[key] = val

        new_lent_to = book.get("lent_to")
        lent_until = book.get("lent_until")

        if new_lent_to and new_lent_to != old_lent_to:
            try:
                await hass.services.async_call("calendar", "create_event", {
                    "entity_id": "calendar.primary",
                    "summary": f"Vrátit knihu: {book.get('title')}",
                    "description": f"Kniha zapůjčena: {new_lent_to}",
                    "end_date": lent_until if lent_until else dt_util.now().strftime("%Y-%m-%d")
                })
            except Exception as e:
                _LOGGER.error("Failed to create calendar event: %s", e)

        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        hass.bus.async_fire("bookcase_updated")

    async def handle_delete_book(call: ServiceCall):
        book_id = call.data.get("book_id")
        if book_id in data["books"]:
            del data["books"][book_id]
            await store.async_save(data)
            hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
            hass.bus.async_fire("bookcase_updated")

    async def handle_refresh_book(call: ServiceCall):
        """Re-fetch metadata for a book from APIs."""
        book_id = call.data.get("book_id")
        if book_id not in data["books"]: return
        isbn = data["books"][book_id].get("isbn", "")
        if not isbn: return
        try:
            import importlib
            from . import api
            importlib.reload(api)
            from .api import fetch_book_metadata
            book_data = await fetch_book_metadata(hass, isbn)
        except Exception as err:
            _LOGGER.error("Bookcase: Refresh failed for %s: %s", isbn, err)
            return
        if not book_data: return
        # Aktualizuj pouze metadata z API, zachovej user data
        for key in ["title", "subtitle", "description", "cover_url", "url"]:
            if book_data.get(key):
                data["books"][book_id][key] = book_data[key]
        if book_data.get("authors"):
            data["books"][book_id]["authors"] = book_data["authors"]
        if book_data.get("publishers"):
            data["books"][book_id]["publisher"] = book_data["publishers"][0]
        if book_data.get("publish_date"):
            data["books"][book_id]["year"] = book_data["publish_date"]
        if book_data.get("language"):
            data["books"][book_id]["language"] = book_data["language"]
        if book_data.get("pages"):
            data["books"][book_id]["page_count"] = book_data["pages"]
        if book_data.get("genres"):
            data["books"][book_id]["genre"] = book_data["genres"]
        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        hass.bus.async_fire("bookcase_updated")
        hass.bus.async_fire("bookcase_info", {"message": f"Metadata obnovena: {data['books'][book_id].get('title')}"})

    async def handle_loan_book(call: ServiceCall):
        book_id = call.data.get("book_id")
        person = call.data.get("person")
        until = call.data.get("until", "")
        if book_id not in data["books"] or not person: return
        
        book = data["books"][book_id]
        if len(book.get("active_loans", [])) >= book.get("count", 1):
            hass.bus.async_fire("bookcase_info", {"message": "Nelze půjčit: Žádný výtisk není dostupný."})
            return
            
        book.setdefault("active_loans", []).append({
            "person": person,
            "until": until,
            "loaned_at": dt_util.now().isoformat()
        })
        
        # Calendar integration fallback
        try:
            await hass.services.async_call("calendar", "create_event", {
                "entity_id": "calendar.primary",
                "summary": f"Vrátit knihu: {book.get('title')}",
                "description": f"Kniha zapůjčena: {person}",
                "end_date": until if until else (dt_util.now() + dt_util.timedelta(days=30)).strftime("%Y-%m-%d")
            })
        except: pass

        await store.async_save(data)
        hass.bus.async_fire("bookcase_updated")
        _LOGGER.info("Bookcase: Loaned '%s' to %s", book.get("title"), person)

    async def handle_return_book(call: ServiceCall):
        book_id = call.data.get("book_id")
        person = call.data.get("person")
        if book_id not in data["books"]: return
        
        book = data["books"][book_id]
        loans = book.get("active_loans", [])
        
        if person:
            book["active_loans"] = [l for l in loans if l.get("person") != person]
        elif loans:
            book["active_loans"].pop(0)
            
        await store.async_save(data)
        hass.bus.async_fire("bookcase_updated")
        _LOGGER.info("Bookcase: Book returned for '%s'", book.get("title"))

    hass.services.async_register(DOMAIN, "add_by_isbn", handle_add_book)
    hass.services.async_register(DOMAIN, "add_manual", handle_add_book_manual)
    hass.services.async_register(DOMAIN, "update_book", handle_update_book)
    hass.services.async_register(DOMAIN, "delete_book", handle_delete_book)
    hass.services.async_register(DOMAIN, "refresh_book", handle_refresh_book)
    hass.services.async_register(DOMAIN, "loan_book", handle_loan_book)
    hass.services.async_register(DOMAIN, "return_book", handle_return_book)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"books": data["books"]}
    
    # Registrace views (HTTP servírování)
    hass.http.register_view(BookcasePanelView())
    hass.http.register_view(BookcaseCoverView(hass, data["books"]))
    hass.http.register_view(BookcaseExportView(data["books"]))
        
    try:
        from homeassistant.components.frontend import async_register_built_in_panel
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Knihovnička",
            sidebar_icon="mdi:bookshelf",
            frontend_url_path="bookcase",
            config={"_panel_custom": {
                "name": "bookcase-panel",
                "module_url": "/bookcase_static/panel.js?v=9.4"
            }},
            require_admin=False,
        )
    except Exception as e:
        _LOGGER.error("Error registering panel: %s", e)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
