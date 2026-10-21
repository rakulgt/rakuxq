#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.b-trial-deploy
# Role: Server-only reversible installation of an explicitly approved 48-hour B trial.
# Inputs: Exact source revision and own candidate assets. Outputs: isolated units/routes/receipt.
# Provenance: Project-authored, AI-assisted. State: private experiment, never change A current/env.
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pipeline import validate_own_model

BASE = Path("/opt/raku/portable/rakuxq")
BACKUPS = Path("/opt/raku/backups/rakuxq")
AUDIT = Path("/opt/raku/logs/rakuxq/b-interactions")
SITE = Path("/etc/nginx/conf.d/xq-rakubank.conf")
ZONES = Path("/etc/nginx/conf.d/rakuxq-b-zones.conf")
ROUTES = Path("/etc/nginx/snippets/rakuxq-b-routes.conf")
UNIT_ROOT = Path("/etc/systemd/system")
UNITS = (
    "rakuxq-b.service",
    "rakuxq-b-expire.service",
    "rakuxq-b-expire.timer",
    "rakuxq-b-audit-retention.service",
    "rakuxq-b-audit-retention.timer",
)


def run(*command: str, check=True):
    return subprocess.run(command, check=check, capture_output=True, text=True, timeout=100)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def health(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=10) as response:
        return json.load(response)


