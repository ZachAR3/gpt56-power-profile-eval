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
import matplotlib.patches as mpatches
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "docs" / "evaluation" / "eval_data.json"
OUT_DIR = ROOT / "docs" / "assets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Shared style — designed for readability in both light and dark GitHub themes
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
        "legend.fontsize": 10,
        "legend.frameon": False,
    }
)

# Consistent colours for the 9 reports — ordered by combined ranking
REPORT_ORDER = [
    "LUNA_MAX",
    "SOL_HIGH",
    "LUNA_XHIGH",
    "5_5_XHIGH",
    "SOL_MEDIUM",
    "LUNA_HIGH",
    "TERRA_XHIGH",
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

# Custom red-yellow-green colormap for heatmaps
RDYG = LinearSegmentedColormap.from_list("rdyg", ["#dc2626", "#f59e0b", "#22c55e"])


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
    fig, ax = plt.subplots(figsize=(13, 6.5))

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
                fontsize=10,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=10, rotation=25, ha="right"
    )
    ax.set_ylabel("Overall usefulness score (/10)")
    ax.set_title("Overall Usefulness Score by Report: Two Evaluators")
    ax.set_ylim(0, 10.5)
    ax.legend(loc="upper right")
    ax.axhline(y=7, color="#999", linestyle="--", linewidth=0.8, zorder=0)
    ax.text(
        len(reports) - 0.5, 7.15, "strong (7)", fontsize=9, color="#666", ha="right"
    )
    fig.tight_layout()
    save(fig, "01_overall_scores.svg")


# ---------------------------------------------------------------------------
# 2. Scorecard heatmap — native SVG rects, not rasterized
# ---------------------------------------------------------------------------
def graph_scorecard_heatmap(data):
    criteria = data["scorecard_glm"]["criteria"]
    # Shorten criterion names for display
    short_criteria = [
        c.replace("Arch. understanding", "Arch.\nUnderstanding")
        .replace("Signal-to-noise", "Signal-to-\nNoise")
        .replace("Fix quality", "Fix\nQuality")
        .replace("Overall usefulness", "Overall\nUsefulness")
        .replace("Completeness", "Complete-\nness")
        .replace("Prioritization", "Priority")
        .replace("Accuracy", "Accuracy")
        .replace("Depth", "Depth")
        for c in criteria
    ]
    reports = REPORT_ORDER

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    for ax, scorecard, title in [
        (ax1, data["scorecard_glm"], "GLM-5.2 Scorecard"),
        (ax2, data["scorecard_sol"], "GPT-5.6-Sol High Scorecard (revised)"),
    ]:
        matrix = np.array([scorecard["scores"][r] for r in reports], dtype=float)

        # Draw native SVG rectangles instead of rasterized imshow
        for i in range(len(reports)):
            for j in range(len(criteria)):
                val = matrix[i, j]
                # Normalize 4-10 to 0-1 for colormap
                norm_val = max(0, min(1, (val - 4) / 6))
                color = RDYG(norm_val)
                rect = mpatches.Rectangle(
                    (j - 0.5, i - 0.5),
                    1,
                    1,
                    facecolor=color,
                    edgecolor="white",
                    linewidth=0.5,
                )
                ax.add_patch(rect)

                text_color = "white" if val < 6.5 else "black"
                ax.text(
                    j,
                    i,
                    f"{val:.1f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color=text_color,
                    fontweight="bold",
                )

        ax.set_xlim(-0.5, len(criteria) - 0.5)
        ax.set_ylim(len(reports) - 0.5, -0.5)
        ax.set_xticks(range(len(short_criteria)))
        ax.set_xticklabels(short_criteria, fontsize=9, ha="center")
        ax.set_yticks(range(len(reports)))
        ax.set_yticklabels([REPORT_LABELS[r] for r in reports], fontsize=10)
        ax.set_title(title, fontsize=13)
        ax.tick_params(length=0)

    # Add color legend manually
    legend_elements = [
        mpatches.Patch(facecolor=RDYG(0.0), edgecolor="white", label="4 (poor)"),
        mpatches.Patch(facecolor=RDYG(0.33), edgecolor="white", label="6 (mixed)"),
        mpatches.Patch(facecolor=RDYG(0.66), edgecolor="white", label="8 (strong)"),
        mpatches.Patch(
            facecolor=RDYG(1.0), edgecolor="white", label="10 (exceptional)"
        ),
    ]
    fig.legend(
        handles=legend_elements,
        loc="lower center",
        ncol=4,
        fontsize=9,
        bbox_to_anchor=(0.5, -0.02),
        title="Score scale",
    )

    fig.suptitle(
        "Scorecard Heatmap: All Criteria by Report",
        fontsize=15,
        fontweight="bold",
        y=1.01,
    )
    fig.tight_layout()
    save(fig, "02_scorecard_heatmap.svg")


