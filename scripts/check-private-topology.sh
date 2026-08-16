#!/usr/bin/env bash

set -u -o pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/compose.yaml"
CADDY_FILE="${ROOT_DIR}/deploy/Caddyfile"
SCAN_HOST="${TOPOLOGY_SCAN_HOST:-127.0.0.1}"
EDGE_PORT="${FACE_MOMENT_EDGE_PORT:-8443}"
INTERNAL_SERVICES=(postgres minio backend background-worker realtime)
INTERNAL_ROLE_SERVICES=(backend background-worker realtime)
INTERNAL_PORTS=(5432 9000 8000 8001 8002)

source_failures=0
runtime_failures=0

fail_source() {
    printf 'source_check=FAIL reason=%s\n' "$1"
    source_failures=$((source_failures + 1))
}

fail_runtime() {
    printf 'runtime_check=FAIL reason=%s\n' "$1"
    runtime_failures=$((runtime_failures + 1))
}

is_uint_port() {
    [[ "$1" =~ ^[0-9]+$ ]] && ((1 <= 10#$1 && 10#$1 <= 65535))
}

printf '%s\n' 'private_topology_check=started'

if [[ ! -f "$COMPOSE_FILE" ]]; then
    fail_source 'compose_file_missing'
fi
if [[ ! -f "$CADDY_FILE" ]]; then
    fail_source 'caddy_file_missing'
fi
if ! is_uint_port "$EDGE_PORT"; then
    fail_source 'edge_port_invalid'
fi
if [[ ! "$SCAN_HOST" =~ ^[A-Za-z0-9_.:-]+$ ]]; then
    fail_source 'scan_host_invalid'
fi

if (( source_failures == 0 )); then
    if command -v docker >/dev/null 2>&1; then
        if ! docker compose -f "$COMPOSE_FILE" config --quiet >/dev/null 2>&1; then
            fail_source 'compose_config_invalid'
        else
            printf '%s\n' 'source_compose_config=PASS'
        fi
    else
        printf '%s\n' 'source_compose_config=NOT_AVAILABLE docker_missing'
    fi

    if grep -Eq '^[[:space:]]{4}ports:[[:space:]]*$' "$COMPOSE_FILE"; then
        port_services="$(awk '
            $0 ~ /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { service=$1; sub(/:$/, "", service); section="" }
            $0 ~ /^    (ports|expose):[[:space:]]*$/ { section=$1; sub(/:$/, "", section); if (section == "ports") print service }
            $0 ~ /^    [A-Za-z0-9_-]+:/ && $0 !~ /^    (ports|expose):/ { section="" }
        ' "$COMPOSE_FILE")"
        if [[ "$port_services" != "edge" ]]; then
            fail_source 'non_edge_service_publishes_host_port'
        else
            printf '%s\n' 'source_host_publish_services=edge'
        fi
    else
        fail_source 'edge_host_publish_missing'
    fi

    if ! grep -Eq '^[[:space:]]{6}-[[:space:]]*"?127\.0\.0\.1:\$\{FACE_MOMENT_EDGE_PORT:-8443\}:8443"?[[:space:]]*$' "$COMPOSE_FILE"; then
        fail_source 'edge_bind_is_not_loopback_8443'
    else
        printf '%s\n' 'source_edge_bind=loopback_only'
    fi

    for service in "${INTERNAL_ROLE_SERVICES[@]}"; do
        if awk -v wanted="$service" '
            $0 ~ /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { service=$1; sub(/:$/, "", service); section="" }
            $0 ~ /^    (ports|expose):[[:space:]]*$/ { section=$1; sub(/:$/, "", section) }
            $0 ~ /^    [A-Za-z0-9_-]+:/ && $0 !~ /^    (ports|expose):/ { section="" }
            service == wanted && section == "ports" { found=1 }
            END { exit found ? 0 : 1 }
        ' "$COMPOSE_FILE"; then
            fail_source "internal_service_publishes_host_port_${service}"
        fi
    done
    printf '%s\n' 'source_internal_host_publications=none'

    for service in "${INTERNAL_ROLE_SERVICES[@]}"; do
        if ! awk -v wanted="$service" '
            $0 ~ /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { service=$1; sub(/:$/, "", service); section="" }
            $0 ~ /^    (ports|expose):[[:space:]]*$/ { section=$1; sub(/:$/, "", section) }
            $0 ~ /^    [A-Za-z0-9_-]+:/ && $0 !~ /^    (ports|expose):/ { section="" }
            service == wanted && section == "expose" { found=1 }
            END { exit found ? 0 : 1 }
        ' "$COMPOSE_FILE"; then
            fail_source "internal_service_expose_missing_${service}"
        fi
    done
    printf '%s\n' 'source_internal_role_visibility=expose_only'

    if ! grep -Eq '^[[:space:]]+internal:[[:space:]]+true[[:space:]]*$' "$COMPOSE_FILE"; then
        fail_source 'private_network_not_internal'
    else
        printf '%s\n' 'source_private_network=internal'
    fi

    if grep -Eq 'reverse_proxy[[:space:]]+(postgres|minio)(:|[[:space:]])' "$CADDY_FILE"; then
        fail_source 'edge_routes_directly_to_storage'
    else
        printf '%s\n' 'source_edge_storage_routes=none'
    fi
fi

runtime_available=0
compose_ps_output=''
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    runtime_available=1
    if compose_ps_output="$(docker compose -f "$COMPOSE_FILE" ps --all --format '{{.Service}}|{{.State}}|{{.Ports}}' 2>/dev/null)"; then
        printf '%s\n' 'runtime_docker=available'
    else
        runtime_available=0
        printf '%s\n' 'runtime_docker=NOT_PROVIDED compose_inspection_unavailable'
    fi
else
    printf '%s\n' 'runtime_docker=NOT_PROVIDED docker_daemon_unavailable'
fi

if (( runtime_available == 1 )); then
    runtime_rows=0
    while IFS='|' read -r service state published; do
        [[ -n "$service" ]] || continue
        runtime_rows=$((runtime_rows + 1))
        case " ${INTERNAL_SERVICES[*]} " in
            *" $service "*)
                if [[ "$published" == *'->'* ]]; then
                    fail_runtime "internal_service_runtime_publication_${service}"
                fi
                ;;
            edge)
                :
                ;;
        esac
    done <<< "$compose_ps_output"
    if (( runtime_rows == 0 )); then
        printf '%s\n' 'runtime_compose_state=NOT_RUNNING'
    else
        printf '%s\n' 'runtime_internal_publications=none'
    fi
