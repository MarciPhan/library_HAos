"""Constants for the Smart Plant integration."""

DOMAIN = "smart_plant"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_PLANTS = "plants"
CONF_USE_API = "use_api"

# API URL for Wikipedia
WIKI_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"



# Moisture heuristics (keywords -> min_soil_moist)
MOISTURE_HEURISTICS = {
    "succulent": 15,
    "desert": 10,
    "arid": 15,
    "drought": 15,
    "cactus": 5,
    "tropical": 50,
    "rainforest": 60,
    "jungle": 50,
    "humid": 50,
    "swamp": 80,
    "aquatic": 90,
    "marsh": 70,
    "houseplant": 35,
    "indoor": 35,
    "epiphyte": 40,
    "mediterranean": 30,
}

# Data keys
DATA_COORDINATOR = "coordinator"

# Plant attributes
ATTR_SPECIES = "species"
ATTR_LAST_WATERED = "last_watered"
ATTR_DAYS_BETWEEN_WATERINGS = "days_between_waterings"
ATTR_HEALTH = "health"
ATTR_IMAGE_URL = "image_url"
ATTR_CUSTOM_IMAGE_URL = "custom_image_url"
ATTR_PID = "pid"

# Default values
DEFAULT_DAYS_BETWEEN_WATERINGS = 7

# Local Plant Database (Aggregation)
LOCAL_PLANTS = {
    "monstera": {"name": "Monstera Deliciosa", "min_soil_moist": 40},
    "ficus": {"name": "Ficus Lyrata", "min_soil_moist": 40},
    "sansevieria": {"name": "Snake Plant (Sansevieria)", "min_soil_moist": 15},
    "aloe": {"name": "Aloe Vera", "min_soil_moist": 15},
    "pothos": {"name": "Pothos (Epipremnum aureum)", "min_soil_moist": 50},
    "zamioculcas": {"name": "ZZ Plant (Zamioculcas)", "min_soil_moist": 15},
    "spathiphyllum": {"name": "Peace Lily (Spathiphyllum)", "min_soil_moist": 60},
    "chlorophytum": {"name": "Spider Plant (Chlorophytum)", "min_soil_moist": 45},
    "dracaena": {"name": "Dragon Tree (Dracaena)", "min_soil_moist": 30},
    "succulent": {"name": "General Succulent", "min_soil_moist": 10},
    "cactus": {"name": "General Cactus", "min_soil_moist": 5},
}

# Health states
HEALTH_EXCELLENT = "Ukázková"
HEALTH_VERY_GOOD = "Prosperující"
HEALTH_GOOD = "Spokojená"
HEALTH_FAIR = "Stagnující"
HEALTH_POOR = "Chřadnoucí"
HEALTH_CRITICAL = "Skomírající"
HEALTH_DEAD = "kompost"

HEALTH_STATES = [
    HEALTH_EXCELLENT,
    HEALTH_VERY_GOOD,
    HEALTH_GOOD,
    HEALTH_FAIR,
    HEALTH_POOR,
    HEALTH_CRITICAL,
    HEALTH_DEAD,
]
