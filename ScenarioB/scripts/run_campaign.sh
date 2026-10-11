#!/bin/bash
# run_campaign.sh - full Step 3 measurement campaign, Scenario B
#
# Usage:  ./run_campaign.sh 2>&1 | tee ../results/campaign.log
#
# 1. Stops systemd-timesyncd for the duration of the campaign: its clock steps
#    (> 0.4 s) trigger UERANSIM radio link failures. Restarted automatically at the end.
# 2. Starts clock_monitor.py, so the absence of clock jumps during the campaign is proven.
# 3. Archives any previous dataset and starts a fresh one.
# 4. Pre-flight: brings the user plane up, then checks that a +50 ms delay on N3
#    and on N6 really shows up in the RTT measured through uesimtun0.
# 5. Runs every condition in sequence; impairments are always cleared on exit.

set -u
cd "$(dirname "$(readlink -f "$0")")"
RESULTS=../results
mkdir -p "$RESULTS"

sudo -v || exit 1
( while true; do sudo -n true; sleep 50; done ) &   # keep sudo alive for the whole run
KEEPALIVE=$!

cleanup() {
    sudo ./impair.sh clear >/dev/null 2>&1
    sudo systemctl start systemd-timesyncd
    kill "$KEEPALIVE" 2>/dev/null
    echo "$(date -Iseconds)  campaign end (impairments cleared, timesyncd restarted)" >> "$RESULTS/incidents.log"
    echo "Cleanup done: impairments cleared, time synchronisation restarted."
}
trap cleanup EXIT

# --- 1-2. Clock ------------------------------------------------------------
sudo systemctl stop systemd-timesyncd
pgrep -f clock_monitor.py >/dev/null || { nohup python3 clock_monitor.py >/dev/null 2>&1 & }
echo "$(date -Iseconds)  campaign start (timesyncd stopped)" >> "$RESULTS/incidents.log"

# --- 3. Fresh dataset ------------------------------------------------------
if [ -f "$RESULTS/dataset.csv" ]; then
    mv "$RESULTS/dataset.csv" "$RESULTS/dataset-archived-$(date +%Y%m%d-%H%M%S).csv"
    echo "Previous dataset archived."
fi

# --- 4. Pre-flight ---------------------------------------------------------
python3 measure.py preflight none --reps 0 || exit 1

ue_rtt() {
    docker exec open5gs-and-ueransim-ues1-1 ping -I uesimtun0 -c 5 -i 0.2 nginx 2>/dev/null \
        | awk -F'/' '/^rtt/ {print $5}'
}
echo "Pre-flight without impairment: RTT = $(ue_rtt) ms"
for loc in N3 N6; do
    sudo ./impair.sh "$loc" delay 50ms >/dev/null
    r=$(ue_rtt)
    sudo ./impair.sh clear >/dev/null
    echo "Pre-flight $loc +50 ms: RTT = ${r:-no reply} ms"
    awk -v r="${r:-0}" 'BEGIN { exit !(r > 40) }' || {
        echo "ABORT: the impairment on $loc has no visible effect on the user plane."; exit 1; }
done

# --- 5. Campaign -----------------------------------------------------------
run() {   # label location udp_rate [netem parameters...]
    local label=$1 loc=$2 rate=$3; shift 3
    echo
    echo "===== $label | $loc | UDP $rate | $(date +%H:%M:%S) ====="
    if [ "$loc" != none ]; then
        sudo ./impair.sh "$loc" "$@" || exit 1
    fi
    python3 measure.py "$label" "$loc" --udp-rate "$rate" || exit 1
    sudo ./impair.sh clear >/dev/null
    sleep 5   # let queues drain before the next condition
}

run baseline        none 10M
run delay50ms       N3   10M delay 50ms
run delay50ms       N6   10M delay 50ms
run loss1pct        N3   10M loss 1%
run loss1pct        N6   10M loss 1%
run baseline-udp30  none 30M
run rate20mbit      N3   30M rate 20mbit
run rate20mbit      N6   30M rate 20mbit
run recovery        none 10M

echo
echo "Campaign finished at $(date +%H:%M:%S)."
