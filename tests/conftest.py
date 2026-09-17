import threading
from types import SimpleNamespace

import pytest

from helpers.config import (
    ClientConfig,
    IgnoreStreamConfig,
    MediaServerConfig,
    ModulesConfig,
    SpeedrrConfig,
)


@pytest.fixture
def speedrr_config() -> SpeedrrConfig:
    return SpeedrrConfig(
        logs_path="./logs/",
        units="Mbit",
        min_upload=8,
        max_upload=500,
        min_download=8,
        max_download=400,
        clients=[],
        modules=ModulesConfig(media_servers=None, schedule=None),
    )


@pytest.fixture
def qbit_client_config() -> ClientConfig:
    return ClientConfig(
        type="qbittorrent",
        url="http://qbittorrent:8080",
        username="admin",
        password="",
        https_verify=False,
    )


@pytest.fixture
def plex_server_config() -> MediaServerConfig:
    return MediaServerConfig(
        type="plex",
        url="http://plex:32400",
        https_verify=False,
        bandwidth_multiplier=1.0,
        update_interval=5,
        ignore_streams=IgnoreStreamConfig(
            local=True,
            ip_networks=None,
            paused_after=300,
        ),
        token="token123",
    )


@pytest.fixture
def make_media_server_module():
    """Build a stand-in for MediaServerModule.

    BaseServer.__init__ only touches `reduction_value_dict` and
    `_update_event` on its module, so a SimpleNamespace is enough and avoids
    MediaServerModule's constructor, which performs a live HTTP call.
    """

    def _make(config):
        return SimpleNamespace(
            _config=config,
            reduction_value_dict={},
            stream_count_dict={},
            _update_event=threading.Event(),
        )

    return _make
