from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, STATUS_READ, STATUS_READING, STATUS_TO_READ

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the Bookcase sensors."""
    async_add_entities([
        BookcaseStatsSensor(hass, entry, "Total Books", "total"),
        BookcaseStatsSensor(hass, entry, "Lent Books", "lent"),
        BookcaseStatsSensor(hass, entry, "Read Books", STATUS_READ),
        BookcaseStatsSensor(hass, entry, "Reading Books", STATUS_READING),
        BookcaseStatsSensor(hass, entry, "To Read Books", STATUS_TO_READ),
    ])

class BookcaseStatsSensor(SensorEntity):
    """Representation of a Bookcase statistics sensor."""

    def __init__(self, hass, entry, name, category):
        self._hass = hass
        self._entry = entry
        self._attr_name = f"Bookcase {name}"
        self._category = category
        self._attr_unique_id = f"{entry.entry_id}_{category}"
        self._attr_icon = "mdi:bookshelf"

    @property
    def state(self):
        """Return the state of the sensor."""
        books = self._hass.data[DOMAIN][self._entry.entry_id]["books"]
        if self._category == "total":
            return sum(b.get("count", 1) for b in books.values())
        
        if self._category == "lent":
            return sum(len(b.get("active_loans", [])) for b in books.values())
        
        return len([b for b in books.values() if b.get("status") == self._category])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        books = self._hass.data[DOMAIN][self._entry.entry_id]["books"]
        processed_books = []
        for book in books.values():
            b = book.copy()
            # Posíláme odkaz na náš vnitřní proxy server, který zajistí kešování
            b["cover_url"] = f"/bookcase_static/covers/{b['id']}.jpg"
            processed_books.append(b)
            
        if self._category == "total":
            return {
                "books": processed_books
            }
        return {}

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            self._hass.bus.async_listen("bookcase_updated", self._update_callback)
        )

    def _update_callback(self, event):
        """Update the sensor state."""
        self.async_write_ha_state()
