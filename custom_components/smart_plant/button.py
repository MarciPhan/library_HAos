"""Buttons for Smart Plant."""
from homeassistant.components.button import ButtonEntity
from .const import DOMAIN
from .entity import SmartPlantEntity

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SmartPlantMarkWateredButton(coordinator, entry),
    ])

class SmartPlantMarkWateredButton(SmartPlantEntity, ButtonEntity):
    """Button to mark plant as watered."""
    _name_suffix = "Mark Watered"
    _attr_icon = "mdi:water"

    async def async_press(self):
        """Handle the button press."""
        await self.coordinator.mark_watered()
