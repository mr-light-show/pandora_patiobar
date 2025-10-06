"""Support for Patiobar Pandora media player."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DEFAULT_NAME
from .coordinator import PatiobarCoordinator

_LOGGER = logging.getLogger(__name__)

SUPPORT_PATIOBAR = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Patiobar Pandora media player."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities([PatiobarMediaPlayer(coordinator, config_entry)])
    
    # Register custom services
    platform = async_get_current_platform()
    
    platform.async_register_entity_service(
        "media_thumbs_up",
        {},
        "async_thumbs_up",
    )
    
    platform.async_register_entity_service(
        "media_thumbs_down", 
        {},
        "async_thumbs_down",
    )


class PatiobarMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Representation of a Patiobar Pandora media player."""

    def __init__(self, coordinator: PatiobarCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the media player."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._config_entry = config_entry
        
        # Entity attributes
        self._attr_unique_id = f"{config_entry.entry_id}_media_player"
        self._attr_name = DEFAULT_NAME
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:pandora"
        
        # Media player attributes
        self._attr_supported_features = SUPPORT_PATIOBAR
        self._attr_media_content_type = MediaType.MUSIC
        self._attr_device_class = "speaker"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry.entry_id)},
            manufacturer="Patiobar",
            model="Pandora Player",
            name=DEFAULT_NAME,
            sw_version="1.0.0",
        )

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the media player."""
        is_running = self.coordinator.is_running
        is_playing = self.coordinator.is_playing
        
        if not is_running:
            state = MediaPlayerState.OFF
        elif is_playing:
            # Swap: when coordinator says "playing", show as "paused" 
            state = MediaPlayerState.PAUSED
        else:
            # Swap: when coordinator says "paused", show as "playing"
            state = MediaPlayerState.PLAYING
            
        _LOGGER.info("🎵 MEDIA PLAYER STATE (SWAPPED): is_running=%s, is_playing=%s -> %s", is_running, is_playing, state)
        return state

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        return self.coordinator.volume / 100.0

    @property
    def source(self) -> str | None:
        """Name of the current input source."""
        song_info = self.coordinator.current_song
        return song_info.get("stationName")

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        return self.coordinator.stations

    @property
    def media_content_id(self) -> str | None:
        """Content ID of current playing media."""
        song_info = self.coordinator.current_song
        return f"{song_info.get('artist', '')} - {song_info.get('title', '')}"

    @property
    def media_content_type(self) -> str | None:
        """Content type of current playing media."""
        return MediaType.MUSIC

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        return None  # Pandora doesn't provide duration

    @property
    def media_position(self) -> int | None:
        """Position of current playing media in seconds."""
        return None  # Not available from Pandora

    @property
    def media_position_updated_at(self) -> None:
        """When was the position of the current playing media valid."""
        return None  # Not available from Pandora

    @property
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        song_info = self.coordinator.current_song
        cover_art = song_info.get("coverArt", "")
        if cover_art and not cover_art.endswith("On_Off.png"):
            return cover_art
        return None

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        song_info = self.coordinator.current_song
        return song_info.get("title")

    @property
    def media_artist(self) -> str | None:
        """Artist of current playing media."""
        song_info = self.coordinator.current_song
        return song_info.get("artist")

    @property
    def media_album_name(self) -> str | None:
        """Album name of current playing media."""
        song_info = self.coordinator.current_song
        return song_info.get("album")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        song_info = self.coordinator.current_song
        attributes = {}
        
        # Rating (loved/rating fields from scope)
        if song_info.get("rating"):
            attributes["rating"] = song_info["rating"]
        if song_info.get("loved"):
            attributes["loved"] = song_info["loved"]
        
        # Station information  
        if song_info.get("songStationName"):
            attributes["song_station"] = song_info["songStationName"]
        
        # Image alt text if available
        if song_info.get("alt"):
            attributes["image_alt"] = song_info["alt"]
            
        return attributes

    async def async_media_play(self) -> None:
        """Send play command."""
        _LOGGER.info("🎵 MEDIA PLAYER: async_media_play() called")
        await self.coordinator.async_media_play()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        _LOGGER.info("🎵 MEDIA PLAYER: async_media_pause() called")
        await self.coordinator.async_media_pause()

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self.coordinator.async_media_next_track()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self.coordinator.async_set_volume_level(volume)

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        await self.coordinator.async_select_source(source)

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self.coordinator.async_turn_on()

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self.coordinator.async_turn_off()

    # Custom service methods for thumbs up/down
    async def async_thumbs_up(self) -> None:
        """Send thumbs up to current track."""
        await self.coordinator.async_thumbs_up()

    async def async_thumbs_down(self) -> None:
        """Send thumbs down to current track."""
        await self.coordinator.async_thumbs_down()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
