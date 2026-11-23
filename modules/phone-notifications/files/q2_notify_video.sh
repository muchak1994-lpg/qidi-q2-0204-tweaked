#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Q2 tweaked - phone notifications: tell the phone where the timelapse video of a print is, with buttons that open it.
#
#   q2_notify_video.sh <print file name>      e.g. hdd500.gcode.3mf
#
# Looks for the newest  timelapse_<name>_<YYYYMMDD>_<HHMM>.mp4  in the timelapse folder (the name the Moonraker timelapse
# component gives; a longer name that only starts the same does not match). When the video is not there yet the render is
# still running: says so once, checks every 15 s for up to 10 min, then says it is not ready.
# The video is NOT uploaded: the public ntfy.sh refuses a video of a few MB (413 "attachment too large, or bandwidth limit
# reached", 23.11.2026). Instead the message has one button per address this printer has that a phone can reach - "Home network"
# (a private address) and "Tailscale" (100.64.0.0/10) - and each opens the file from the printer's own web server
# (http://<address>/server/files/timelapse/<file>). The phone taps the one that fits where it is. The addresses are read from the
# printer when the message is made; none is stored anywhere else and none is written into the message text.
# The name is only ever compared as text; it is never run by a shell (the listener also refuses special characters).

DIR="${Q2_TIMELAPSE_DIR:-/home/qidi/printer_data/timelapse}"
SEND="${Q2_NOTIFY_SEND:-sh /home/qidi/q2-notify/q2_notify_send.sh}"
WEB="${Q2_NOTIFY_WEB_PATH:-/server/files/timelapse/}"
POLL="${Q2_VIDEO_POLL:-15}"
TIMEOUT="${Q2_VIDEO_TIMEOUT:-600}"
NAME=$1
[ -n "$NAME" ] || exit 0

find_video() {  # the file names carry the time, so the last one in glob order is the newest
    found=""
    for f in "$DIR"/timelapse_"$NAME"_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9].mp4; do
        [ -f "$f" ] && found=$f
    done
    [ -n "$found" ]
}

addresses() {  # the printer's IPv4 addresses (Q2_NOTIFY_ADDRS replaces the lookup, for the tests)
    if [ -n "${Q2_NOTIFY_ADDRS+x}" ]; then
        printf '%s\n' $Q2_NOTIFY_ADDRS
    else
        # the network interfaces ... and Tailscale itself: on the Q2 it runs without an interface of its own (23.11.2026), so
        # `ip addr` shows only the Wi-Fi address and `tailscale ip -4` gives the other one. A failing command only drops its part.
        if [ -n "${Q2_NOTIFY_IPCMD+x}" ]; then
            sh -c "$Q2_NOTIFY_IPCMD" 2>/dev/null
        else
            ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1
        fi
        if [ -n "${Q2_NOTIFY_TSCMD+x}" ]; then
            sh -c "$Q2_NOTIFY_TSCMD" 2>/dev/null
        else
            tailscale ip -4 2>/dev/null
        fi
    fi
}

urlencode() {  # percent-encode every byte except letters, digits and . _ ~ -
    printf '%s' "$1" | LC_ALL=C awk '
        BEGIN { for (i = 1; i < 256; i++) ord[sprintf("%c", i)] = i }
        { s = $0; out = ""
          for (n = 1; n <= length(s); n++) {
              c = substr(s, n, 1)
              if (c ~ /[A-Za-z0-9._~-]/) out = out c; else out = out sprintf("%%%02X", ord[c])
          }
          printf "%s", out }'
}

waited=0
told=0
while ! find_video; do
    if [ "$told" = 0 ]; then
        $SEND "Timelapse" "$NAME: the timelapse is rendering, the video follows" --prio 2
        told=1
    fi
    if [ "$waited" -ge "$TIMEOUT" ]; then
        $SEND "Timelapse" "$NAME: the timelapse is not ready (gave up after $((TIMEOUT / 60)) min); it stays on the printer" --prio 2
        exit 0
    fi
    sleep "$POLL"
    waited=$((waited + POLL))
done

file=$(urlencode "$(basename "$found")")
home=0
tail_url=""
set --
for ip in $(addresses); do
    case "$ip" in
        100.6[4-9].*|100.[7-9][0-9].*|100.1[01][0-9].*|100.12[0-7].*)       # Tailscale: 100.64.0.0/10
            [ -n "$tail_url" ] || tail_url="Tailscale=http://$ip$WEB$file" ;;
        172.17.*) ;;                                                         # the default Docker bridge, not a network a phone is on
        192.168.*|10.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*)               # private networks: the home network
            home=$((home + 1))
            if [ "$home" = 1 ]; then set -- "$@" --view "Home network=http://$ip$WEB$file"
            elif [ "$home" = 2 ]; then set -- "$@" --view "Home network 2=http://$ip$WEB$file"; fi ;;
    esac
done
[ -n "$tail_url" ] && set -- "$@" --view "$tail_url"

if [ $# -gt 0 ]; then
    $SEND "Timelapse" "$NAME
Tap a button to open the video. If it does not open, the same file is in Fluidd under Timelapse." --prio 3 "$@"
else
    $SEND "Timelapse" "$NAME
The video is on the printer: Fluidd, Timelapse." --prio 3
fi
exit 0
