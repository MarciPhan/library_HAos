import logging
import uuid
import re
import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import discovery
from homeassistant.components.http import StaticPathConfig
from .const import DOMAIN, STATUS_TO_READ
from .api import fetch_book_metadata

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry):
    """Set up Bookcase from a config entry."""
    from homeassistant.helpers.storage import Store
    store = Store(hass, 1, "bookcase_data")
    data = await store.async_load() or {"books": {}}

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
            "ratings_by": {},
            "notes_by": {},
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
            "ratings_by": {},
            "notes_by": {},
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

        old_lent_to = data["books"][book_id].get("lent_to")
        updates = {}
        for key in ["status", "is_read", "date_read", "ratings_by", "notes_by",
                    "description", "lent_to", "lent_until", "count", "genre",
                    "read_by", "wishlist_by", "title", "subtitle", "authors",
                    "cover_url", "publisher", "year", "language", "page_count",
                    "url", "isbn"]:
            if key in call.data:
                updates[key] = call.data[key]

        data["books"][book_id].update(updates)
        new_lent_to = data["books"][book_id].get("lent_to")
        lent_until = data["books"][book_id].get("lent_until")

        if new_lent_to and new_lent_to != old_lent_to:
            try:
                await hass.services.async_call("calendar", "create_event", {
                    "entity_id": "calendar.primary",
                    "summary": f"Vrátit knihu: {data['books'][book_id].get('title')}",
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
    
    if "static_path_registered" not in hass.data[DOMAIN]:
        await hass.http.async_register_static_paths([
            StaticPathConfig("/bookcase_static", hass.config.path("custom_components/bookcase/www"), False)
        ])
        
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
                    "module_url": "/bookcase_static/panel.js?v=6.2"
                }},
                require_admin=False,
            )
            hass.data[DOMAIN]["static_path_registered"] = True
        except Exception as e:
            _LOGGER.error("Error registering panel: %s", e)

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
