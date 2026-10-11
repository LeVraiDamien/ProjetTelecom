#!/usr/bin/env python3
"""Step 3 analysis - Scenario B.

Reads ../results/dataset.csv (long format written by measure.py) and produces:
  ../results/summary.csv            one row per (condition, location): mean / std / median
  ../results/summary.md             the same table in Markdown, ready for the report
  ../results/figures/*.png          comparison figures

Notes on the data:
  - UDP 'received_mbps' as recorded is the SENDER-side rate (iperf3 -R JSON field);
    the delivered throughput is therefore recomputed as offered x (1 - loss/100).
    Loss and jitter come from the receiver side and are correct.
  - HTTP response time is analysed per request (60 samples per condition): the median
    is reported next to the mean because a few retransmission timeouts dominate the mean.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "..", "results")
FIGS = os.path.join(RESULTS, "figures")
os.makedirs(FIGS, exist_ok=True)

ORDER = [("baseline", "none"), ("delay50ms", "N3"), ("delay50ms", "N6"),
         ("loss1pct", "N3"), ("loss1pct", "N6"), ("baseline-udp30", "none"),
         ("rate20mbit", "N3"), ("rate20mbit", "N6"), ("recovery", "none")]
LABELS = {("baseline", "none"): "Baseline",
          ("delay50ms", "N3"): "Delay 50 ms\nN3", ("delay50ms", "N6"): "Delay 50 ms\nN6",
          ("loss1pct", "N3"): "Loss 1 %\nN3", ("loss1pct", "N6"): "Loss 1 %\nN6",
          ("baseline-udp30", "none"): "Baseline\n(UDP 30M)",
          ("rate20mbit", "N3"): "Rate 20 Mbit/s\nN3", ("rate20mbit", "N6"): "Rate 20 Mbit/s\nN6",
          ("recovery", "none"): "Recovery"}
COLORS = {"none": "#7f7f7f", "N3": "#1f77b4", "N6": "#ff7f0e"}

df = pd.read_csv(os.path.join(RESULTS, "dataset.csv"))
df = df[df.condition != "preflight"]

# ---------------------------------------------------------------- per repetition
def per_rep(test, metric):
    s = df[(df.test == test) & (df.metric == metric)]
    return s.groupby(["condition", "location", "repetition"]).value.mean()

reps = pd.DataFrame({
    "rtt_ms": per_rep("icmp", "rtt_avg"),
    "icmp_loss_pct": per_rep("icmp", "loss_pct"),
    "tcp_mbps": per_rep("tcp", "receiver_mbps"),
    "tcp_retransmits": per_rep("tcp", "retransmits"),
    "udp_offered_mbps": per_rep("udp", "offered_mbps"),
    "udp_loss_pct": per_rep("udp", "loss_pct"),
    "udp_jitter_ms": per_rep("udp", "jitter_ms"),
})
reps["udp_delivered_mbps"] = reps.udp_offered_mbps * (1 - reps.udp_loss_pct / 100)

# HTTP: per request
http = df[(df.test == "http") & (df.metric == "http_total_ms")]
http_ok = df[(df.test == "http") & (df.metric == "http_success")]

# ---------------------------------------------------------------- summary table
rows = []
for cond, loc in ORDER:
    r = reps.loc[(cond, loc)]
    h = http[(http.condition == cond) & (http.location == loc)].value
    ok = http_ok[(http_ok.condition == cond) & (http_ok.location == loc)].value
    rows.append({
        "condition": cond, "location": loc,
        "rtt_ms_mean": r.rtt_ms.mean(), "rtt_ms_std": r.rtt_ms.std(),
        "tcp_mbps_mean": r.tcp_mbps.mean(), "tcp_mbps_std": r.tcp_mbps.std(),
        "tcp_retr_mean": r.tcp_retransmits.mean(),
        "udp_offered_mbps": r.udp_offered_mbps.mean(),
        "udp_delivered_mbps": r.udp_delivered_mbps.mean(),
        "udp_loss_pct_mean": r.udp_loss_pct.mean(),
        "udp_jitter_ms_mean": r.udp_jitter_ms.mean(),
        "http_ms_mean": h.mean(), "http_ms_median": h.median(),
        "http_ms_p95": h.quantile(0.95), "http_ms_max": h.max(),
        "http_success_pct": 100 * ok.mean(),
    })
summary = pd.DataFrame(rows)
summary.to_csv(os.path.join(RESULTS, "summary.csv"), index=False)

def fmt(v, d=2):
    return f"{v:,.{d}f}"

md = ["| Condition | Location | RTT (ms) | TCP (Mbit/s) | TCP retr. | UDP offered / delivered (Mbit/s) | UDP loss (%) | UDP jitter (ms) | HTTP median / mean / p95 (ms) | HTTP success |",
      "|---|---|---|---|---|---|---|---|---|---|"]
for s in summary.itertuples():
    md.append(f"| {s.condition} | {s.location} | {fmt(s.rtt_ms_mean)} ± {fmt(s.rtt_ms_std)} | "
              f"{fmt(s.tcp_mbps_mean, 1)} ± {fmt(s.tcp_mbps_std, 1)} | {fmt(s.tcp_retr_mean, 0)} | "
              f"{fmt(s.udp_offered_mbps, 0)} / {fmt(s.udp_delivered_mbps)} | {fmt(s.udp_loss_pct_mean)} | "
              f"{fmt(s.udp_jitter_ms_mean, 3)} | {fmt(s.http_ms_median)} / {fmt(s.http_ms_mean)} / {fmt(s.http_ms_p95)} | "
              f"{fmt(s.http_success_pct, 0)} % |")
with open(os.path.join(RESULTS, "summary.md"), "w") as f:
    f.write("Mean ± standard deviation over 3 repetitions; HTTP statistics over 60 requests.\n\n")
    f.write("\n".join(md) + "\n")

# ---------------------------------------------------------------- figures
x = np.arange(len(ORDER))
labels = [LABELS[k] for k in ORDER]
colors = [COLORS[loc] for _, loc in ORDER]

def bar(metric_mean, metric_std, ylabel, title, fname, log=False):
    fig, ax = plt.subplots(figsize=(11, 5))
    means = summary[metric_mean].values
    stds = summary[metric_std].values if metric_std else None
    ax.bar(x, means, yerr=stds, capsize=4, color=colors)
    if log:
        ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3, which="both")
    for i, v in enumerate(means):
        ax.text(i, v, f"{v:,.1f}", ha="center", va="bottom", fontsize=8)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS.values()]
    ax.legend(handles, ["No impairment", "Impairment on N3", "Impairment on N6"], fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, fname), dpi=150)
    plt.close(fig)

bar("rtt_ms_mean", "rtt_ms_std", "RTT (ms)", "ICMP RTT through the 5G user plane", "rtt.png")
bar("tcp_mbps_mean", "tcp_mbps_std", "TCP throughput (Mbit/s, log scale)",
    "Downlink TCP throughput through the 5G user plane", "tcp_throughput.png", log=True)
bar("udp_loss_pct_mean", None, "UDP loss (%)",
    "Downlink UDP loss (10 Mbit/s offered, 30 Mbit/s for rate-limit runs)", "udp_loss.png")

# HTTP distribution (box plot, log scale): shows the retransmission-timeout outliers
fig, ax = plt.subplots(figsize=(11, 5))
data = [http[(http.condition == c) & (http.location == l)].value.values for c, l in ORDER]
bp = ax.boxplot(data, patch_artist=True, showfliers=True)
for patch, c in zip(bp["boxes"], colors):
    patch.set_facecolor(c)
    patch.set_alpha(0.6)
ax.set_yscale("log")
ax.set_xticks(x + 1)
ax.set_xticklabels(labels, fontsize=9)
ax.set_ylabel("HTTP response time (ms, log scale)")
ax.set_title("HTTP response time per request (60 requests per condition)")
ax.grid(axis="y", alpha=0.3, which="both")
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "http_response_time.png"), dpi=150)
plt.close(fig)

# Key finding: same impairment, different location -> TCP throughput
fig, ax = plt.subplots(figsize=(8, 5))
groups = [("delay50ms", "Delay 50 ms"), ("loss1pct", "Loss 1 %"), ("rate20mbit", "Rate 20 Mbit/s")]
w = 0.35
for j, (loc, off) in enumerate([("N3", -w / 2), ("N6", w / 2)]):
    vals = [summary[(summary.condition == g) & (summary.location == loc)].tcp_mbps_mean.iloc[0] for g, _ in groups]
    errs = [summary[(summary.condition == g) & (summary.location == loc)].tcp_mbps_std.iloc[0] for g, _ in groups]
    ax.bar(np.arange(3) + off, vals, w, yerr=errs, capsize=4, color=COLORS[loc], label=f"Impairment on {loc}")
    for i, v in enumerate(vals):
        ax.text(i + off, v, f"{v:,.1f}", ha="center", va="bottom", fontsize=8)
base = summary[summary.condition == "baseline"].tcp_mbps_mean.iloc[0]
ax.axhline(base, color="#7f7f7f", ls="--", lw=1, label=f"Baseline ({base:,.0f} Mbit/s)")
ax.set_yscale("log")
ax.set_xticks(np.arange(3))
ax.set_xticklabels([g for _, g in groups])
ax.set_ylabel("TCP throughput (Mbit/s, log scale)")
ax.set_title("Same impairment, different location: N3 vs N6")
ax.legend(fontsize=8)
ax.grid(axis="y", alpha=0.3, which="both")
fig.tight_layout()
fig.savefig(os.path.join(FIGS, "n3_vs_n6_tcp.png"), dpi=150)
plt.close(fig)

print(open(os.path.join(RESULTS, "summary.md")).read())
print(f"Figures written to {os.path.normpath(FIGS)}")
