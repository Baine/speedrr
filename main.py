import threading
import traceback

from clients import qbittorrent, transmission
from helpers import arguments, config, log_loader
from helpers.log_loader import logger
from modules import media_server, schedule


def resolve_speed(value: int | float | str, max_speed: int) -> float:
    """Resolve a config speed value, in the config's units.

    Accepts numbers, percentage strings ("50%" of max_speed), and "unlimited"
    (returned as infinity).
    """

    if isinstance(value, str):
        if value.lower() == "unlimited":
            return float("inf")

        if value.endswith("%"):
            return max_speed * float(value[:-1]) / 100

        return float(value)

    return float(value)


def format_speed(value: float, units: str) -> str:
    return "unlimited" if value == float("inf") else f"{value}{units}"


if __name__ == "__main__":
    args = arguments.load_args()

    logger.debug("Loading config")

    if not args.config:
        logger.critical(
            "No config file specified, use --config_path arg or SPEEDRR_CONFIG "
            "env var to specify a config file."
        )
        exit()

    cfg = config.load_config(args.config)

    if cfg.logs_path:
        log_loader.set_file_handler(cfg.logs_path, args.log_file_level)

    log_loader.stdout_handler.setLevel(args.log_level)

    logger.info("Starting Speedrr")

    update_event = threading.Event()

    clients: list[qbittorrent.qBittorrentClient | transmission.TransmissionClient] = []
    for client in cfg.clients:
        if client.type == "qbittorrent":
            torrent_client = qbittorrent.qBittorrentClient(cfg, client)

        elif client.type == "transmission":
            torrent_client = transmission.TransmissionClient(cfg, client)

        else:
            logger.critical(f"Unknown client type in config: {client.type}")
            exit()

        clients.append(torrent_client)

    sum_client_upload_shares = sum(client.upload_shares for client in cfg.clients)
    sum_client_download_shares = sum(client.download_shares for client in cfg.clients)

    modules: list[media_server.MediaServerModule | schedule.ScheduleModule] = []
    if cfg.modules.media_servers:
        plex_module = media_server.MediaServerModule(cfg, cfg.modules.media_servers, update_event)
        modules.append(plex_module)

    if cfg.modules.schedule:
        schedule_module = schedule.ScheduleModule(cfg, cfg.modules.schedule, update_event)
        modules.append(schedule_module)

    if not modules:
        logger.critical("No modules enabled in config, exiting")
        exit()

    for module in modules:
        module.run()
        logger.info(f"Started module: {module.__class__.__name__}")

    # Force an initial update
    update_event.set()

    while True:
        # Without a timeout, Ctrl+C won't work.
        # Polling isn't great, but it will work.
        event_triggered = update_event.wait(timeout=0.2)
        if not event_triggered:
            continue

        # Clear immediately, so that the next event can be set.
        update_event.clear()

        logger.info("Update event triggered")

        try:
            module_reduction_values = [module.get_reduction_value() for module in modules]

            # These are in the config's units
            upload_reductions = [module[0] for module in module_reduction_values]
            download_reductions = [module[1] for module in module_reduction_values]

            # A media server module in stream-based mode signals it with -inf
            using_stream_based_speeds = any(r == float("-inf") for r in upload_reductions)

            if using_stream_based_speeds:
                # The base upload speed comes from the stream count, and schedule
                # reductions apply on top of it.
                target_speed = next(
                    (
                        module.get_target_upload_speed()
                        for module in modules
                        if isinstance(module, media_server.MediaServerModule)
                    ),
                    cfg.max_upload,
                )
                base_upload_speed = resolve_speed(target_speed, cfg.max_upload)
                schedule_reductions = [r for r in upload_reductions if r != float("-inf")]

                if any(r == float("inf") for r in schedule_reductions):
                    new_upload_speed = float("inf")
                elif schedule_reductions:
                    # An unlimited base speed is reduced from max_upload
                    reduced_base = (
                        cfg.max_upload if base_upload_speed == float("inf") else base_upload_speed
                    )
                    new_upload_speed = max(cfg.min_upload, reduced_base - sum(schedule_reductions))
                else:
                    new_upload_speed = base_upload_speed
            else:
                if any(r == float("inf") for r in upload_reductions):
                    new_upload_speed = float("inf")
                else:
                    new_upload_speed = max(cfg.min_upload, cfg.max_upload - sum(upload_reductions))

            # Download is always reduction-based; stream-based mode does not affect it.
            if any(r == float("inf") for r in download_reductions):
                new_download_speed = float("inf")
            else:
                new_download_speed = max(
                    cfg.min_download, cfg.max_download - sum(download_reductions)
                )

            logger.info(f"New calculated upload speed: {format_speed(new_upload_speed, cfg.units)}")
            logger.info(
                f"New calculated download speed: {format_speed(new_download_speed, cfg.units)}"
            )

            logger.info("Getting active torrent counts")

            client_active_torrent_dict = {
                client: client.get_active_torrent_count() for client in clients
            }

            sum_active_torrents = sum(client_active_torrent_dict.values())

            for torrent_client, active_torrent_count in client_active_torrent_dict.items():
                # Unlimited speed is shared whole, so skip the splitting
                if new_upload_speed == float("inf"):
                    effective_upload_speed = float("inf")
                elif cfg.manual_speed_algorithm_share:
                    effective_upload_speed = (
                        torrent_client._client_config.download_shares
                        / sum_client_upload_shares
                        * new_upload_speed
                    )
                else:
                    effective_upload_speed = (
                        (active_torrent_count / sum_active_torrents * new_upload_speed)
                        if active_torrent_count > 0
                        else new_upload_speed
                    )

                if new_download_speed == float("inf"):
                    effective_download_speed = float("inf")
                elif cfg.manual_speed_algorithm_share:
                    effective_download_speed = (
                        torrent_client._client_config.upload_shares
                        / sum_client_download_shares
                        * new_download_speed
                    )
                else:
                    effective_download_speed = (
                        (active_torrent_count / sum_active_torrents * new_download_speed)
                        if active_torrent_count > 0
                        else new_download_speed
                    )

                try:
                    torrent_client.set_upload_speed(effective_upload_speed)
                    torrent_client.set_download_speed(effective_download_speed)

                except Exception:
                    logger.warning(
                        f"An error occurred while updating {torrent_client._client_config.url}, "
                        "skipping:\n" + traceback.format_exc()
                    )

                else:
                    logger.info(
                        f"Set upload speed for {torrent_client._client_config.url} to "
                        f"{format_speed(effective_upload_speed, cfg.units)}"
                    )
                    logger.info(
                        f"Set download speed for {torrent_client._client_config.url} to "
                        f"{format_speed(effective_download_speed, cfg.units)}"
                    )

            logger.info("Speeds updated")

        except Exception:
            logger.error("An error occurred while updating clients:\n" + traceback.format_exc())

        logger.info("Waiting for next update event")