# ---------------------------------------------------------------------------
# 3. Evaluator comparison scatter — GLM score vs Sol score
# ---------------------------------------------------------------------------
def graph_evaluator_comparison(data):
    reports = REPORT_ORDER
    glm_overall = [data["scorecard_glm"]["scores"][r][7] for r in reports]
    sol_overall = [data["scorecard_sol"]["scores"][r][7] for r in reports]

    fig, ax = plt.subplots(figsize=(10, 9))
    for i, r in enumerate(reports):
        ax.scatter(
            glm_overall[i],
            sol_overall[i],
            s=200,
            c=REPORT_COLORS[r],
            edgecolors=EDGE,
            linewidth=1.5,
            zorder=5,
        )
        # Smart label placement to avoid overlaps
        offset_x, offset_y = 10, 10
        if r == "GLM_MAX":
            offset_x, offset_y = -10, -18
        elif r == "5_5_HIGH":
            offset_x, offset_y = 10, -15
        elif r == "SOL_HIGH":
            offset_x, offset_y = -15, 12
        elif r == "LUNA_MAX":
            offset_x, offset_y = 12, 8
        elif r == "TERRA_XHIGH":
            offset_x, offset_y = 10, -15
        elif r == "SOL_MEDIUM":
            offset_x, offset_y = 10, 10
        elif r == "LUNA_XHIGH":
            offset_x, offset_y = -15, 10
        elif r == "5_5_XHIGH":
            offset_x, offset_y = 10, -15
        elif r == "LUNA_HIGH":
            offset_x, offset_y = 10, 10
        ax.annotate(
            REPORT_LABELS[r],
            (glm_overall[i], sol_overall[i]),
            textcoords="offset points",
            xytext=(offset_x, offset_y),
            fontsize=10,
            fontweight="bold",
            arrowprops=dict(arrowstyle="-", color="#999", lw=0.5)
            if abs(offset_x) > 12
            else None,
        )

    # Diagonal reference line
    lim = [3.5, 10]
    ax.plot(
        lim,
        lim,
        color="#ccc",
        linestyle="--",
        linewidth=1,
        zorder=1,
        label="Agreement line (y=x)",
    )
    ax.set_xlim(3.5, 10)
    ax.set_ylim(3.5, 10)
    ax.set_xlabel("GLM-5.2 overall usefulness score (/10)")
    ax.set_ylabel("GPT-5.6-Sol High overall usefulness score (/10)")
    ax.set_title("Evaluator Comparison: Overall Usefulness Scores")
    ax.legend(loc="lower right")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.2)
    save(fig, "03_evaluator_comparison.svg")


