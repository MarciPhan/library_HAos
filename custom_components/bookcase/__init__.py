import logging
import uuid
import re
import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import discovery
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
        if not isbn: return

        # 1. Rychlý pokus o získání základních dat (max 2.5s)
        book_data = await fetch_book_metadata(hass, isbn, fast=True)
        
        book_id = str(uuid.uuid4())
        new_book = {
            "id": book_id,
            "isbn": isbn,
            "title": book_data.get("title", f"Kniha: {isbn}") if book_data else f"Načítám: {isbn}...",
            "authors": book_data.get("authors", []) if book_data else [],
            "publisher": book_data.get("publishers", [""])[0] if book_data and book_data.get("publishers") else "",
            "year": book_data.get("publish_date", "") if book_data else "",
            "language": "cs",
            "page_count": book_data.get("pages", 0) if book_data else 0,
            "cover_url": book_data.get("cover_url", "") if book_data else "",
            "description": book_data.get("description", "") if book_data else "",
            "status": STATUS_TO_READ,
            "added_at": dt_util.now().isoformat(),
            "read_by": [],
            "wishlist_by": []
        }

        data["books"][book_id] = new_book
        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        hass.bus.async_fire("bookcase_updated")

        # 2. Donačtení všech detailů na pozadí
        async def enrich_book():
            full_data = await fetch_book_metadata(hass, isbn, fast=False)
            if full_data:
                data["books"][book_id].update({
                    "title": full_data.get("title", data["books"][book_id]["title"]),
                    "authors": full_data.get("authors", data["books"][book_id]["authors"]),
                    "publisher": full_data.get("publishers", [""])[0] if full_data.get("publishers") else data["books"][book_id]["publisher"],
                    "year": full_data.get("publish_date", data["books"][book_id]["year"]),
                    "page_count": full_data.get("pages", data["books"][book_id]["page_count"]),
                    "cover_url": full_data.get("cover_url", data["books"][book_id]["cover_url"]),
                    "description": full_data.get("description", data["books"][book_id]["description"])
                })
                await store.async_save(data)
                hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
                hass.bus.async_fire("bookcase_updated")
                _LOGGER.info(f"Bookcase: Book enriched: {data['books'][book_id]['title']}")

        hass.async_create_task(enrich_book())

    async def handle_add_book_manual(call: ServiceCall):
        book_id = str(uuid.uuid4())
        new_book = {
            "id": book_id,
            "isbn": call.data.get("isbn", ""),
            "title": call.data.get("title", "Nová kniha"),
            "authors": call.data.get("authors", []),
            "publisher": call.data.get("publisher", ""),
            "year": call.data.get("year", ""),
            "language": call.data.get("language", "Čeština"),
            "page_count": call.data.get("page_count", 0),
            "cover_url": call.data.get("cover_url", ""),
            "status": call.data.get("status", STATUS_TO_READ),
            "notes": call.data.get("notes", ""),
            "description": call.data.get("description", ""),
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
        for key in ["status", "is_read", "date_read", "rating", "notes", "description", "lent_to", "lent_until", "count", "genre", "read_by", "wishlist_by", "title", "authors", "cover_url"]:
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

    hass.services.async_register(DOMAIN, "add_by_isbn", handle_add_book)
    hass.services.async_register(DOMAIN, "add_manual", handle_add_book_manual)
    hass.services.async_register(DOMAIN, "update_book", handle_update_book)
    hass.services.async_register(DOMAIN, "delete_book", handle_delete_book)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"books": data["books"]}
    
    if "bookcase_static" not in hass.http.views:
        hass.http.register_static_path("/bookcase_static", hass.config.path("custom_components/bookcase/www"), False)
        
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
                    "module_url": "/bookcase_static/panel.js?v=3.2"
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
