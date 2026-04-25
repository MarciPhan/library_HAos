"""Dates for Smart Plant."""
from homeassistant.components.date import DateEntity
from .const import DOMAIN
from .entity import SmartPlantEntity

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up dates."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SmartPlantLastWateredDate(coordinator, entry),
    ])

class SmartPlantLastWateredDate(SmartPlantEntity, DateEntity):
    """Date entity for last watered date."""
    _name_suffix = "Last Watered"

    @property
    def native_value(self):
        """Return the last watered date."""
        dt = self.coordinator.data.get("last_watered")
        if dt:
            return dt.date()
        return None