fi

if command -v ss >/dev/null 2>&1; then
    socket_output="$(ss -ltnH 2>/dev/null || true)"
    socket_hits=0
    for port in "${INTERNAL_PORTS[@]}"; do
        if awk -v suffix=":${port}" '$4 ~ (suffix "$|\\]" suffix "$|\\." suffix ":") { found=1 } END { exit found ? 0 : 1 }' <<< "$socket_output"; then
            fail_runtime "host_listening_socket_internal_port_${port}"
            socket_hits=$((socket_hits + 1))
        fi
    done
    if (( socket_hits == 0 )); then
        printf '%s\n' 'runtime_host_internal_listeners=none_observed'
    fi
else
    printf '%s\n' 'runtime_host_socket_scan=NOT_PROVIDED ss_missing'
fi

external_scan_available=0
if command -v nc >/dev/null 2>&1 && is_uint_port "$EDGE_PORT" && [[ "$SCAN_HOST" =~ ^[A-Za-z0-9_.:-]+$ ]]; then
    external_scan_available=1
    if nc -z -w 1 "$SCAN_HOST" "$EDGE_PORT" >/dev/null 2>&1; then
        printf '%s\n' 'external_scan_edge=reachable'
        edge_reachable=1
    else
        printf '%s\n' 'external_scan_edge=not_reachable'
        edge_reachable=0
    fi
    internal_reachable=0
    for port in "${INTERNAL_PORTS[@]}"; do
        if nc -z -w 1 "$SCAN_HOST" "$port" >/dev/null 2>&1; then
            printf 'external_scan_internal_%s=reachable\n' "$port"
            fail_runtime "external_internal_port_reachable_${port}"
            internal_reachable=$((internal_reachable + 1))
        else
            printf 'external_scan_internal_%s=not_reachable\n' "$port"
        fi
    done
    if (( internal_reachable == 0 )); then
        printf '%s\n' 'external_scan_internal_ports=private'
    fi
else
    printf '%s\n' 'external_scan=NOT_PROVIDED nc_or_target_unavailable'
fi

if (( source_failures > 0 )); then
    printf 'private_topology_check=FAIL source_failures=%s runtime_failures=%s\n' "$source_failures" "$runtime_failures"
    exit 1
fi

if (( runtime_available == 0 || external_scan_available == 0 )); then
    printf '%s\n' 'private_topology_check=SOURCE_ONLY runtime_or_external_scan_unavailable'
    printf '%s\n' 'runtime_external_claim=NOT_PROVEN'
    exit 0
fi

if (( edge_reachable != 1 )); then
    printf '%s\n' 'private_topology_check=SOURCE_RUNTIME_ONLY_edge_not_reachable'
    printf '%s\n' 'runtime_external_claim=NOT_PROVEN'
    exit 0
fi

if (( runtime_failures > 0 )); then
    printf 'private_topology_check=FAIL source_failures=%s runtime_failures=%s\n' "$source_failures" "$runtime_failures"
    exit 1
fi

printf '%s\n' 'private_topology_check=PASS edge_only_external_reachability'
