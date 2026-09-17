import threading
import time

import httpx
import pytest

from helpers.config import IgnoreStreamConfig, MediaServerConfig, StreamBasedSpeedsConfig
from modules.media_server import MediaServerModule, PlexServer, SiloServer, TautulliServer


# 8.8.8.8 stands in for a remote stream. RFC 5737 documentation ranges
# (203.0.113.0/24 and friends) look like better placeholders but are wrong here:
# Python's ipaddress module classifies them as private, so process_session()
# would ignore them as local. No network traffic occurs -- the address is only
# ever parsed.
def plex_session(session_id="s1", bandwidth=5000, state="playing", address="8.8.8.8"):
    return {
        "title": "Some Movie",
        "Session": {"id": session_id, "bandwidth": bandwidth},
        "Player": {"state": state, "address": address},
    }


def plex_payload(*sessions):
    return {
        "MediaContainer": {
            "size": len(sessions),
            "Metadata": list(sessions),
        }
    }


@pytest.fixture
def plex(speedrr_config, plex_server_config, make_media_server_module):
    return PlexServer(speedrr_config, plex_server_config, make_media_server_module(speedrr_config))


def test_plex_returns_zero_when_no_sessions(httpx_mock, plex):
    httpx_mock.add_response(json={"MediaContainer": {"size": 0}})

    assert plex.get_bandwidth() == 0


def test_plex_sums_remote_session_bandwidth(httpx_mock, plex):
    httpx_mock.add_response(
        json=plex_payload(
            plex_session(session_id="a", bandwidth=4000),
            plex_session(session_id="b", bandwidth=1500),
        )
    )

    assert plex.get_bandwidth() == 5500


def test_plex_ignores_private_addresses_when_local_is_ignored(httpx_mock, plex):
    httpx_mock.add_response(
        json=plex_payload(
            plex_session(session_id="a", bandwidth=4000, address="192.168.1.50"),
            plex_session(session_id="b", bandwidth=1500, address="8.8.8.8"),
            plex_session(session_id="c", bandwidth=0, address="8.8.8.8"),
        )
    )

    assert plex.get_bandwidth() == 1500

    # Only non-ignored sessions with bandwidth count as active streams:
    # the local session and the zero-bandwidth session are excluded.
    assert plex._module.stream_count_dict[plex._server_config] == 1


def test_plex_treats_the_literal_lan_address_as_local(httpx_mock, plex):
    # Regression guard: Plex reports "lan" where an IP is expected, and
    # ipaddress.ip_address("lan") raises. The code special-cases it.
    httpx_mock.add_response(json=plex_payload(plex_session(bandwidth=9000, address="lan")))

    assert plex.get_bandwidth() == 0


def test_plex_raises_on_a_payload_without_a_mediacontainer(httpx_mock, plex):
    httpx_mock.add_response(json={"error": "bad token"})

    with pytest.raises(Exception, match="Error from Plex"):
        plex.get_bandwidth()


def test_plex_raises_for_http_errors(httpx_mock, plex):
    httpx_mock.add_response(status_code=401)

    with pytest.raises(httpx.HTTPStatusError):
        plex.get_bandwidth()


def test_ip_networks_extend_what_counts_as_local(
    httpx_mock, speedrr_config, make_media_server_module
):
    config = MediaServerConfig(
        type="plex",
        url="http://plex:32400",
        https_verify=False,
        bandwidth_multiplier=1.0,
        update_interval=5,
        ignore_streams=IgnoreStreamConfig(
            local=False,
            ip_networks=("203.0.113.0/24",),
            paused_after=300,
        ),
        token="token123",
    )
    server = PlexServer(speedrr_config, config, make_media_server_module(speedrr_config))
    httpx_mock.add_response(json=plex_payload(plex_session(bandwidth=7000, address="203.0.113.5")))

    assert server.get_bandwidth() == 0


def test_tautulli_sums_session_bandwidth(httpx_mock, speedrr_config, make_media_server_module):
    config = MediaServerConfig(
        type="tautulli",
        url="http://tautulli:8181",
        https_verify=False,
        bandwidth_multiplier=1.0,
        update_interval=5,
        ignore_streams=IgnoreStreamConfig(local=True, ip_networks=None, paused_after=300),
        api_key="key123",
    )
    server = TautulliServer(speedrr_config, config, make_media_server_module(speedrr_config))
    httpx_mock.add_response(
        json={
            "response": {
                "result": "success",
                "data": {
                    "sessions": [
                        {
                            "session_id": "a",
                            "bandwidth": 3000,
                            "state": "playing",
                            "ip_address": "8.8.8.8",
                            "full_title": "Show",
                        }
                    ]
                },
            }
        }
    )

    assert server.get_bandwidth() == 3000


def test_tautulli_raises_when_the_api_reports_failure(
    httpx_mock, speedrr_config, make_media_server_module
):
    config = MediaServerConfig(
        type="tautulli",
        url="http://tautulli:8181",
        https_verify=False,
        bandwidth_multiplier=1.0,
        update_interval=5,
        ignore_streams=IgnoreStreamConfig(local=True, ip_networks=None, paused_after=300),
        api_key="key123",
    )
    server = TautulliServer(speedrr_config, config, make_media_server_module(speedrr_config))
    httpx_mock.add_response(json={"response": {"result": "error", "message": "invalid apikey"}})

    with pytest.raises(Exception, match="Error from Tautulli"):
        server.get_bandwidth()


