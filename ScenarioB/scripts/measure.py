#!/usr/bin/env python3
"""Step 3 measurement runner - Scenario B (5G SA, Open5GS + UERANSIM).

Usage:
    python3 measure.py <condition> <location> [--reps 3] [--udp-rate 10M]

    condition : free label, e.g. baseline, delay50ms, loss1pct, rate20mbit
    location  : where the impairment is applied: none, N3 or N6

Every test runs on the complete user-plane path, bound to the UE tunnel:
    UE (uesimtun0) -> gNB -> N3/GTP-U -> UPF -> N6 -> Nginx / iperf3

TCP and UDP tests use iperf3 -R (server -> UE, downlink), so that the data
crosses the segments where impairments are applied (UPF egress towards the
gNB for N3, server egress towards the UPF for N6).

Results are appended to ../results/dataset.csv (long format, one row per
measured value) and pushed to the Prometheus Pushgateway for Grafana.
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATASET = os.path.join(HERE, "..", "results", "dataset.csv")
PUSHGATEWAY = "http://localhost:9091/metrics/job/measure"
UE_CONTAINER = "open5gs-and-ueransim-ues1-1"
INCIDENTS = os.path.join(HERE, "..", "results", "incidents.log")
MAX_RECOVERIES = 3

PING_COUNT = 50          # 50 probes, 0.2 s apart
TEST_DURATION = 10       # seconds, for iperf3
HTTP_REQUESTS = 20       # requests per repetition

FIELDS = ["timestamp", "condition", "location", "repetition", "test",
          "sample", "metric", "value", "unit"]


# --------------------------------------------------------------------------
# Execution inside the UE container
# --------------------------------------------------------------------------
def ue(cmd, timeout=TEST_DURATION + 30):
    full = ["docker", "exec", UE_CONTAINER] + cmd
    r = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout


def ue_ip():
    _, out = ue(["ip", "-4", "-o", "addr", "show", "uesimtun0"])
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
    if not m:
        raise SystemExit("uesimtun0 has no IPv4 address: is the PDU session up?")
    return m.group(1)


def user_plane_alive():
    """Quick check through the tunnel: an interface that is UP with an IP address
    does not prove the UE is still attached (radio link failure keeps uesimtun0 up)."""
    _, out = ue(["ping", "-I", "uesimtun0", "-c", "3", "-W", "2", "nginx"], timeout=30)
    m = re.search(r"(\d+) received", out)
    return bool(m) and int(m.group(1)) > 0


def incident(text):
    os.makedirs(os.path.dirname(INCIDENTS), exist_ok=True)
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')}  {text}"
    with open(INCIDENTS, "a") as f:
        f.write(line + "\n")
    print(f"  ! {text}")


def recover(reason):
    """UERANSIM does not recover from a radio link failure on its own (the gNB keeps
    the stale UE context and discards the new RRC Setup Request), so the only reliable
    fix is a UE restart, which forces a fresh registration and PDU session."""
    incident(f"user plane down ({reason}) -> restarting UE")
    subprocess.run(["docker", "restart", UE_CONTAINER], capture_output=True, timeout=60)
    for _ in range(30):                      # up to ~60 s
        time.sleep(2)
        try:
            ip = ue_ip()
        except SystemExit:
            continue
        if user_plane_alive():
            incident(f"user plane restored, new UE address {ip}")
            return ip
    raise SystemExit("ABORT: user plane could not be restored after a UE restart.")


# --------------------------------------------------------------------------
# Parsers (kept separate so they can be tested on saved outputs)
# --------------------------------------------------------------------------
def parse_ping(out):
    res = {}
    m = re.search(r"(\d+) packets transmitted, (\d+) received.*?([\d.]+)% packet loss", out)
    if m:
        res["packets_tx"] = (int(m.group(1)), "count")
        res["packets_rx"] = (int(m.group(2)), "count")
        res["loss_pct"] = (float(m.group(3)), "%")
    m = re.search(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", out)
    if m:
        for k, v in zip(["rtt_min", "rtt_avg", "rtt_max", "rtt_mdev"], m.groups()):
            res[k] = (float(v), "ms")
    return res


def _pick(end, key):
    for part in ("sum_received", "sum"):
        if part in end and key in end[part]:
            return end[part][key]
    return None


def parse_iperf_tcp(out):
    d = json.loads(out)
    if "error" in d:
        raise RuntimeError(d["error"])
    end = d["end"]
    return {
        "sender_mbps": (end["sum_sent"]["bits_per_second"] / 1e6, "Mbit/s"),
        "receiver_mbps": (end["sum_received"]["bits_per_second"] / 1e6, "Mbit/s"),
        "retransmits": (end["sum_sent"].get("retransmits", 0), "count"),
        "bytes": (end["sum_received"]["bytes"], "bytes"),
    }


def parse_iperf_udp(out, offered_mbps):
    d = json.loads(out)
    if "error" in d:
        raise RuntimeError(d["error"])
    end = d["end"]
    return {
        "offered_mbps": (offered_mbps, "Mbit/s"),
        # in reverse mode iperf3 reports the SENDER rate here: derive the delivered rate
        "received_mbps": (_pick(end, "bits_per_second") / 1e6
                          * (1 - (_pick(end, "lost_percent") or 0) / 100), "Mbit/s"),
        "loss_pct": (_pick(end, "lost_percent"), "%"),
        "jitter_ms": (_pick(end, "jitter_ms"), "ms"),
        "packets": (_pick(end, "packets"), "count"),
    }


def parse_http(out):
    """One line per request: code connect_s total_s size_bytes."""
    rows = []
    for line in out.strip().splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        code, connect, total, size = parts
        rows.append({
            "http_success": (1 if code == "200" else 0, "bool"),
            "http_connect_ms": (float(connect) * 1000, "ms"),
            "http_total_ms": (float(total) * 1000, "ms"),
            "http_size": (float(size), "bytes"),
        })
    return rows


def rate_to_mbps(rate):
    m = re.fullmatch(r"([\d.]+)([KkMmGg]?)", rate)
    value, unit = float(m.group(1)), m.group(2).upper()
    return value * {"K": 1e-3, "M": 1, "G": 1e3, "": 1e-6}[unit]


# --------------------------------------------------------------------------
# Output: CSV + Pushgateway
# --------------------------------------------------------------------------
def write_rows(rows):
    os.makedirs(os.path.dirname(DATASET), exist_ok=True)
    new = not os.path.exists(DATASET)
    with open(DATASET, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)


def push(metrics, condition, location):
    lines = [f'measure_{name}{{condition="{condition}",location="{location}"}} {value}'
             for name, value in metrics.items() if value is not None]
    body = ("\n".join(lines) + "\n").encode()
    try:
        urllib.request.urlopen(urllib.request.Request(PUSHGATEWAY, data=body, method="POST"), timeout=5)
    except Exception as e:  # Grafana is optional: never lose a measurement because of it
        print(f"  (pushgateway unreachable: {e})")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("condition")
    ap.add_argument("location", choices=["none", "N3", "N6"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--udp-rate", default="10M")
    a = ap.parse_args()

    offered = rate_to_mbps(a.udp_rate)
    try:
        ip = ue_ip()
    except SystemExit:
        ip = None
    if ip is None or not user_plane_alive():
        ip = recover(f"{a.condition}/{a.location} before start")
    print(f"Condition={a.condition} location={a.location} UE={ip} reps={a.reps}")

    rep, recoveries = 1, 0
    while rep <= a.reps:
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        rows = []

        def add(test, values, sample=1):
            for metric, (value, unit) in values.items():
                rows.append(dict(timestamp=ts, condition=a.condition, location=a.location,
                                 repetition=rep, test=test, sample=sample,
                                 metric=metric, value=value, unit=unit))

        # Level 1 - network: ICMP RTT and loss
        _, out = ue(["ping", "-I", "uesimtun0", "-c", str(PING_COUNT), "-i", "0.2", "nginx"])
        ping = parse_ping(out)
        add("icmp", ping)

        # Level 2 - transport: TCP (downlink)
        try:
            _, out = ue(["iperf3", "-c", "iperf3", "-B", ip, "-R", "-t", str(TEST_DURATION), "-J"])
            tcp = parse_iperf_tcp(out)
            add("tcp", tcp)
        except Exception as e:
            tcp = {}
            print(f"  TCP test failed: {e}")

        # Level 2 - transport: UDP (downlink, fixed offered rate)
        try:
            _, out = ue(["iperf3", "-c", "iperf3", "-B", ip, "-R", "-u", "-b", a.udp_rate,
                         "-t", str(TEST_DURATION), "-J"])
            udp = parse_iperf_udp(out, offered)
            add("udp", udp)
        except Exception as e:
            udp = {}
            print(f"  UDP test failed: {e}")

        # Level 3 - application: repeated HTTP requests to Nginx
        loop = (f"for i in $(seq 1 {HTTP_REQUESTS}); do "
                "curl -s -o /dev/null -m 5 --interface uesimtun0 "
                "-w '%{http_code} %{time_connect} %{time_total} %{size_download}\\n' "
                "http://nginx; done")
        _, out = ue(["sh", "-c", loop], timeout=HTTP_REQUESTS * 6 + 30)
        http = parse_http(out)
        for i, req in enumerate(http, 1):
            add("http", req, sample=i)

        # A repetition only counts if the user plane was still alive at its end:
        # a radio link failure in the middle would silently corrupt the values.
        if not user_plane_alive():
            recoveries += 1
            if recoveries > MAX_RECOVERIES:
                raise SystemExit("ABORT: too many radio link failures in one condition.")
            incident(f"{a.condition}/{a.location} rep {rep} discarded (link lost during the repetition)")
            ip = recover(f"{a.condition}/{a.location} after rep {rep}")
            continue                          # redo the same repetition

        write_rows(rows)

        n_ok = sum(r["http_success"][0] for r in http)
        ok_times = [r["http_total_ms"][0] for r in http if r["http_success"][0] == 1]
        mean_http = (sum(ok_times) / len(ok_times)) if ok_times else None  # failed requests excluded
        push({
            "rtt_avg_ms": ping.get("rtt_avg", (None,))[0],
            "icmp_loss_pct": ping.get("loss_pct", (None,))[0],
            "tcp_mbps": tcp.get("receiver_mbps", (None,))[0],
            "tcp_retransmits": tcp.get("retransmits", (None,))[0],
            "udp_mbps": udp.get("received_mbps", (None,))[0],
            "udp_loss_pct": udp.get("loss_pct", (None,))[0],
            "udp_jitter_ms": udp.get("jitter_ms", (None,))[0],
            "http_time_ms": mean_http,
            "http_success_rate": (n_ok / len(http)) if http else None,
        }, a.condition, a.location)

        http_str = (f"HTTP {n_ok}/{len(http)} OK, mean {mean_http:.2f} ms" if mean_http is not None
                    else f"HTTP {n_ok}/{len(http)} OK")

        def fmt(d, k, f="{:.2f}"):
            return f.format(d[k][0]) if k in d and d[k][0] is not None else "n/a"

        print(f"  rep {rep}: RTT {fmt(ping, 'rtt_avg')} ms, ICMP loss {fmt(ping, 'loss_pct')} % | "
              f"TCP {fmt(tcp, 'receiver_mbps')} Mbit/s, retr {fmt(tcp, 'retransmits', '{:.0f}')} | "
              f"UDP {fmt(udp, 'received_mbps')}/{offered:g} Mbit/s, loss {fmt(udp, 'loss_pct')} %, "
              f"jitter {fmt(udp, 'jitter_ms', '{:.3f}')} ms | "
              f"{http_str}")
        rep += 1

    print(f"Results appended to {os.path.normpath(DATASET)}")


if __name__ == "__main__":
    main()