# ---------------------------------------------------------------------------
# 4. Cost vs performance scatter — improved label placement
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

    fig, ax = plt.subplots(figsize=(11, 8))
    for i, r in enumerate(reports):
        ax.scatter(
            costs[i],
            avg_scores[i],
            s=findings[i] * 40,
            c=REPORT_COLORS[r],
            edgecolors=EDGE,
            linewidth=1.5,
            zorder=5,
        )
        # Smart label placement
        offset_y = 0.25 if i % 2 == 0 else -0.4
        offset_x = 0.1
        if r == "LUNA_MAX":
            offset_x, offset_y = 0.15, 0.3
        elif r == "SOL_HIGH":
            offset_x, offset_y = -0.15, 0.3
        elif r == "GLM_MAX":
            offset_x, offset_y = 0.15, -0.5
        elif r == "5_5_HIGH":
            offset_x, offset_y = 0.15, -0.5
        elif r == "TERRA_XHIGH":
            offset_x, offset_y = 0.15, 0.3
        elif r == "SOL_MEDIUM":
            offset_x, offset_y = 0.15, -0.5
        elif r == "LUNA_HIGH":
            offset_x, offset_y = 0.15, 0.3
        ax.annotate(
            f"{REPORT_LABELS[r]}\n({findings[i]} findings)",
            (costs[i], avg_scores[i]),
            textcoords="offset points",
            xytext=(12, offset_y * 15),
            ha="left",
            fontsize=9,
            fontweight="bold",
        )

    ax.axhline(
        y=7.0,
        color="#999",
        linestyle="--",
        linewidth=0.8,
        zorder=0,
        label="Strong threshold (7.0)",
    )
    ax.set_xlabel("Production cost (USD)")
    ax.set_ylabel("Average overall score (/10, mean of both evaluators)")
    ax.set_title("Cost vs. Performance (bubble size = findings count)")
    ax.set_xlim(-0.2, 6.0)
    ax.set_ylim(4.5, 9.5)
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.2)

    # Add quadrant annotations
    ax.text(
        0.3,
        9.2,
        "Best value\n(high score, low cost)",
        fontsize=8,
        color="#666",
        style="italic",
        ha="left",
        va="top",
    )
    save(fig, "04_cost_vs_performance.svg")


