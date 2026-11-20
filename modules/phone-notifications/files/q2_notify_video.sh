#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Q2 tweaked - phone notifications: send the timelapse video of a print to the phone.
#
#   q2_notify_video.sh <print file name>      e.g. hdd500.gcode.3mf
#
# Looks for the newest  timelapse_<name>_<YYYYMMDD>_<HHMM>.mp4  in the timelapse folder (the name the Moonraker timelapse
# component gives; a longer name that only starts the same does not match). When the video is not there yet the render is
# still running: says so once, checks every 15 s for up to 10 min, then says it is not ready. The video goes out through
# q2_notify_send.sh as an attachment; one over 14 MB (the ntfy limit is 15 MB) is announced but not uploaded.
# The name is only ever compared as text; it is never run by a shell (the listener also refuses special characters).

DIR="${Q2_TIMELAPSE_DIR:-/home/qidi/printer_data/timelapse}"
SEND="${Q2_NOTIFY_SEND:-sh /home/qidi/q2-notify/q2_notify_send.sh}"
POLL="${Q2_VIDEO_POLL:-15}"
TIMEOUT="${Q2_VIDEO_TIMEOUT:-600}"
MAX="${Q2_VIDEO_MAX_BYTES:-14680064}"
NAME=$1
[ -n "$NAME" ] || exit 0

find_video() {  # the file names carry the time, so the last one in glob order is the newest
    found=""
    for f in "$DIR"/timelapse_"$NAME"_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9].mp4; do
        [ -f "$f" ] && found=$f
    done
    [ -n "$found" ]
}

waited=0
told=0
while ! find_video; do
    if [ "$told" = 0 ]; then
        $SEND "Timelapse" "$NAME: the timelapse is rendering, the video follows" --prio 2 --tags movie_camera
        told=1
    fi
    if [ "$waited" -ge "$TIMEOUT" ]; then
        $SEND "Timelapse" "$NAME: the timelapse is not ready (gave up after $((TIMEOUT / 60)) min); it stays on the printer" --prio 2 --tags movie_camera
        exit 0
    fi
    sleep "$POLL"
    waited=$((waited + POLL))
done

size=$(wc -c < "$found")
if [ "$size" -gt "$MAX" ]; then
    $SEND "Timelapse" "$NAME: the video is too large to send ($((size / 1048576)) MB); it stays on the printer" --prio 2 --tags movie_camera
    exit 0
fi
$SEND "Timelapse" "$NAME" --prio 3 --tags movie_camera --attach "$found"
exit 0
