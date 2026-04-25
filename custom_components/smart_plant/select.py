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
        health = self.coordinator.data.get("health")
        # Mapování starých stavů (anglických i původních českých) na nové kreativní stavy
        health_map = {
            "Excellent": "Ukázková", "Výborné": "Ukázková",
            "Very Good": "Prosperující", "Velmi dobré": "Prosperující",
            "Good": "Spokojená", "Dobré": "Spokojená",
            "Fair": "Stagnující", "Ucházející": "Stagnující",
            "Poor": "Chřadnoucí", "Špatné": "Chřadnoucí",
            "Critical": "Skomírající", "Kritické": "Skomírající",
            "Needs attention": "Skomírající"
        }
        return health_map.get(health, health)

    async def async_select_option(self, option):
        """Change the health state."""
        await self.coordinator.set_health(option)
