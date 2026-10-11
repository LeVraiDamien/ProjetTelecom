# Project 1 — Network Deployment, Measurement, and Observability

**Scenario A**: simplified software-based network (Linux network namespaces + veth) hybridized with a containerized application service (Nginx via Docker), deployed under WSL2.

Full report: [**REPORT.md**](REPORT.md)

## Repository structure

```
.
├── README.md
├── REPORT.md              # Full technical report (Steps 1, 2, 3)
├── setup.sh                # Rebuilds the entire topology: namespaces + veth + Nginx container
├── testStep3.sh             # Performance measurement suite (baseline / degraded conditions)
├── get-docker.sh            # Official Docker install script (reference)
└── assets/                  # Comparison charts referenced in the report
```

## Quick start

```bash
chmod +x setup.sh testStep3.sh
./setup.sh
```

See [REPORT.md](REPORT.md) for full details: topology, proof of operation, traffic captures (ICMP/TCP/UDP/HTTP), and performance measurements under degraded conditions (delay, loss, rate limiting).