def silo_session(
    session_id="s1", bitrate: int | None = 5000, paused=False, address="8.8.8.8", title="Movie"
):
    return {
        "session_id": session_id,
        "stream_bitrate_kbps": bitrate,
        "is_paused": paused,
        "client_ip": address,
        "media_title": title,
    }


@pytest.fixture
def silo(speedrr_config, make_media_server_module):
    config = MediaServerConfig(
        type="silo",
        url="http://silo:8080",
        https_verify=False,
        bandwidth_multiplier=1.0,
        update_interval=5,
        ignore_streams=IgnoreStreamConfig(local=True, ip_networks=None, paused_after=300),
        api_key="sa_key123",
    )
    return SiloServer(speedrr_config, config, make_media_server_module(speedrr_config))


def test_silo_counts_playing_session_bitrate_as_bandwidth(httpx_mock, silo):
    httpx_mock.add_response(json=[silo_session(session_id="a", bitrate=4500)])

    assert silo.get_bandwidth() == 4500

    # stream_bitrate_kbps is already Kbit/s, so no bit_conv is applied,
    # and auth goes through the Bearer header.
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer sa_key123"
    assert request.url.path == "/api/v1/admin/sessions"


def test_silo_ignores_session_paused_for_too_long(httpx_mock, silo):
    # process_session semantics: a paused session is only dropped once it has
    # been paused for longer than paused_after, so pre-seed the pause time.
    silo._paused_since["a"] = int(time.time()) - 1000
    httpx_mock.add_response(json=[silo_session(session_id="a", bitrate=4500, paused=True)])

    assert silo.get_bandwidth() == 0
    assert silo._module.stream_count_dict[silo._server_config] == 0


def test_silo_null_bitrate_counts_as_zero(httpx_mock, silo):
    httpx_mock.add_response(
        json=[
            silo_session(session_id="a", bitrate=4000),
            silo_session(session_id="b", bitrate=None),
        ]
    )

    assert silo.get_bandwidth() == 4000
    assert silo._module.stream_count_dict[silo._server_config] == 1


def stream_plex_config(speeds, default=None):
    return MediaServerConfig(
        type="plex",
        url="http://plex:32400",
        https_verify=False,
        bandwidth_multiplier=1.0,
        update_interval=5,
        ignore_streams=IgnoreStreamConfig(local=True, ip_networks=None, paused_after=300),
        token="token123",
        stream_based_speeds=StreamBasedSpeedsConfig(enabled=True, speeds=speeds, default=default),
    )


def test_unreachable_server_at_startup_does_not_crash(
    httpx_mock, speedrr_config, plex_server_config
):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

    # Must construct without raising; the run loop retries every update_interval.
    module = MediaServerModule(speedrr_config, [plex_server_config], threading.Event())

    assert module.get_reduction_value() == (0, 0)


def make_module(httpx_mock, speedrr_config, server_config, sessions=None):
    """Build a real MediaServerModule.

    The constructor polls each server once, so a mocked response is needed.
    """
    httpx_mock.add_response(json=sessions or {"MediaContainer": {"size": 0}})
    return MediaServerModule(speedrr_config, [server_config], threading.Event())


def test_target_upload_speed_exact_match(httpx_mock, speedrr_config):
    config = stream_plex_config({1: 10, 2: 8})
    module = make_module(httpx_mock, speedrr_config, config)
    module.stream_count_dict[config] = 2

    assert module.get_target_upload_speed() == 8


def test_target_upload_speed_falls_back_to_highest_defined_count(httpx_mock, speedrr_config):
    config = stream_plex_config({0: "unlimited", 1: 10, 3: 6})
    module = make_module(httpx_mock, speedrr_config, config)
    module.stream_count_dict[config] = 5

    assert module.get_target_upload_speed() == 6


def test_target_upload_speed_uses_default_below_defined_counts(httpx_mock, speedrr_config):
    config = stream_plex_config({2: 8}, default=5)
    module = make_module(httpx_mock, speedrr_config, config)
    module.stream_count_dict[config] = 1

    assert module.get_target_upload_speed() == 5


def test_target_upload_speed_falls_back_to_max_upload(httpx_mock, speedrr_config):
    config = stream_plex_config({2: 8})
    module = make_module(httpx_mock, speedrr_config, config)
    module.stream_count_dict[config] = 1

    # speedrr_config has max_upload=500
    assert module.get_target_upload_speed() == 500


def test_reduction_value_is_a_minus_inf_marker_in_stream_mode(httpx_mock, speedrr_config):
    config = stream_plex_config({0: "unlimited", 1: 10})
    module = make_module(httpx_mock, speedrr_config, config)

    assert module.get_reduction_value() == (float("-inf"), 0)


def test_reduction_value_sums_bandwidths_without_stream_mode(
    httpx_mock, speedrr_config, plex_server_config
):
    module = make_module(
        httpx_mock,
        speedrr_config,
        plex_server_config,
        sessions=plex_payload(
            plex_session(session_id="a", bandwidth=4000),
            plex_session(session_id="b", bandwidth=1500),
        ),
    )

    # The constructor only polls get_bandwidth; the reduction is set by the
    # server thread's loop, which this test bypasses via set_reduction.
    module.servers[0].set_reduction(5500)

    # 5500 Kbit converted to the config's Mbit units
    assert module.get_reduction_value() == pytest.approx((5.5, 0))