# ---------------------------------------------------------------------------
# 5. Ranking comparison — diverging bar with improved labels
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

    fig, ax = plt.subplots(figsize=(11, 6.5))
    y = np.arange(len(reports))
    bars = ax.barh(y, diffs, color=colors, edgecolor=EDGE, height=0.6)
    for i, (bar, diff) in enumerate(zip(bars, diffs)):
        # Place label outside the bar
        if diff >= 0:
            x_pos = diff + 0.15
            ha = "left"
        else:
            x_pos = diff - 0.15
            ha = "right"
        sign = "+" if diff > 0 else ""
        ax.text(
            x_pos,
            i,
            f"{sign}{diff}  (GLM:{glm_rank[reports[i]]} / Sol:{sol_rank[reports[i]]})",
            va="center",
            ha=ha,
            fontsize=9,
            fontweight="bold",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel(
        "Rank difference (GLM rank − Sol rank)\n← GLM ranks higher | Sol ranks higher →"
    )
    ax.set_title("Ranking Differences Between Evaluators")
    ax.axvline(x=0, color="#333", linewidth=1.2)
    ax.set_xlim(-7.5, 7.5)
    ax.grid(True, axis="x", alpha=0.2)
    save(fig, "05_ranking_comparison.svg")


# ---------------------------------------------------------------------------
# 6. Issue coverage heatmap — native SVG rects, not rasterized
# ---------------------------------------------------------------------------
def graph_issue_coverage(data):
    coverage = data["issue_coverage"]
    issue_ids = [iss["id"] for iss in coverage["issues"]]
    reports = REPORT_ORDER

    value_map = {"yes": 1.0, "partial": 0.5, "no": 0.0}
    matrix = np.array(
        [[value_map[coverage["matrix"][r][iid]] for iid in issue_ids] for r in reports],
        dtype=float,
    )

    fig, ax = plt.subplots(figsize=(16, 7.5))

    # Draw native SVG rectangles instead of rasterized imshow
    for i in range(len(reports)):
        for j in range(len(issue_ids)):
            val = matrix[i, j]
            color = RDYG(val)
            rect = mpatches.Rectangle(
                (j - 0.5, i - 0.5),
                1,
                1,
                facecolor=color,
                edgecolor="white",
                linewidth=0.5,
            )
            ax.add_patch(rect)

            status = coverage["matrix"][reports[i]][issue_ids[j]]
            symbol = {"yes": "✓", "partial": "◐", "no": "✗"}[status]
            text_color = "white" if val < 0.3 else "black"
            ax.text(
                j,
                i,
                symbol,
                ha="center",
                va="center",
                fontsize=11,
                color=text_color,
                fontweight="bold",
            )

    ax.set_xlim(-0.5, len(issue_ids) - 0.5)
    ax.set_ylim(len(reports) - 0.5, -0.5)
    ax.set_xticks(range(len(issue_ids)))
    ax.set_xticklabels(issue_ids, fontsize=9)
    ax.set_yticks(range(len(reports)))
    ax.set_yticklabels([REPORT_LABELS[r] for r in reports], fontsize=10)
    ax.tick_params(length=0)

    ax.set_title(
        "Issue Coverage Matrix: Which Reports Caught Which Issues", fontsize=14
    )
    # Legend
    legend_elements = [
        mpatches.Patch(facecolor=RDYG(1.0), edgecolor=EDGE, label="✓ Identified"),
        mpatches.Patch(facecolor=RDYG(0.5), edgecolor=EDGE, label="◐ Partial"),
        mpatches.Patch(facecolor=RDYG(0.0), edgecolor=EDGE, label="✗ Missed"),
    ]
    ax.legend(
        handles=legend_elements,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=3,
        fontsize=10,
    )

    # Add severity group labels
    sev_groups = [
        ("Critical", 0, 0),
        ("High", 1, 6),
        ("Medium", 7, 14),
        ("Low", 15, 23),
    ]
    for name, start, end in sev_groups:
        ax.annotate(
            name,
            xy=((start + end) / 2, -1.5),
            fontsize=9,
            fontweight="bold",
            ha="center",
            color="#333",
        )

    fig.tight_layout()
    save(fig, "06_issue_coverage.svg")


# ---------------------------------------------------------------------------
# 7. Cost efficiency — improved readability
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
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5))

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
            fontsize=10,
            fontweight="bold",
        )
    ax1.set_xticks(x)
    ax1.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=9, rotation=25, ha="right"
    )
    ax1.set_ylabel("Cost per finding (USD)")
    ax1.set_title("Cost per Finding (lower is better)")
    ax1.set_ylim(0, max(cost_per_finding) * 1.25)

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
            fontsize=10,
            fontweight="bold",
        )
    ax2.set_xticks(x)
    ax2.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=9, rotation=25, ha="right"
    )
    ax2.set_ylabel("Cost per score point (USD)")
    ax2.set_title("Cost per Score Point (lower is better)")
    ax2.set_ylim(0, max(cost_per_score) * 1.25)

    fig.suptitle("Cost Efficiency Analysis", fontsize=15, fontweight="bold", y=1.02)
    fig.tight_layout()
    save(fig, "07_cost_efficiency.svg")


# ---------------------------------------------------------------------------
# 8. Findings by severity per report — stacked bar for better readability
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
    w = 0.65
    fig, ax = plt.subplots(figsize=(13, 6.5))

    # Stacked bars
    bottoms = np.zeros(len(reports))
    for i, sev in enumerate(severities):
        vals = np.array(counts[sev])
        bars = ax.bar(
            x, vals, w, bottom=bottoms, label=sev, color=sev_colors[i], edgecolor=EDGE
        )
        # Add count labels inside each segment
        for j, (b, v) in enumerate(zip(bars, vals)):
            if v > 0:
                y_pos = bottoms[j] + v / 2
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    y_pos,
                    str(v),
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color="white" if sev in ("Critical", "High") else "black",
                )
        bottoms += vals

    # Add total count on top of each bar
    for i, total in enumerate(bottoms):
        ax.text(
            i,
            total + 0.2,
            str(int(total)),
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=10, rotation=25, ha="right"
    )
    ax.set_ylabel("Number of issues identified (incl. partial)")
    ax.set_title("Issues Identified by Severity per Report (stacked)")
    ax.legend(loc="upper right", ncol=4)
    ax.set_ylim(0, max(bottoms) + 2)
    save(fig, "08_severity_distribution.svg")


