#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Q2 tweaked - phone notifications: listen on the command channel and act on the buttons of the messages.
#
# Reads the ntfy command channel ($NTFY_SERVER/$CMD_TOPIC/raw, one message body per line) and understands exactly these
# commands; everything else is ignored:
#   resume            resume the print   (only while the print is paused)
#   cancel            cancel the print   (only while the print is paused)
#   video <name>      send the timelapse of that print (q2_notify_video.sh runs in the background)
#   photo             send the camera picture now (any state; only reads the camera and the name of the print file)
#   maintdone <task>  mark a maintenance task as done (task: rails, zscrews or fans; runs TWEAKED_MAINT_DONE)
# resume/cancel go to Moonraker on this printer (127.0.0.1); the state is read first, so a command delivered twice (the
# listener reconnects) does nothing the second time. A video name may not contain / \ ; | & $ ` ' " < > * ? ~ ! # and
# may not start with - or . : it is passed to q2_notify_video.sh as ONE argument and never reaches a shell.
# If the connection drops the listener connects again after 10 s. Does nothing when the notifications are off.

CONF="${Q2_NOTIFY_CONF:-/home/qidi/printer_data/config/q2_notify.conf}"
CURL="${Q2_NOTIFY_CURL:-curl}"
VIDEO="${Q2_NOTIFY_VIDEO:-sh /home/qidi/q2-notify/q2_notify_video.sh}"
SEND="${Q2_NOTIFY_SEND:-sh /home/qidi/q2-notify/q2_notify_send.sh}"
SNAPSHOT="${Q2_NOTIFY_SNAPSHOT:-http://127.0.0.1/webcam/?action=snapshot}"
MOONRAKER="${Q2_NOTIFY_MOONRAKER:-http://127.0.0.1:7125}"
RETRY="${Q2_NOTIFY_RETRY:-10}"
LOOPS="${Q2_NOTIFY_LOOPS:-0}"          # 0 = for ever (a number is for the tests)

ENABLED=0
NTFY_SERVER=""
CMD_TOPIC=""
[ -r "$CONF" ] || exit 0
while IFS='=' read -r key value; do
    value=$(printf '%s' "$value" | tr -d '\r')
    case "$key" in
        ENABLED) ENABLED=$value ;;
        NTFY_SERVER) NTFY_SERVER=${value%/} ;;
        CMD_TOPIC) CMD_TOPIC=$value ;;
    esac
done < "$CONF"
[ "$ENABLED" = "1" ] && [ -n "$NTFY_SERVER" ] && [ -n "$CMD_TOPIC" ] || exit 0

print_state() {
    $CURL -s --max-time 5 "$MOONRAKER/printer/objects/query?print_stats=state" 2>/dev/null \
        | sed -n 's/.*"state": *"\([a-z]*\)".*/\1/p' | head -n 1
}

print_file() {
    $CURL -s --max-time 5 "$MOONRAKER/printer/objects/query?print_stats=filename" 2>/dev/null \
        | sed -n 's/.*"filename": *"\([^"]*\)".*/\1/p' | head -n 1
}

handle() {
    line=$(printf '%s' "$1" | tr -d '\r')
    case "$line" in
        resume|cancel)
            [ "$(print_state)" = "paused" ] && $CURL -s --max-time 10 -X POST "$MOONRAKER/printer/print/$line" >/dev/null 2>&1
            ;;
        photo)
            name=$(print_file)
            [ -n "$name" ] || name="No print file loaded"
            $SEND "Camera" "$name" --prio 3 --tags camera --attach "$SNAPSHOT" >/dev/null 2>&1 &
            ;;
        "maintdone "*)  # the Done button of a maintenance reminder: only the three known task names
            case "${line#maintdone }" in
                rails|zscrews|fans)
                    $CURL -s --max-time 10 -X POST "$MOONRAKER/printer/gcode/script?script=TWEAKED_MAINT_DONE%20TASK=${line#maintdone }" >/dev/null 2>&1 ;;
            esac
            ;;
        "video "*)
            name=${line#video }
            case "$name" in
                ""|-*|.*|*/*|*\\*|*\;*|*\|*|*\&*|*\$*|*\`*|*\'*|*\"*|*\<*|*\>*|*\**|*\?*|*\~*|*\!*|*\#*) return 0 ;;
            esac
            $VIDEO "$name" >/dev/null 2>&1 &
            ;;
    esac
    return 0
}

n=0
while :; do
    $CURL -sN "$NTFY_SERVER/$CMD_TOPIC/raw" 2>/dev/null | while IFS= read -r line; do
        handle "$line"
    done
    n=$((n + 1))
    [ "$LOOPS" -gt 0 ] && [ "$n" -ge "$LOOPS" ] && break
    sleep "$RETRY"
done
exit 0
