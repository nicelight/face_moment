#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    printf 'Run as root: sudo ./install.sh\n' >&2
    exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
swan_dir=/etc/swanctl

for required_file in \
    "${script_dir}/face-moment.conf" \
    "${script_dir}/face-moment-xfrm.service" \
    "${script_dir}/strongswan-ports.conf" \
    "${script_dir}/strongswan-xfrm.conf" \
    "${script_dir}/ca-cert.pem" \
    "${script_dir}/central-cert.pem" \
    "${script_dir}/central-key.pem"; do
    [[ -f "${required_file}" ]] || {
        printf 'Missing bundle file: %s\n' "${required_file}" >&2
        exit 1
    }
done

command -v swanctl >/dev/null
install -d -m 755 "${swan_dir}/conf.d" "${swan_dir}/x509ca" "${swan_dir}/x509" "${swan_dir}/private"
install -m 644 "${script_dir}/face-moment.conf" "${swan_dir}/conf.d/face-moment.conf"
install -m 644 "${script_dir}/ca-cert.pem" "${swan_dir}/x509ca/face-moment-ca.pem"
install -m 644 "${script_dir}/central-cert.pem" "${swan_dir}/x509/central-cert.pem"
install -m 600 "${script_dir}/central-key.pem" "${swan_dir}/private/central-key.pem"
install -m 644 "${script_dir}/strongswan-ports.conf" \
    /etc/strongswan.d/face-moment-ports.conf

if ! grep -Eq '^[[:space:]]*include[[:space:]]+conf\.d/\*\.conf' "${swan_dir}/swanctl.conf"; then
    printf '\ninclude conf.d/*.conf\n' >> "${swan_dir}/swanctl.conf"
fi

install -m 644 "${script_dir}/face-moment-xfrm.service" /etc/systemd/system/face-moment-xfrm.service
install -d -m 755 /etc/systemd/system/strongswan.service.d
install -m 644 "${script_dir}/strongswan-xfrm.conf" \
    /etc/systemd/system/strongswan.service.d/face-moment-xfrm.conf

chown root:root \
    "${swan_dir}/conf.d/face-moment.conf" \
    "${swan_dir}/x509ca/face-moment-ca.pem" \
    "${swan_dir}/x509/central-cert.pem" \
    "${swan_dir}/private/central-key.pem" \
    /etc/strongswan.d/face-moment-ports.conf \
    /etc/systemd/system/face-moment-xfrm.service \
    /etc/systemd/system/strongswan.service.d/face-moment-xfrm.conf

systemd-analyze verify /etc/systemd/system/face-moment-xfrm.service
systemctl daemon-reload
systemctl enable --now face-moment-xfrm.service
systemctl enable strongswan.service
systemctl restart strongswan.service
swanctl --load-creds
swanctl --load-conns

printf 'Central IPsec configuration installed.\n'
printf 'Interface: '
ip -brief address show ipsec0
printf 'Connections:\n'
swanctl --list-conns
