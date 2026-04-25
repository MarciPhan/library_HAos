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

class BookcaseCoverView(HomeAssistantView):
    """View to serve and cache book covers."""
    url = "/bookcase_static/covers/{book_id}.jpg"
    name = "api:bookcase:cover"
    requires_auth = False # Veřejně dostupné pro panel

    def __init__(self, hass, books):
        self.hass = hass
        self.books = books
        # Cesta k obálkám v rámci www adresáře komponenty
        self.cover_dir = os.path.join(os.path.dirname(__file__), "www", "covers")
        if not os.path.exists(self.cover_dir):
            os.makedirs(self.cover_dir, exist_ok=True)

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
        
        # 3. Stáhneme obálku
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(cover_url, timeout=10) as response:
                    if response.status == 200:
                        content = await response.read()
                        with open(file_path, "wb") as f:
                            f.write(content)
                        return aiohttp.web.Response(body=content, content_type="image/jpeg")
        except Exception as e:
            _LOGGER.error("Failed to fetch cover from %s: %s", cover_url, e)

        return aiohttp.web.Response(status=404)

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up Bookcase from a config entry."""
    from homeassistant.helpers.storage import Store
    store = Store(hass, 1, "bookcase_data")
    data = await store.async_load() or {"books": {}}

    # Migrace stávajících dat
    migrated = False
    for book_id, book in data.get("books", {}).items():
        # 1. Agresivnější migrace titulu (rozdělení podle dvojtečky)
        current_title = book.get("title", "")
        if ":" in current_title:
            parts = current_title.split(":", 1)
            new_title = parts[0].strip()
            new_subtitle = parts[1].strip()
            # Pokud už podnázev existoval, přidáme ho k novému
            if book.get("subtitle") and book["subtitle"] != new_subtitle:
                book["subtitle"] = f"{new_subtitle} - {book['subtitle']}"
            else:
                book["subtitle"] = new_subtitle
            book["title"] = new_title
            _LOGGER.info("Migrated title for book %s: %s -> %s | %s", 
                         book_id, current_title, book["title"], book["subtitle"])
            migrated = True
        
        # 2. Migrace stavu fyzické knihy (na globální 'condition')
        if "condition" not in book:
            old_conds = book.pop("conditions_by", {})
            book["condition"] = next(iter(old_conds.values()), "") if old_conds else ""
            migrated = True
            
        # 3. Inicializace 'statuses_by' pro personalizovaný status
        if "statuses_by" not in book:
            book["statuses_by"] = {}
            # Pokud má kniha globální status, můžeme ho zinicializovat pro všechny, 
            # kteří knihu už nějak interagovali (např. v read_by)
            if book.get("status"):
                # Pro jistotu zmigrujeme globální status do statuses_by pro existující záznamy
                for user in book.get("read_by", []):
                    book["statuses_by"][user] = "read"
                for user in book.get("wishlist_by", []):
                    book["statuses_by"][user] = "wishlist"
            migrated = True
    
    if migrated:
        await store.async_save(data)
        _LOGGER.info("Bookcase: Data migration completed (titles split by colon)")

    async def handle_add_book(call: ServiceCall):
        isbn = re.sub(r'[- ]', '', call.data.get("isbn", ""))
        if not isbn:
            return

        # Kontrola duplicitního ISBN – povolíme, ale zkopírujeme metadata z existující
        existing_copy = None
        for existing in data["books"].values():
            if existing.get("isbn") == isbn:
                existing_copy = existing
                break

        if existing_copy:
            # Máme ji už v knihovně → zkopírujeme metadata (okamžité, bez internetu)
            book_data = {
                "title": existing_copy.get("title"),
                "subtitle": existing_copy.get("subtitle", ""),
                "authors": existing_copy.get("authors", []),
                "publishers": [existing_copy.get("publisher")] if existing_copy.get("publisher") else [],
                "publish_date": existing_copy.get("year"),
                "pages": existing_copy.get("page_count"),
                "cover_url": existing_copy.get("cover_url"),
                "description": existing_copy.get("description"),
                "language": existing_copy.get("language", ""),
                "genres": existing_copy.get("genre", []),
                "url": existing_copy.get("url", ""),
            }
            hass.bus.async_fire("bookcase_info", {"message": f"Další výtisk: {existing_copy.get('title', isbn)}"})
            _LOGGER.info("Bookcase: Adding another copy of ISBN %s (%s)", isbn, existing_copy.get("title"))
        else:
            # Nové ISBN → fetch z internetu
            try:
                book_data = await fetch_book_metadata(hass, isbn)
            except Exception as err:
                _LOGGER.error("Bookcase: Metadata fetch failed for ISBN %s: %s", isbn, err)
                book_data = None

        book_id = str(uuid.uuid4())
        new_book = {
            "id": book_id,
            "isbn": isbn,
            "title": book_data.get("title", f"Kniha: {isbn}") if book_data else f"Kniha: {isbn}",
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
            "date_read": "",
            "added_at": dt_util.now().isoformat(),
            "read_by": [],
            "wishlist_by": []
        }

        data["books"][book_id] = new_book
        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        hass.bus.async_fire("bookcase_updated")
        _LOGGER.info("Bookcase: Added book '%s' (ISBN: %s)", new_book["title"], isbn)

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
            "description": call.data.get("description", ""),
            "genre": call.data.get("genre", []),
            "url": call.data.get("url", ""),
            "count": call.data.get("count", 1),
            "condition": call.data.get("condition", ""),
            "ratings_by": {},
            "notes_by": {},
            "statuses_by": {},
            "date_read": call.data.get("date_read", ""),
            "added_at": dt_util.now().isoformat(),
            "read_by": [],
            "wishlist_by": []
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

    hass.services.async_register(DOMAIN, "add_by_isbn", handle_add_book)
    hass.services.async_register(DOMAIN, "add_manual", handle_add_book_manual)
    hass.services.async_register(DOMAIN, "update_book", handle_update_book)
    hass.services.async_register(DOMAIN, "delete_book", handle_delete_book)
    hass.services.async_register(DOMAIN, "refresh_book", handle_refresh_book)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"books": data["books"]}
    
    # Registrace views (HTTP servírování)
    hass.http.register_view(BookcasePanelView())
    hass.http.register_view(BookcaseCoverView(hass, data["books"]))
        
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
                "module_url": "/bookcase_static/panel.js?v=8.3"
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
