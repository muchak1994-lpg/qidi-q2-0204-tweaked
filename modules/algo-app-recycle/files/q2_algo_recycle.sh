#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 muchak1994-lpg (QIDI Q2 02.04 Tweaked) - with Claude (Anthropic) and Codex "Stefan" (OpenAI)
# algo-app-recycle: restarts the AI service (algo_app) once a print has been over for a while, so the printer does not keep
# the ~100+ MB the AI model took for the print. It only RESTARTS a running service that is big; it never starts a stopped one
# (a stopped service means the owner stopped it on purpose), never touches a printer that is printing or paused, and re-checks
# right before the restart. Everything can be set by environment variables (used by the tests).
API=${Q2_RECYCLE_API:-http://127.0.0.1:7125/printer/objects/query?print_stats}
INTERVAL=${Q2_RECYCLE_INTERVAL:-10}      # seconds between checks
DELAY=${Q2_RECYCLE_DELAY:-120}           # seconds a finished print must stay finished (video files get closed, timelapse is done)
MIN_RSS_KB=${Q2_RECYCLE_MIN_RSS_KB:-130000}   # below this the service is already small: nothing to give back
SERVICE=${Q2_RECYCLE_SERVICE:-algo_app}
PROC=${Q2_RECYCLE_PROC:-/proc}
MAX_LOOPS=${Q2_RECYCLE_MAX_LOOPS:-0}     # 0 = run forever (tests set a limit)

log() { logger -t q2-algo-recycle "$*" 2>/dev/null || echo "$*" >&2; }

# prints the print_stats state, or nothing when Moonraker does not answer
get_state() {
    curl -s -m 5 "$API" 2>/dev/null | sed -n 's/.*"state": *"\([a-z_]*\)".*/\1/p' | head -n 1
}

busy() {
    case "$1" in printing|paused) return 0 ;; esac
    return 1
}

recycle() {
    if [ "$(systemctl is-active "$SERVICE" 2>/dev/null)" != "active" ]; then
        log "skip: $SERVICE is not running (not started on purpose)"
        return
    fi
    pid=$(systemctl show -p MainPID --value "$SERVICE" 2>/dev/null)
    rss=$(awk '/^VmRSS:/ {print $2}' "$PROC/$pid/status" 2>/dev/null)
    case "$rss" in ''|*[!0-9]*) log "skip: cannot read the size of $SERVICE (pid '$pid')"; return ;; esac
    if [ "$rss" -lt "$MIN_RSS_KB" ]; then
        log "skip: $SERVICE is only $((rss / 1024)) MB, nothing to give back"
        return
    fi
    if busy "$(get_state)"; then
        log "skip: a new print started"
        return
    fi
    log "restarting $SERVICE after the print ($((rss / 1024)) MB)"
    systemctl restart "$SERVICE"
}

armed=0
waited=0
loops=0
while :; do
    state=$(get_state)
    if busy "$state"; then
        armed=1
        waited=0
    else
        case "$state" in
            complete|cancelled|standby|error)
                if [ "$armed" = 1 ]; then
                    waited=$((waited + INTERVAL))
                    if [ "$waited" -ge "$DELAY" ]; then
                        recycle
                        armed=0
                        waited=0
                    fi
                fi
                ;;
        esac
    fi
    loops=$((loops + 1))
    if [ "$MAX_LOOPS" -gt 0 ] && [ "$loops" -ge "$MAX_LOOPS" ]; then
        break
    fi
    sleep "$INTERVAL"
done
