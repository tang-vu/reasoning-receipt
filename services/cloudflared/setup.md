# Cloudflare Tunnel setup — expose the local backend as `api.rrtrace.xyz`

Harvey's PC runs the FastAPI server + agent daemon for the hackathon's two weeks. The dashboard at `rrtrace.xyz` (static, GitHub Pages) talks to the backend through a Cloudflare-terminated TLS tunnel that points at `localhost:8000` here — no public IP, no port-forward, no inbound firewall hole.

Total setup: ~10 min, one-time.

## 1. Install `cloudflared`

Windows (PowerShell, admin):

```powershell
winget install --id Cloudflare.cloudflared
# OR direct download: https://github.com/cloudflare/cloudflared/releases/latest
```

Confirm: `cloudflared --version` returns a version string.

## 2. Authenticate to Cloudflare

```powershell
cloudflared tunnel login
```

Browser opens → sign in → pick `rrtrace.xyz` as the authorised zone → click "Authorize". A cert lands at `%USERPROFILE%\.cloudflared\cert.pem`.

## 3. Create the tunnel

```powershell
cloudflared tunnel create rrtrace-backend
```

Prints a **TUNNEL UUID** like `b0d8a1c4-...`. Copy it. A credentials JSON also lands at `%USERPROFILE%\.cloudflared\<TUNNEL-UUID>.json`.

## 4. Drop in the config

Copy `services/cloudflared/config.example.yml` to `%USERPROFILE%\.cloudflared\config.yml`. Replace `<TUNNEL-UUID>` (both lines) with the UUID from step 3.

## 5. Wire DNS in Cloudflare

For each hostname the config proxies (`api.rrtrace.xyz`, `events.rrtrace.xyz`):

```powershell
cloudflared tunnel route dns rrtrace-backend api.rrtrace.xyz
cloudflared tunnel route dns rrtrace-backend events.rrtrace.xyz
```

These create CNAME records of the form `<UUID>.cfargotunnel.com` automatically. They MUST be **proxied (orange cloud)** — that's how Cloudflare terminates TLS and routes to the tunnel.

(This is the opposite of the apex `rrtrace.xyz` A records, which must stay grey-cloud DNS-only so GitHub Pages can provision its own cert. Mixed setup is fine.)

## 6. Run the tunnel

Foreground (for testing):

```powershell
cloudflared tunnel run rrtrace-backend
```

You should see `INF Connection registered` log lines. Open `https://api.rrtrace.xyz/stats` in a browser — should return JSON from the FastAPI server. If the server isn't running on `:8000` yet, start it: `uv run uvicorn server.main:app`.

Install as a Windows service (so it survives reboot/sleep, runs all 2 weeks unattended):

```powershell
# Run as admin
cloudflared service install
```

Verify: `Get-Service cloudflared` shows `Running`. Stops gracefully on shutdown.

## 7. Configure FastAPI CORS

The static dashboard at `https://rrtrace.xyz` will fetch from `https://api.rrtrace.xyz`. CORS must allow that origin — see `server/main.py`'s CORS middleware. Default `*` is fine for the hackathon, but if narrowed: include `https://rrtrace.xyz`, `https://www.rrtrace.xyz`.

## 8. Smoke test

```powershell
# From outside the LAN (or just a phone on cellular):
curl https://api.rrtrace.xyz/stats
curl -N https://events.rrtrace.xyz/events/stream    # should hold open + stream receipts
```

## Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `tunnel run` fails with `ERR Couldn't start tunnel` | Cred JSON path wrong in config.yml | Use forward slashes or escape backslashes |
| `502 Bad Gateway` on `api.rrtrace.xyz` | FastAPI not running on `:8000` | `uv run uvicorn server.main:app` |
| `1033 Argo Tunnel error` | Tunnel registered but DNS record missing | Re-run step 5 |
| CORS error in browser console | Origin not whitelisted | Add origin to `server/main.py` CORS middleware |
| Sleep hibernate kills tunnel | Windows sleep with networking off | Set "Power & sleep" → Never sleep when plugged in |

## What to monitor over the 2 weeks

- `cloudflared` service status (Windows Services panel)
- FastAPI uvicorn process (will need a watchdog — see `scripts/run-server.ps1` once added)
- Agent daemon (`python -m agent.loop`)

If any of the three dies, the dashboard goes blank. Phase 6 plan adds a healthcheck + auto-restart watchdog.
