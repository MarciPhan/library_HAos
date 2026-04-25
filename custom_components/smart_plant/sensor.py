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
        SmartPlantDescriptionSensor(coordinator, entry),
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
        
        # Soil Moisture
        moist = d.get("min_soil_moist", 40)
        tips.append(f"💧 Min. vlhkost: {moist}%")
        
        # Watering intensity
        watering = d.get("watering")
        if not watering:
            if moist <= 20: watering = "Minimální (nechat proschnout)"
            elif moist <= 40: watering = "Střední (mírně vlhké)"
            else: watering = "Pravidelná (stále vlhké)"
        else:
            # Počeštění anglických z API
            trans = {"Frequent": "Častá", "Average": "Střední", "Minimum": "Minimální"}
            watering = trans.get(watering, watering)
            
        tips.append(f"🚿 Zálivka: {watering}")
            
        # Sunlight
        sun = d.get("sunlight")
        if sun:
            if isinstance(sun, list):
                sun_str = ", ".join(sun)
            else:
                sun_str = str(sun)
            # Částečný překlad z API zdrojů
            sun_str = sun_str.replace("full sun", "Plné slunce").replace("part shade", "Polostín").replace("part sun", "Polostín")
        else:
            sun_str = "Světlé stanoviště"
            
        tips.append(f"☀️ Světlo: {sun_str}")
            
        # Temperature
        min_t = d.get("min_temp")
        if min_t:
            tips.append(f"🌡️ Teplota: {min_t}-{d.get('max_temp', '?')}°C")
        else:
            tips.append("🌡️ Pokojová (18-24°C)")
            
        return "\n".join(tips)

    @property
    def extra_state_attributes(self):
        """Return all details as attributes."""
        attrs = dict(self.coordinator.details)
        attrs["health_history"] = self.coordinator.data.get("health_history")
        return attrs

class SmartPlantDescriptionSensor(SmartPlantEntity, SensorEntity):
    """Sensor for plant description."""
    _name_suffix = "Description"
    _attr_icon = "mdi:text-box-outline"

    @property
    def native_value(self):
        """Return the plant description."""
        return self.coordinator.details.get("description", "Popis není k dispozici")