def write(path: Path, content: str, mode=0o644):
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--engine-source", type=Path, required=True)
    parser.add_argument("--engine-sha256", required=True)
    parser.add_argument("--network-source", type=Path, required=True)
    parser.add_argument("--network-sha256", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        raise ValueError("Server root and exact revision required")
    root = BASE / "b-trials" / args.revision
    source = Path(__file__).resolve().parents[3]
    if source != root / "source" or root.resolve() != root:
        raise ValueError("Unexpected trial source directory")
    for candidate, expected in (
        (args.engine_source, args.engine_sha256),
        (args.network_source, args.network_sha256),
    ):
        if (
            not candidate.resolve().is_relative_to(BASE / "candidates")
            or digest(candidate) != expected
        ):
            raise ValueError("Unexpected candidate asset/fingerprint")
    net_meta = args.network_source.with_suffix(args.network_source.suffix + ".meta.json")
    validate_own_model(json.loads(net_meta.read_text()), args.network_sha256)
    if not health(8040).get("engine_ready"):
        raise RuntimeError("A must be healthy before installing B")
    api = (BASE / "current").resolve()
    env = Path("/opt/raku/secrets/rakuxq/api.env")
    a_env_digest = digest(env)
    existing = [ZONES, ROUTES, *(UNIT_ROOT / name for name in UNITS)]
    if any(path.exists() for path in existing):
        raise RuntimeError("Existing B configuration requires explicit review; not overwriting it")
    marker = "    include /etc/nginx/snippets/rakuxq-api-routes.conf;"
    original_site = SITE.read_text()
    if original_site.count(marker) != 1:
        raise RuntimeError("A site configuration differs from the expected insertion point")
    if f"# configuration file {SITE}:" not in run("nginx", "-T").stdout:
        raise RuntimeError("Expected project site is not part of active Nginx configuration")
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8041))
    started = datetime.now(UTC).replace(microsecond=0)
    expiry = started + timedelta(hours=48)
    backup = BACKUPS / f"{started:%Y%m%d-%H%M%S}-b48-{args.revision}"
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(SITE, backup / SITE.name)
    AUDIT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if AUDIT.resolve() != AUDIT:
        raise ValueError("Unexpected B audit directory")
    shutil.chown(AUDIT, user="rakuxq", group="rakuxq")
    AUDIT.chmod(0o700)
    engine, network = root / "rakuxq-engine", root / "bootstrap-a.rknn"
    for src, dest in (
        (args.engine_source, engine),
        (args.network_source, network),
        (net_meta, network.with_suffix(".rknn.meta.json")),
    ):
        if dest.exists():
            raise ValueError("Refusing to overwrite a trial asset")
        shutil.copy2(src, dest)
        dest.chmod(0o755 if dest == engine else 0o444)
    values = {
        "RAKUXQ_B_EXPIRES_AT": expiry.isoformat(),
        "RAKUXQ_REQUIRE_API_KEY": "true",
        "RAKUXQ_ENGINE_PATH": str(engine),
        "RAKUXQ_ENGINE_PATH_SHA256": args.engine_sha256,
        "RAKUXQ_ENGINE_NETWORK": str(network),
        "RAKUXQ_ENGINE_NETWORK_SHA256": args.network_sha256,
        "RAKUXQ_ENGINE_VERSION": "0.1.0-experimental/bootstrap-a/private-b48",
        "RAKUXQ_ENGINE_THREADS": "1",
        "RAKUXQ_ENGINE_HASH_MB": "16",
        "RAKUXQ_ORT_INTRA_OP_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "RAKUXQ_PUBLIC_METRICS_DB": "",
        "RAKUXQ_GEOIP_CITY_DB": "",
        "RAKUXQ_AUDIT_DIR": str(AUDIT),
        "RAKUXQ_AUDIT_MAX_TOTAL_BYTES": str(256 * 1024 * 1024),
        "RAKUXQ_AUDIT_RETENTION_HOURS": "12",
        "RAKUXQ_LEGAL_CONSENTS_DB": "/opt/raku/logs/rakuxq/legal/acceptances.sqlite3",
    }
    write(root / "trial.env", "".join(f'{k}="{v}"\n' for k, v in values.items()))
    python = api / ".venv/bin/python"
    tools = source / "packages/rakuxq-engine/tools"
    command = (
        f"{python} -m uvicorn serve_b:create_app --factory --app-dir {tools} "
        "--host 127.0.0.1 --port 8041 --workers 1 --limit-concurrency 4 --no-access-log"
    )
    units = {
        "rakuxq-b.service": f"""[Unit]
Description=RakuXQ private B experiment (fixed 48-hour deadline)
After=network-online.target
[Service]
User=rakuxq
Group=rakuxq
WorkingDirectory={root}
EnvironmentFile={env}
EnvironmentFile={root}/trial.env
ExecStart={command}
Restart=no
RuntimeMaxSec=172800
TimeoutStopSec=15
Nice=10
CPUQuota=100%
CPUWeight=10
MemoryHigh=512M
MemoryMax=640M
TasksMax=64
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/raku/secrets/rakuxq {AUDIT} /opt/raku/logs/rakuxq/legal
[Install]
WantedBy=multi-user.target
""",
        "rakuxq-b-expire.service": """[Unit]
Description=Stop only the expired RakuXQ B experiment
[Service]
Type=oneshot
ExecStart=/usr/bin/systemctl disable --now rakuxq-b.service
""",
        "rakuxq-b-expire.timer": f"""[Unit]
Description=Absolute RakuXQ B expiry (never extended by restart)
[Timer]
OnCalendar={expiry:%Y-%m-%d %H:%M:%S} UTC
Persistent=true
AccuracySec=1s
Unit=rakuxq-b-expire.service
[Install]
WantedBy=timers.target
""",
        "rakuxq-b-audit-retention.service": f"""[Unit]
Description=Prune only B test originals older than 12 hours
[Service]
Type=oneshot
User=rakuxq
Group=rakuxq
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart={python} {tools}/serve_b.py --prune-audit
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths={AUDIT}
""",
        "rakuxq-b-audit-retention.timer": """[Unit]
Description=Keep B audit retention independent of the 48-hour server lifetime
[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=5s
[Install]
WantedBy=timers.target
""",
    }
    try:
        for name, text in units.items():
            write(UNIT_ROOT / name, text)
        write(
            ZONES,
            """limit_req_zone $binary_remote_addr zone=rakuxq_b_trial:1m rate=15r/m;
limit_conn_zone $binary_remote_addr zone=rakuxq_b_conn:1m;
""",
        )
        write(
            ROUTES,
            """location ^~ /b/ {
    limit_req zone=rakuxq_b_trial burst=3 nodelay;
    limit_req_status 429;
    limit_conn rakuxq_b_conn 2;
    proxy_pass http://127.0.0.1:8041/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_connect_timeout 3s;
    proxy_read_timeout 45s;
    proxy_send_timeout 45s;
    error_page 502 504 = @rakuxq_b_offline;
}
location @rakuxq_b_offline {
    default_type application/json;
    return 503 '{"detail":{"code":"B_TEST_OFFLINE","message":"B offline; A unchanged."}}';
}
""",
        )
        write(
            SITE,
            original_site.replace(
                marker, "    include /etc/nginx/snippets/rakuxq-b-routes.conf;\n" + marker
            ),
        )
        run("nginx", "-t")
        run("systemctl", "daemon-reload")
        run(
            "systemctl",
            "enable",
            "--now",
            "rakuxq-b.service",
            "rakuxq-b-expire.timer",
            "rakuxq-b-audit-retention.timer",
        )
        ready = False
        for _ in range(45):
            try:
                status = health(8041)
                if status.get("provider_ready") and status.get("engine_ready"):
                    if not status["engine"]["name"].startswith("RakuXQ "):
                        raise ValueError("B must never run the A engine")
                    if status["engine"]["network_sha256"] != args.network_sha256:
                        raise ValueError("B network identity differs")
                    ready = True
                    break
            except OSError:
                pass
            time.sleep(1)
        if not ready:
            raise RuntimeError("B did not become ready; rolling back only B")
        run("systemctl", "reload", "nginx")
        if (BASE / "current").resolve() != api or digest(env) != a_env_digest:
            raise RuntimeError("A identity/environment unexpectedly changed")
        if not health(8040).get("engine_ready"):
            raise RuntimeError("A health check failed")
        receipt = {
            "plan": "B-experimental",
            "source_revision": args.revision,
            "started_at": started.isoformat(),
            "expires_at": expiry.isoformat(),
            "backup": str(backup),
            "api_release": api.name,
            "engine_sha256": args.engine_sha256,
            "network_sha256": args.network_sha256,
            "vision": "same models as A",
            "public_metrics": False,
            "default_production_promoted": False,
            "audit_retention_hours": 12,
        }
        write(root / "trial.json", json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt))
    except Exception:
        run(
            "systemctl",
            "disable",
            "--now",
            "rakuxq-b.service",
            "rakuxq-b-expire.timer",
            "rakuxq-b-audit-retention.timer",
            check=False,
        )
        shutil.copy2(backup / SITE.name, SITE)
        for path in existing:
            if path.exists():
                path.unlink()
        run("systemctl", "daemon-reload", check=False)
        run("nginx", "-t")
        run("systemctl", "reload", "nginx")
        raise


if __name__ == "__main__":
    main()
