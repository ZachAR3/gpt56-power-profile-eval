# SolTerraLuna — Power-Profile Overhaul Model Evaluation

A comparative evaluation of **nine AI model configurations** that independently
reviewed the same power-profile overhaul in the `honor-control` codebase. Two
independent meta-evaluators — **GLM-5.2** and **GPT-5.6-Sol High** (with web
access) — then audited all nine reports to reduce single-model bias.

## TL;DR

| Rank | Report | Model | Effort | Cost | Avg score | Key strength |
|------|--------|-------|--------|------|-----------|--------------|
| 1 | **SOL High** | GPT-5.6-Sol | high | $5.08 | 9.0 | Best overall accuracy and deployment awareness |
| 2 | **LUNA Max** | GPT-5.6-Luna | max | $2.11 | 8.4 | Deepest investigation, unique dependency discovery |
| 3 | **TERRA XHigh** | GPT-5.6-Terra | xhigh | $3.04 | 8.3 | Zero false positives, unique turbo finding |
| 4 | **SOL Medium** | GPT-5.6-Sol | medium | $1.29 | 8.1 | Best value, high signal-to-noise |
| 5 | **LUNA XHigh** | GPT-5.6-Luna | xhigh | $1.39 | 8.1 | Solid, broad coverage |
| 6 | **5.5 XHigh** | GPT-5.5 | xhigh | $5.23 | 7.6 | Good coverage, missed deployment blockers |
| 7 | **GLM Max** | GLM-5.2 | max | $1.79 | 7.0 | Unique findings, but two incorrect High-severity claims |
| 8 | **LUNA High** | GPT-5.6-Luna | high | $0.85 | 7.5 | Concise, missed PPD ownership contradiction |
| 9 | **5.5 High** | GPT-5.5 | high | $2.51 | 6.4 | Understated severity, missed most issues |

**Both evaluators agree** on the top two (SOL High, LUNA Max) and on the overall
verdict: the overhaul is **unsafe to merge or release**. The primary disagreement
is about GLM Max (ranked 3rd by GLM, 9th by Sol). Independent verification confirms
Sol is correct — GLM Max's claim that `ProtectSystem=strict` blocks `systemctl
mask` is wrong, because `systemctl mask` is a D-Bus operation handled by PID 1.

**Best value:** SOL Medium ($1.29) identified key issues that several higher-cost
reports missed. **Best overall:** SOL High ($5.08) had the best accuracy and
deployment awareness.

## Key graphs

### Overall scores by evaluator

![Overall Scores](docs/assets/01_overall_scores.svg)

### Cost vs. performance

![Cost vs Performance](docs/assets/04_cost_vs_performance.svg)

### Issue coverage matrix

![Issue Coverage](docs/assets/06_issue_coverage.svg)

### Ranking differences between evaluators

![Ranking Comparison](docs/assets/05_ranking_comparison.svg)

More graphs are in the [full report](MODELS_EVAL_SUMMARY.md) and the
`docs/assets/` directory.

## Repository contents

| File | Description |
|------|-------------|
| `MODELS_EVAL_SUMMARY.md` | **Combined report** reconciling both meta-evaluations |
| `GLM_MODELS_EVAL.md` | Meta-evaluation by GLM-5.2 (no web access) |
| `SOL_WEB_HIGH_MODELS_EVAL.md` | Meta-evaluation by GPT-5.6-Sol High (with web access) |
| `5.5_HIGH_EVAL.md` | GPT-5.5 high-effort code review (7 findings) |
| `5.5_XHIGH_EVAL.md` | GPT-5.5 xhigh-effort code review (12 findings) |
| `GLM_MAX_EVAL.md` | GLM-5.2 max-effort code review (16 findings) |
| `LUNA_HIGH_EVAL.md` | GPT-5.6-Luna high-effort code review (8 findings) |
| `LUNA_MAX_EVAL.md` | GPT-5.6-Luna max-effort code review (14 findings) |
| `LUNA_XHIGH_EVAL.md` | GPT-5.6-Luna xhigh-effort code review (13 findings) |
| `SOL_HIGH_EVAL.md` | GPT-5.6-Sol high-effort code review (11 findings) |
| `SOL_MEDIUM_EVAL.md` | GPT-5.6-Sol medium-effort code review (9 findings) |
| `TERRA_XHIGH_EVAL.md` | GPT-5.6-Terra xhigh-effort code review (7 findings) |
| `generate_graphs.py` | Script that regenerates all graphs from `docs/evaluation/eval_data.json` |
| `docs/evaluation/eval_data.json` | Normalized data (scores, costs, rankings, issue coverage) |
| `docs/assets/` | SVG graphs |
| `honor-control.tar.gz` | Archived snapshot of the reviewed codebase (not committed; 279 MB) |

## Regenerating the graphs

```bash
pip install matplotlib numpy
python3 generate_graphs.py
```

Graphs are written to `docs/assets/` as SVG files. The script reads all data from
`docs/evaluation/eval_data.json`, so graphs and tables are fully reproducible from
the normalized data.

## Methodology

- **Subject:** `honor-control` power-profile overhaul, commit `34d31f9` (review range
  `4d8994a..34d31f9`, 4 commits, 326 insertions / 7 deletions across 4 files).
- **Models evaluated:** Nine configurations across 5 models (GPT-5.5, GPT-5.6-Luna,
  GPT-5.6-Sol, GPT-5.6-Terra, GLM-5.2) at medium/high/xhigh/max effort levels.
- **Meta-evaluators:** Two independent evaluations (GLM-5.2 without web access,
  GPT-5.6-Sol High with web access) scored all nine reports across 8 criteria.
- **Cost data:** Extracted from Codex session logs and opencode database using
  official API pricing. Total evaluation cost: $23.29.
- **No real hardware was touched** in any review. All findings are based on
  code-path analysis, dependency source inspection, arithmetic verification, and
  safe probes.

For the complete analysis including disagreements, confidence levels, and
per-workload recommendations, see the [full combined report](MODELS_EVAL_SUMMARY.md).
