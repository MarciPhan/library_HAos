"""Selects for Smart Plant."""
from homeassistant.components.select import SelectEntity
from .const import DOMAIN, HEALTH_STATES
from .entity import SmartPlantEntity

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up selects."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SmartPlantHealthSelect(coordinator, entry),
    ])

class SmartPlantHealthSelect(SmartPlantEntity, SelectEntity):
    """Select entity for plant health."""
    _name_suffix = "Health"
    _attr_options = HEALTH_STATES
    _attr_icon = "mdi:heart-pulse"

    @property
    def current_option(self):
        """Return the current health."""
        return self.coordinator.data.get("health")

    async def async_select_option(self, option):
        """Change the health state."""
        await self.coordinator.set_health(option)
