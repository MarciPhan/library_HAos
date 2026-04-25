"""Config flow for Smart Plant integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import os
import json
import logging
from .const import (
    DOMAIN, 
    ATTR_SPECIES, 
    ATTR_PID
)
_LOGGER = logging.getLogger(__name__)
from .api import WikipediaAPI

class SmartPlantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Plant."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._plant_name = None
        self._search_results = []
        self._selected_source = "wikipedia"
        self._custom_image = None

    async def async_step_user(self, user_input=None):
        """Step to search for a plant."""
        errors = {}
        if user_input is not None:
            self._plant_name = user_input["name"]
            search_query = user_input["species_search"]
            self._custom_image = user_input.get("custom_image_url")
            
            # 1. Search in local database
            path = os.path.join(os.path.dirname(__file__), "plants.json")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    plants = json.load(f)
                
                query = search_query.lower()
                matches = []
                for pid, info in plants.items():
                    if query in pid.lower() or query in info["name"].lower():
                        matches.append({"pid": pid, "alias": info["name"], "source": "local"})
                
                self._search_results = matches
            except Exception as e:
                _LOGGER.error("Failed to read local plants db: %s", e)
                self._search_results = []

            # 2. Fallback to Wikipedia if no local results
            if not self._search_results:
                session = async_get_clientsession(self.hass)
                lang = "en"
                if hasattr(self.hass.config, "language") and self.hass.config.language:
                    lang = self.hass.config.language[:2]
                api = WikipediaAPI(session, lang=lang)
                
                wiki_results = await api.search_plants(search_query)
                self._search_results = wiki_results

            if not self._search_results:
                errors["base"] = "no_plants_found"
            elif len(self._search_results) == 1:
                return await self.async_step_select_species({"pid": self._search_results[0]["pid"]})
            else:
                return await self.async_step_select_species()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("name"): str,
                vol.Required("species_search"): str,
                vol.Optional("custom_image_url"): str,
            }),
            errors=errors,
        )

    async def async_step_select_species(self, user_input=None):
        """Step to select a species."""
        if user_input is not None:
            pid = user_input["pid"]
            
            # Find which source the selected pid came from
            selected_plant = next((p for p in self._search_results if p["pid"] == pid), None)
            source = selected_plant["source"] if selected_plant else "wikipedia"
            
            if source == "local":
                path = os.path.join(os.path.dirname(__file__), "plants.json")
                with open(path, "r", encoding="utf-8") as f:
                    plants = json.load(f)
                details = plants.get(pid, {"name": pid})
                details["source"] = "local"
            else:
                session = async_get_clientsession(self.hass)
                lang = "en"
                if hasattr(self.hass.config, "language") and self.hass.config.language:
                    lang = self.hass.config.language[:2]
                api = WikipediaAPI(session, lang=lang)
                details = await api.get_plant_detail(pid)
            
            options = {}
            if self._custom_image:
                options["custom_image_url"] = self._custom_image

            return self.async_create_entry(
                title=f"{self._plant_name} ({details.get('name', pid)})",
                data={
                    "name": self._plant_name,
                    ATTR_PID: pid,
                    ATTR_SPECIES: details.get('name', pid),
                    "details": details
                },
                options=options
            )

        species_options = {p["pid"]: p["alias"] for p in self._search_results}
        return self.async_show_form(
            step_id="select_species",
            data_schema=vol.Schema({
                vol.Required("pid"): vol.In(species_options),
            }),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SmartPlantOptionsFlowHandler(config_entry)

class SmartPlantOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # Handle image path if provided
            image_path = user_input.get("custom_image_path")
            if image_path and os.path.exists(image_path):
                coordinator = self.hass.data[DOMAIN].get(self.config_entry.entry_id)
                if coordinator:
                    await coordinator.async_copy_custom_image(image_path)
            
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("days_between_waterings", default=self.config_entry.options.get("days_between_waterings", 7)): int,
                vol.Optional("custom_image_path"): str,
                vol.Optional("custom_image_url", default=self.config_entry.options.get("custom_image_url", "")): str,
            }),
        )
