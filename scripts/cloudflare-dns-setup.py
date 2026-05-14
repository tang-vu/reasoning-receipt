"""One-shot Cloudflare DNS setup for rrtrace.xyz.

Adds the 4 GitHub Pages A records on the apex (DNS-only / grey cloud) and
the 2 tunnel CNAMEs for api + events (proxied / orange cloud).

Idempotent: skips records that already exist with the right value.

Requires `CLOUDFLARE_API_TOKEN` in .env with Zone DNS Edit permission on
rrtrace.xyz. Create one at:
  https://dash.cloudflare.com/profile/api-tokens
  -> Template "Edit zone DNS" -> Zone resources: include rrtrace.xyz
  -> Create -> copy.

Usage:
  uv run python -m scripts.cloudflare-dns-setup

Tunnel UUID is read from `~/.cloudflared/config.yml` or
`CLOUDFLARE_TUNNEL_UUID` in .env (fallback). Override with --tunnel-uuid.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

ZONE_NAME = "rrtrace.xyz"
APEX_IPS = (
    "185.199.108.153",
    "185.199.109.153",
    "185.199.110.153",
    "185.199.111.153",
)
WWW_CNAME_TARGET = "tang-vu.github.io"


def _tunnel_uuid_from_config() -> str | None:
    cfg = Path.home() / ".cloudflared" / "config.yml"
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        return data.get("tunnel") if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


class CfDns:
    def __init__(self, token: str) -> None:
        self.client = httpx.Client(
            base_url="https://api.cloudflare.com/client/v4",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )

    def zone_id(self, name: str) -> str:
        r = self.client.get("/zones", params={"name": name})
        r.raise_for_status()
        result = r.json()["result"]
        if not result:
            raise SystemExit(f"zone {name!r} not found — token may not have access")
        return result[0]["id"]

    def list_records(self, zone_id: str, name: str | None = None) -> list[dict]:
        params = {"per_page": 200}
        if name is not None:
            params["name"] = name
        r = self.client.get(f"/zones/{zone_id}/dns_records", params=params)
        r.raise_for_status()
        return r.json()["result"]

    def create_record(
        self,
        zone_id: str,
        *,
        type_: str,
        name: str,
        content: str,
        proxied: bool,
        comment: str,
    ) -> dict:
        payload = {
            "type": type_,
            "name": name,
            "content": content,
            "ttl": 1,  # auto
            "proxied": proxied,
            "comment": comment,
        }
        r = self.client.post(f"/zones/{zone_id}/dns_records", json=payload)
        if r.status_code >= 400:
            raise SystemExit(f"create {type_} {name} -> {content}: {r.status_code} {r.text}")
        return r.json()["result"]

    def delete_record(self, zone_id: str, record_id: str) -> None:
        r = self.client.delete(f"/zones/{zone_id}/dns_records/{record_id}")
        r.raise_for_status()


def _ensure_apex_a_records(cf: CfDns, zone_id: str, log: logging.Logger) -> None:
    """4 A records on the apex, DNS-only (grey cloud)."""
    existing = cf.list_records(zone_id, name=ZONE_NAME)
    existing_by_ip = {r["content"]: r for r in existing if r["type"] == "A"}
    for ip in APEX_IPS:
        if ip in existing_by_ip:
            log.info("[apex A] already exists: %s -> %s", ZONE_NAME, ip)
            continue
        cf.create_record(
            zone_id,
            type_="A",
            name=ZONE_NAME,
            content=ip,
            proxied=False,  # MUST be DNS-only for GH Pages cert provisioning
            comment="GH Pages — rrtrace v0.3",
        )
        log.info("[apex A] created: %s -> %s (grey)", ZONE_NAME, ip)


def _ensure_www_cname(cf: CfDns, zone_id: str, log: logging.Logger) -> None:
    name = f"www.{ZONE_NAME}"
    existing = cf.list_records(zone_id, name=name)
    if any(r["type"] == "CNAME" and r["content"].rstrip(".") == WWW_CNAME_TARGET for r in existing):
        log.info("[www CNAME] already correct")
        return
    cf.create_record(
        zone_id,
        type_="CNAME",
        name=name,
        content=WWW_CNAME_TARGET,
        proxied=False,
        comment="GH Pages — rrtrace v0.3",
    )
    log.info("[www CNAME] created: %s -> %s (grey)", name, WWW_CNAME_TARGET)


def _ensure_tunnel_cnames(
    cf: CfDns, zone_id: str, tunnel_uuid: str, log: logging.Logger
) -> None:
    """api + events both CNAME to <UUID>.cfargotunnel.com, proxied orange."""
    target = f"{tunnel_uuid}.cfargotunnel.com"
    for subdomain in ("api", "events"):
        name = f"{subdomain}.{ZONE_NAME}"
        existing = cf.list_records(zone_id, name=name)
        match = next(
            (
                r
                for r in existing
                if r["type"] == "CNAME" and r["content"].rstrip(".") == target
            ),
            None,
        )
        if match and match.get("proxied"):
            log.info("[%s CNAME] already correct", subdomain)
            continue
        if match:
            cf.delete_record(zone_id, match["id"])
            log.info("[%s CNAME] removing un-proxied stale record", subdomain)
        cf.create_record(
            zone_id,
            type_="CNAME",
            name=name,
            content=target,
            proxied=True,  # MUST be proxied for CF Tunnel to terminate TLS
            comment="CF Tunnel — rrtrace v0.3",
        )
        log.info("[%s CNAME] created: %s -> %s (orange)", subdomain, name, target)


def _maybe_cleanup_astromystic_pollution(cf: CfDns, log: logging.Logger) -> None:
    """`cloudflared tunnel route dns` earlier inadvertently created CNAMEs in the
    astromystic.app zone for api/events.rrtrace.xyz. Best-effort delete."""
    try:
        astromystic_zone = cf.zone_id("astromystic.app")
    except SystemExit:
        log.info("[cleanup] astromystic.app zone not accessible from this token — skipping")
        return
    polluted_names = (f"api.{ZONE_NAME}.astromystic.app", f"events.{ZONE_NAME}.astromystic.app")
    for name in polluted_names:
        records = cf.list_records(astromystic_zone, name=name)
        for r in records:
            cf.delete_record(astromystic_zone, r["id"])
            log.info("[cleanup] removed stale %s in astromystic zone", name)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)-5s %(message)s")
    log = logging.getLogger("cf-dns")

    parser = argparse.ArgumentParser()
    parser.add_argument("--tunnel-uuid", default=None, help="override tunnel UUID")
    args = parser.parse_args()

    token = os.getenv("CLOUDFLARE_API_TOKEN")
    if not token:
        log.error("CLOUDFLARE_API_TOKEN missing from environment")
        log.error("Get one at https://dash.cloudflare.com/profile/api-tokens")
        sys.exit(1)

    tunnel_uuid = args.tunnel_uuid or os.getenv("CLOUDFLARE_TUNNEL_UUID") or _tunnel_uuid_from_config()
    if not tunnel_uuid:
        log.error("tunnel UUID not found — pass --tunnel-uuid or set in ~/.cloudflared/config.yml")
        sys.exit(1)

    cf = CfDns(token)
    zone_id = cf.zone_id(ZONE_NAME)
    log.info("zone %s id %s", ZONE_NAME, zone_id)

    _ensure_apex_a_records(cf, zone_id, log)
    _ensure_www_cname(cf, zone_id, log)
    _ensure_tunnel_cnames(cf, zone_id, tunnel_uuid, log)
    _maybe_cleanup_astromystic_pollution(cf, log)

    log.info("DONE. DNS propagation ~1-5 min via Cloudflare.")
    log.info("Test: nslookup rrtrace.xyz 1.1.1.1   (expect 4 A records)")
    log.info("Test: nslookup api.rrtrace.xyz 1.1.1.1 (expect CF-proxied CNAME)")


if __name__ == "__main__":
    main()