# ---------------------------------------------------------------------------
# 9. Performance by reasoning effort — fixed label overlaps
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

    fig, ax = plt.subplots(figsize=(11, 7))
    effort_order = ["medium", "high", "xhigh", "max"]
    effort_colors = {
        "medium": "#0891b2",
        "high": "#2563eb",
        "xhigh": "#7c3aed",
        "max": "#dc2626",
    }
    effort_x = {"medium": 0, "high": 1, "xhigh": 2, "max": 3}

    # Track y-positions per effort level to avoid overlaps
    effort_y_positions = {e: [] for e in effort_order}

    for effort in effort_order:
        for rid, score, cost in efforts[effort]:
            # Deterministic jitter based on report id hash
            rng = np.random.RandomState(hash(rid) % 1000)
            jitter = rng.uniform(-0.12, 0.12)
            x = effort_x[effort] + jitter

            # Adjust y to avoid overlaps within the same effort level
            y = score
            for prev_y in effort_y_positions[effort]:
                if abs(y - prev_y) < 0.3:
                    y = prev_y - 0.35
            effort_y_positions[effort].append(y)

            ax.scatter(
                x,
                y,
                s=cost * 80,
                c=effort_colors[effort],
                edgecolors=EDGE,
                linewidth=1.2,
                zorder=5,
                alpha=0.85,
            )
            ax.annotate(
                REPORT_LABELS[rid],
                (x, y),
                textcoords="offset points",
                xytext=(10, 5),
                fontsize=9,
                fontweight="bold",
            )

    ax.set_xticks(range(4))
    ax.set_xticklabels(["Medium", "High", "XHigh", "Max"], fontsize=12)
    ax.set_xlabel("Reasoning effort level")
    ax.set_ylabel("Average overall score (/10, mean of both evaluators)")
    ax.set_title("Performance by Reasoning Effort (bubble size = cost)")
    ax.set_ylim(4.5, 9.5)
    ax.grid(True, alpha=0.2)

    # Add legend for effort colors
    legend_elements = [
        mpatches.Patch(facecolor=effort_colors[e], edgecolor=EDGE, label=e.capitalize())
        for e in effort_order
    ]
    ax.legend(handles=legend_elements, loc="lower left")

    # Add bubble size reference
    for size, label in [(1, r"\$1"), (3, r"\$3"), (5, r"\$5")]:
        ax.scatter(
            [],
            [],
            s=size * 80,
            c="#ccc",
            edgecolors=EDGE,
            linewidth=1,
            label=label,
        )
    ax.legend(loc="lower left", fontsize=9, title="Cost (bubble size)")
    save(fig, "09_effort_analysis.svg")


# ---------------------------------------------------------------------------
# 10. Severity-weighted coverage — with legend
# ---------------------------------------------------------------------------
def graph_severity_weighted_coverage(data):
    swc = data.get("severity_weighted_coverage", {})
    if not swc:
        return
    reports = REPORT_ORDER
    sev_cov = [swc["coverage"][r]["severity_weighted_pct"] for r in reports]
    ch_cov = [swc["coverage"][r]["critical_high_pct"] for r in reports]

    x = np.arange(len(reports))
    w = 0.38
    fig, ax = plt.subplots(figsize=(13, 6.5))
    b1 = ax.bar(
        x - w / 2,
        sev_cov,
        w,
        label="Severity-weighted coverage",
        color=EVAL_COLORS["glm"],
        edgecolor=EDGE,
        alpha=0.85,
    )
    b2 = ax.bar(
        x + w / 2,
        ch_cov,
        w,
        label="Critical/High coverage",
        color=EVAL_COLORS["sol"],
        edgecolor=EDGE,
        alpha=0.85,
    )

    for bars in (b1, b2):
        for b in bars:
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 1.0,
                f"{b.get_height():.1f}%",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=10, rotation=25, ha="right"
    )
    ax.set_ylabel("Coverage (%)")
    ax.set_title("Severity-Weighted Finding Coverage (Sol revised methodology)")
    ax.set_ylim(0, 100)
    ax.legend(loc="upper right")
    save(fig, "10_severity_weighted_coverage.svg")


