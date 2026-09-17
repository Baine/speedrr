"""Verify this build against a live qBittorrent server.

A clean `podman build` proves nothing about the bug this fork exists for: speedrr
fails at login, not at import. Run this against the real server before deploying.

On tower, from the mux network:

    docker run --rm --network mux \
      -v /mnt/user/appdata/speedrr:/data \
      -v $PWD/scripts/verify_qbt.py:/tmp/verify_qbt.py:ro \
      ghcr.io/Baine/speedrr:vX.Y.Z python /tmp/verify_qbt.py

Writes a temporary upload limit and restores the original before exiting.
"""

import os
import sys
from importlib.metadata import version

sys.path.insert(0, "/home")
os.chdir("/home")

from clients.qbittorrent import qBittorrentClient
from helpers.config import SpeedrrConfig

CONFIG = os.environ.get("SPEEDRR_CONFIG", "/data/config.yaml")

cfg = SpeedrrConfig.from_yaml_file(CONFIG)
qcfgs = [c for c in cfg.clients if c.type == "qbittorrent"]
if not qcfgs:
    sys.exit(f"no qbittorrent client configured in {CONFIG}")

print(f"[1] qbittorrent clients in config: {len(qcfgs)}")
ccfg = qcfgs[0]
print(f"[2] url={ccfg.url} username={ccfg.username!r} password_set={bool(ccfg.password)}")
print(f"[3] qbittorrent-api == {version('qbittorrent-api')}")

qb = qBittorrentClient(cfg, ccfg)  # performs auth_log_in()
print("[4] LOGIN OK")

print(f"[5] qBittorrent app={qb._client.app_version()} webapi={qb._client.app_web_api_version()}")
print(f"[6] active torrent count = {qb.get_active_torrent_count()}")

orig_up = qb._client.transfer_upload_limit()
orig_down = qb._client.transfer_download_limit()
print(f"[7] original limits: upload={orig_up} B/s download={orig_down} B/s")

try:
    qb.set_upload_speed(123)
    readback = qb._client.transfer_upload_limit()
    print(f"[8] after set_upload_speed(123 {cfg.units}): upload_limit={readback} B/s")
    assert readback > 0, "upload limit did not take effect"
    print("[9] WRITE PATH OK")

finally:
    qb._client.transfer_set_upload_limit(orig_up)
    qb._client.transfer_set_download_limit(orig_down)
    restored_up = qb._client.transfer_upload_limit()
    restored_down = qb._client.transfer_download_limit()
    print(f"[10] restored limits: upload={restored_up} download={restored_down}")
    assert restored_up == orig_up and restored_down == orig_down, "RESTORE FAILED"
    print("[11] RESTORE VERIFIED")

print("ALL CHECKS PASSED")
