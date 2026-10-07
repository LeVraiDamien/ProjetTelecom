#!/bin/bash
# impair.sh - controlled network degradation for Step 3 (Scenario B)
#
# Usage (root required for nsenter):
#   sudo ./impair.sh N3 <netem parameters>   e.g. delay 50ms | loss 1% | rate 20mbit
#   sudo ./impair.sh N6 <netem parameters>
#   sudo ./impair.sh clear
#   sudo ./impair.sh show
#
# All components share one Docker bridge, so the UPF has a single eth0 that
# carries N3, N4 and N6 at the same time. Impairments are therefore scoped:
#   N3 : UPF eth0 egress, ONLY GTP-U packets (UDP dport 2152) -> downlink gNB-bound traffic
#   N6 : Nginx and iperf3 eth0 egress (these containers only carry N6 traffic) -> downlink
# Both locations act on the downlink direction, so they are directly comparable.

set -e

PROJECT=open5gs-and-ueransim
UPF=${PROJECT}-upf-1
N6_SERVERS="${PROJECT}-nginx-1 ${PROJECT}-iperf3-1"
LOG="$(dirname "$(readlink -f "$0")")/../results/impairments.log"
PUSHGATEWAY=http://localhost:9091/metrics/job/impairment

pid()   { docker inspect -f '{{.State.Pid}}' "$1"; }
in_ns() { local c=$1; shift; nsenter -t "$(pid "$c")" -n "$@"; }

clear_all() {
    for c in $UPF $N6_SERVERS; do
        in_ns "$c" tc qdisc del dev eth0 root 2>/dev/null || true
    done
}

# Publish the configured impairment to Grafana (PUT replaces the previous state)
push_state() {   # location delay_ms loss_pct rate_mbit
    curl -s -X PUT --data-binary @- "$PUSHGATEWAY" >/dev/null <<EOF || true
impairment_delay_ms{location="$1"} $2
impairment_loss_pct{location="$1"} $3
impairment_rate_mbit{location="$1"} $4
EOF
}

log() {
    mkdir -p "$(dirname "$LOG")"
    echo "$(date -Iseconds)  $*" >> "$LOG"
    [ -n "$SUDO_USER" ] && chown "$SUDO_USER:$SUDO_USER" "$LOG" "$(dirname "$LOG")" 2>/dev/null || true
}

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo (nsenter needs root)."; exit 1
fi

case "$1" in
    clear)
        clear_all
        push_state none 0 0 0
        log "clear"
        echo "All impairments removed."
        exit 0 ;;
    show)
        for c in $UPF $N6_SERVERS; do
            echo "=== $c ==="
            in_ns "$c" tc -s qdisc show dev eth0
            in_ns "$c" tc filter show dev eth0 2>/dev/null || true
        done
        exit 0 ;;
    N3|N6) LOCATION=$1; shift ;;
    *) echo "Usage: $0 N3|N6 <netem params> | clear | show"; exit 1 ;;
esac

[ $# -gt 0 ] || { echo "Missing netem parameters (e.g. delay 50ms)"; exit 1; }

# Numeric values for Grafana
DELAY=0; LOSS=0; RATE=0
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
    v=${args[$((i + 1))]:-}
    case "${args[$i]}" in
        delay) DELAY=${v%ms} ;;
        loss)  LOSS=${v%\%} ;;
        rate)  v=${v,,}
               case "$v" in
                   *mbit) RATE=${v%mbit} ;;
                   *kbit) RATE=$(awk "BEGIN{print ${v%kbit}/1000}") ;;
                   *)     RATE=$v ;;
               esac ;;
    esac
done

clear_all   # never stack impairments

if [ "$LOCATION" = N3 ]; then
    # 4-band prio: the default priomap only uses bands 1-3, so band 4 receives
    # nothing except what the filter explicitly sends to it (GTP-U).
    in_ns $UPF tc qdisc add dev eth0 root handle 1: prio bands 4 \
        priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1
    in_ns $UPF tc qdisc add dev eth0 parent 1:4 handle 40: netem "$@"
    in_ns $UPF tc filter add dev eth0 parent 1: protocol ip prio 1 u32 \
        match ip protocol 17 0xff match ip dport 2152 0xffff flowid 1:4
else
    for c in $N6_SERVERS; do
        in_ns "$c" tc qdisc add dev eth0 root netem "$@"
    done
fi

push_state "$LOCATION" "$DELAY" "$LOSS" "$RATE"
log "$LOCATION netem $*"
echo "Applied on $LOCATION: netem $*"
