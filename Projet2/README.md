# Project 1 — Network Deployment, Measurement, and Observability
## Scenario B — Advanced Software-Based 5G Telecommunications Network

**Status: Step 1 complete. Step 2 partially complete (N2, N3, N4 documented; N6/application traffic pending). Step 3 not yet started.**

Full report: [**REPORT.md**](REPORT.md)

## Repository structure

```
.
├── README.md
├── REPORT.md                              # Full technical report (work in progress)
├── ngc.yaml                                # 5G Core deployment (13 network functions)
├── gnb1.yaml                               # gNB + 3 simulated UEs
├── register_subscriber.sh                  # Subscriber provisioning script
├── config/
│   └── smf.yaml                            # SMF configuration (N4/PFCP, UE IP pool)
└── evidence/
    ├── registration-sequence-full.log      # Core + RAN logs for one registration cycle
    ├── n2-n3-n4-summary.txt                # tcpdump text summary: N2 (SCTP) + N4 (PFCP)
    ├── n3-summary.txt                      # tcpdump text summary: N3 (GTP-U)
    └── gtp-u-encapsulation-wireshark.png   # Wireshark screenshot: GTP-U inner/outer packet
```

This base was deployed from [Gradiant/openverso-images](https://github.com/Gradiant/openverso-images) (`docs/open5gs-and-ueransim`), using the same `gradiant/open5gs` and `gradiant/ueransim` images referenced in the course material.

## Quick start

```bash
docker compose -f ngc.yaml up -d
./register_subscriber.sh
docker compose -f gnb1.yaml up -d
```

See [REPORT.md](REPORT.md) for the full topology, proof of operation, protocol analysis, and known gaps still to complete.
