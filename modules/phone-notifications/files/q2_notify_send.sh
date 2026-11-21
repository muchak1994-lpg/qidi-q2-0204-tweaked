#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-only
# Q2 tweaked - phone notifications: publish one message to the ntfy channel from q2_notify.conf.
#
#   q2_notify_send.sh <title> <message> [--prio N] [--tags a,b] [--click URL] [--attach FILE] [--action LABEL=BODY]...
#   q2_notify_send.sh --tsv "<title>\t<message>\t<prio>\t<tags>\t<click>\t<attach>\t<action1>\t<action2>\t<action3>"
#
# --tsv is one argument with tab-separated fields (an empty field = not set); Klipper's gcode_shell_command splits a command
# line at spaces, which would break file names with spaces. In --tsv mode the two characters \n in the message become a newline.
# A button is shown as: LABEL, and tapping it sends BODY to the command channel ($NTFY_SERVER/$CMD_TOPIC); the message then
# disappears, except after the button "photo" (a picture on request).
# --attach takes a file, or an http(s) address that is downloaded first (a failed download only drops the picture).
# Without --attach the message goes out as JSON (UTF-8 safe); with --attach as a file upload (PUT), where non-ASCII
# header text is RFC 2047 encoded. Does nothing (exit 0) when the notifications are off or there is no config.
# Never blocks long: curl has --max-time; any failure is ignored (a lost notification must not disturb a print).

CONF="${Q2_NOTIFY_CONF:-/home/qidi/printer_data/config/q2_notify.conf}"
CURL="${Q2_NOTIFY_CURL:-curl}"
ETA="${Q2_NOTIFY_ETA:-python3 /home/qidi/q2-notify/q2_notify_eta.py}"

ENABLED=0
NTFY_SERVER=""
EVENTS_TOPIC=""
CMD_TOPIC=""
[ -r "$CONF" ] || exit 0
while IFS='=' read -r key value; do
    value=$(printf '%s' "$value" | tr -d '\r')
    case "$key" in
        ENABLED) ENABLED=$value ;;
        NTFY_SERVER) NTFY_SERVER=${value%/} ;;
        EVENTS_TOPIC) EVENTS_TOPIC=$value ;;
        CMD_TOPIC) CMD_TOPIC=$value ;;
    esac
done < "$CONF"
[ "$ENABLED" = "1" ] && [ -n "$NTFY_SERVER" ] && [ -n "$EVENTS_TOPIC" ] || exit 0

TAB=$(printf '\t')
PRIO=""
TAGS=""
CLICK=""
ATTACH=""
ACTIONS=""

if [ "$1" = "--tsv" ]; then
    tsv=$2
    field() { printf '%s' "$tsv" | cut -d "$TAB" -f "$1"; }
    TITLE=$(field 1)
    MESSAGE=$(field 2 | sed 's/\\n/\n/g')
    PRIO=$(field 3)
    TAGS=$(field 4)
    CLICK=$(field 5)
    ATTACH=$(field 6)
    for n in 7 8 9; do
        a=$(field $n)
        [ -n "$a" ] && ACTIONS="$ACTIONS$a
"
    done
else
    TITLE=$1
    MESSAGE=$2
    shift 2 2>/dev/null
    while [ $# -gt 0 ]; do
        case "$1" in
            --prio) PRIO=$2 ;;
            --tags) TAGS=$2 ;;
            --click) CLICK=$2 ;;
            --attach) ATTACH=$2 ;;
            --action) ACTIONS="$ACTIONS$2
" ;;
        esac
        shift 2 2>/dev/null || break
    done
fi

