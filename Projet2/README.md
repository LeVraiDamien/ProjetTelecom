# Project 1 — Network Deployment, Measurement, and Observability
## Scenario B — Advanced Software-Based 5G Telecommunications Network

**Status: Step 1 and Step 2 complete. Step 3 not yet started.**

Full report: [**REPORT.md**](REPORT.md)

## Repository structure

```
.
├── README.md
├── REPORT.md                              # Full technical report (work in progress)
├── ngc.yaml                                # 5G Core deployment (13 network functions)
├── gnb1.yaml                               # gNB + 3 simulated UEs
├── app.yaml                                # N6 data network: Nginx + iperf3
├── register_subscriber.sh                  # Subscriber provisioning script
├── config/
│   └── smf.yaml                            # SMF configuration (N4/PFCP, UE IP pool)
└── evidence/
    ├── registration-sequence-full.log      # Core + RAN logs for one registration cycle
    ├── n2-n3-n4-summary.txt                # tcpdump text summary: N2 (SCTP) + N4 (PFCP)
    ├── n3-summary.txt                      # tcpdump text summary: N3 (GTP-U)
    ├── gtp-u-encapsulation-wireshark.png   # Wireshark: ICMP inside GTP-U
    ├── n6-tcp-via-5g-wireshark.png         # Wireshark: TCP/HTTP session inside GTP-U
    ├── n6-udp-iperf3.txt                   # iperf3 UDP run through the 5G path
    ├── sba-nrf-scp.log                     # NRF + SCP logs (registration, discovery, heartbeats)
    └── sba-startup-2026-10-06.txt          # Time-sorted NRF/SCP startup excerpt
```

This base was deployed from [Gradiant/openverso-images](https://github.com/Gradiant/openverso-images) (`docs/open5gs-and-ueransim`), using the same `gradiant/open5gs` and `gradiant/ueransim` images referenced in the course material.

## Quick start

```bash
docker compose -f ngc.yaml up -d
./register_subscriber.sh
docker compose -f gnb1.yaml up -d
docker compose -f app.yaml up -d
```

User-plane tests must be bound to the UE tunnel (`ping -I uesimtun0`, `curl --interface uesimtun0`), otherwise traffic leaves through the container's `eth0` and bypasses the 5G core.

See [REPORT.md](REPORT.md) for the full topology, proof of operation, protocol analysis (N2, N3, N4, N6, SBI), and the two diagnosed incidents.
