<p align="center">
    <img src="https://raw.githubusercontent.com/Baine/speedrr/main/images/speedrr_text.png" alt="speedrr" width="336" height="84">
    <br/>
    <h1>speedrr - Dynamic Upload and Download Speed Manager for Torrenting</h1>
</p>

> ### About this fork
>
> A fork of [sgtsquiggs/speedrr](https://github.com/sgtsquiggs/speedrr) — itself a maintenance fork
> of [itschasa/speedrr](https://github.com/itschasa/speedrr) (upstream, inactive since 2025-07-16)
> patched to run against **qBittorrent 5.2+** — which extends speedrr with:
> - **Silo** media server support (via Silo's native admin sessions API)
> - **Stream-based speed control** and **unlimited speed** support (port of upstream PR #34)
> - The schedule module can be disabled by omitting it from the config
>
> Image: `ghcr.io/Baine/speedrr`.

Change your torrent client's upload speed dynamically, on certain events such as:
- When a Plex/Jellyfin/Emby/Silo stream starts
- Time of day and day of the week
- <i>More coming soon!</i>


Change your torrent client's download speed dynamically, on certain events such as:
- Time of day and day of the week
- <i>More coming soon!</i>


This script is ideal for users with limited upload speed, however anyone can use it to maximise their upload speed, whilst keeping their Plex/Jellyfin/Emby streams buffer-free! Also great to adjust the download rate during the day, in case the bandwidth is needed for something else!


## Features
- Multi-server support for Plex, Jellyfin, Emby, Tautulli, and Silo.
- Supports qBittorrent and Transmission.
- Multi-torrent-client support.
    - Bandwidth is split between them, by number of downloading/uploading torrents.
- Schedule a time/day when upload speed should be lowered.
- Support for unlimited speeds in schedules (equivalent to turning off speed limits).
- Stream-based speed control: set specific upload speeds based on the number of active streams, instead of bandwidth usage.


## Setup

### Docker
Pull the image with:
```cmd
docker pull ghcr.io/Baine/speedrr
```

Your config file should be stored outside of the container, for easy editing.

You can then add a volume to the container (like /data/), which points to a folder where your config is stored.

Example `docker run` command:
```
docker run -d
    -e SPEEDRR_CONFIG=/data/config.yaml
    -v /folder_with_config/:/data/
    --name speedrr
    --network host
    ghcr.io/Baine/speedrr
```

### Unraid
1. Open your console and run the following command:
```
cd /boot/config/plugins/dockerMan/templates-user && touch my-speedrr.xml && nano my-speedrr.xml
```
2. Go to <a href="https://raw.githubusercontent.com/Baine/speedrr/main/speedrr-unraid.xml">speedrr-unraid.xml</a>, and copy and paste it into your console.
3. Press Ctrl+O, then Enter, then Ctrl+X (to save the file and exit).
4. Open your WebUI > `Docker` > `Add Container`.
5. Click `Select a template`, and select `speedrr`.
6. The options should be fine as they are defaulted. Apply changes.
7. Using the <a href="https://github.com/Baine/speedrr/blob/main/config.yaml">template</a>, create config.yaml in your /appdata/speedrr/ folder, and fill out the config.
8. Start/Restart the container in the WebUI.
9. Check everything is working in the logs (Docker Logs).

### Source
1. Download the source code.
2. Install [uv](https://docs.astral.sh/uv/); it will fetch Python 3.12 for you.
3. Install the required modules with `uv sync`.
4. Edit the config to your liking.
5. Run `uv run python main.py --config_path config.yaml` to start.


## Contributing
Anyone is welcome to contribute! Feel free to open pull requests.

## Issues and Bugs
Please report any bugs in the <a href="https://github.com/Baine/speedrr/issues">Issues</a> section.

## Feature Suggestions
Got an idea for the project? Suggest it <a href="https://github.com/Baine/speedrr/issues">here</a>!