expand_clock() {  # @@+SECONDS@@ in the message becomes the clock time that many seconds from now (HH:MM)
    msg=$1
    while :; do
        secs=$(printf '%s' "$msg" | sed -n 's/.*@@+\([0-9][0-9]*\)@@.*/\1/p' | head -n 1)
        [ -n "$secs" ] || break
        now=${Q2_NOTIFY_NOW:-$(date +%s)}
        hhmm=$(date -d "@$((now + secs))" +%H:%M 2>/dev/null) || hhmm="?"
        msg=$(printf '%s' "$msg" | sed "s/@@+${secs}@@/$hhmm/")
    done
    printf '%s' "$msg"
}
expand_eta() {  # @@ETA:ELAPSED:FALLBACK@@ becomes "<time left> left, done at @@+SECONDS@@": the time left is the slicer's
                # estimate minus ELAPSED (what the printer screen shows up to 50 %), or FALLBACK seconds without an estimate
    msg=$1
    while :; do
        tok=$(printf '%s' "$msg" | sed -n 's/.*\(@@ETA:[0-9][0-9]*:[0-9][0-9]*@@\).*/\1/p' | head -n 1)
        [ -n "$tok" ] || break
        el=${tok#@@ETA:}; el=${el%%:*}
        fb=${tok#@@ETA:*:}; fb=${fb%@@}
        left=$($ETA "$el" 2>/dev/null | head -n 1 | tr -cd '0-9')
        [ -n "$left" ] || left=$fb
        m=$((left / 60))
        if [ "$m" -ge 60 ]; then text=$(printf '%dh %02dm' $((m / 60)) $((m % 60))); else text="$m min"; fi
        new=$(printf '%s' "$msg" | sed "s/$tok/$text left, done at @@+$left@@/")
        [ "$new" = "$msg" ] && break    # never loop for ever if a token could not be replaced
        msg=$new
    done
    printf '%s' "$msg"
}
expand_fil() {  # @@FIL:MM@@ becomes the filament used: grams (the slicer's weight in proportion, from Moonraker) or, without
                # that, metres computed from MM millimetres
    msg=$1
    while :; do
        tok=$(printf '%s' "$msg" | sed -n 's/.*\(@@FIL:[0-9][0-9]*@@\).*/\1/p' | head -n 1)
        [ -n "$tok" ] || break
        mm=${tok#@@FIL:}; mm=${mm%@@}
        grams=$($ETA --weight "$mm" 2>/dev/null | head -n 1 | tr -cd '0-9.')
        if [ -n "$grams" ]; then text="$grams g"; else text="$((mm / 1000)).$(((mm % 1000) / 100)) m"; fi
        new=$(printf '%s' "$msg" | sed "s/$tok/$text/")
        [ "$new" = "$msg" ] && break    # never loop for ever if a token could not be replaced
        msg=$new
    done
    printf '%s' "$msg"
}
MESSAGE=$(expand_eta "$MESSAGE")
MESSAGE=$(expand_fil "$MESSAGE")
MESSAGE=$(expand_clock "$MESSAGE")

json_escape() {
    printf '%s' "$1" | tr -d '\000-\010\013\014\016-\037' | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/\t/\\t/g' \
        | awk 'NR>1{printf "\\n"} {printf "%s",$0}'
}

header_text() {  # one line, RFC 2047 encoded when it is not plain ASCII
    one=$(printf '%s' "$1" | tr '\n\r' '  ')
    if printf '%s' "$one" | LC_ALL=C grep -q '[^ -~]'; then
        printf '=?UTF-8?B?%s?=' "$(printf '%s' "$one" | base64 | tr -d '\n')"
    else
        printf '%s' "$one"
    fi
}

button_clears() {  # tapping a button removes its message, except "photo" (the picture is an extra, the message stays)
    case "$1" in photo) printf false ;; *) printf true ;; esac
}

SNAP=""
trap '[ -n "$SNAP" ] && rm -f "$SNAP"' EXIT
case "$ATTACH" in  # an address: fetch the picture first (e.g. the camera snapshot), a failure only drops the picture
    http://*|https://*)
        SNAP="${Q2_NOTIFY_TMP:-/tmp}/q2_notify_snap.$$.jpg"
        $CURL -sS --max-time 8 -o "$SNAP" "$ATTACH" >/dev/null 2>&1
        if [ -s "$SNAP" ]; then ATTACH=$SNAP; else ATTACH=""; fi ;;
esac

if [ -n "$ATTACH" ] && [ -f "$ATTACH" ]; then
    set -- -sS --max-time 60 -T "$ATTACH" -H "Filename: $(basename "$ATTACH")" \
        -H "Title: $(header_text "$TITLE")" -H "Message: $(header_text "$MESSAGE")"
    [ -n "$PRIO" ] && set -- "$@" -H "Priority: $PRIO"
    [ -n "$TAGS" ] && set -- "$@" -H "Tags: $TAGS"
    [ -n "$CLICK" ] && set -- "$@" -H "Click: $CLICK"
    if [ -n "$ACTIONS" ] && [ -n "$CMD_TOPIC" ]; then
        header=""
        while IFS= read -r a; do
            [ -n "$a" ] || continue
            header="$header${header:+; }http, ${a%%=*}, $NTFY_SERVER/$CMD_TOPIC, method=POST, body=${a#*=}, clear=$(button_clears "${a#*=}")"
        done <<EOF
$ACTIONS
EOF
        set -- "$@" -H "Actions: $header"
    fi
    $CURL "$@" "$NTFY_SERVER/$EVENTS_TOPIC" >/dev/null 2>&1
    exit 0
fi

json="{\"topic\":\"$(json_escape "$EVENTS_TOPIC")\",\"title\":\"$(json_escape "$TITLE")\",\"message\":\"$(json_escape "$MESSAGE")\""
[ -n "$PRIO" ] && json="$json,\"priority\":$PRIO"
if [ -n "$TAGS" ]; then
    list=""
    for t in $(printf '%s' "$TAGS" | tr ',' ' '); do
        list="$list${list:+,}\"$(json_escape "$t")\""
    done
    json="$json,\"tags\":[$list]"
fi
[ -n "$CLICK" ] && json="$json,\"click\":\"$(json_escape "$CLICK")\""
if [ -n "$ACTIONS" ] && [ -n "$CMD_TOPIC" ]; then
    list=""
    while IFS= read -r a; do
        [ -n "$a" ] || continue
        list="$list${list:+,}{\"action\":\"http\",\"label\":\"$(json_escape "${a%%=*}")\",\"url\":\"$(json_escape "$NTFY_SERVER/$CMD_TOPIC")\",\"method\":\"POST\",\"body\":\"$(json_escape "${a#*=}")\",\"clear\":$(button_clears "${a#*=}")}"
    done <<EOF
$ACTIONS
EOF
    json="$json,\"actions\":[$list]"
fi
json="$json}"
$CURL -sS --max-time 15 -H "Content-Type: application/json" -d "$json" "$NTFY_SERVER" >/dev/null 2>&1
exit 0
