from importlib.metadata import version

import pytest
import qbittorrentapi
import requests

from clients.qbittorrent import qBittorrentClient


class FakeQbitClient:
    """Stand-in for qbittorrentapi.Client.

    qbittorrent-api talks over `requests`, not httpx, so pytest-httpx cannot
    intercept it. Substituting the client class is the cheapest honest seam.
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.upload_limits = []
        self.download_limits = []
        self.login_error = None
        self.torrents = []
        self.torrents_info_calls = []

    def auth_log_in(self):
        if self.login_error is not None:
            raise self.login_error

    def torrents_info(self, status_filter=None):
        self.torrents_info_calls.append(status_filter)
        if status_filter == "downloading":
            return [t for t in self.torrents if t.state_enum.is_downloading]
        if status_filter == "seeding":
            return [t for t in self.torrents if t.state_enum.is_uploading]
        return self.torrents

    def transfer_set_upload_limit(self, limit):
        self.upload_limits.append(limit)

    def transfer_set_download_limit(self, limit):
        self.download_limits.append(limit)


class FakeTorrent:
    def __init__(self, downloading=False, uploading=False):
        self.state_enum = type(
            "State", (), {"is_downloading": downloading, "is_uploading": uploading}
        )()


@pytest.fixture
def fake_qbit(monkeypatch):
    created = {}

    def factory(**kwargs):
        client = FakeQbitClient(**kwargs)
        created["client"] = client
        return client

    monkeypatch.setattr(qbittorrentapi, "Client", factory)
    return created


def test_installed_qbittorrent_api_is_new_enough_for_the_204_login():
    """A version-floor check -- NOT proof the 204 fix actually works.

    This asserts the *presence* of the fix in the installed package, not its
    *correctness*: it only parses the installed qbittorrent-api version and
    compares it to the 2025.11.0 floor below which qBittorrent 5.2+'s empty
    204 login body gets misread as a failed login (qbittorrent-api compared
    the body to "Ok." and raised LoginFailed on a login that had actually
    succeeded). It cannot see whether that comparison logic is actually
    correct -- qbittorrent-api talks over `requests`, not httpx, so this test
    file can't intercept the request the way pytest-httpx does elsewhere in
    this suite.

    Its distinct value: a static bound in pyproject.toml can't catch a build
    where the *installed* package has drifted below the pin -- which is
    exactly how the original incident happened (a July 2025 image still
    carrying qbittorrent-api 2025.7.0). This is a runtime tripwire for that.

    For a test that actually drives the fixed login path against a synthetic
    204 response, see test_real_login_accepts_the_actual_empty_204_body
    below.
    """
    installed = version("qbittorrent-api")
    major, minor = (int(part) for part in installed.split(".")[:2])

    assert (major, minor) >= (2025, 11), (
        f"qbittorrent-api {installed} rejects successful qBittorrent 5.2+ "
        "logins; the floor is 2025.11.0"
    )


def test_login_failure_message_points_at_the_version_not_the_credentials(
    speedrr_config, qbit_client_config, monkeypatch
):
    def failing_factory(**kwargs):
        client = FakeQbitClient(**kwargs)
        client.login_error = qbittorrentapi.LoginFailed()
        return client

    monkeypatch.setattr(qbittorrentapi, "Client", failing_factory)

    with pytest.raises(Exception) as excinfo:
        qBittorrentClient(speedrr_config, qbit_client_config)

    message = str(excinfo.value)
    assert "2025.11.0" in message
    assert "204" in message


def test_forbidden_login_reports_a_temporary_ban(speedrr_config, qbit_client_config, monkeypatch):
    def banned_factory(**kwargs):
        client = FakeQbitClient(**kwargs)
        client.login_error = qbittorrentapi.Forbidden403Error()
        return client

    monkeypatch.setattr(qbittorrentapi, "Client", banned_factory)

    with pytest.raises(Exception, match="temporarily banned"):
        qBittorrentClient(speedrr_config, qbit_client_config)


def test_active_torrent_count_ignores_idle_torrents(fake_qbit, speedrr_config, qbit_client_config):
    client = qBittorrentClient(speedrr_config, qbit_client_config)
    fake_qbit["client"].torrents = [
        FakeTorrent(downloading=True),
        FakeTorrent(uploading=True),
        FakeTorrent(),
    ]

    assert client.get_active_torrent_count() == 2
    # The count must use server-side filters, not a full library dump.
    assert fake_qbit["client"].torrents_info_calls == ["downloading", "seeding"]


def test_set_upload_speed_converts_config_units_to_bytes(
    fake_qbit, speedrr_config, qbit_client_config
):
    client = qBittorrentClient(speedrr_config, qbit_client_config)
    client.set_upload_speed(1)  # speedrr_config.units == "Mbit"

    assert fake_qbit["client"].upload_limits == [125000]


def test_set_download_speed_converts_config_units_to_bytes(
    fake_qbit, speedrr_config, qbit_client_config
):
    client = qBittorrentClient(speedrr_config, qbit_client_config)
    client.set_download_speed(400)

    assert fake_qbit["client"].download_limits == [50000000]


def test_speeds_floor_at_one_byte_per_second(fake_qbit, speedrr_config, qbit_client_config):
    # bit_conv underflows to 0.0 for tiny values, and qBittorrent treats 0
    # as unlimited -- the exact opposite of the intent.
    client = qBittorrentClient(speedrr_config, qbit_client_config)
    client.set_upload_speed(0)

    assert fake_qbit["client"].upload_limits == [1]


def test_unlimited_sets_a_zero_limit(fake_qbit, speedrr_config, qbit_client_config):
    # qBittorrent reads limit 0 as "no limit", which is exactly the intent here.
    client = qBittorrentClient(speedrr_config, qbit_client_config)
    client.set_upload_speed(float("inf"))
    client.set_download_speed(float("inf"))

    assert fake_qbit["client"].upload_limits == [0]
    assert fake_qbit["client"].download_limits == [0]


def _canned_response(status_code, request=None):
    """Build a real `requests.models.Response`, not a mock.

    Stands in for qBittorrent's WebAPI reply so qbittorrent-api's actual
    HTTP-body comparison logic runs against it, unmodified.
    """
    response = requests.models.Response()
    response.status_code = status_code
    response._content = b""
    response.request = request
    response.headers["Set-Cookie"] = "SID=deadbeef; HttpOnly; Path=/"
    return response


def test_real_login_accepts_the_actual_empty_204_body(
    speedrr_config, qbit_client_config, monkeypatch
):
    """The behavioral companion the version-floor check above can't be.

    Drives the *real* qbittorrentapi.Client.auth_log_in() login path -- not
    the FakeQbitClient stand-in used elsewhere in this file -- against a
    synthetic 204 response with an empty body, exactly what qBittorrent
    5.2+ answers on a successful login. Patches requests.Session.send, the
    seam Session.request() ultimately calls, so qbittorrent-api's real
    success/failure comparison (`auth_response.text == "" or "Ok."`) is
    what's under test, not a fake standing in for it.
    """
    calls = []

    def fake_send(self, request, **kwargs):
        calls.append(request)
        return _canned_response(204, request)

    monkeypatch.setattr(requests.Session, "send", fake_send)

    qBittorrentClient(speedrr_config, qbit_client_config)  # must not raise

    assert calls, "expected the login POST to reach requests.Session.send"


def test_real_login_still_raises_temporary_ban_for_403(
    speedrr_config, qbit_client_config, monkeypatch
):
    """Proves the 204 test above is discriminating, not just permissive.

    Same real login path as test_real_login_accepts_the_actual_empty_204_body,
    but a 403 response must still raise the "temporarily banned" error. If
    this test failed, the 204 test could be passing by swallowing every
    response rather than actually exercising qbittorrent-api's real
    success/failure logic.
    """

    def fake_send(self, request, **kwargs):
        return _canned_response(403, request)

    monkeypatch.setattr(requests.Session, "send", fake_send)

    with pytest.raises(Exception, match="temporarily banned"):
        qBittorrentClient(speedrr_config, qbit_client_config)