# ---------------------------------------------------------------------------
# 11. NEW: Finding quality breakdown — confirmed vs partial vs incorrect vs low-value
# ---------------------------------------------------------------------------
def graph_finding_quality(data):
    """Show the breakdown of each report's findings by quality classification."""
    swc = data.get("severity_weighted_coverage", {})
    if not swc:
        return
    reports = REPORT_ORDER
    confirmed = [swc["coverage"][r]["confirmed"] for r in reports]
    partial = [swc["coverage"][r]["partial"] for r in reports]
    incorrect = [swc["coverage"][r]["incorrect"] for r in reports]
    unverifiable = [swc["coverage"][r]["unverifiable"] for r in reports]
    low_value = [swc["coverage"][r]["low_value_duplicate"] for r in reports]

    x = np.arange(len(reports))
    w = 0.65
    fig, ax = plt.subplots(figsize=(13, 7))

    bottoms = np.zeros(len(reports))
    categories = [
        (confirmed, "Confirmed", "#22c55e"),
        (partial, "Partial", "#f59e0b"),
        (incorrect, "Incorrect", "#dc2626"),
        (unverifiable, "Unverifiable", "#6b7280"),
        (low_value, "Low-value / duplicate", "#9ca3af"),
    ]

    for vals, label, color in categories:
        vals_arr = np.array(vals)
        bars = ax.bar(
            x, vals_arr, w, bottom=bottoms, label=label, color=color, edgecolor=EDGE
        )
        for j, (b, v) in enumerate(zip(bars, vals_arr)):
            if v > 0:
                y_pos = bottoms[j] + v / 2
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    y_pos,
                    str(v),
                    ha="center",
                    va="center",
                    fontsize=9,
                    fontweight="bold",
                    color="white" if color in ("#dc2626", "#22c55e") else "black",
                )
        bottoms += vals_arr

    # Total on top
    for i, total in enumerate(bottoms):
        ax.text(
            i,
            total + 0.3,
            str(int(total)),
            ha="center",
            va="bottom",
            fontsize=11,
            fontweight="bold",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [REPORT_LABELS[r] for r in reports], fontsize=10, rotation=25, ha="right"
    )
    ax.set_ylabel("Number of findings")
    ax.set_title("Finding Quality Breakdown by Report (Sol's canonical 18-issue set)")
    ax.legend(loc="upper right", ncol=3, fontsize=9)
    ax.set_ylim(0, max(bottoms) + 3)
    save(fig, "11_finding_quality.svg")


