#!/usr/bin/env python3
"""Generate shareable graphs from the SolTerraLuna power-profile overhaul evals."""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent / "images"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Shared style
# ---------------------------------------------------------------------------
plt.rcParams.update(
    {
        "font.size": 12,
        "axes.titlesize": 16,
        "axes.titleweight": "bold",
        "axes.labelsize": 13,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
    }
)

MODELS = ["LUNA", "SOL", "TERRA"]
COLORS = {"LUNA": "#4C9BE8", "SOL": "#F2A04C", "TERRA": "#5CB85C"}
EDGE = "#333333"


def save(fig, name):
    path = OUT / name
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    print(f"  wrote {path}")


# ---------------------------------------------------------------------------
# 1. Final scores — both comparison reports side by side
# ---------------------------------------------------------------------------
def graph_final_scores():
    glm_scores = [87.0, 76.0, 60.0]  # GLM_EVAL_COMPARISON.md
    web_scores = [90.1, 83.7, 79.9]  # SOL_WEB_EVAL_COMPARISON.md

    x = np.arange(len(MODELS))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 5.5))
    b1 = ax.bar(
        x - w / 2,
        glm_scores,
        w,
        label="GLM comparison",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
        alpha=0.65,
    )
    b2 = ax.bar(
        x + w / 2,
        web_scores,
        w,
        label="Web comparison",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
    )

    for bars in (b1, b2):
        for b in bars:
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.8,
                f"{b.get_height():.1f}",
                ha="center",
                va="bottom",
                fontsize=11,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(MODELS)
    ax.set_ylabel("Score (/100)")
    ax.set_title("Final Weighted Scores by Model")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False)
    save(fig, "01_final_scores.png")


# ---------------------------------------------------------------------------
# 2. Findings discovered per model
# ---------------------------------------------------------------------------
def graph_findings_count():
    counts = [14, 9, 7]
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        MODELS, counts, color=[COLORS[m] for m in MODELS], edgecolor=EDGE, width=0.6
    )
    for b, c in zip(bars, counts):
        ax.text(
            b.get_x() + b.get_width() / 2,
            c + 0.2,
            str(c),
            ha="center",
            va="bottom",
            fontsize=14,
            fontweight="bold",
        )
    ax.set_ylabel("Findings")
    ax.set_title("Issues Discovered per Model")
    ax.set_ylim(0, max(counts) + 2)
    save(fig, "02_findings_count.png")


# ---------------------------------------------------------------------------
# 3. Cost analysis — production cost + cost per finding
# ---------------------------------------------------------------------------
def graph_cost_analysis():
    # LUNA uses the first-run investigation cost ($2.11) as the final verdict:
    # the $1.20 re-run only succeeded because it reused cached context from this run.
    prod_cost = [2.11, 1.29, 3.04]  # LUNA, SOL, TERRA
    cost_per_finding = [round(2.11 / 14, 2), round(1.29 / 9, 2), round(3.04 / 7, 2)]

    x = np.arange(len(MODELS))
    w = 0.38
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    bars = ax1.bar(x, prod_cost, w, color=[COLORS[m] for m in MODELS], edgecolor=EDGE)
    for b, c in zip(bars, prod_cost):
        ax1.text(
            b.get_x() + b.get_width() / 2,
            c + 0.05,
            f"${c:.2f}",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )
    ax1.set_xticks(x)
    ax1.set_xticklabels(MODELS)
    ax1.set_ylabel("Production cost (USD)")
    ax1.set_title("Production Run Cost")
    ax1.set_ylim(0, max(prod_cost) + 0.6)

    bars2 = ax2.bar(
        x, cost_per_finding, w, color=[COLORS[m] for m in MODELS], edgecolor=EDGE
    )
    for b, c in zip(bars2, cost_per_finding):
        ax2.text(
            b.get_x() + b.get_width() / 2,
            c + 0.01,
            f"${c:.2f}",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )
    ax2.set_xticks(x)
    ax2.set_xticklabels(MODELS)
    ax2.set_ylabel("Cost per finding (USD)")
    ax2.set_title("Cost per Finding (lower is better)")
    ax2.set_ylim(0, max(cost_per_finding) + 0.08)

    fig.suptitle("Cost Efficiency Analysis", fontsize=16, fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, "03_cost_analysis.png")


# ---------------------------------------------------------------------------
# 4. Scorecard radar chart (7 dimensions)
# ---------------------------------------------------------------------------
def graph_scorecard_radar():
    dims = [
        "Technical\ncorrectness",
        "Coverage &\ndiscovery",
        "Evidence &\nverification",
        "Severity\ncalibration",
        "Architecture\n& context",
        "Fix quality &\nactionability",
        "Clarity &\nefficiency",
    ]
    # From GLM_EVAL_COMPARISON.md scorecard (raw /10)
    data = {
        "LUNA": [9, 9, 9, 8, 9, 8, 7],
        "SOL": [8, 6, 8, 8, 8, 8, 8],
        "TERRA": [6, 5, 6, 6, 7, 6, 8],
    }

    n = len(dims)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    for m in MODELS:
        vals = data[m] + data[m][:1]
        ax.plot(angles, vals, linewidth=2, label=m, color=COLORS[m])
        ax.fill(angles, vals, alpha=0.15, color=COLORS[m])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dims, fontsize=10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=9)
    ax.set_ylim(0, 10)
    ax.set_title(
        "Scorecard by Dimension (GLM comparison, /10)",
        fontsize=14,
        fontweight="bold",
        pad=25,
    )
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.10), frameon=False)
    save(fig, "04_scorecard_radar.png")


