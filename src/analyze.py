"""Policy comparison statistics across replications.

Reads `output/replications.json` (N_REPLICATIONS independent runs per policy
from `src.main`) and answers the report's primary question:

    Are the policies measurably different on KPI X, and which one wins?

For every KPI in METRICS we run:

1. **One-way ANOVA** across all policies. H0 = all policy means are equal.
2. **Tukey HSD post-hoc**, gives a pairwise CI and adjusted p for every pair.
3. **95% confidence intervals per policy** (t-distribution, df = N_REPS - 1).
4. **Pairwise Welch's t-test + Cohen's d** vs. the Heuristic baseline so the
   report has a per-policy "is it better than the random baseline" answer.

ANOVA is the right test for *policy comparison* (continuous KPIs, k>=3
groups). Chi-square stays in `validate.py` because that's a different
question — model-vs-SAP distribution shape, not policy-vs-policy means.

Output:
    output/policy_stats.json
    output/policy_stats.txt
"""

import json
import math
import os
import statistics
from typing import Iterable

import numpy as np
from scipy import stats


# KPIs we report on. Each entry: key in the per-rep dict + a direction
# ("lower" or "higher" is better) for the verdict text.
METRICS = [
    ("avg_prep_time",          "lower",  "Avg prep time (min/order)"),
    ("avg_lead_time",          "lower",  "Avg lead time (min/order)"),
    ("avg_op_queue_wait",      "lower",  "Avg operator-queue wait (min)"),
    ("avg_walk_distance",      "lower",  "Avg walk distance (m/order)"),
    ("total_walk_distance",    "lower",  "Total walk distance (m)"),
    ("reach_truck_utilization","higher", "RT utilization"),
    ("operator_utilization",   "higher", "Operator utilization"),
    ("orders_completed",       "higher", "Orders completed"),
]

BASELINE_POLICY = "Baseline (Heuristic)"


def _by_policy(reps: dict, key: str) -> dict[str, list[float]]:
    return {pol: [r[key] for r in rs] for pol, rs in reps.items()}


def _mean_ci(values: list[float], alpha: float = 0.05) -> tuple[float, float, float, float]:
    """Returns (mean, half_width, ci_lo, ci_hi) using Student-t."""
    n = len(values)
    m = statistics.fmean(values)
    if n < 2:
        return m, float("nan"), m, m
    sd = statistics.stdev(values)
    se = sd / math.sqrt(n)
    t_crit = stats.t.ppf(1 - alpha / 2, df=n - 1)
    h = t_crit * se
    return m, h, m - h, m + h