# ---------------------------------------------------------------------------
# 12. NEW: Evaluator fairness — score delta analysis
# ---------------------------------------------------------------------------
def graph_evaluator_fairness(data):
    """Show how much each evaluator's scores differ, to assess fairness/bias."""
    reports = REPORT_ORDER
    criteria = data["scorecard_glm"]["criteria"]

    # Calculate average score delta per report across all criteria
    deltas = []
    for r in reports:
        glm_scores = data["scorecard_glm"]["scores"][r]
        sol_scores = data["scorecard_sol"]["scores"][r]
        avg_delta = np.mean([s - g for g, s in zip(glm_scores, sol_scores)])
        deltas.append(avg_delta)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5))

    # Left: per-report average delta
    x = np.arange(len(reports))
    colors = [EVAL_COLORS["sol"] if d > 0 else EVAL_COLORS["glm"] for d in deltas]
    bars = ax1.barh(x, deltas, color=colors, edgecolor=EDGE, height=0.6)
    for i, (bar, delta) in enumerate(zip(bars, deltas)):
        x_pos = delta + (0.05 if delta >= 0 else -0.05)
        ha = "left" if delta >= 0 else "right"
        ax1.text(
            x_pos,
            i,
            f"{delta:+.2f}",
            va="center",
            ha=ha,
            fontsize=10,
            fontweight="bold",
        )
    ax1.set_yticks(x)
    ax1.set_yticklabels([REPORT_LABELS[r] for r in reports], fontsize=10)
    ax1.set_xlabel(
        "Average score delta (Sol − GLM)\n← GLM scores higher | Sol scores higher →"
    )
    ax1.set_title("Evaluator Score Delta per Report")
    ax1.axvline(x=0, color="#333", linewidth=1.2)
    ax1.set_xlim(-4, 4)
    ax1.grid(True, axis="x", alpha=0.2)

    # Right: per-criterion average delta
    crit_deltas = []
    for j, c in enumerate(criteria):
        avg = np.mean(
            [
                data["scorecard_sol"]["scores"][r][j]
                - data["scorecard_glm"]["scores"][r][j]
                for r in reports
            ]
        )
        crit_deltas.append(avg)

    x2 = np.arange(len(criteria))
    colors2 = [EVAL_COLORS["sol"] if d > 0 else EVAL_COLORS["glm"] for d in crit_deltas]
    bars2 = ax2.barh(x2, crit_deltas, color=colors2, edgecolor=EDGE, height=0.6)
    for i, (bar, delta) in enumerate(zip(bars2, crit_deltas)):
        x_pos = delta + (0.05 if delta >= 0 else -0.05)
        ha = "left" if delta >= 0 else "right"
        ax2.text(
            x_pos,
            i,
            f"{delta:+.2f}",
            va="center",
            ha=ha,
            fontsize=10,
            fontweight="bold",
        )
    ax2.set_yticks(x2)
    ax2.set_yticklabels(criteria, fontsize=10)
    ax2.set_xlabel(
        "Average score delta (Sol − GLM)\n← GLM scores higher | Sol scores higher →"
    )
    ax2.set_title("Evaluator Score Delta per Criterion")
    ax2.axvline(x=0, color="#333", linewidth=1.2)
    ax2.set_xlim(-4, 4)
    ax2.grid(True, axis="x", alpha=0.2)

    fig.suptitle(
        "Evaluator Fairness Analysis: Where Do GLM and Sol Disagree?",
        fontsize=14,
        fontweight="bold",
        y=1.02,
    )
    fig.tight_layout()
    save(fig, "12_evaluator_fairness.svg")


