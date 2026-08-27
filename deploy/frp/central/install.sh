#!/usr/bin/env bash
set -euo pipefail

if (( EUID != 0 )); then
  printf 'Run as root: sudo %s <public-hostname>\n' "$0" >&2
  exit 1
fi

if (( $# != 1 )) || [[ ! "$1" =~ ^[A-Za-z0-9.-]+$ ]]; then
  printf 'Usage: sudo %s <public-hostname>\n' "$0" >&2
  exit 1
fi

public_host=${1,,}
bundle_dir=$(cd -- "$(dirname -- "$0")" && pwd)

for required_file in frpc frpc.toml frpc.service client_token; do
  if [[ ! -s "$bundle_dir/$required_file" ]]; then
    printf 'Missing bundle file: %s\n' "$required_file" >&2
    exit 1
  fi
done

if ! getent passwd frpc >/dev/null; then
  useradd --system --home-dir /var/lib/frp --create-home --shell /usr/sbin/nologin frpc
fi

install -d -o root -g frpc -m 0750 /etc/frp
install -o root -g root -m 0755 "$bundle_dir/frpc" /usr/local/bin/frpc
install -o root -g frpc -m 0640 "$bundle_dir/frpc.toml" /etc/frp/frpc.toml
install -o frpc -g frpc -m 0600 "$bundle_dir/client_token" /etc/frp/client_token
install -o root -g root -m 0644 "$bundle_dir/frpc.service" /etc/systemd/system/frpc.service

install -o root -g frpc -m 0640 /dev/null /etc/frp/face-moment.env
printf 'FACE_MOMENT_PUBLIC_HOST=%s\n' "$public_host" > /etc/frp/face-moment.env
chown root:frpc /etc/frp/face-moment.env
chmod 0640 /etc/frp/face-moment.env

FACE_MOMENT_PUBLIC_HOST="$public_host" /usr/local/bin/frpc verify -c /etc/frp/frpc.toml

systemctl daemon-reload
systemctl enable --now frpc
systemctl restart frpc
sleep 3

printf '\n=== Local Face Moment HTTPS ===\n'
if curl -kfsS --max-time 5 https://localhost:8443/ >/dev/null; then
  printf 'OK: https://localhost:8443 is reachable\n'
else
  printf 'WARNING: https://localhost:8443 is not reachable; FRP will reconnect, but the application endpoint must be started.\n'
fi

printf '\n=== FRP client ===\n'
systemctl --no-pager --full status frpc
journalctl -u frpc -n 30 --no-pager -o cat
