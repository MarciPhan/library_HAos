"""Data coordinator for Smart Plant."""
import logging
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, 
    DEFAULT_DAYS_BETWEEN_WATERINGS,
    ATTR_LAST_WATERED,
    ATTR_DAYS_BETWEEN_WATERINGS,
    HEALTH_GOOD
)

_LOGGER = logging.getLogger(__name__)

class SmartPlantCoordinator(DataUpdateCoordinator):
    """Class to manage fetching plant data and calculating states."""

    def __init__(self, hass: HomeAssistant, entry):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=60), # Refresh states every hour
        )
        self.entry = entry
        self.plant_id = entry.entry_id
        
        # Load data from entry
        data = entry.data
        options = entry.options
        
        self.name = data.get("name")
        self.pid = data.get("pid")
        self.details = data.get("details", {})
        
        # States (persisted in config entry options or private store)
        self.last_watered = options.get(ATTR_LAST_WATERED)
        if self.last_watered:
            self.last_watered = datetime.fromisoformat(self.last_watered)
        else:
            self.last_watered = dt_util.now() - timedelta(days=7) # Default to a week ago
            
        # Calculate default days from OPB details
        default_days = DEFAULT_DAYS_BETWEEN_WATERINGS
        min_moist = self.details.get("min_soil_moist")
        if min_moist is not None:
            if min_moist > 60: default_days = 2
            elif min_moist > 45: default_days = 4
            elif min_moist > 30: default_days = 7
            elif min_moist > 15: default_days = 10
            else: default_days = 14
            
        self.days_between_waterings = options.get(ATTR_DAYS_BETWEEN_WATERINGS, default_days)
        self.health = options.get("health", HEALTH_GOOD)
        self.watering_history = options.get("watering_history", [])
        self.health_history = options.get("health_history", [])

    async def _async_update_data(self):
        """Calculate current states."""
        now = dt_util.now()
        
        next_watering = self.last_watered + timedelta(days=self.days_between_waterings)
        needs_water = now >= next_watering
        is_overdue = now >= (next_watering + timedelta(days=2)) # Problem after 2 days of delay
        
        return {
            "needs_water": needs_water,
            "is_overdue": is_overdue,
            "next_watering": next_watering,
            "last_watered": self.last_watered,
            "days_between": self.days_between_waterings,
            "health": self.health,
            "watering_history": self.watering_history,
            "health_history": self.health_history,
        }

    async def mark_watered(self):
        """Mark the plant as watered and learn the pattern."""
        now = dt_util.now()
        
        # Adaptive learning: Calculate actual days since last watering
        if self.last_watered:
            actual_delta = (now - self.last_watered).days
            if actual_delta > 0:
                # Weighted average: 80% current interval, 20% new observation
                # This makes it learn slowly and stay stable
                new_interval = round((self.days_between_waterings * 0.8) + (actual_delta * 0.2))
                # Keep it within reasonable bounds
                new_interval = max(1, min(60, new_interval))
                
                if new_interval != self.days_between_waterings:
                    _LOGGER.info("Smart Plant %s: Learning new interval: %s -> %s days", 
                                 self.name, self.days_between_waterings, new_interval)
                    self.days_between_waterings = new_interval

        self.last_watered = now
        
        # Update history
        self.watering_history.insert(0, now.isoformat())
        self.watering_history = self.watering_history[:10] # Keep last 10
        
        await self._async_update_options()
        await self.async_request_refresh()

    async def set_days_between(self, days):
        """Update the interval."""
        self.days_between_waterings = days
        await self._async_update_options()
        await self.async_request_refresh()

    async def set_health(self, health):
        """Update health."""
        if self.health != health:
            now = dt_util.now()
            self.health_history.insert(0, {"date": now.isoformat(), "state": health})
            self.health_history = self.health_history[:10]
        
        self.health = health
        await self._async_update_options()
        await self.async_request_refresh()

    async def _async_update_options(self):
        """Save current states to options."""
        new_options = dict(self.entry.options)
        new_options.update({
            ATTR_LAST_WATERED: self.last_watered.isoformat(),
            ATTR_DAYS_BETWEEN_WATERINGS: self.days_between_waterings,
            "health": self.health,
            "watering_history": self.watering_history,
            "health_history": self.health_history,
        })
        self.hass.config_entries.async_update_entry(self.entry, options=new_options)
