from dataclasses import dataclass, field
from typing import Literal

from dataclass_wizard.mixins.yaml import YAMLWizard  # type: ignore


@dataclass(frozen=True)
class ClientConfig(YAMLWizard):
    type: Literal["qbittorrent", "deluge", "transmission"]
    url: str
    username: str
    password: str
    https_verify: bool
    download_shares: int = 1
    upload_shares: int = 1


@dataclass(frozen=True)
class IgnoreStreamConfig(YAMLWizard):
    local: bool
    ip_networks: tuple[str, ...] | None
    paused_after: int


@dataclass(frozen=True)
class StreamBasedSpeedsConfig(YAMLWizard):
    enabled: bool
    speeds: dict[int, int | float | str]
    default: int | float | str | None = None


@dataclass(frozen=True)
class MediaServerConfig(YAMLWizard):
    type: Literal["plex", "tautulli", "jellyfin", "emby", "silo"]
    url: str
    https_verify: bool
    bandwidth_multiplier: float
    update_interval: int
    ignore_streams: IgnoreStreamConfig
    token: str | None = None
    api_key: str | None = None
    stream_based_speeds: StreamBasedSpeedsConfig | None = None

    def __hash__(self) -> int:
        return super().__hash__()


@dataclass(frozen=True)
class ScheduleConfig(YAMLWizard):
    start: str
    end: str
    days: tuple[Literal["all", "mon", "tue", "wed", "thu", "fri", "sat", "sun"], ...]
    upload: int | str
    download: int | str


@dataclass(frozen=True)
class ModulesConfig(YAMLWizard):
    media_servers: list[MediaServerConfig] | None = None
    schedule: list[ScheduleConfig] | None = None


@dataclass(frozen=True)
class SpeedrrConfig(YAMLWizard):
    logs_path: str | None
    units: Literal[
        "bit",
        "B",
        "byte",
        "Kbit",
        "kilobit",
        "Kibit",
        "kibibit",
        "KB",
        "kilobyte",
        "KiB",
        "kibibyte",
        "Mbit",
        "megabit",
        "Mibit",
        "mebibit",
        "MB",
        "megabyte",
        "MiB",
        "mebibyte",
        "Gbit",
        "gigabit",
        "Gibit",
        "gibibit",
        "GB",
        "gigabyte",
        "GiB",
        "gibibyte",
    ]
    min_upload: int
    max_upload: int
    min_download: int
    max_download: int
    clients: list[ClientConfig]
    modules: ModulesConfig = field(default_factory=ModulesConfig)
    manual_speed_algorithm_share: bool | None = False


def load_config(config_file: str) -> SpeedrrConfig:
    config = SpeedrrConfig.from_yaml_file(config_file)
    if isinstance(config, list):
        raise ValueError("Config can't be a list")
    return config
