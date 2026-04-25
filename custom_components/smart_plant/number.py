"""Numbers for Smart Plant."""
from homeassistant.components.number import NumberEntity
from .const import DOMAIN
from .entity import SmartPlantEntity

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up numbers."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SmartPlantIntervalNumber(coordinator, entry),
    ])

class SmartPlantIntervalNumber(SmartPlantEntity, NumberEntity):
    """Number entity for days between waterings."""
    _name_suffix = "Days Between Waterings"
    _attr_native_min_value = 1
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_icon = "mdi:calendar-range"

    @property
    def native_value(self):
        """Return the interval."""
        return self.coordinator.data.get("days_between")

    async def async_set_native_value(self, value):
        """Set new value."""
        await self.coordinator.set_days_between(int(value))
