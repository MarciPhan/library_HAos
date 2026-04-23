import logging
import uuid
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.storage import Store
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION, STATUS_TO_READ
from .api import fetch_book_metadata

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Bookcase integration via YAML (not recommended but for legacy support)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bookcase from a config entry."""
    
    # Initialize storage
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    
    # Load data
    data = await store.async_load()
    if data is None:
        data = {"books": {}}
        await store.async_save(data)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "store": store,
        "books": data["books"]
    }

    # Register services
    async def handle_add_book(call: ServiceCall):
        isbn = call.data.get("isbn")
        if not isbn:
            _LOGGER.error("No ISBN provided")
            return

        metadata = await fetch_book_metadata(isbn)
        if not metadata:
            _LOGGER.error("Could not fetch metadata for ISBN: %s", isbn)
            return

        book_id = str(uuid.uuid4())
        new_book = {
            "id": book_id,
            "isbn": isbn,
            "title": metadata["title"],
            "subtitle": metadata.get("subtitle"),
            "authors": metadata["authors"],
            "publisher": metadata["publishers"][0] if metadata.get("publishers") else "Neznámé",
            "year": metadata.get("publish_date"),
            "language": metadata["languages"][0] if metadata.get("languages") else "Neznámý",
            "page_count": metadata.get("pages") or 0,
            "count": 1,
            "cover_url": metadata["cover_url"],
            "link": metadata.get("url"),
            "genre": metadata.get("subjects", []),
            "status": STATUS_TO_READ,
            "is_read": False,
            "date_read": None,
            "rating": 0,
            "notes": "",
            "lent_to": None,
            "added_at": hass.datetime.now().isoformat() if hasattr(hass, 'datetime') else ""
        }

        data["books"][book_id] = new_book
        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        _LOGGER.info("Added book: %s", metadata["title"])
        
        # Trigger sensor update
        hass.bus.async_fire("bookcase_updated")

    async def handle_update_book(call: ServiceCall):
        book_id = call.data.get("book_id")
        if book_id not in data["books"]:
            _LOGGER.error("Book ID not found: %s", book_id)
            return

        updates = {}
        for key in ["status", "is_read", "date_read", "rating", "notes", "lent_to", "count", "genre"]:
            if key in call.data:
                updates[key] = call.data[key]

        data["books"][book_id].update(updates)
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
    hass.services.async_register(DOMAIN, "update_book", handle_update_book)
    hass.services.async_register(DOMAIN, "delete_book", handle_delete_book)

    # Forward to sensor platform
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
