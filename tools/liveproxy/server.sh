#!/bin/bash

commands=(liveproxy streamlink python python3)
host="0.0.0.0"
port=53422

for cmd in "${commands[@]}"; do
	if ! command -v "$cmd" >/dev/null 2>&1; then
		echo "error: $cmd not found" >&2
		exit 1
	fi
done

port_check() {
	local port="${1:-}"

	if [[ ! "$port" =~ ^[0-9]+$ ]] ||
		((port < 1 || port > 65535)); then
		echo "error: invalid port: $port" >&2
		return 2
	fi

	if (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
		return 0
	else
		return 1
	fi
}

if port_check "$port"; then
	echo "Server already running"
else
	liveproxy --host="$host" --port="$port"
fi
