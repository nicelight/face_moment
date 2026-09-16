---
description: Operation of the public VPS Caddy edge, ACME certificate and FRP routing for Face Moment.
status: active
last_updated: 2026-09-16
source_of_truth:
  - .memory-bank/runbooks/vps-caddy.md
---
# VPS Caddy and FRP

## Scope and topology

This runbook owns the public VPS (`46.8.200.99`) Caddy configuration and its
interaction with FRP. It is called by [server deployment](server-deployment.md)
and is not a guide for deploying application containers.

```text
Visitor IP → VPS Caddy :443 → 127.0.0.1:18443 → FRP → face-pc :8443
face-pc frpc ── WSS /~!frp on face-time.moment-studio.ru ──► VPS frps :7000
```

The two names intentionally have different roles:

- `face-moment.ru` is the public application origin.
- `face-time.moment-studio.ru` remains the FRP WSS control channel and the
  path used by the administrative SSH tunnel. Do not point application traffic
  or the central FRP client at a new hostname merely to change the public
  origin.

## Access and managed files

Connect from the operator workstation as the VPS administrator:

```bash
ssh igornskprod
```

The VPS uses Caddy and `frps`; Docker is not part of this host. The managed
paths are:

| Purpose | VPS path | Source-managed input |
|---|---|---|
| Caddy configuration | `/etc/caddy/Caddyfile` | `deploy/frp/vps/Caddyfile` |
| Caddy environment | `/etc/caddy/face-moment.env` | `deploy/frp/vps/face-moment.env` |
| Caddy systemd override | `/etc/systemd/system/caddy.service.d/face-moment.conf` | `deploy/frp/vps/caddy-face-moment.conf` |
| FRP server configuration | `/etc/frp/frps.toml` | `deploy/frp/vps/frps.toml` |
| FRP token | `/etc/frp/server_token` | server-only secret; never copy or print |

`frps` publishes `127.0.0.1:18443` for the application and
`127.0.0.1:10022` for SSH only on VPS loopback. They must not be exposed by a
firewall rule or bound to the public interface.

## Public DNS and HTTPS certificate

REG.RU is the DNS provider for `face-moment.ru`. Before enabling the site,
verify that its authoritative DNS has an apex A record to `46.8.200.99` and no
unintended AAAA record:

```bash
dig +short A face-moment.ru @1.1.1.1
dig +short AAAA face-moment.ru @1.1.1.1
```

Caddy on the VPS obtains and renews the public ACME certificate automatically
(normally from Let's Encrypt). No certificate purchase from REG.RU, Certbot,
manual upload or DNS API integration is required. Keep public TCP `80` and
`443` reachable and preserve Caddy's persistent data directory across normal
updates so account and certificate state survive.

The certificate ends at the VPS. The next HTTPS hop has Caddy's internal
certificate (`tls internal`) and uses TLS SNI `localhost`; that SNI is separate
from the preserved public HTTP `Host` header.

## Apply a Caddy configuration change

Only apply a reviewed source commit together with the matching central
application release. From the reviewed workstation checkout, make an isolated
temporary staging directory and copy the three non-secret Caddy files:

```bash
ssh igornskprod 'install -d -m 700 /tmp/face-moment-caddy'
scp deploy/frp/vps/Caddyfile deploy/frp/vps/face-moment.env deploy/frp/vps/caddy-face-moment.conf igornskprod:/tmp/face-moment-caddy/
```

On the VPS, install them with sudo, validate using the same environment as
systemd, then reload without restarting FRP:

```bash
sudo install -d -m 755 /etc/caddy
sudo install -m 644 /tmp/face-moment-caddy/Caddyfile /etc/caddy/Caddyfile
sudo install -m 640 /tmp/face-moment-caddy/face-moment.env /etc/caddy/face-moment.env
sudo install -d -m 755 /etc/systemd/system/caddy.service.d
sudo install -m 644 /tmp/face-moment-caddy/caddy-face-moment.conf /etc/systemd/system/caddy.service.d/face-moment.conf
sudo sh -c 'set -a; . /etc/caddy/face-moment.env; caddy validate --config /etc/caddy/Caddyfile'
sudo systemctl daemon-reload
sudo systemctl reload caddy
sudo systemctl --no-pager --full status caddy
```

Set these two values in `/etc/caddy/face-moment.env` before validation:

```text
FACE_MOMENT_PUBLIC_HOST=face-moment.ru
FACE_MOMENT_FRP_HOST=face-time.moment-studio.ru
```

Do not copy this VPS environment file to `/etc/frp/face-moment.env` on the
central host: that file belongs to the existing FRP client and keeps its WSS
hostname. Do not alter `/etc/frp/server_token` or reinstall `frps` for an
ordinary public-origin change.

If Caddy cannot obtain a certificate, inspect `journalctl -u caddy` and first
correct DNS or ports. Do not fall back to a self-signed public certificate.

## Trusted visitor IP

The VPS Caddy overwrites `X-Forwarded-For` with the direct visitor IP and
preserves the public `Host`. Inner Caddy must accept this forwarding data only
from the one immediate FRP/Docker peer that connects to it. This peer is not
the visitor, the VPS public IP or automatically the inner edge's fixed Docker
address.

The KISS configuration uses one exact `FACE_MOMENT_FRP_PROXY_IP`; it must be
measured during deployment. For one unauthenticated controlled request,
temporarily add this site-level directive to central `deploy/Caddyfile`:

```caddyfile
log {
    output stdout
    format json
}
```

Reload only the inner edge, issue a request to `https://face-moment.ru/`, then
read its direct `request.remote_ip`:

```bash
docker compose exec -T edge caddy reload --config /etc/caddy/Caddyfile
docker compose logs --tail=30 edge
```

Set that exact address in central `/opt/face-moment/.env`, remove the temporary
`log` block, and reload the edge once more. Do not make authenticated requests
while that temporary access log exists.

The non-routable default `192.0.2.1` intentionally trusts no real peer. Never
replace it with `private_ranges`, a CIDR broader than the observed peer, or the
VPS public address. The small operational risk is that Docker network
recreation can change the peer address; repeat this controlled measurement
after such a network change.

## Acceptance checks

After both sides are live, verify the public certificate and routes:

```bash
curl -fsSI --max-time 10 https://face-moment.ru/
sudo journalctl -u caddy -n 100 --no-pager -o cat
sudo systemctl is-active frps
```

Then check that a public request arrives with `Host: face-moment.ru`, that two
different visitor IPs have independent phone rate-limit budgets, that a forged
`X-Forwarded-For` is ignored, and that `ssh -l facemoment facecentral` still
works. The isolated regression test
`tests/infrastructure/test_proxy_forwarding.py` is the code-level proof; these
are the live configuration checks.