# ---------------------------------------------------------------------------
# 13. NEW: Accuracy vs coverage — quality vs quantity trade-off
# ---------------------------------------------------------------------------
def graph_accuracy_vs_coverage(data):
    """Scatter plot showing the trade-off between accuracy and finding coverage."""
    swc = data.get("severity_weighted_coverage", {})
    if not swc:
        return
    reports = REPORT_ORDER

    # Use Sol's accuracy scores (column 0) and severity-weighted coverage
    accuracy = [data["scorecard_sol"]["scores"][r][0] for r in reports]
    coverage = [swc["coverage"][r]["severity_weighted_pct"] for r in reports]
    costs = [
        next(r["cost_usd"] for r in data["reports"] if r["id"] == rid)
        for rid in reports
    ]

    fig, ax = plt.subplots(figsize=(11, 8))
    for i, r in enumerate(reports):
        ax.scatter(
            accuracy[i],
            coverage[i],
            s=costs[i] * 60,
            c=REPORT_COLORS[r],
            edgecolors=EDGE,
            linewidth=1.5,
            zorder=5,
        )
        offset_x, offset_y = 10, 8
        if r == "GLM_MAX":
            offset_x, offset_y = -15, -20
        elif r == "SOL_HIGH":
            offset_x, offset_y = 10, -18
        elif r == "LUNA_MAX":
            offset_x, offset_y = 10, 8
        elif r == "TERRA_XHIGH":
            offset_x, offset_y = 10, -18
        elif r == "5_5_HIGH":
            offset_x, offset_y = 10, 8
        elif r == "SOL_MEDIUM":
            offset_x, offset_y = 10, 8
        ax.annotate(
            REPORT_LABELS[r],
            (accuracy[i], coverage[i]),
            textcoords="offset points",
            xytext=(offset_x, offset_y),
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xlabel("Accuracy score (Sol revised, /10)")
    ax.set_ylabel("Severity-weighted coverage (%)")
    ax.set_title("Accuracy vs. Coverage (bubble size = cost)")
    ax.set_xlim(3.5, 10.5)
    ax.set_ylim(25, 90)
    ax.grid(True, alpha=0.2)

    # Add quadrant labels
    ax.text(
        9.5,
        85,
        "Ideal\n(high accuracy,\nhigh coverage)",
        fontsize=8,
        color="#666",
        style="italic",
        ha="center",
        va="top",
    )
    ax.text(
        5,
        35,
        "Problem\n(low accuracy,\nlow coverage)",
        fontsize=8,
        color="#666",
        style="italic",
        ha="center",
        va="bottom",
    )
    save(fig, "13_accuracy_vs_coverage.svg")


# ---------------------------------------------------------------------------
# 14. NEW: Cost vs. validated findings (only confirmed, not raw count)
# ---------------------------------------------------------------------------
def graph_cost_vs_validated(data):
    """Cost vs. number of confirmed findings — a fairer efficiency metric."""
    swc = data.get("severity_weighted_coverage", {})
    if not swc:
        return
    reports = REPORT_ORDER
    costs = [
        next(r["cost_usd"] for r in data["reports"] if r["id"] == rid)
        for rid in reports
    ]
    confirmed = [swc["coverage"][r]["confirmed"] for r in reports]
    partial = [swc["coverage"][r]["partial"] for r in reports]
    incorrect = [swc["coverage"][r]["incorrect"] for r in reports]

    fig, ax = plt.subplots(figsize=(11, 8))
    for i, r in enumerate(reports):
        # Use confirmed + partial as the "validated" count
        validated = confirmed[i] + partial[i]
        ax.scatter(
            costs[i],
            validated,
            s=150,
            c=REPORT_COLORS[r],
            edgecolors=EDGE,
            linewidth=1.5,
            zorder=5,
        )
        offset_y = 0.3 if i % 2 == 0 else -0.5
        ax.annotate(
            f"{REPORT_LABELS[r]}\n({confirmed[i]} confirmed, {incorrect[i]} incorrect)",
            (costs[i], validated),
            textcoords="offset points",
            xytext=(12, offset_y * 12),
            ha="left",
            fontsize=9,
            fontweight="bold",
        )

    ax.set_xlabel("Production cost (USD)")
    ax.set_ylabel("Validated findings (confirmed + partial)")
    ax.set_title("Cost vs. Validated Findings (fairer efficiency metric)")
    ax.set_xlim(-0.2, 6.0)
    ax.set_ylim(3, 16)
    ax.grid(True, alpha=0.2)

    # Add a "value frontier" annotation
    ax.text(
        1.3,
        15,
        "Best validated\nfindings per dollar",
        fontsize=8,
        color="#666",
        style="italic",
        ha="center",
        va="top",
    )
    save(fig, "14_cost_vs_validated.svg")


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
    graph_severity_weighted_coverage(data)
    graph_finding_quality(data)
    graph_evaluator_fairness(data)
    graph_accuracy_vs_coverage(data)
    graph_cost_vs_validated(data)
    print("Done. 14 SVG files written to docs/assets/")
