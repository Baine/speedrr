# speedrr — Codebase Analysis

## What it is
A Python 3.12 daemon that dynamically throttles torrent clients' up/download speed limits based on (1) active media-server streams (Plex/Jellyfin/Emby/Tautulli) and (2) time-of-day/weekday schedules. This particular repo is already a **maintenance fork** of `itschasa/speedrr` by `sgtsquiggs` — it only patches compatibility with **qBittorrent 5.2+** (qbittorrent-api ≥ 2025.11.0 handles the 204-empty-body login change) and modernizes tooling (uv, ruff, pyright, pytest, podman/alpine image). It changes nothing about behavior or config.

## Architecture (event-driven, single process)

```
main.py ── loads config (YAML → frozen dataclasses via dataclass-wizard)
        ├─ builds torrent clients        [clients/]
        ├─ builds modules                [modules/]
        │    └─ each runs background threads that set reductions
        │       and signal a shared threading.Event
        └─ main loop: waits on the event → computes new speeds → pushes to clients
```

### Flow of one speed update (`main.py:69-155`)
1. `update_event` fires (set by any module when its reduction changes).
2. Each module returns a `(upload_reduction, download_reduction)` tuple; reductions are **summed**.
3. `new_speed = max(min_speed, max_speed − Σ reductions)` — independently for upload and download.
4. That total is **split across torrent clients**:
   - default: proportional to each client's count of active (downloading/uploading) torrents; a client with 0 active torrents gets the full speed.
   - `manual_speed_algorithm_share: true`: split by configured `upload_shares`/`download_shares` weights instead. ⚠️ **Note: the mapping is swapped** — upload speed uses `download_shares`, download speed uses `upload_shares` (`main.py:109-118`). Possibly intentional ("shares of the other direction's demand"), but it looks like a latent bug.
5. Speeds converted via `helpers/bit_convert.py` (`bit_conv`, decimal vs binary unit table) and pushed: qBittorrent `transfer_set_up/download_limit` (bytes/s), Transmission `set_session(speed_limit_up/down)` (KB/s). Floor of 1 (clients can't do 0).

### Modules (`modules/`)
- **`MediaServerModule`** (`media_server.py`): one polling thread per configured server (`BaseServer(threading.Thread)`, `update_interval` s). Each `get_bandwidth()` → sum of stream bandwidths (Kbit/s) after filters → converted to config units → stored in `reduction_value_dict`; fires the event only on change. **Upload-only**: always returns `(_, 0)`.
  - Filters (`process_session`): ignore paused streams after `paused_after` s (tracks `_paused_since` per session id), ignore private/LAN IPs if `ignore_streams.local`, ignore configured `ip_networks`. `bandwidth_multiplier` scales reported bandwidth.
  - Backends: **Plex** (`/status/sessions` + X-Plex-Token), **Tautulli** (`get_activity` API), **Jellyfin/Emby** (`/Sessions`; direct play = sum of MediaStream BitRates, transcode = TranscodingInfo.Bitrate).
- **`ScheduleModule`** (`schedule.py`): one thread per schedule entry. Parses `"HH:MM"` start/end + weekdays, precomputes absolute reduction values (percent of max or fixed). Loop: compute next start/end occurrence (searching up to 7 days ahead, skipping non-matching weekdays), sleep until then, set/remove its reduction, fire event. Handles end-past-midnight via the day list.

### Clients (`clients/`)
- `qBittorrentClient` (qbittorrent-api), `TransmissionClient` (transmission-rpc). Same interface: `get_active_torrent_count()`, `set_upload_speed()`, `set_download_speed()`. `ClientConfig.type` literal also allows `"deluge"` but **no Deluge client is implemented** — config would crash with "Unknown client type".

### Config (`helpers/config.py`)
Frozen dataclasses mapped from YAML: `SpeedrrConfig` (units, min/max up/down, clients, modules, shares flag), `ClientConfig`, `MediaServerConfig`+`IgnoreStreamConfig`, `ScheduleConfig`, `ModulesConfig`.

### Support
- `helpers/log_loader.py`: colored stdout logger, optional dated file log, global excepthook.
- `helpers/arguments.py`: `--config_path` (or `SPEEDRR_CONFIG`), `--log_level`, `--log_file_level` (env fallbacks).
- `scripts/verify_qbt.py`: standalone live-server check (login, read/write limits with restore) — the fork's key deployment verification.
- Tests: pytest (+pytest-httpx) covering bit conversion, config loading, log loader, schedule threads, media server session processing, and both clients. CI: ruff check + format, pyright, pytest; release workflow builds/pushes GHCR image on `v*` tags. Makefile orchestrates `make check/build/load/verify/release` against a personal "tower" (Unraid) host.

## Observations worth knowing before forking
1. **Share-mapping oddity** in `main.py:109-118` (see above) — worth a look.
2. **Media servers never reduce download** — hardcoded `(_, 0)`.
3. `paused_after` tracking keys on session id, not client IP; duplicate sessions from one IP behave per-session.
4. Single shared `threading.Event` + 0.2s polling loop; all module threads are daemons.
5. No state persisted; on restart it recomputes everything from scratch.
6. Fork-specific history lives in commit messages + pyproject comments (qBittorrent 5.2 login, dataclass-wizard 1.0 relocation, httpx 0.28 pin forced by pytest-httpx).

## Quick summary
**speedrr = config-driven speed governor**: `new_speed = max(min, max − Σ(module reductions))`, split across clients by active-torrent count (or manual shares), applied on an event bus whenever a media-server poll or schedule boundary changes anything. ~1,000 lines of runtime code, clean separation (config/clients/modules/main), well-tested, containerized.

## Fork changes (this repo's second fork)
- **Silo media server support**: new `SiloServer` backend in `modules/media_server.py` polls `GET /api/v1/admin/sessions` with `Authorization: Bearer <api_key>` (an admin `sa_`-prefixed key). Silo reports sessions natively in snake_case (`session_id`, `is_paused`, `client_ip`, `media_title`, `stream_bitrate_kbps`) with bitrate already in Kbit/s, so no unit conversion is needed. Note: Silo's Jellyfin-compat `GET /Sessions` is always empty — the native API is the only source of live sessions.
- **Schedule can be disabled**: `modules.media_servers` and `modules.schedule` now default to `null` in `helpers/config.py` (previously required fields, parse error if omitted), and the whole `modules` block is optional.
- **Stream-based speed control + unlimited speeds** (port of upstream PR #34): media servers can define `stream_based_speeds: {enabled, speeds, default}` so the upload speed is chosen by the count of active non-ignored streams (exact count → highest defined count ≤ current → default → max_upload) instead of bandwidth arithmetic; values may be numbers, `"N%"` of max_upload, or `"unlimited"`. `"unlimited"` is also accepted as schedule upload/download values and removes the client's speed limit entirely (qBittorrent limit 0, Transmission limit disabled). Stream-based mode is signaled to `main.py` via a `-inf` reduction marker.
- **Upstream status**: upstream `main` has no commits newer than this fork's base; the only upstream work not previously present was the two open PRs (#37's login-error message hint — our pin `qbittorrent-api>=2025.11.0` already resolves past it — and #34, now ported). Deluge support and media-server-driven download throttling do not exist upstream at all.
