"""Sensors for Smart Plant."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from .const import DOMAIN
from .entity import SmartPlantEntity

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        SmartPlantNextWateringSensor(coordinator, entry),
        SmartPlantCareTipsSensor(coordinator, entry),
    ])

class SmartPlantNextWateringSensor(SmartPlantEntity, SensorEntity):
    """Sensor for next watering date."""
    _name_suffix = "Next Watering"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the next watering date."""
        return self.coordinator.data.get("next_watering")

    @property
    def extra_state_attributes(self):
        """Return history as attributes."""
        return {
            "watering_history": self.coordinator.data.get("watering_history"),
            "last_watered": self.coordinator.data.get("last_watered"),
        }

class SmartPlantCareTipsSensor(SmartPlantEntity, SensorEntity):
    """Sensor for care tips."""
    _name_suffix = "Care Tips"
    _attr_icon = "mdi:information-outline"

    @property
    def native_value(self):
        """Return a summary of care requirements."""
        d = self.coordinator.details
        tips = []
        if d.get("min_light_lux"):
            tips.append(f"Světlo: {d['min_light_lux']}-{d.get('max_light_lux', '?')} lux")
        if d.get("min_temp"):
            tips.append(f"Teplota: {d['min_temp']}-{d.get('max_temp', '?')}°C")
        if d.get("min_soil_moist"):
            tips.append(f"Vlhkost půdy: {d['min_soil_moist']}%")
        
        return " | ".join(tips) if tips else "Informace nejsou k dispozici"

    @property
    def extra_state_attributes(self):
        """Return all details as attributes."""
        attrs = dict(self.coordinator.details)
        attrs["health_history"] = self.coordinator.data.get("health_history")
        return attrs
