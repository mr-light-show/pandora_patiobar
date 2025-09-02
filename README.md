# Pandora via Patiobar for Home Assistant

A Home Assistant integration that connects to your Patiobar service to control Pandora through the websocket interface.

## Features

- **Full Media Player Control**: Play, pause, next track, volume control
- **Station Selection**: Browse and select from your Pandora stations  
- **Thumbs Up/Down**: Rate songs with thumbs up or thumbs down
- **Real-time Updates**: Live song information, artwork, and playback status
- **Turn On/Off**: Start and stop the Pianobar service remotely

## Requirements

- Home Assistant 2023.1 or newer
- A running Patiobar service (tested against [this repository](https://github.com/mr-light-show/Patiobar))
- Network access from Home Assistant to your Patiobar host

## Installation

### HACS Installation (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"  
3. Click the three dots menu and select "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/patiobar_pandora` directory to your Home Assistant `custom_components` folder
2. Restart Home Assistant
3. The integration will appear in Settings > Devices & Services

## Configuration

1. Go to Settings > Devices & Services
2. Click "Add Integration" and search for "Patiobar Pandora"
3. Enter your Patiobar host information:
   - **Host**: The IP address or hostname where Patiobar is running (default: localhost)
   - **Port**: The port Patiobar is listening on (default: 80)

## Usage

### Basic Media Control

The integration creates a media player entity with standard controls:

- **Play/Pause**: Control playback
- **Next Track**: Skip to the next song
- **Volume**: Adjust the volume (0-100%)
- **Source Selection**: Choose from your Pandora stations
- **Turn On/Off**: Start or stop the Pianobar service

### Thumbs Up/Down

Use the custom services for rating songs:

```yaml
# Automation example - thumbs up the current song
service: patiobar_pandora.thumbs_up
target:
  entity_id: media_player.patiobar_pandora

# Automation example - thumbs down the current song  
service: patiobar_pandora.thumbs_down
target:
  entity_id: media_player.patiobar_pandora
```

### Media Player Attributes

The entity provides these attributes:

- `media_title`: Song title
- `media_artist`: Artist name
- `media_album_name`: Album name
- `media_image_url`: Album artwork URL
- `source`: Current station name
- `rating`: Current song rating (if available)
- `song_station`: Station that song came from

### Example Lovelace Card

```yaml
type: media-control
entity: media_player.patiobar_pandora
```

Or for more advanced control:

```yaml
type: entities
title: Pandora Control
entities:
  - entity: media_player.patiobar_pandora
  - type: buttons
    entities:
      - entity: media_player.patiobar_pandora
        name: Thumbs Up
        tap_action:
          action: call-service
          service: patiobar_pandora.thumbs_up
          target:
            entity_id: media_player.patiobar_pandora
      - entity: media_player.patiobar_pandora  
        name: Thumbs Down
        tap_action:
          action: call-service
          service: patiobar_pandora.thumbs_down
          target:
            entity_id: media_player.patiobar_pandora
```

## Troubleshooting

### Connection Issues

1. Verify Patiobar is running and accessible at the configured host/port
2. Check that the `/inactivity` endpoint returns data when accessed directly
3. Ensure no firewall is blocking the connection
4. Check Home Assistant logs for connection errors

### Websocket Issues

1. The integration uses Socket.IO websockets - ensure your Patiobar version supports this
2. Check that the websocket endpoint is available at `ws://host:port/socket.io/`
3. Look for websocket connection errors in the Home Assistant logs

### No Stations Available

1. Ensure your Pianobar configuration has stations configured
2. Check that the station list file exists at the expected location
3. Restart both Patiobar and the Home Assistant integration

## Support

For issues and feature requests, please use the GitHub repository issues section.

## License

This project is licensed under the same terms as the original Patiobar project.