# ---------------------------------------------------------------------------
# 5. Unique findings per model
# ---------------------------------------------------------------------------
def graph_unique_findings():
    unique = [6, 2, 1]  # LUNA, SOL, TERRA
    shared = [14 - 6, 9 - 2, 7 - 1]  # non-unique findings

    x = np.arange(len(MODELS))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(
        x,
        unique,
        0.6,
        label="Unique findings",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
    )
    ax.bar(
        x,
        shared,
        0.6,
        bottom=unique,
        label="Shared findings",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
        alpha=0.4,
    )

    for i, (u, s) in enumerate(zip(unique, shared)):
        ax.text(
            i,
            u / 2,
            str(u),
            ha="center",
            va="center",
            fontsize=13,
            fontweight="bold",
            color="white",
        )
        ax.text(
            i, u + s / 2, str(s), ha="center", va="center", fontsize=11, color="white"
        )

    ax.set_xticks(x)
    ax.set_xticklabels(MODELS)
    ax.set_ylabel("Findings")
    ax.set_title("Unique vs Shared Findings per Model")
    ax.legend(frameon=False)
    save(fig, "05_unique_findings.png")


# ---------------------------------------------------------------------------
# 6. Token usage (production sessions)
# ---------------------------------------------------------------------------
def graph_token_usage():
    # production sessions only, in millions of tokens
    # LUNA uses the 18:17 first-run investigation session (the real investigation cost)
    non_cached = [14.14 - 13.79, 0.95 - 0.86, 7.44 - 7.20]  # input - cached
    cached = [13.79, 0.86, 7.20]
    output = [0.063, 0.013, 0.042]

    x = np.arange(len(MODELS))
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar(
        x,
        non_cached,
        0.6,
        label="Non-cached input",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
    )
    ax.bar(
        x,
        cached,
        0.6,
        bottom=non_cached,
        label="Cached input",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
        alpha=0.5,
    )
    ax.bar(
        x,
        output,
        0.6,
        bottom=[a + b for a, b in zip(non_cached, cached)],
        label="Output (incl. reasoning)",
        color="#888888",
        edgecolor=EDGE,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(MODELS)
    ax.set_ylabel("Tokens (millions)")
    ax.set_title("Token Usage — Production Sessions")
    ax.legend(frameon=False, fontsize=10)
    save(fig, "06_token_usage.png")


# ---------------------------------------------------------------------------
# 7. Wasted vs production cost
# ---------------------------------------------------------------------------
def graph_wasted_cost():
    # LUNA's $2.11 first run is counted as production (the real investigation);
    # only file-management sessions ($0.03 + $0.02) remain as wasted.
    prod = [2.11, 1.29, 3.04]
    wasted = [0.05, 0.00, 1.43]

    x = np.arange(len(MODELS))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 5.5))
    b1 = ax.bar(
        x - w / 2,
        prod,
        w,
        label="Production",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
    )
    b2 = ax.bar(
        x + w / 2,
        wasted,
        w,
        label="Wasted",
        color=[COLORS[m] for m in MODELS],
        edgecolor=EDGE,
        alpha=0.4,
        hatch="//",
    )

    for bars in (b1, b2):
        for b in bars:
            if b.get_height() > 0:
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    b.get_height() + 0.04,
                    f"${b.get_height():.2f}",
                    ha="center",
                    va="bottom",
                    fontsize=10,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(MODELS)
    ax.set_ylabel("Cost (USD)")
    ax.set_title("Production vs Wasted Session Cost")
    ax.legend(frameon=False)
    ax.set_ylim(0, max(max(prod), max(wasted)) + 0.6)
    save(fig, "07_wasted_vs_production.png")


# ---------------------------------------------------------------------------
# 8. Severity distribution of findings
# ---------------------------------------------------------------------------
def graph_severity_distribution():
    # LUNA: 2 critical, 6 high, 4 medium, 2 low
    # SOL:  1 critical, 3 high, 3 medium, 2 low
    # TERRA: 1 critical, 2 high, 3 medium, 1 low
    severities = ["Critical", "High", "Medium", "Low"]
    data = {
        "LUNA": [2, 6, 4, 2],
        "SOL": [1, 3, 3, 2],
        "TERRA": [1, 2, 3, 1],
    }
    sev_colors = ["#d62728", "#ff7f0e", "#1f77b4", "#7f7f7f"]

    x = np.arange(len(MODELS))
    w = 0.2
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for i, sev in enumerate(severities):
        vals = [data[m][i] for m in MODELS]
        offset = (i - 1.5) * w
        bars = ax.bar(
            x + offset, vals, w, label=sev, color=sev_colors[i], edgecolor=EDGE
        )
        for b in bars:
            if b.get_height() > 0:
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    b.get_height() + 0.05,
                    str(int(b.get_height())),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(MODELS)
    ax.set_ylabel("Number of findings")
    ax.set_title("Findings by Severity")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.set_ylim(0, 7)
    save(fig, "08_severity_distribution.png")


if __name__ == "__main__":
    print("Generating graphs...")
    graph_final_scores()
    graph_findings_count()
    graph_cost_analysis()
    graph_scorecard_radar()
    graph_unique_findings()
    graph_token_usage()
    graph_wasted_cost()
    graph_severity_distribution()
    print("Done.")
