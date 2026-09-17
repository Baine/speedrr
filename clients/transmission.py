import urllib.parse

import transmission_rpc
from transmission_rpc.error import (
    TransmissionAuthError,
    TransmissionConnectError,
    TransmissionTimeoutError,
)

from helpers.bit_convert import bit_conv
from helpers.config import ClientConfig, SpeedrrConfig
from helpers.log_loader import logger


class TransmissionClient:
    def __init__(self, config: SpeedrrConfig, config_client: ClientConfig) -> None:
        self._client_config = config_client
        self._config = config

        # Gets hostname, port, and path from url and checks if values are sensible
        u = urllib.parse.urlparse(config_client.url)

        protocol = u.scheme
        if protocol == "http":
            default_port = 80
        elif protocol == "https":
            default_port = 443
        else:
            raise ValueError(f"<trans|{self._client_config.url}> Unknown url scheme {u.scheme}")

        if u.hostname is None:
            raise ValueError(f"<trans|{self._client_config.url}> Missing hostname")

        logger.debug(
            f"<trans|{self._client_config.url}> Connecting to Transmission at {config_client.url}"
        )

        try:
            self._client = transmission_rpc.Client(
                protocol=protocol,
                username=config_client.username,
                password=config_client.password,
                host=u.hostname,
                port=u.port or default_port,
                path=u.path or "/transmission/rpc",
            )

        except TransmissionTimeoutError as exc:
            raise Exception(
                f"<trans|{self._client_config.url}> Connection to Transmission timed out"
            ) from exc

        except TransmissionAuthError as exc:
            raise Exception(
                f"<trans|{self._client_config.url}> Failed to login to Transmission, "
                "check your credentials"
            ) from exc

        except TransmissionConnectError as exc:
            raise Exception(
                f"<trans|{self._client_config.url}> Failed to connect to Transmission, "
                "check your url"
            ) from exc

        logger.debug(f"<trans|{self._client_config.url}> Connected to Transmission")

    def get_active_torrent_count(self) -> int:
        "Get the number of torrents that are currently downloading or uploading."

        logger.debug(f"<trans|{self._client_config.url}> Getting active torrent count")

        sessionStats = self._client.session_stats()
        return sessionStats.active_torrent_count

    def set_upload_speed(self, speed: int | float) -> None:
        "Set the upload speed limit for the client, in config units."

        if speed == float("inf"):
            logger.debug(f"<trans|{self._client_config.url}> Setting upload speed to unlimited")
            self._client.set_session(speed_limit_up_enabled=False)
            return

        logger.debug(
            f"<trans|{self._client_config.url}> Setting upload speed to {speed}{self._config.units}"
        )

        speed_limit_up = max(1, int(bit_conv(speed, self._config.units, "KB")))
        self._client.set_session(speed_limit_up_enabled=True, speed_limit_up=speed_limit_up)

    def set_download_speed(self, speed: int | float) -> None:
        "Set the download speed limit for the client, in config units."

        if speed == float("inf"):
            logger.debug(f"<trans|{self._client_config.url}> Setting download speed to unlimited")
            self._client.set_session(speed_limit_down_enabled=False)
            return

        logger.debug(
            f"<trans|{self._client_config.url}> Setting dowload speed to "
            f"{speed}{self._config.units}"
        )

        speed_limit_down = max(1, int(bit_conv(speed, self._config.units, "KB")))
        self._client.set_session(speed_limit_down_enabled=True, speed_limit_down=speed_limit_down)
