import logging
import os
import uuid

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.storage import Store
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION, STATUS_TO_READ
from .api import fetch_book_metadata

_LOGGER = logging.getLogger(__name__)

PANEL_URL = "bookcase"
WWW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")


class BookcasePanelView(HomeAssistantView):
    """Serve panel JS files for the Bookcase integration."""

    url = "/bookcase_static/{filename:.+}"
    name = "bookcase:static"
    requires_auth = False

    async def get(self, request, filename):
        """Serve the requested file."""
        filepath = os.path.join(WWW_DIR, filename)
        if not os.path.isfile(filepath):
            _LOGGER.error("Bookcase: file not found: %s", filepath)
            raise web.HTTPNotFound()

        _LOGGER.debug("Bookcase: serving %s", filepath)
        return web.FileResponse(
            filepath,
            headers={"Cache-Control": "no-cache"},
        )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Bookcase integration."""
    # Serve panel assets via custom HTTP view
    hass.http.register_view(BookcasePanelView())
    _LOGGER.info("Bookcase: HTTP view registered for /bookcase_static/")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bookcase from a config entry."""

    # Register sidebar panel (only once)
    if PANEL_URL not in hass.data.get("frontend_panels", {}):
        try:
            from homeassistant.components.panel_custom import async_register_panel
            await async_register_panel(
                hass,
                frontend_url_path=PANEL_URL,
                webcomponent_name="bookcase-panel",
                sidebar_title="Knihovnička",
                sidebar_icon="mdi:bookshelf",
                module_url="/bookcase_static/panel.js?v=2.3",
                require_admin=False,
            )
            _LOGGER.info("Bookcase: sidebar panel registered")
        except Exception as err:
            _LOGGER.error("Bookcase: failed to register panel: %s", err)

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
            "added_at": dt_util.now().isoformat()
        }

        data["books"][book_id] = new_book
        await store.async_save(data)
        hass.data[DOMAIN][entry.entry_id]["books"] = data["books"]
        _LOGGER.info("Added book: %s", metadata["title"])

        # Trigger sensor update
        hass.bus.async_fire("bookcase_updated")

    async def handle_update_book(call: ServiceCall):
        book_id = call.data.get("book_id")
        if not book_id or book_id not in data["books"]:
            _LOGGER.error("Book ID not found: %s", book_id)
            return

        old_lent_to = data["books"][book_id].get("lent_to")
        updates = {}
        for key in ["status", "is_read", "date_read", "rating", "notes", "lent_to", "lent_until", "count", "genre", "read_by"]:
            if key in call.data:
                updates[key] = call.data[key]

        data["books"][book_id].update(updates)
        new_lent_to = data["books"][book_id].get("lent_to")
        lent_until = data["books"][book_id].get("lent_until")

        # Google Calendar Integration
        if new_lent_to and new_lent_to != old_lent_to:
            try:
                book_title = data["books"][book_id].get("title", "Kniha")
                
                # End date: either custom or 30 days from now
                if lent_until:
                    end_dt = lent_until + "T23:59:59" # End of the day
                else:
                    end_dt = (dt_util.now() + dt_util.timedelta(days=30)).isoformat()

                await hass.services.async_call(
                    "google", "create_event",
                    {
                        "entity_id": "calendar.primary",
                        "summary": f"Vrátit knihu: {book_title} (půjčil {new_lent_to})",
                        "description": f"Kniha {book_title} by měla být vrácena od osoby: {new_lent_to}",
                        "start_date_time": dt_util.now().isoformat(),
                        "end_date_time": end_dt,
                    }
                )
                _LOGGER.info("Google Calendar event created for book: %s", book_title)
            except Exception as e:
                _LOGGER.error("Failed to create Google Calendar event: %s", e)

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
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Remove sidebar panel if no more entries
    if not hass.data.get(DOMAIN):
        try:
            hass.components.frontend.async_remove_panel(PANEL_URL)
            _LOGGER.info("Bookcase: sidebar panel removed")
        except Exception:
            pass

    return unload_ok
