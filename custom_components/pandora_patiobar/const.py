"""Constants for the Patiobar Pandora integration."""

DOMAIN = "pandora_patiobar"

# Configuration constants
CONF_HOST = "host"
CONF_PORT = "port"
CONF_WEBSOCKET_PORT = "websocket_port"

# Default values
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 80
DEFAULT_WEBSOCKET_PORT = 80
DEFAULT_NAME = "Pandora via Patiobar"

# Websocket events
WS_EVENT_START = "start"
WS_EVENT_STOP = "stop"
WS_EVENT_STATIONS = "stations"
WS_EVENT_VOLUME = "volume"
WS_EVENT_ACTION = "action"
WS_EVENT_LOVEHATE = "lovehate"
WS_EVENT_STATION = "station"
WS_EVENT_STATION_LIST = "stationList"
WS_EVENT_SONG = "song"

# Media player constants
SUPPORT_PAUSE = "pause"
SUPPORT_PLAY = "play"
SUPPORT_NEXT_TRACK = "next_track"
SUPPORT_VOLUME_SET = "volume_set"
SUPPORT_SELECT_SOURCE = "select_source"
SUPPORT_TURN_ON = "turn_on"
SUPPORT_TURN_OFF = "turn_off"

# Pandora rating constants
RATING_LOVE = "1"
RATING_HATE = "0"
RATING_NONE = ""

# Update intervals
UPDATE_INTERVAL = 5  # seconds
