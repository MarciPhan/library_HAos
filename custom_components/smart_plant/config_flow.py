"""Config flow for Smart Plant integration."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_CLIENT_ID, CONF_CLIENT_SECRET, ATTR_SPECIES, ATTR_PID
from .api import OpenPlantbookAPI

class SmartPlantConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Smart Plant."""

    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self._client_id = None
        self._client_secret = None
        self._plant_name = None
        self._search_results = []

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Check if we already have API credentials
        entries = self._async_current_entries()
        api_entry = next((entry for entry in entries if entry.unique_id == "smart_plant_api"), None)

        if not api_entry:
            return await self.async_step_api_setup()
        
        return await self.async_step_plant_setup()

    async def async_step_api_setup(self, user_input=None):
        """Setup API credentials."""
        errors = {}
        if user_input is not None:
            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]

            session = async_get_clientsession(self.hass)
            api = OpenPlantbookAPI(self._client_id, self._client_secret, session)
            if await api.authenticate():
                return self.async_create_entry(
                    title="Smart Plant API Settings",
                    data={
                        CONF_CLIENT_ID: self._client_id,
                        CONF_CLIENT_SECRET: self._client_secret,
                    },
                    unique_id="smart_plant_api"
                )
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="api_setup",
            data_schema=vol.Schema({
                vol.Required(CONF_CLIENT_ID): str,
                vol.Required(CONF_CLIENT_SECRET): str,
            }),
            errors=errors,
        )

    async def async_step_plant_setup(self, user_input=None):
        """Step to add a plant."""
        errors = {}
        if user_input is not None:
            self._plant_name = user_input["name"]
            search_query = user_input["species_search"]
            
            # Get API from the settings entry
            api_entry = next((entry for entry in self._async_current_entries() if entry.unique_id == "smart_plant_api"), None)
            if not api_entry:
                return await self.async_step_api_setup()
            
            session = async_get_clientsession(self.hass)
            api = OpenPlantbookAPI(api_entry.data[CONF_CLIENT_ID], api_entry.data[CONF_CLIENT_SECRET], session)
            
            self._search_results = await api.search_plants(search_query)
            if not self._search_results:
                errors["base"] = "no_plants_found"
            elif len(self._search_results) == 1:
                # Only one result, skip selection
                return await self.async_step_select_species({"pid": self._search_results[0]["pid"]})
            else:
                return await self.async_step_select_species()

        return self.async_show_form(
            step_id="plant_setup",
            data_schema=vol.Schema({
                vol.Required("name"): str,
                vol.Required("species_search"): str,
            }),
            errors=errors,
        )

    async def async_step_select_species(self, user_input=None):
        """Step to select a species from search results."""
        errors = {}
        if user_input is not None:
            pid = user_input["pid"]
            selected_plant = next((p for p in self._search_results if p["pid"] == pid), None)
            
            # Fetch full details
            api_entry = next((entry for entry in self._async_current_entries() if entry.unique_id == "smart_plant_api"), None)
            session = async_get_clientsession(self.hass)
            api = OpenPlantbookAPI(api_entry.data[CONF_CLIENT_ID], api_entry.data[CONF_CLIENT_SECRET], session)
            
            details = await api.get_plant_detail(pid)
            
            # Create the plant entry
            return self.async_create_entry(
                title=f"{self._plant_name} ({selected_plant.get('display_pid', pid)})",
                data={
                    "name": self._plant_name,
                    ATTR_PID: pid,
                    ATTR_SPECIES: selected_plant.get('display_pid', pid),
                    "details": details
                }
            )

        species_options = {p["pid"]: f"{p.get('display_pid', p['pid'])} ({p.get('alias', '')})" for p in self._search_results}
        
        return self.async_show_form(
            step_id="select_species",
            data_schema=vol.Schema({
                vol.Required("pid"): vol.In(species_options),
            }),
            errors=errors,
        )
