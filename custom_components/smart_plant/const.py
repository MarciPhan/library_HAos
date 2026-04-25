"""Constants for the Smart Plant integration."""

DOMAIN = "smart_plant"

CONF_CLIENT_ID = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_PLANTS = "plants"

# OpenPlantbook API constants
OPB_BASE_URL = "https://open.plantbook.io/api/v1"
OPB_TOKEN_URL = "https://open.plantbook.io/api/v1/token/"

# Data keys
DATA_COORDINATOR = "coordinator"

# Plant attributes
ATTR_SPECIES = "species"
ATTR_LAST_WATERED = "last_watered"
ATTR_DAYS_BETWEEN_WATERINGS = "days_between_waterings"
ATTR_HEALTH = "health"
ATTR_IMAGE_URL = "image_url"
ATTR_PID = "pid"

# Default values
DEFAULT_DAYS_BETWEEN_WATERINGS = 7

# Health states
HEALTH_EXCELLENT = "Excellent"
HEALTH_VERY_GOOD = "Very Good"
HEALTH_GOOD = "Good"
HEALTH_FAIR = "Fair"
HEALTH_POOR = "Poor"
HEALTH_CRITICAL = "Critical"

HEALTH_STATES = [
    HEALTH_EXCELLENT,
    HEALTH_VERY_GOOD,
    HEALTH_GOOD,
    HEALTH_FAIR,
    HEALTH_POOR,
    HEALTH_CRITICAL,
]
