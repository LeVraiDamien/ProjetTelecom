# Project 1 — Network Deployment, Measurement, and Observability
## Scenario B — Advanced Software-Based 5G Telecommunications Network

A complete 5G Standalone network in Docker (Open5GS core, UERANSIM gNB and UEs, Nginx and iperf3 on N6), observed with logs and packet captures, measured under controlled degradation, and monitored with Prometheus and Grafana.

**Status: Steps 1, 2 and 3 complete.** Full report: [**REPORT.md**](REPORT.md)

User-plane path: `UE → gNB → N3/GTP-U → UPF → N6 → Nginx / iperf3`
Control-plane path: `gNB → N2/NGAP/SCTP → AMF → SMF → N4/PFCP → UPF`, plus the service-based interfaces (NRF, SCP, AUSF, UDM, UDR, PCF).

Deployment base: [Gradiant/openverso-images](https://github.com/Gradiant/openverso-images) (`docs/open5gs-and-ueransim`), same `gradiant/open5gs` and `gradiant/ueransim` images as the course material.

---

## System requirements

- Linux with Docker Engine and the Docker Compose plugin (developed on WSL2, Ubuntu 24.04, kernel 6.18, 8 GB RAM)
- Kernel modules: `sctp` (N2) and `tun` (UE tunnels, UPF)
- `iproute2` (`tc`, NetEm), `nsenter`, `tcpdump`, `curl`, `sudo`
- Python 3 with pandas and Matplotlib (`sudo apt-get install python3-pandas python3-matplotlib`)
- Wireshark (optional, for GTP-U decoding)

## Repository structure

```
.
├── README.md
├── REPORT.md                       # full technical report (Steps 1-3, diagnoses, limitations)
├── ngc.yaml                        # 5G core: AMF, AUSF, BSF, MongoDB, NRF, NSSF, PCF, SCP, SMF, UDM, UDR, UPF, WebUI
├── gnb1.yaml                       # gNB + 3 simulated UEs
├── app.yaml                        # N6 data network: Nginx + iperf3
├── monitoring.yaml                 # Prometheus, Pushgateway, cAdvisor, Grafana
├── register_subscriber.sh          # subscriber provisioning in MongoDB (+ open5gs-dbctl)
├── config/smf.yaml                 # SMF: N4/PFCP, UE pool 10.45.0.0/16, MTU 1400
├── monitoring/                     # prometheus.yml, Grafana datasource + dashboard (provisioned)
├── scripts/
│   ├── measure.py                  # measurements for one condition -> results/dataset.csv + Pushgateway
│   ├── impair.sh                   # tc/NetEm impairments on N3 (GTP-U only) or N6
│   ├── run_campaign.sh             # full campaign: pre-flight checks, 9 conditions, cleanup
│   ├── analyze.py                  # pandas/Matplotlib analysis -> summary + figures
│   └── clock_monitor.py            # detects host clock steps (see REPORT §5.2)
├── results/
│   ├── dataset.csv                 # campaign dataset (long format, 2,592 rows)
│   ├── summary.csv, summary.md     # statistical summary per condition
│   ├── figures/                    # RTT, TCP, UDP loss, HTTP distribution, N3 vs N6
│   ├── campaign.log, incidents.log, impairments.log, clock-events.log
│   ├── capture-n3-n6-loss1pct.pcap # N3 + N6 capture during 1 % loss on N3 (headers only)
│   └── dataset-archived-*.csv      # earlier baseline (6 Oct), superseded by the campaign, kept for history
└── evidence/                       # Step 2 logs and captures, Wireshark and Grafana screenshots
```

## Deployment

All compose files must use the same project name: the scripts address containers by name (`open5gs-and-ueransim-*`).

```bash
export COMPOSE_PROJECT_NAME=open5gs-and-ueransim
sudo modprobe sctp

docker compose -f ngc.yaml up -d
./register_subscriber.sh
docker compose -f gnb1.yaml up -d
docker compose -f app.yaml up -d
docker compose -f monitoring.yaml up -d
```

## Verification

User-plane tests must be bound to the UE tunnel; otherwise the traffic leaves the UE container through `eth0` and bypasses the 5G core (REPORT §3.5).

```bash
docker exec open5gs-and-ueransim-ues1-1 ip -4 addr show uesimtun0      # PDU session address 10.45.0.x
docker exec open5gs-and-ueransim-ues1-1 ping -I uesimtun0 -c 4 nginx
docker exec open5gs-and-ueransim-ues1-1 curl -s -o /dev/null -w "%{http_code}\n" --interface uesimtun0 http://nginx
sudo tcpdump -i br-$(docker network inspect open5gs-and-ueransim_default -f '{{.Id}}' | cut -c1-12) -n udp port 2152   # GTP-U on N3
```

An `UP` tunnel interface is not proof of a working path: after a radio link failure, `uesimtun0` keeps its address while the UE is detached (REPORT §5.2). Restart the UE container to recover.

## Measurement procedure

```bash
cd scripts
python3 measure.py baseline none              # 3 repetitions: ping, TCP, UDP, HTTP through uesimtun0
python3 measure.py delay50ms N3               # label + location of the impairment currently applied
python3 measure.py rate20mbit N6 --udp-rate 30M
```

Each repetition records 50 pings, a 10 s downlink TCP test, a 10 s downlink UDP test at a fixed offered rate, and 20 HTTP requests. The script checks the user plane before and after every repetition and restarts the UE if needed (logged in `results/incidents.log`).

## Impairment procedure

```bash
sudo ./impair.sh N3 delay 50ms     # UPF egress, GTP-U packets only (UDP dport 2152)
sudo ./impair.sh N6 loss 1%        # egress of the Nginx and iperf3 containers
sudo ./impair.sh N3 rate 20mbit
sudo ./impair.sh show              # qdiscs, filter and counters
sudo ./impair.sh clear
```

Full campaign (≈20 min, keep the machine awake):

```bash
./run_campaign.sh 2>&1 | tee ../results/campaign.log
```

It stops `systemd-timesyncd` for the duration (its clock steps break the UERANSIM radio link on WSL2), starts `clock_monitor.py`, archives the previous dataset, validates both impairment locations (+50 ms must appear in the RTT), runs the 9 conditions, and always clears impairments and restores time synchronisation on exit.

## Data analysis

```bash
python3 analyze.py
```

Reads `results/dataset.csv`, writes `results/summary.csv`, `results/summary.md` and five figures in `results/figures/`.

## Monitoring

Grafana: http://localhost:3000 (admin / admin), dashboard **"Step 3 - 5G user-plane measurement campaign"** (provisioned, UTC, preset to the campaign window). Prometheus: http://localhost:9090. If `localhost` does not answer from a Windows browser, use the WSL address (`hostname -I`).

## Expected outputs

| Condition | RTT | TCP downlink | UDP loss | HTTP median |
|---|---|---|---|---|
| baseline | ~3 ms | ~1.05 Gbit/s | 0 % | ~1.6 ms |
| delay 50 ms (N3 / N6) | ~54 ms | ~24 / ~130 Mbit/s | 0 % | ~106 ms |
| loss 1 % (N3 / N6) | ~3 ms | ~235 / ~685 Mbit/s | ~1 % | ~1.5 ms |
| rate 20 Mbit/s (N3 / N6), UDP 30M | ~2.5 ms | 18.5 / 19.1 Mbit/s | ~31 / ~30 % | ~2.2 ms |

Absolute throughputs depend on the CPU of the host, since the gNB and the UPF process every packet in user space.

## Known limitations

- Single Docker bridge: N3, N4 and N6 share the UPF's `eth0`, so N3 impairments use a port filter and N6 impairments are applied on the servers; both act on the downlink only.
- Container IP addresses change across restarts; captures filter by port.
- WSL2 clock steps cause UERANSIM radio link failures; measure with `systemd-timesyncd` stopped (done by `run_campaign.sh`).
- UERANSIM does not recover from a radio link failure on its own (stale UE context at the gNB); the UE must be restarted.
- cAdvisor exports only host-level counters in this setup; Open5GS UPF N3 packet counters stay at 0.
- The low TCP throughput under delay on N3 is not fully explained (REPORT §4.7).
