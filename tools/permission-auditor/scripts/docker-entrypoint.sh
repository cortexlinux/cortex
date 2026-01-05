#!/bin/bash
# docker-entrypoint.sh - Handle UID/GID mapping between host and container

set -e

if [[ -n "$HOST_UID" ]] && [[ -n "$HOST_GID" ]]; then
    if [[ "$HOST_UID" =~ ^[0-9]+$ ]] && [[ "$HOST_GID" =~ ^[0-9]+$ ]]; then
        sudo usermod -u "$HOST_UID" appuser 2>/dev/null || true
        sudo groupmod -g "$HOST_GID" appgroup 2>/dev/null || true
        sudo chown -R "$HOST_UID:$HOST_GID" /app 2>/dev/null || true
    else
        echo "⚠️ Warning: HOST_UID/HOST_GID are not numeric: $HOST_UID/$HOST_GID"
    fi
fi

exec "$@"
