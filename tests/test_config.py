import pytest
from dataclass_wizard.errors import ParseError

from helpers.config import SpeedrrConfig

VALID_YAML = """
logs_path: ./logs/
units: Mbit
min_upload: 8
max_upload: 500
min_download: 8
max_download: 400
clients:
  - type: qbittorrent
    url: http://qbittorrent:8080
    username: admin
    password: ""
    https_verify: false
modules:
  media_servers:
    - type: plex
      url: http://plex:32400
      token: abc
      https_verify: false
      bandwidth_multiplier: 1.0
      update_interval: 5
      ignore_streams:
        local: true
        ip_networks: null
        paused_after: 300
  schedule:
    - start: "08:00"
      end: "02:00"
      days: ["all"]
      upload: 100
      download: 100
"""


def write(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return str(path)


def test_loads_a_valid_config(tmp_path):
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, VALID_YAML))

    assert config.units == "Mbit"
    assert config.max_upload == 500
    assert len(config.clients) == 1
    assert config.clients[0].type == "qbittorrent"
    assert config.modules.media_servers is not None
    assert config.modules.schedule is not None


def test_schedule_can_be_disabled(tmp_path):
    disabled = VALID_YAML.replace(
        """  schedule:
    - start: "08:00"
      end: "02:00"
      days: ["all"]
      upload: 100
      download: 100
""",
        "  schedule: null\n",
    )
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, disabled))

    assert config.modules.media_servers is not None
    assert config.modules.schedule is None


def test_ignore_streams_ip_networks_is_optional(tmp_path):
    no_networks = VALID_YAML.replace(
        "      ignore_streams:\n        local: true\n        ip_networks: null\n",
        "      ignore_streams:\n        local: true\n",
    )
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, no_networks))

    assert config.modules.media_servers[0].ignore_streams.ip_networks is None


def test_client_share_defaults_are_one(tmp_path):
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, VALID_YAML))

    assert config.clients[0].upload_shares == 1
    assert config.clients[0].download_shares == 1


def test_manual_share_algorithm_defaults_to_false(tmp_path):
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, VALID_YAML))

    assert config.manual_speed_algorithm_share is False


def test_rejects_an_unknown_units_value(tmp_path):
    bad = VALID_YAML.replace("units: Mbit", "units: furlongs")

    with pytest.raises(ParseError):
        SpeedrrConfig.from_yaml_file(write(tmp_path, bad))


def test_rejects_an_unknown_client_type(tmp_path):
    bad = VALID_YAML.replace("type: qbittorrent", "type: rtorrent")

    with pytest.raises(ParseError):
        SpeedrrConfig.from_yaml_file(write(tmp_path, bad))


def test_rejects_an_unknown_media_server_type(tmp_path):
    bad = VALID_YAML.replace("type: plex", "type: kodi")

    with pytest.raises(ParseError):
        SpeedrrConfig.from_yaml_file(write(tmp_path, bad))


STREAM_BASED_YAML = VALID_YAML.replace(
    """      ignore_streams:
        local: true
        ip_networks: null
        paused_after: 300
""",
    """      ignore_streams:
        local: true
        ip_networks: null
        paused_after: 300
      stream_based_speeds:
        enabled: true
        speeds:
          0: unlimited
          1: 10
          2: "50%"
        default: 5
""",
)


def test_stream_based_speeds_parse(tmp_path):
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, STREAM_BASED_YAML))

    speeds_config = config.modules.media_servers[0].stream_based_speeds
    assert speeds_config is not None
    assert speeds_config.enabled is True
    # YAML integer keys arrive as ints (dataclass-wizard coerces dict keys per
    # the dict[int, ...] annotation), so counts match with plain int lookups.
    assert speeds_config.speeds == {0: "unlimited", 1: 10, 2: "50%"}
    assert all(isinstance(key, int) for key in speeds_config.speeds)
    assert speeds_config.default == 5


def test_stream_based_speeds_default_is_optional(tmp_path):
    without_default = STREAM_BASED_YAML.replace("        default: 5\n", "")
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, without_default))

    speeds_config = config.modules.media_servers[0].stream_based_speeds
    assert speeds_config is not None
    assert speeds_config.default is None


def test_stream_based_speeds_is_optional_on_servers(tmp_path):
    config = SpeedrrConfig.from_yaml_file(write(tmp_path, VALID_YAML))

    assert config.modules.media_servers[0].stream_based_speeds is None
