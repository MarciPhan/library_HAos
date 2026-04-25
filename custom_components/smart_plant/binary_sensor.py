"""Binary sensors for Smart Plant."""
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from .const import DOMAIN
from .entity import SmartPlantEntity

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SmartPlantTodoSensor(coordinator, entry),
        SmartPlantProblemSensor(coordinator, entry),
    ])

class SmartPlantTodoSensor(SmartPlantEntity, BinarySensorEntity):
    """Sensor for watering todo."""
    _name_suffix = "Needs Water"
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    @property
    def is_on(self):
        """Return true if plant needs water."""
        return self.coordinator.data.get("needs_water")

class SmartPlantProblemSensor(SmartPlantEntity, BinarySensorEntity):
    """Sensor for watering problem."""
    _name_suffix = "Problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self):
        """Return true if plant is overdue."""
        return self.coordinator.data.get("is_overdue")
