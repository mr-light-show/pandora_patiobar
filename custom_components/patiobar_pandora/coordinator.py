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
        self._current_song = {}
        self._volume = 50
        self._is_playing = False
        self._is_running = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    @property
    def stations(self) -> list[str]:
        """Return available stations."""
        return self._stations

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
                async with websockets.connect(self.ws_url) as websocket:
                    self.websocket = websocket
                    # Send initial Socket.IO handshake
                    await websocket.send("40")  # Socket.IO connect message
                    
                    async for message in websocket:
                        await self._handle_websocket_message(message)
                        
            except Exception as err:
                _LOGGER.error("Websocket connection error: %s", err)
                await asyncio.sleep(5)  # Wait before reconnecting

    async def _handle_websocket_message(self, message: str) -> None:
        """Handle incoming websocket messages."""
        try:
            if message.startswith("42"):  # Socket.IO event message
                # Parse Socket.IO message format: 42["event_name", data]
                json_part = message[2:]  # Remove "42" prefix
                data = json.loads(json_part)
                
                if len(data) >= 2:
                    event_name = data[0]
                    event_data = data[1] if len(data) > 1 else {}
                    
                    await self._process_websocket_event(event_name, event_data)
                    
        except json.JSONDecodeError:
            _LOGGER.debug("Non-JSON websocket message: %s", message)
        except Exception as err:
            _LOGGER.error("Error handling websocket message: %s", err)

    async def _process_websocket_event(self, event: str, data: dict[str, Any]) -> None:
        """Process websocket events."""
        _LOGGER.debug("Received websocket event: %s with data: %s", event, data)
        
        if event == WS_EVENT_START:
            self._current_song = data
            self._is_playing = data.get("isplaying", False)
            self._is_running = data.get("isrunning", False)
            self.async_set_updated_data(await self._async_update_data())
            
        elif event == WS_EVENT_STATIONS:
            stations_data = data.get("stations", [])
            # Filter out empty strings
            self._stations = [s for s in stations_data if s.strip()]
            self.async_set_updated_data(await self._async_update_data())
            
        elif event == WS_EVENT_VOLUME:
            self._volume = data.get("volume", 50)
            self.async_set_updated_data(await self._async_update_data())

    # Media control methods
    async def async_media_play(self) -> None:
        """Send play command."""
        await self._send_http_command("play")

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self._send_http_command("pause")

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self._send_http_command("next")

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
            station_index = self._stations.index(source)
            if self.websocket:
                message = f'42["changeStation", {{"stationId": "{station_index}"}}]'
                await self.websocket.send(message)
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
        except Exception as err:
            _LOGGER.error("Error sending thumbs up: %s", err)

    async def async_thumbs_down(self) -> None:
        """Send thumbs down."""
        try:
            if self.websocket:
                message = '42["action", {"action": "-"}]'
                await self.websocket.send(message)
        except Exception as err:
            _LOGGER.error("Error sending thumbs down: %s", err)

    async def _send_http_command(self, action: str) -> None:
        """Send HTTP command to patiobar."""
        try:
            url = f"{self.http_url}/ha?action={action}"
            async with self.session.post(url) as response:
                if response.status != 200:
                    _LOGGER.error("HTTP command %s failed with status %s", action, response.status)
        except Exception as err:
            _LOGGER.error("Error sending HTTP command %s: %s", action, err)
