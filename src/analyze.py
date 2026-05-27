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

import csv
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
    if "paired_by_order" in report:
        lines.append("--- Paired-by-order Wilcoxon tests vs Baseline (Heuristic)")
        lines.append("    (N_REPLICATIONS=1 → comparison is per-order, not per-rep)")
        lines.append("    p_raw = uncorrected; p_holm = Holm-Bonferroni family-wise; * uses p_holm.")
        lines.append("")
        for pol, metrics in report["paired_by_order"].items():
            lines.append(f"  {pol}")
            for key, st in metrics.items():
                marker = "*" if st["significant_at_0.05"] else " "
                p_raw = st.get("p_raw", st.get("p_value"))
                p_holm = st.get("p_holm", st.get("p_value"))
                lines.append(
                    f"   {marker} {st['label']:20s}  "
                    f"mean_diff={_fmt(st['mean_diff']):>10s}  "
                    f"median_diff={_fmt(st['median_diff']):>10s}  "
                    f"W={_fmt(st['wilcoxon_W'], '.1f'):>10s}  "
                    f"p_raw={_fmt(p_raw, '.4f')}  "
                    f"p_holm={_fmt(p_holm, '.4f')}  "
                    f"(n={st['n_paired']})"
                )
            lines.append("")
    lines.append("Notes:")
    lines.append("  - ANOVA / Tukey / Welch require N_REPLICATIONS >= 2; with same-seed")
    lines.append("    single-trajectory runs (advisor's setup) they are not applicable —")
    lines.append("    use the paired-by-order Wilcoxon block above instead.")
    lines.append("  - ANOVA tests whether at least one policy mean differs from the rest.")
    lines.append("  - Tukey HSD controls family-wise error across all policy pairs.")
    lines.append("  - Welch t-test does not assume equal variances; pairs each non-")
    lines.append("    baseline policy against the Heuristic to give a per-policy verdict.")
    lines.append("  - Cohen's d magnitude (rule of thumb): 0.2 small, 0.5 medium, 0.8 large.")
    lines.append("  - Wilcoxon signed-rank is the non-parametric paired test on per-order")
    lines.append("    KPI differences (policy minus Heuristic on the same order).")
    lines.append("  - Holm-Bonferroni correction is applied across the Wilcoxon family")
    lines.append("    (3 metrics × (n_policies - 1) tests). p_raw shows uncorrected;")
    lines.append("    p_holm shows family-wise corrected. * uses p_holm < 0.05.")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def paired_by_order(per_policy_csv: dict[str, str]) -> dict:
    """Paired-by-order comparison when N_REPLICATIONS == 1.

    With a single trajectory per policy (advisor-mandated same-seed run),
    each order has one realisation per policy. We pair on `order_id` and
    run Wilcoxon signed-rank tests on per-order walk distance, prep time,
    and lead time relative to the Heuristic baseline.

    H3 fix: Holm-Bonferroni correction is applied across the family of
    Wilcoxon tests (3 metrics × (n_policies-1)). Each entry carries both
    `p_raw` (uncorrected) and `p_holm` (family-wise corrected); the
    `significant_at_0.05` flag uses `p_holm` to avoid false positives
    from running many tests.

    M7 fix: skipped policies (n_paired < 30) are logged to stdout instead
    of being silently dropped.

    Args:
        per_policy_csv: {policy_name: csv_path_with_per_order_rows}
    """
    base_name = BASELINE_POLICY
    if base_name not in per_policy_csv:
        return {}
    base_rows = _read_order_csv(per_policy_csv[base_name])
    if not base_rows:
        return {}

    out: dict[str, dict] = {}
    metric_keys = [
        ("walk_distance", "walk distance (m)", "lower"),
        ("prep_time", "prep time (min)", "lower"),
        ("lead_time", "lead time (min)", "lower"),
    ]

    # Pass 1: compute Wilcoxon stats; collect raw p-values for Holm pass.
    pvals_for_holm: list[float] = []
    holm_index: list[tuple[str, str]] = []
    for pol, csv_path in per_policy_csv.items():
        if pol == base_name:
            continue
        pol_rows = _read_order_csv(csv_path)
        common = sorted(set(base_rows) & set(pol_rows))
        if len(common) < 30:
            print(f"  [SKIP paired_by_order] {pol} vs {base_name}: "
                  f"n_common={len(common)} < 30 — insufficient paired "
                  f"observations.")
            continue
        per_metric = {}
        for key, label, direction in metric_keys:
            base_vals = [base_rows[i].get(key, 0.0) for i in common]
            pol_vals = [pol_rows[i].get(key, 0.0) for i in common]
            diff = [p - b for p, b in zip(pol_vals, base_vals)]
            try:
                w, p = stats.wilcoxon(diff, zero_method="wilcox", alternative="two-sided")
                w_stat, p_val = float(w), float(p)
            except (ValueError, ZeroDivisionError):
                w_stat, p_val = float("nan"), float("nan")
            per_metric[key] = {
                "label": label,
                "direction": direction,
                "n_paired": len(common),
                "mean_diff": statistics.fmean(diff),
                "median_diff": statistics.median(diff),
                "wilcoxon_W": w_stat,
                "p_raw": p_val,
                "p_holm": p_val,  # filled in pass 2
                "significant_at_0.05": False,
            }
            if not math.isnan(p_val):
                pvals_for_holm.append(p_val)
                holm_index.append((pol, key))
        out[pol] = per_metric

    # Pass 2: Holm-Bonferroni correction across the family of tests.
    if pvals_for_holm:
        try:
            from statsmodels.stats.multitest import multipletests
            _, p_holm_arr, _, _ = multipletests(
                pvals_for_holm, alpha=0.05, method="holm"
            )
            for (pol, key), p_holm in zip(holm_index, p_holm_arr):
                entry = out[pol][key]
                entry["p_holm"] = float(p_holm)
                entry["significant_at_0.05"] = bool(p_holm < 0.05)
        except ImportError:
            print("  [WARN paired_by_order] statsmodels missing — "
                  "Holm correction skipped; using raw p-values.")
            for (pol, key) in holm_index:
                entry = out[pol][key]
                entry["holm_correction_skipped"] = True
                entry["significant_at_0.05"] = bool(entry["p_raw"] < 0.05)
    return out


def _read_order_csv(path: str) -> dict[int, dict]:
    if not os.path.exists(path):
        return {}
    rows: dict[int, dict] = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                oid = int(row["order_id"])
            except (ValueError, KeyError):
                continue
            rows[oid] = {k: (float(v) if v not in (None, "") else 0.0)
                         for k, v in row.items() if k not in ("order_id", "line")}
    return rows


def run_analysis(reps_path: str = "output/replications.json") -> dict:
    with open(reps_path) as f:
        reps = json.load(f)
    report = analyze(reps)

    # If N=1, also do paired-by-order Wilcoxon tests on the per-order CSVs.
    n_reps = max(len(rs) for rs in reps.values()) if reps else 0
    if n_reps == 1:
        per_policy_csv = {
            pol: f"output/{pol.lower().replace(' ', '_').replace('(', '').replace(')', '')}.csv"
            for pol in reps.keys()
        }
        paired = paired_by_order(per_policy_csv)
        if paired:
            report["paired_by_order"] = paired

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
        else:
            print(f"  {block['label']:34s}  winner={block['winner']:25s}  "
                  f"(N=1, ANOVA n/a)")
    return report


if __name__ == "__main__":
    run_analysis()
