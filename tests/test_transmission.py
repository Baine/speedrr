import pytest
import transmission_rpc

from clients.transmission import TransmissionClient
from helpers.config import ClientConfig


def client_config(url):
    return ClientConfig(
        type="transmission",
        url=url,
        username="user",
        password="pass",
        https_verify=False,
    )


class FakeTransClient:
    """Stand-in for transmission_rpc.Client, recording set_session calls."""

    def __init__(self, **kwargs):
        self.sessions = []

    def set_session(self, **kwargs):
        self.sessions.append(kwargs)


@pytest.fixture
def fake_trans(monkeypatch):
    created = {}

    def factory(**kwargs):
        client = FakeTransClient(**kwargs)
        created["client"] = client
        return client

    monkeypatch.setattr(transmission_rpc, "Client", factory)
    return created


def test_rejects_an_unknown_url_scheme(speedrr_config):
    with pytest.raises(ValueError, match="Unknown url scheme"):
        TransmissionClient(speedrr_config, client_config("ftp://host:9091"))


def test_rejects_a_url_with_no_hostname(speedrr_config):
    with pytest.raises(ValueError, match="Missing hostname"):
        TransmissionClient(speedrr_config, client_config("http://"))


def test_limited_speeds_keep_the_speed_limit_enabled(fake_trans, speedrr_config):
    client = TransmissionClient(speedrr_config, client_config("http://transmission:9091"))
    client.set_upload_speed(1)  # speedrr_config.units == "Mbit"
    client.set_download_speed(1)

    up, down = fake_trans["client"].sessions
    assert up == {"speed_limit_up_enabled": True, "speed_limit_up": 125}
    assert down == {"speed_limit_down_enabled": True, "speed_limit_down": 125}


def test_unlimited_disables_the_speed_limit(fake_trans, speedrr_config):
    client = TransmissionClient(speedrr_config, client_config("http://transmission:9091"))
    client.set_upload_speed(float("inf"))
    client.set_download_speed(float("inf"))

    assert fake_trans["client"].sessions == [
        {"speed_limit_up_enabled": False},
        {"speed_limit_down_enabled": False},
    ]