def _cohens_d(a: list[float], b: list[float]) -> float:
    """Pooled-SD Cohen's d. Returns 0 when both groups are constant."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan")
    va, vb = statistics.variance(a), statistics.variance(b)
    pooled = math.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled == 0:
        return 0.0
    return (statistics.fmean(a) - statistics.fmean(b)) / pooled


def _cv(values: list[float]) -> float:
    """Coefficient of variation = stdev / |mean|. Indicates replication
    adequacy: rule of thumb says CV < ~0.10 means N_REPS is enough."""
    m = statistics.fmean(values)
    if m == 0:
        return float("nan")
    if len(values) < 2:
        return 0.0
    return statistics.stdev(values) / abs(m)


def _anova(groups: list[list[float]]):
    if any(len(g) < 2 for g in groups):
        return None
    f, p = stats.f_oneway(*groups)
    return {"F": float(f), "p_value": float(p), "k": len(groups),
            "df_between": len(groups) - 1,
            "df_within": sum(len(g) for g in groups) - len(groups)}


def _tukey(groups: list[list[float]], labels: list[str]):
    """scipy.stats.tukey_hsd, packaged as pairs."""
    if any(len(g) < 2 for g in groups) or len(groups) < 2:
        return None
    res = stats.tukey_hsd(*groups)
    pairs = []
    k = len(groups)
    for i in range(k):
        for j in range(i + 1, k):
            ci = res.confidence_interval(confidence_level=0.95)
            pairs.append({
                "policy_a": labels[i],
                "policy_b": labels[j],
                "mean_diff": float(res.statistic[i, j]),
                "p_value": float(res.pvalue[i, j]),
                "ci_low": float(ci.low[i, j]),
                "ci_high": float(ci.high[i, j]),
                "significant_at_0.05": bool(res.pvalue[i, j] < 0.05),
            })
    return pairs


def _welch_vs_baseline(groups: dict[str, list[float]]):
    if BASELINE_POLICY not in groups:
        return None
    base = groups[BASELINE_POLICY]
    out = []
    for pol, vals in groups.items():
        if pol == BASELINE_POLICY:
            continue
        t, p = stats.ttest_ind(vals, base, equal_var=False)
        out.append({
            "policy": pol,
            "vs": BASELINE_POLICY,
            "t": float(t),
            "p_value": float(p),
            "cohens_d": _cohens_d(vals, base),
            "significant_at_0.05": bool(p < 0.05),
        })
    return out


def _winner(groups: dict[str, list[float]], direction: str) -> str:
    means = {p: statistics.fmean(v) for p, v in groups.items()}
    if direction == "lower":
        return min(means, key=means.get)
    return max(means, key=means.get)


def analyze(reps: dict) -> dict:
    report = {"n_replications": {p: len(rs) for p, rs in reps.items()},
              "metrics": {}}
    for key, direction, label in METRICS:
        groups = _by_policy(reps, key)
        policies = list(groups.keys())
        glist = [groups[p] for p in policies]

        per_policy = {}
        for p, vs in groups.items():
            mean, h, lo, hi = _mean_ci(vs)
            per_policy[p] = {
                "n": len(vs),
                "mean": mean,
                "stdev": statistics.stdev(vs) if len(vs) > 1 else 0.0,
                "ci95_half_width": h,
                "ci95_low": lo,
                "ci95_high": hi,
                "cv": _cv(vs),
                "min": min(vs),
                "max": max(vs),
            }

        report["metrics"][key] = {
            "label": label,
            "direction": direction,
            "winner": _winner(groups, direction),
            "per_policy": per_policy,
            "anova": _anova(glist),
            "tukey_hsd": _tukey(glist, policies),
            "welch_vs_baseline": _welch_vs_baseline(groups),
        }
    return report


def _fmt(x, fmt=".3f"):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    return format(x, fmt)


def write_text_report(report: dict, path: str) -> None:
    lines = []
    lines.append("Policy comparison statistics")
    lines.append("=" * 72)
    lines.append("")
    lines.append("Replications per policy:")
    for p, n in report["n_replications"].items():
        lines.append(f"  {p:30s} n = {n}")
    lines.append("")

    for key, block in report["metrics"].items():
        lines.append(f"--- {block['label']}  (direction: {block['direction']} is better)")
        lines.append(f"Winner: {block['winner']}")
        lines.append("")
        lines.append(f"  {'Policy':30s}  {'mean':>10s}  {'±95% CI':>10s}  {'stdev':>10s}  {'CV':>6s}")
        for p, st in block["per_policy"].items():
            lines.append(
                f"  {p:30s}  {_fmt(st['mean']):>10s}  "
                f"{_fmt(st['ci95_half_width']):>10s}  "
                f"{_fmt(st['stdev']):>10s}  {_fmt(st['cv'], '.3f'):>6s}"
            )
        a = block["anova"]
        if a:
            verdict = "REJECT H0 (means differ)" if a["p_value"] < 0.05 else "fail to reject H0"
            lines.append(
                f"\n  ANOVA: F({a['df_between']},{a['df_within']}) = "
                f"{a['F']:.3f}, p = {a['p_value']:.4f} -> {verdict}"
            )
        if block["tukey_hsd"]:
            sig_pairs = [t for t in block["tukey_hsd"] if t["significant_at_0.05"]]
            lines.append(f"\n  Tukey HSD pairs significant at 0.05: {len(sig_pairs)} of "
                         f"{len(block['tukey_hsd'])}")
            for t in block["tukey_hsd"]:
                marker = "*" if t["significant_at_0.05"] else " "
                lines.append(
                    f"   {marker} {t['policy_a']:28s} vs {t['policy_b']:28s}  "
                    f"diff={_fmt(t['mean_diff']):>10s}  "
                    f"95% CI [{_fmt(t['ci_low'])}, {_fmt(t['ci_high'])}]  "
                    f"p={_fmt(t['p_value'], '.4f')}"
                )
        if block["welch_vs_baseline"]:
            lines.append("\n  Welch t-test vs baseline (Heuristic) + Cohen's d:")
            for w in block["welch_vs_baseline"]:
                marker = "*" if w["significant_at_0.05"] else " "
                lines.append(
                    f"   {marker} {w['policy']:30s}  t={_fmt(w['t'])}  "
                    f"p={_fmt(w['p_value'], '.4f')}  d={_fmt(w['cohens_d'])}"
                )
        lines.append("")
    lines.append("Notes:")
    lines.append("  - ANOVA tests whether at least one policy mean differs from the rest.")
    lines.append("  - Tukey HSD controls family-wise error across all policy pairs.")
    lines.append("  - Welch t-test does not assume equal variances; pairs each non-")
    lines.append("    baseline policy against the Heuristic to give a per-policy verdict.")
    lines.append("  - Cohen's d magnitude (rule of thumb): 0.2 small, 0.5 medium, 0.8 large.")
    lines.append("  - CV per policy < ~0.10 suggests N_REPLICATIONS is adequate for that KPI.")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def run_analysis(reps_path: str = "output/replications.json") -> dict:
    with open(reps_path) as f:
        reps = json.load(f)
    report = analyze(reps)
    os.makedirs("output", exist_ok=True)
    with open("output/policy_stats.json", "w") as f:
        json.dump(report, f, indent=2)
    write_text_report(report, "output/policy_stats.txt")
    print("Wrote output/policy_stats.{json,txt}")
    # Quick stdout summary
    for key, block in report["metrics"].items():
        a = block["anova"]
        if a:
            print(f"  {block['label']:34s}  winner={block['winner']:25s}  "
                  f"ANOVA p={a['p_value']:.4f}")
    return report


if __name__ == "__main__":
    run_analysis()
