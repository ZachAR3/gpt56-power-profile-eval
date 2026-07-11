#!/usr/bin/env python3
"""Generate SVG graphs from the normalized evaluation data.

Reads ``docs/evaluation/eval_data.json`` and writes SVG files to
``docs/assets/``.  Run from the repository root::

    python3 generate_graphs.py

Dependencies: matplotlib, numpy (both standard scientific Python packages).
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "docs" / "evaluation" / "eval_data.json"
OUT_DIR = ROOT / "docs" / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Shared style — designed to be readable in both light and dark GitHub themes
# ---------------------------------------------------------------------------
plt.rcParams.update(
    {
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.titleweight": "bold",
        "axes.labelsize": 12,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    }
)

# Consistent colours for the 9 reports
REPORT_ORDER = [
    "SOL_HIGH",
    "LUNA_MAX",
    "TERRA_XHIGH",
    "SOL_MEDIUM",
    "LUNA_XHIGH",
    "5_5_XHIGH",
    "LUNA_HIGH",
    "5_5_HIGH",
    "GLM_MAX",
]
REPORT_LABELS = {
    "5_5_HIGH": "5.5 High",
    "5_5_XHIGH": "5.5 XHigh",
    "GLM_MAX": "GLM Max",
    "LUNA_HIGH": "Luna High",
    "LUNA_MAX": "Luna Max",
    "LUNA_XHIGH": "Luna XHigh",
    "SOL_HIGH": "Sol High",
    "SOL_MEDIUM": "Sol Medium",
    "TERRA_XHIGH": "Terra XHigh",
}
REPORT_COLORS = {
    "SOL_HIGH": "#2563eb",  # blue
    "LUNA_MAX": "#7c3aed",  # purple
    "TERRA_XHIGH": "#059669",  # green
    "SOL_MEDIUM": "#0891b2",  # cyan
    "LUNA_XHIGH": "#6366f1",  # indigo
    "5_5_XHIGH": "#d97706",  # amber
    "LUNA_HIGH": "#ec4899",  # pink
    "5_5_HIGH": "#dc2626",  # red
    "GLM_MAX": "#ea580c",  # orange
}
EVAL_COLORS = {"glm": "#2563eb", "sol": "#ea580c"}
EDGE = "#333333"


def load_data():
    with open(DATA_FILE) as f:
        return json.load(f)


def save(fig, name):
    path = OUT_DIR / name
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    print(f"  wrote {path}")


# ---------------------------------------------------------------------------
# 1. Overall usefulness scores — GLM vs Sol side by side
# ---------------------------------------------------------------------------
def graph_overall_scores(data):
    reports = REPORT_ORDER
    glm_scores = [data["scorecard_glm"]["scores"][r][7] for r in reports]
    sol_scores = [data["scorecard_sol"]["scores"][r][7] for r in reports]

    x = np.arange(len(reports))
    w = 0.38
    fig, ax = plt.subplots(figsize=(12, 6))

    b1 = ax.bar(
        x - w / 2,
        glm_scores,
        w,
        label="GLM-5.2 (evaluator)",
        color=EVAL_COLORS["glm"],
        edgecolor=EDGE,
        alpha=0.85,
    )
    b2 = ax.bar(
        x + w / 2,
        sol_scores,
        w,
        label="GPT-5.6-Sol High (evaluator)",
        color=EVAL_COLORS["sol"],
        edgecolor=EDGE,
        alpha=0.85,
    )

    for bars in (b1, b2):
        for b in bars:
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.15,
                f"{b.get_height():.1f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=10, rotation=20, ha="right"
    )
    ax.set_ylabel("Overall usefulness score (/10)")
    ax.set_title("Overall Usefulness Score by Report — Two Evaluators")
    ax.set_ylim(0, 10.5)
    ax.legend(frameon=False, loc="upper right")
    ax.axhline(y=7, color="#ccc", linestyle="--", linewidth=0.8, zorder=0)
    ax.text(len(reports) - 0.5, 7.1, "strong (7)", fontsize=8, color="#999", ha="right")
    save(fig, "01_overall_scores.svg")


# ---------------------------------------------------------------------------
# 2. Scorecard heatmap — all criteria × all reports, both evaluators
# ---------------------------------------------------------------------------
def graph_scorecard_heatmap(data):
    criteria = data["scorecard_glm"]["criteria"]
    reports = REPORT_ORDER

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    for ax, scorecard, title in [
        (ax1, data["scorecard_glm"], "GLM-5.2 Scorecard"),
        (ax2, data["scorecard_sol"], "GPT-5.6-Sol High Scorecard"),
    ]:
        matrix = np.array([scorecard["scores"][r] for r in reports])
        im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=4, vmax=10)
        ax.set_xticks(range(len(criteria)))
        ax.set_xticklabels(criteria, fontsize=8, rotation=35, ha="right")
        ax.set_yticks(range(len(reports)))
        ax.set_yticklabels([REPORT_LABELS[r] for r in reports], fontsize=9)
        ax.set_title(title)
        for i in range(len(reports)):
            for j in range(len(criteria)):
                val = matrix[i, j]
                color = "white" if val < 6.5 else "black"
                ax.text(
                    j,
                    i,
                    f"{val:.1f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=color,
                )

    fig.colorbar(im, ax=[ax1, ax2], shrink=0.8, label="Score (/10)")
    fig.suptitle(
        "Scorecard Heatmap — All Criteria by Report",
        fontsize=15,
        fontweight="bold",
        y=1.02,
    )
    save(fig, "02_scorecard_heatmap.svg")


# ---------------------------------------------------------------------------
# 3. Evaluator comparison scatter — GLM score vs Sol score
# ---------------------------------------------------------------------------
def graph_evaluator_comparison(data):
    reports = REPORT_ORDER
    glm_overall = [data["scorecard_glm"]["scores"][r][7] for r in reports]
    sol_overall = [data["scorecard_sol"]["scores"][r][7] for r in reports]

    fig, ax = plt.subplots(figsize=(9, 8))
    for i, r in enumerate(reports):
        ax.scatter(
            glm_overall[i],
            sol_overall[i],
            s=180,
            c=REPORT_COLORS[r],
            edgecolors=EDGE,
            linewidth=1.5,
            zorder=5,
        )
        # Offset labels to avoid overlap
        offset_x = 0.15
        offset_y = 0.15
        if r == "GLM_MAX":
            offset_y = -0.3
        elif r == "5_5_HIGH":
            offset_y = -0.3
        elif r == "SOL_HIGH":
            offset_x = -0.15
            offset_y = 0.2
        ax.annotate(
            REPORT_LABELS[r],
            (glm_overall[i], sol_overall[i]),
            textcoords="offset points",
            xytext=(8, 8),
            fontsize=10,
            fontweight="bold",
        )

    # Diagonal reference line
    lim = [4, 10]
    ax.plot(
        lim,
        lim,
        color="#ccc",
        linestyle="--",
        linewidth=1,
        zorder=1,
        label="Agreement line",
    )
    ax.set_xlim(4.5, 9.8)
    ax.set_ylim(4.5, 9.8)
    ax.set_xlabel("GLM-5.2 overall usefulness score (/10)")
    ax.set_ylabel("GPT-5.6-Sol High overall usefulness score (/10)")
    ax.set_title("Evaluator Comparison — Overall Usefulness Scores")
    ax.legend(frameon=False, loc="lower right")
    ax.set_aspect("equal")
    save(fig, "03_evaluator_comparison.svg")


# ---------------------------------------------------------------------------
# 4. Cost vs performance scatter
# ---------------------------------------------------------------------------
def graph_cost_vs_performance(data):
    reports = REPORT_ORDER
    costs = [
        next(r["cost_usd"] for r in data["reports"] if r["id"] == rid)
        for rid in reports
    ]
    glm_scores = [data["scorecard_glm"]["scores"][rid][7] for rid in reports]
    sol_scores = [data["scorecard_sol"]["scores"][rid][7] for rid in reports]
    avg_scores = [(g + s) / 2 for g, s in zip(glm_scores, sol_scores)]
    findings = [
        next(r["findings_count"] for r in data["reports"] if r["id"] == rid)
        for rid in reports
    ]

    fig, ax = plt.subplots(figsize=(10, 7))
    for i, r in enumerate(reports):
        ax.scatter(
            costs[i],
            avg_scores[i],
            s=findings[i] * 35,
            c=REPORT_COLORS[r],
            edgecolors=EDGE,
            linewidth=1.5,
            zorder=5,
            label=REPORT_LABELS[r],
        )
        offset_y = 0.2 if i % 2 == 0 else -0.35
        ax.annotate(
            f"{REPORT_LABELS[r]}\n({findings[i]} findings)",
            (costs[i], avg_scores[i]),
            textcoords="offset points",
            xytext=(0, offset_y * 12),
            ha="center",
            fontsize=8,
            fontweight="bold",
        )

    ax.axhline(y=7.5, color="#ccc", linestyle="--", linewidth=0.8, zorder=0)
    ax.set_xlabel("Production cost (USD)")
    ax.set_ylabel("Average overall score (/10, mean of both evaluators)")
    ax.set_title("Cost vs. Performance (bubble size = findings count)")
    ax.set_xlim(0, 6)
    ax.set_ylim(5.5, 9.5)
    ax.legend(frameon=False, loc="lower right", fontsize=8, ncol=2)
    save(fig, "04_cost_vs_performance.svg")


# ---------------------------------------------------------------------------
# 5. Ranking comparison — diverging bar showing rank differences
# ---------------------------------------------------------------------------
def graph_ranking_comparison(data):
    reports = REPORT_ORDER
    glm_rank = {v: int(k) for k, v in data["rankings"]["glm"].items()}
    sol_rank = {v: int(k) for k, v in data["rankings"]["sol"].items()}

    diffs = []
    labels = []
    colors = []
    for r in reports:
        g = glm_rank[r]
        s = sol_rank[r]
        diff = g - s  # negative = Sol ranks worse, positive = Sol ranks better
        diffs.append(diff)
        labels.append(REPORT_LABELS[r])
        colors.append(REPORT_COLORS[r])

    fig, ax = plt.subplots(figsize=(10, 6))
    y = np.arange(len(reports))
    bars = ax.barh(y, diffs, color=colors, edgecolor=EDGE, height=0.6)
    for i, (bar, diff) in enumerate(zip(bars, diffs)):
        x_pos = diff + (0.15 if diff >= 0 else -0.15)
        ha = "left" if diff >= 0 else "right"
        sign = "+" if diff > 0 else ""
        ax.text(
            x_pos,
            i,
            f"{sign}{diff} (GLM:{glm_rank[reports[i]]} / Sol:{sol_rank[reports[i]]})",
            va="center",
            ha=ha,
            fontsize=9,
            fontweight="bold",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel(
        "Rank difference (GLM rank − Sol rank)\nPositive = Sol ranks higher; Negative = GLM ranks higher"
    )
    ax.set_title("Ranking Differences Between Evaluators")
    ax.axvline(x=0, color="#333", linewidth=1)
    ax.set_xlim(-7, 7)
    save(fig, "05_ranking_comparison.svg")


# ---------------------------------------------------------------------------
# 6. Issue coverage heatmap
# ---------------------------------------------------------------------------
def graph_issue_coverage(data):
    coverage = data["issue_coverage"]
    issue_ids = [iss["id"] for iss in coverage["issues"]]
    issue_labels = [
        f"{iss['id']}: {iss['description'][:45]}..."
        if len(iss["description"]) > 45
        else f"{iss['id']}: {iss['description']}"
        for iss in coverage["issues"]
    ]
    reports = REPORT_ORDER

    value_map = {"yes": 1.0, "partial": 0.5, "no": 0.0}
    matrix = np.array(
        [[value_map[coverage["matrix"][r][iid]] for iid in issue_ids] for r in reports]
    )

    fig, ax = plt.subplots(figsize=(14, 7))
    cmap = plt.cm.RdYlGn
    im = ax.imshow(matrix, aspect="auto", cmap=cmap, vmin=0, vmax=1)

    ax.set_xticks(range(len(issue_ids)))
    ax.set_xticklabels(issue_ids, fontsize=9, rotation=0)
    ax.set_yticks(range(len(reports)))
    ax.set_yticklabels([REPORT_LABELS[r] for r in reports], fontsize=9)

    for i in range(len(reports)):
        for j in range(len(issue_ids)):
            val = coverage["matrix"][reports[i]][issue_ids[j]]
            symbol = {"yes": "✓", "partial": "◐", "no": "✗"}[val]
            color = "white" if matrix[i, j] < 0.3 else "black"
            ax.text(
                j,
                i,
                symbol,
                ha="center",
                va="center",
                fontsize=10,
                color=color,
                fontweight="bold",
            )

    ax.set_title("Issue Coverage Matrix — Which Reports Caught Which Issues")
    # Legend
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor=cmap(1.0), edgecolor=EDGE, label="✓ Identified"),
        Patch(facecolor=cmap(0.5), edgecolor=EDGE, label="◐ Partial"),
        Patch(facecolor=cmap(0.0), edgecolor=EDGE, label="✗ Missed"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=3,
        frameon=False,
    )
    save(fig, "06_issue_coverage.svg")


# ---------------------------------------------------------------------------
# 7. Cost efficiency — cost per finding and cost per score point
# ---------------------------------------------------------------------------
def graph_cost_efficiency(data):
    reports = REPORT_ORDER
    costs = [
        next(r["cost_usd"] for r in data["reports"] if r["id"] == rid)
        for rid in reports
    ]
    findings = [
        next(r["findings_count"] for r in data["reports"] if r["id"] == rid)
        for rid in reports
    ]
    glm_scores = [data["scorecard_glm"]["scores"][rid][7] for rid in reports]
    sol_scores = [data["scorecard_sol"]["scores"][rid][7] for rid in reports]
    avg_scores = [(g + s) / 2 for g, s in zip(glm_scores, sol_scores)]

    cost_per_finding = [c / f if f > 0 else 0 for c, f in zip(costs, findings)]
    cost_per_score = [c / s for c, s in zip(costs, avg_scores)]

    x = np.arange(len(reports))
    w = 0.38
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    bars1 = ax1.bar(
        x,
        cost_per_finding,
        w,
        color=[REPORT_COLORS[r] for r in reports],
        edgecolor=EDGE,
    )
    for b, v in zip(bars1, cost_per_finding):
        ax1.text(
            b.get_x() + b.get_width() / 2,
            b.get_height() + 0.01,
            f"${v:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )
    ax1.set_xticks(x)
    ax1.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=8, rotation=20, ha="right"
    )
    ax1.set_ylabel("Cost per finding (USD)")
    ax1.set_title("Cost per Finding (lower is better)")
    ax1.set_ylim(0, max(cost_per_finding) * 1.2)

    bars2 = ax2.bar(
        x, cost_per_score, w, color=[REPORT_COLORS[r] for r in reports], edgecolor=EDGE
    )
    for b, v in zip(bars2, cost_per_score):
        ax2.text(
            b.get_x() + b.get_width() / 2,
            b.get_height() + 0.01,
            f"${v:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )
    ax2.set_xticks(x)
    ax2.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=8, rotation=20, ha="right"
    )
    ax2.set_ylabel("Cost per score point (USD)")
    ax2.set_title("Cost per Score Point (lower is better)")
    ax2.set_ylim(0, max(cost_per_score) * 1.2)

    fig.suptitle("Cost Efficiency Analysis", fontsize=15, fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, "07_cost_efficiency.svg")


# ---------------------------------------------------------------------------
# 8. Findings by severity per report
# ---------------------------------------------------------------------------
def graph_severity_distribution(data):
    coverage = data["issue_coverage"]
    reports = REPORT_ORDER
    severities = ["Critical", "High", "Medium", "Low"]
    sev_colors = ["#dc2626", "#ea580c", "#2563eb", "#6b7280"]

    # Count issues by severity for each report
    counts = {sev: [] for sev in severities}
    for r in reports:
        matrix = coverage["matrix"][r]
        for sev in severities:
            count = sum(
                1
                for iss in coverage["issues"]
                if iss["severity"] == sev and matrix[iss["id"]] in ("yes", "partial")
            )
            counts[sev].append(count)

    x = np.arange(len(reports))
    w = 0.2
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, sev in enumerate(severities):
        offset = (i - 1.5) * w
        bars = ax.bar(
            x + offset, counts[sev], w, label=sev, color=sev_colors[i], edgecolor=EDGE
        )
        for b in bars:
            if b.get_height() > 0:
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    b.get_height() + 0.08,
                    str(int(b.get_height())),
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=9, rotation=20, ha="right"
    )
    ax.set_ylabel("Number of issues identified (incl. partial)")
    ax.set_title("Issues Identified by Severity per Report")
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.set_ylim(0, max(max(v) for v in counts.values()) + 2)
    save(fig, "08_severity_distribution.svg")


# ---------------------------------------------------------------------------
# 9. Performance by reasoning effort level
# ---------------------------------------------------------------------------
def graph_effort_analysis(data):
    reports = REPORT_ORDER
    efforts = {"medium": [], "high": [], "xhigh": [], "max": []}
    for r in data["reports"]:
        effort = r["effort"]
        glm_score = data["scorecard_glm"]["scores"][r["id"]][7]
        sol_score = data["scorecard_sol"]["scores"][r["id"]][7]
        avg = (glm_score + sol_score) / 2
        efforts[effort].append((r["id"], avg, r["cost_usd"]))

    fig, ax = plt.subplots(figsize=(10, 6))
    effort_order = ["medium", "high", "xhigh", "max"]
    effort_colors = {
        "medium": "#0891b2",
        "high": "#2563eb",
        "xhigh": "#7c3aed",
        "max": "#dc2626",
    }
    effort_x = {"medium": 0, "high": 1, "xhigh": 2, "max": 3}

    for effort in effort_order:
        for rid, score, cost in efforts[effort]:
            jitter = np.random.RandomState(hash(rid) % 1000).uniform(-0.15, 0.15)
            x = effort_x[effort] + jitter
            ax.scatter(
                x,
                score,
                s=cost * 80,
                c=effort_colors[effort],
                edgecolors=EDGE,
                linewidth=1.2,
                zorder=5,
                alpha=0.85,
            )
            ax.annotate(
                REPORT_LABELS[rid],
                (x, score),
                textcoords="offset points",
                xytext=(8, 5),
                fontsize=8,
                fontweight="bold",
            )

    ax.set_xticks(range(4))
    ax.set_xticklabels(["Medium", "High", "XHigh", "Max"], fontsize=11)
    ax.set_xlabel("Reasoning effort level")
    ax.set_ylabel("Average overall score (/10, mean of both evaluators)")
    ax.set_title("Performance by Reasoning Effort (bubble size = cost)")
    ax.set_ylim(5, 10)
    save(fig, "09_effort_analysis.svg")


if __name__ == "__main__":
    print("Generating graphs from docs/evaluation/eval_data.json...")
    data = load_data()
    graph_overall_scores(data)
    graph_scorecard_heatmap(data)
    graph_evaluator_comparison(data)
    graph_cost_vs_performance(data)
    graph_ranking_comparison(data)
    graph_issue_coverage(data)
    graph_cost_efficiency(data)
    graph_severity_distribution(data)
    graph_effort_analysis(data)
    print("Done. SVG files written to docs/assets/")
