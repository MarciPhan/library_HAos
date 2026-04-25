"""Base entity for Smart Plant."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN

class SmartPlantEntity(CoordinatorEntity):
    """Base class for Smart Plant entities."""

    def __init__(self, coordinator, entry):
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self.__class__.__name__}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.data.get("name"),
            "manufacturer": "Smart Plant",
            "model": entry.data.get("species"),
        }

    @property
    def name(self):
        """Return the name of the entity."""
        return f"{self.entry.data.get('name')} {self._name_suffix}"
