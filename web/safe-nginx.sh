#!/bin/sh
# The child's raw stdout/stderr enter only this pipe, never the Docker log driver.
set -u
fifo=/tmp/opspilot-nginx-log
rm -f "$fifo"
mkfifo -m 600 "$fifo" || exit 1
awk '
function event(kind,reason){printf "{\"event\":\"%s\",\"reason\":\"%s\",\"time\":\"%s\"}\n",kind,reason,strftime("%Y-%m-%dT%H:%M:%SZ");fflush()}
NF==4 && length($1)==32 && $1 ~ /^[0-9a-f]+$/ && $2 ~ /^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$/ && $3 ~ /^[0-9][0-9][0-9]$/ && $4 ~ /^[0-9.]+$/ && length($4)<16 {
 printf "{\"event\":\"proxy.access\",\"request_id\":\"%s\",\"method\":\"%s\",\"status\":%d,\"duration_seconds\":%s,\"time\":\"%s\"}\n",$1,$2,$3,$4,strftime("%Y-%m-%dT%H:%M:%SZ");fflush();next
}
/connect\(\) failed|no live upstreams/{event("proxy.error","UPSTREAM_UNAVAILABLE");next}
/upstream timed out/{event("proxy.error","UPSTREAM_TIMEOUT");next}
/SSL_do_handshake|SSL:/{event("proxy.error","TLS_HANDSHAKE");next}
/limiting requests|too large body|client sent/{event("proxy.error","REQUEST_REJECTED");next}
/Permission denied|open\(\).*failed/{event("proxy.error","FILE_ACCESS");next}
/\[error\]|\[crit\]|\[alert\]|\[emerg\]/{event("proxy.error","PROXY_ERROR");next}
{event("proxy.diagnostic","CONTROL_OR_NOTICE")}
' < "$fifo" &
filter_pid=$!
/docker-entrypoint.sh nginx -g 'daemon off;' > "$fifo" 2>&1 &
nginx_pid=$!
trap 'kill -TERM "$nginx_pid" "$filter_pid" 2>/dev/null || true' TERM INT
wait "$nginx_pid"
status=$?
kill "$filter_pid" 2>/dev/null || true
rm -f "$fifo"
exit "$status"
