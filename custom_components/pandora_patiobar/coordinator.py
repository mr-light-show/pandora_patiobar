"""Coordinator for Patiobar Pandora integration."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import aiohttp
import websockets
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_PORT,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DOMAIN,
    UPDATE_INTERVAL,
    WS_EVENT_START,
    WS_EVENT_STATIONS,
    WS_EVENT_VOLUME,
    WS_EVENT_STATION,
    WS_EVENT_STATION_LIST,
    WS_EVENT_SONG,
)

_LOGGER = logging.getLogger(__name__)


class PatiobarCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from Patiobar."""

    def __init__(
        self,
        hass: HomeAssistant,
        session: aiohttp.ClientSession,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.session = session
        self.entry = entry
        self.host = entry.data.get(CONF_HOST, DEFAULT_HOST)
        self.port = entry.data.get(CONF_PORT, DEFAULT_PORT)
        self.ws_url = f"ws://{self.host}:{self.port}/socket.io/?EIO=3&transport=websocket"
        self.http_url = f"http://{self.host}:{self.port}"
        
        self.websocket = None
        self.websocket_task = None
        self._stations = []
        self._stations_raw = []  # Store original station names with numbers
        self._current_song = {}
        self._volume = 50
        self._is_playing = False  # Start as False, will be updated from websocket
        self._is_running = False
        
        _LOGGER.info("🎵 COORDINATOR INIT - Initial state: is_playing=%s, is_running=%s", self._is_playing, self._is_running)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    @property
    def stations(self) -> list[str]:
        """Return available stations with cleaned names."""
        return self._stations
    
    def _clean_station_name(self, station_name: str) -> str:
        """Clean station name by removing numbers, prefixes, and 'Radio'."""
        import re
        
        # Remove leading numbers and dots/parentheses (e.g. "0) Station Name" -> "Station Name")
        cleaned = re.sub(r'^\d+[\)\.\]\:\-\s]+', '', station_name.strip())
        
        # Remove trailing numbers in parentheses (e.g. "Station Name (1)" -> "Station Name")
        cleaned = re.sub(r'\s*\(\d+\)$', '', cleaned)
        
        # Remove the word "Radio" only if it's the last word (case-insensitive)
        cleaned = re.sub(r'\bRadio\s*$', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up multiple spaces and leading/trailing whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        # If cleaning removed everything, return original
        if not cleaned:
            cleaned = station_name.strip()
            
        return cleaned
    
    def _process_stations(self, raw_stations: list[str]) -> None:
        """Process and clean station names while preserving selection ability."""
        # Store raw stations for index mapping
        self._stations_raw = [s.strip() for s in raw_stations if s.strip()]
        
        # Create cleaned display names
        self._stations = [self._clean_station_name(s) for s in self._stations_raw]
        
        _LOGGER.debug("Raw stations: %s", self._stations_raw)
        _LOGGER.debug("Cleaned stations: %s", self._stations)

    @property
    def current_song(self) -> dict[str, Any]:
        """Return current song information."""
        return self._current_song

    @property
    def volume(self) -> int:
        """Return current volume."""
        return self._volume

    @property
    def is_playing(self) -> bool:
        """Return if currently playing."""
        return self._is_playing

    @property
    def is_running(self) -> bool:
        """Return if Pianobar is running."""
        return self._is_running

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API endpoint."""
        try:
            # For now, we'll rely on websocket updates
            # But we can add HTTP polling here if needed
            return {
                "stations": self._stations,
                "current_song": self._current_song,
                "volume": self._volume,
                "is_playing": self._is_playing,
                "is_running": self._is_running,
            }
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    async def async_config_entry_first_refresh(self) -> None:
        """Perform first refresh."""
        await super().async_config_entry_first_refresh()
        # Start websocket connection after first refresh
        self.websocket_task = asyncio.create_task(self._websocket_handler())
        # Request initial station list
        await self._request_initial_data()

    async def async_disconnect(self) -> None:
        """Disconnect from websocket."""
        if self.websocket_task:
            self.websocket_task.cancel()
            try:
                await self.websocket_task
            except asyncio.CancelledError:
                pass
        if self.websocket:
            await self.websocket.close()

    async def _websocket_handler(self) -> None:
        """Handle websocket connection."""
        while True:
            try:
                _LOGGER.debug("Connecting to websocket at %s", self.ws_url)
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=30,  # Send ping every 30 seconds
                    ping_timeout=10,   # Wait 10 seconds for pong
                    close_timeout=10   # Wait 10 seconds for close
                ) as websocket:
                    self.websocket = websocket
                    _LOGGER.info("Websocket connected successfully")
                    # Send initial Socket.IO handshake
                    await websocket.send("40")  # Socket.IO connect message
                    _LOGGER.debug("Sent Socket.IO handshake")
                    
                    # Start keepalive task
                    keepalive_task = asyncio.create_task(self._keepalive_handler(websocket))
                    
                    try:
                        async for message in websocket:
                            await self._handle_websocket_message(message)
                    finally:
                        keepalive_task.cancel()
                        try:
                            await keepalive_task
                        except asyncio.CancelledError:
                            pass
                        
            except Exception as err:
                _LOGGER.error("Websocket connection error: %s", err)
                await asyncio.sleep(5)  # Wait before reconnecting

    async def _keepalive_handler(self, websocket) -> None:
        """Send Socket.IO keepalive messages to maintain connection."""
        try:
            while True:
                await asyncio.sleep(25)  # Send keepalive every 25 seconds
                await websocket.send("2")  # Socket.IO ping message
                _LOGGER.debug("Sent Socket.IO keepalive ping")
        except Exception as err:
            _LOGGER.debug("Keepalive handler stopped: %s", err)

    async def _handle_websocket_message(self, message: str) -> None:
        """Handle incoming websocket messages."""
        try:
            _LOGGER.debug("Raw websocket message received: %s", message)
            
            if message.startswith("42"):  # Socket.IO event message
                # Parse Socket.IO message format: 42["event_name", data]
                json_part = message[2:]  # Remove "42" prefix
                data = json.loads(json_part)
                
                if len(data) >= 1:
                    event_name = data[0]
                    event_data = data[1] if len(data) > 1 else {}
                    
                    _LOGGER.debug("Parsed websocket event: '%s' with data: %s", event_name, event_data)
                    await self._process_websocket_event(event_name, event_data)
                    
        except json.JSONDecodeError:
            _LOGGER.debug("Non-JSON websocket message: %s", message)
        except Exception as err:
            _LOGGER.error("Error handling websocket message: %s", err)

    def _update_from_scope_data(self, data: dict[str, Any], source: str = "websocket") -> bool:
        """
        Update coordinator state from scope data payload.
        
        Args:
            data: Websocket data payload potentially containing scope fields
            source: Source description for logging (e.g. "websocket", "song_event")
            
        Returns:
            bool: True if any state was updated
        """
        state_updated = False
        
        # Server/process status fields
        if "patiobarRunning" in data:
            _LOGGER.debug("Found patiobarRunning: %s", data.get("patiobarRunning"))
            
        if "pianobarRunning" in data:
            old_running = self._is_running
            self._is_running = data.get("pianobarRunning", False)
            if old_running != self._is_running:
                _LOGGER.info("Piano bar running state changed: %s -> %s", old_running, self._is_running)
                state_updated = True
        elif "isrunning" in data:
            old_running = self._is_running
            self._is_running = data.get("isrunning", False)
            if old_running != self._is_running:
                _LOGGER.info("Piano bar running state changed: %s -> %s", old_running, self._is_running)
                state_updated = True
                
        # Play state - prioritize pianobarPlaying over isplaying
        if "pianobarPlaying" in data:
            old_playing = self._is_playing
            self._is_playing = data.get("pianobarPlaying", False)
            if old_playing != self._is_playing:
                _LOGGER.info("Piano bar playing state changed: %s -> %s", old_playing, self._is_playing)
                state_updated = True
        elif "isplaying" in data:
            old_playing = self._is_playing
            self._is_playing = data.get("isplaying", False)
            if old_playing != self._is_playing:
                _LOGGER.info("Piano bar playing state changed: %s -> %s", old_playing, self._is_playing)
                state_updated = True
                
        # Audio control
        if "volume" in data:
            old_volume = self._volume
            volume_value = data.get("volume")
            # Use volume if provided and valid, otherwise keep current or default to 50
            self._volume = volume_value if volume_value is not None else self._volume or 50
            if old_volume != self._volume:
                _LOGGER.debug("Volume changed: %s -> %s", old_volume, self._volume)
                state_updated = True
            else:
                # Force update even if volume hasn't changed to ensure UI sync
                state_updated = True
                
        # Song information - update current_song with all available fields
        song_fields = ["artist", "album", "title", "stationName", "songStationName", "src", "coverArt", "alt", "loved", "rating"]
        song_updated = False
        for field in song_fields:
            if field in data:
                old_value = self._current_song.get(field)
                new_value = data.get(field)
                if old_value != new_value:
                    self._current_song[field] = new_value
                    song_updated = True
                    _LOGGER.debug("Song field '%s' updated: %s -> %s", field, old_value, new_value)
                    
        # Map 'src' to 'coverArt' for compatibility (if src is provided but not coverArt)
        if "src" in data and "coverArt" not in data:
            self._current_song["coverArt"] = data.get("src")
        # Map 'coverArt' to 'src' for compatibility (if coverArt is provided but not src)  
        elif "coverArt" in data and "src" not in data:
            self._current_song["src"] = data.get("coverArt")
            
        # Station list data
        if "stations" in data:
            stations_data = data.get("stations", [])
            if isinstance(stations_data, list) and stations_data:
                raw_stations = [s for s in stations_data if s.strip()]
                if raw_stations != self._stations_raw:
                    self._process_stations(raw_stations)
                    _LOGGER.info("🎵 FOUND stations: %s (%s)", len(raw_stations), source)
                    state_updated = True
                    
        final_updated = state_updated or song_updated
        _LOGGER.info("🎵 SCOPE DATA RESULT - state_updated=%s, song_updated=%s, final=%s", state_updated, song_updated, final_updated)
        return final_updated

    async def _process_websocket_event(self, event: str, data: dict[str, Any]) -> None:
        """Process websocket events."""
        _LOGGER.info("🎵 WEBSOCKET EVENT: '%s' with data: %s", event, data)
        
        # Update state from scope data (handles all common scope fields)
        state_updated = self._update_from_scope_data(data, f"event:{event}")
        
        # Update Home Assistant if any state changed
        if state_updated:
            _LOGGER.info("🎵 TRIGGERING HOME ASSISTANT UPDATE - state_updated=True")
            self.async_set_updated_data(await self._async_update_data())
        else:
            _LOGGER.info("🎵 NO HOME ASSISTANT UPDATE - state_updated=False")
            
        if event == WS_EVENT_START:
            # All data already handled by _update_from_scope_data
            _LOGGER.info("🎵 START EVENT - state updated by scope data handler")
            
        elif event == WS_EVENT_STATIONS:
            # Stations already handled by _update_from_scope_data
            _LOGGER.info("🎵 STATIONS EVENT - processed by scope data handler")
            
        elif event == WS_EVENT_VOLUME:
            # Volume already handled by _update_from_scope_data
            _LOGGER.info("🎵 VOLUME EVENT - processed by scope data handler")
            
        elif event == WS_EVENT_STATION:
            # Station info already handled by _update_from_scope_data
            _LOGGER.info("🎵 STATION EVENT - processed by scope data handler")
                
        elif event == WS_EVENT_STATION_LIST:
            # Station list already handled by _update_from_scope_data
            _LOGGER.info("🎵 STATION_LIST EVENT - processed by scope data handler")
            
        elif event == WS_EVENT_SONG:
            # Song data already handled by _update_from_scope_data
            # Preserve existing rating if not provided in new data
            existing_rating = self._current_song.get("rating")
            if "rating" not in data and existing_rating:
                self._current_song["rating"] = existing_rating
                _LOGGER.info("🎵 WS_EVENT_SONG - preserved existing rating: %s", existing_rating)
        
        elif event == "action":
            # Handle action responses (like play/pause toggle)
            action = data.get("action", "")
            _LOGGER.info("🎵 ACTION EVENT: action='%s', data: %s", action, data)
            
            if action == "p":
                # Play/pause toggle - temporarily update state then wait for websocket confirmation
                old_state = self._is_playing
                self._is_playing = not self._is_playing
                _LOGGER.info("🎵 PLAY/PAUSE TOGGLE - temporary state: %s -> %s (waiting for pianobarPlaying confirmation)", old_state, self._is_playing)
                self.async_set_updated_data(await self._async_update_data())
                
                # Request status to get actual pianobarPlaying state
                await self._request_current_status()
            elif action == "i":
                # Song info request response - already handled above
                pass
            
        elif event == "pause" or event == "play":
            # Handle play/pause state changes
            self._is_playing = (event == "play")
            _LOGGER.info("🎵 PLAY/PAUSE EVENT: %s -> is_playing: %s", event, self._is_playing)
            self.async_set_updated_data(await self._async_update_data())
        
        elif event == "status":
            # Status data already handled by _update_from_scope_data
            _LOGGER.info("🎵 STATUS EVENT - processed by scope data handler")
        
        # Catch-all for any unrecognized events
        else:
            _LOGGER.info("🎵 UNRECOGNIZED EVENT: '%s' with data: %s", event, data)
            # All scope data already handled by _update_from_scope_data above

    # Media control methods
    async def async_media_play(self) -> None:
        """Send play command."""
        try:
            _LOGGER.info("🎵 SENDING PLAY COMMAND - current is_playing: %s", self._is_playing)
            if self.websocket:
                # Use pianobar "p" command for play/pause toggle
                message = '42["action", {"action": "p"}]'
                await self.websocket.send(message)
                _LOGGER.info("🎵 SENT PLAY COMMAND via websocket: %s", message)
            else:
                await self._send_http_command("play")
                _LOGGER.info("🎵 SENT PLAY COMMAND via HTTP")
        except Exception as err:
            _LOGGER.error("Error sending play command: %s", err)

    async def async_media_pause(self) -> None:
        """Send pause command."""
        try:
            _LOGGER.warning("🎵 SENDING PAUSE COMMAND - current is_playing: %s", self._is_playing)
            if self.websocket:
                # Use pianobar "p" command for play/pause toggle
                message = '42["action", {"action": "p"}]'
                await self.websocket.send(message)
                _LOGGER.info("🎵 SENT PAUSE COMMAND via websocket: %s", message)
            else:
                await self._send_http_command("pause")
                _LOGGER.info("🎵 SENT PAUSE COMMAND via HTTP")
        except Exception as err:
            _LOGGER.error("Error sending pause command: %s", err)

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        try:
            if self.websocket:
                # Use pianobar "n" command for next track
                message = '42["action", {"action": "n"}]'
                await self.websocket.send(message)
                _LOGGER.debug("Sent next track command via websocket")
            else:
                await self._send_http_command("next")
        except Exception as err:
            _LOGGER.error("Error sending next track command: %s", err)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level (0-1)."""
        volume_percent = int(volume * 100)
        try:
            # Send volume via websocket
            if self.websocket:
                message = f'42["action", {{"action": "v{volume_percent}"}}]'
                await self.websocket.send(message)
        except Exception as err:
            _LOGGER.error("Error setting volume: %s", err)

    async def async_select_source(self, source: str) -> None:
        """Select station/source."""
        try:
            if source not in self._stations:
                _LOGGER.error("Cleaned station '%s' not found in cleaned station list: %s", source, self._stations)
                return
                
            station_index = self._stations.index(source)
            raw_station_name = self._stations_raw[station_index] if station_index < len(self._stations_raw) else source
            
            _LOGGER.info("Selecting cleaned station '%s' (raw: '%s') at index %d", source, raw_station_name, station_index)
            
            # Use the correct Patiobar websocket command format
            if self.websocket:
                # Send changeStation command with 0-based stationId
                message = f'42["changeStation", {{"stationId": {station_index}}}]'
                await self.websocket.send(message)
                _LOGGER.debug("Sent changeStation command: %s", message)
                
                # Station change typically starts playback - set playing state
                old_playing = self._is_playing
                self._is_playing = True
                _LOGGER.info("🎵 STATION CHANGE - set is_playing: %s -> True (station changes start playback)", old_playing)
                self.async_set_updated_data(await self._async_update_data())
                
            else:
                # Fallback to HTTP command if websocket not available
                await self._send_http_command(f"{station_index}")
                _LOGGER.debug("Sent HTTP station selection command for index %d", station_index)
                
                # Also set playing state for HTTP fallback
                old_playing = self._is_playing
                self._is_playing = True
                _LOGGER.info("🎵 STATION CHANGE (HTTP) - set is_playing: %s -> True", old_playing)
                self.async_set_updated_data(await self._async_update_data())
                
        except (ValueError, Exception) as err:
            _LOGGER.error("Error selecting station %s: %s", source, err)

    async def async_turn_on(self) -> None:
        """Turn on (start Pianobar)."""
        try:
            if self.websocket:
                message = '42["process", {"action": "start"}]'
                await self.websocket.send(message)
        except Exception as err:
            _LOGGER.error("Error starting Pianobar: %s", err)

    async def async_turn_off(self) -> None:
        """Turn off (stop Pianobar)."""
        try:
            if self.websocket:
                message = '42["process", {"action": "stop"}]'
                await self.websocket.send(message)
        except Exception as err:
            _LOGGER.error("Error stopping Pianobar: %s", err)

    async def async_thumbs_up(self) -> None:
        """Send thumbs up."""
        try:
            if self.websocket:
                message = '42["action", {"action": "+"}]'
                await self.websocket.send(message)
                _LOGGER.debug("Sent thumbs up command: %s", message)
                
                # Update both rating and loved state immediately
                self._current_song["rating"] = "1"
                self._current_song["loved"] = True
                _LOGGER.info("🎵 THUMBS UP - updated rating=1, loved=True")
                self.async_set_updated_data(await self._async_update_data())
                
        except Exception as err:
            _LOGGER.error("Error sending thumbs up: %s", err)

    async def async_thumbs_down(self) -> None:
        """Send thumbs down."""
        try:
            if self.websocket:
                message = '42["action", {"action": "-"}]'
                await self.websocket.send(message)
                _LOGGER.debug("Sent thumbs down command: %s", message)
                
                # Update both rating and loved state immediately
                self._current_song["rating"] = "0"
                self._current_song["loved"] = False
                _LOGGER.info("🎵 THUMBS DOWN - updated rating=0, loved=False")
                self.async_set_updated_data(await self._async_update_data())
                
        except Exception as err:
            _LOGGER.error("Error sending thumbs down: %s", err)

    async def async_request_song_info(self) -> None:
        """Send 'i' command to request current song information."""
        try:
            if self.websocket:
                message = '42["action", {"action": "i"}]'
                await self.websocket.send(message)
                _LOGGER.debug("Sent song info request command: %s", message)
        except Exception as err:
            _LOGGER.error("Error sending song info request: %s", err)

    async def _request_current_status(self) -> None:
        """Request current status from Patiobar."""
        try:
            if self.websocket:
                # Request current status
                status_message = '42["getStatus"]'
                await self.websocket.send(status_message)
                _LOGGER.info("🎵 REQUESTED CURRENT STATUS")
                
                # Also try song info request
                await self.async_request_song_info()
        except Exception as err:
            _LOGGER.error("Error requesting current status: %s", err)

    async def _request_initial_data(self) -> None:
        """Request initial data from Patiobar including station list."""
        await asyncio.sleep(2)  # Give websocket time to connect
        try:
            if self.websocket:
                # Try multiple methods to get station list
                # Method 1: getStations command
                stations_message = '42["getStations"]'
                await self.websocket.send(stations_message)
                _LOGGER.debug("Requested station list from Patiobar")
                
                # Method 2: Alternative station request
                alt_stations_message = '42["stations"]'
                await self.websocket.send(alt_stations_message)
                _LOGGER.debug("Requested station list (alternative format)")
                

                
                # Request current status
                status_message = '42["getStatus"]'
                await self.websocket.send(status_message)
                _LOGGER.debug("Requested current status from Patiobar")
                
                # Request current song info
                await self.async_request_song_info()
                
                # Also try HTTP endpoint for station list
                await self._fetch_stations_http()
                
        except Exception as err:
            _LOGGER.error("Error requesting initial data: %s", err)
    
    async def _fetch_stations_http(self) -> None:
        """Fetch stations via HTTP endpoint as backup."""
        try:
            # Try multiple HTTP endpoints that might provide station data
            endpoints = ["/stations", "/getStations", "/stationList", "/data"]
            
            for endpoint in endpoints:
                try:
                    url = f"{self.http_url}{endpoint}"
                    async with self.session.get(url) as response:
                        if response.status == 200:
                            stations_data = await response.json()
                            raw_stations = []
                            
                            if isinstance(stations_data, list) and stations_data:
                                raw_stations = [s for s in stations_data if s.strip()]
                            elif isinstance(stations_data, dict) and "stations" in stations_data:
                                station_list = stations_data["stations"]
                                if isinstance(station_list, list) and station_list:
                                    raw_stations = [s for s in station_list if s.strip()]
                            
                            if raw_stations:
                                self._process_stations(raw_stations)
                                _LOGGER.info("Fetched stations via HTTP %s - Raw: %s, Cleaned: %s", endpoint, self._stations_raw, self._stations)
                                self.async_set_updated_data(await self._async_update_data())
                                return
                except Exception as endpoint_err:
                    _LOGGER.debug("HTTP endpoint %s failed: %s", endpoint, endpoint_err)
                    
        except Exception as err:
            _LOGGER.debug("HTTP station fetch failed (this is normal): %s", err)

    async def _send_http_command(self, action: str) -> None:
        """Send HTTP command to patiobar."""
        try:
            url = f"{self.http_url}/ha?action={action}"
            async with self.session.post(url) as response:
                if response.status != 200:
                    _LOGGER.error("HTTP command %s failed with status %s", action, response.status)
        except Exception as err:
            _LOGGER.error("Error sending HTTP command %s: %s", action, err)
