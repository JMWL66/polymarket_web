#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
BOT_PID_FILE="$RUNTIME_DIR/paper_bot.pid"
SERVER_PID_FILE="$RUNTIME_DIR/status_server.pid"

stop_pid_file() {
    local pid_file="$1"
    if [[ -f "$pid_file" ]]; then
        local pid
        pid="$(cat "$pid_file")"
        if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$pid_file"
    fi
}

stop_port_listener() {
    local port="$1"
    local pids
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids:-}" ]]; then
        kill $pids 2>/dev/null || true
        sleep 1
    fi
}

stop_pid_file "$BOT_PID_FILE"
stop_pid_file "$SERVER_PID_FILE"
stop_port_listener 8889

echo "模拟交易与监控服务已停止"
