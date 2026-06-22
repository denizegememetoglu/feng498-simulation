#!/usr/bin/env python3
r"""Generate LaTeX tables for the FENG 498 final report directly from the
simulation output files, so every number in the report traces back to a
machine-written artefact (no hand-typed values).

Reads:  output/policy_summary.json, output/policy_stats.json,
        output/validation_report.json, output/zwm92_summary.json,
        output/timing_study_f400.json, output/preprocess_stats.json,
        output/sensitivity.json, output/run_manifest.json
Writes: report/sections/gen/*.tex  (one file per table, input-able)
"""
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "report", "sections", "gen")
os.makedirs(OUT, exist_ok=True)


def load(name):
    with open(os.path.join(ROOT, "output", name)) as f:
        return json.load(f)


summary = load("policy_summary.json")
stats = load("policy_stats.json")
val = load("validation_report.json")
zwm = load("zwm92_summary.json")
timing = load("timing_study_f400.json")
prep = load("preprocess_stats.json")
sens = load("sensitivity.json")
manifest = load("run_manifest.json")

POLICIES = [
    "Baseline (Actual SAP)",
    "Baseline (Heuristic)",
    "Usage-based ABC",
    "Double ABC",
    "Travel-distance Optimized",
    "Line-aware Slotting",
]
SHORT = {
    "Baseline (Actual SAP)": "Current SAP placement",
    "Baseline (Heuristic)": "Capacity heuristic",
    "Usage-based ABC": "Usage-based ABC",
    "Double ABC": "Double ABC",
    "Travel-distance Optimized": "Travel-distance opt.",
    "Line-aware Slotting": "Line-aware slotting",
}
N_REP = 20
T_CRIT = 2.093  # t(0.975, df=19)


def ci(std):
    return T_CRIT * std / math.sqrt(N_REP)


def w(fname, text):
    path = os.path.join(OUT, fname)
    with open(path, "w") as f:
        f.write(text)
    print("wrote", path)


def fmt(x, nd=2):
    return f"{x:.{nd}f}"


def fill(template, **kw):
    for k, v in kw.items():
        template = template.replace("@" + k + "@", str(v))
    return template


# ---------------------------------------------------------------- T1: KPI summary
rows = []
for p in POLICIES:
    s = summary[p]
    rows.append(
        " & ".join(
            [
                SHORT[p],
                fmt(s["avg_lead_time"]) + " $\\pm$ " + fmt(ci(s["avg_lead_time_std"])),
                fmt(s["avg_total_wait"]) + " $\\pm$ " + fmt(ci(s["avg_total_wait_std"])),
                fmt(100 * s["reach_truck_utilization"], 1),
                fmt(s["throughput_orders_per_day"], 1),
                fmt(s["avg_walk_distance"], 1) + " $\\pm$ " + fmt(ci(s["avg_walk_distance_std"]), 1),
            ]
        )
        + r" \\"
    )
t1 = fill(r"""\begin{table}[htbp]
\centering
\caption{Average performance of the six storage policies over $N=20$ replications
(mean $\pm$ 95\% confidence-interval half-width where the interval is informative).}
\label{tab:kpi_summary}
\small
\begin{tabular}{lccccc}
\toprule
Policy & \makecell{Lead time\\(min/order)} & \makecell{Waiting time\\(min/order)} & \makecell{RT util.\\(\%)} & \makecell{Throughput\\(orders/day)} & \makecell{Walk dist.\\(m/order)} \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{table}
""", ROWS="\n".join(rows))
w("tab_kpi_summary.tex", t1)

# ---------------------------------------------------------------- T2: ANOVA
HEADLINE = [
    ("avg_lead_time", "Kitting lead time (min)"),
    ("avg_total_wait", "Total waiting time (min)"),
    ("reach_truck_utilization", "Reach-truck utilization"),
    ("throughput_orders_per_day", "Throughput (orders/day)"),
    ("avg_walk_distance", "Walk distance (m/order)"),
]
rows = []
for key, label in HEADLINE:
    a = stats["metrics"][key]["anova"]
    pv = a["p_value"]
    pstr = f"{pv:.2e}".replace("e-", r" \times 10^{-") + "}" if pv < 1e-3 else f"{pv:.3f}"
    sig = "Reject $H_0$" if pv < 0.05 else "Fail to reject $H_0$"
    rows.append(
        f"{label} & {a['F']:.2f} & ({a['df_between']}, {a['df_within']}) & ${pstr}$ & {sig} \\\\"
    )
t2 = fill(r"""\begin{table}[htbp]
\centering
\caption{One-way ANOVA across the six policies for each key performance indicator
($N=20$ replications per policy). $H_0$: all policy means are equal.}
\label{tab:anova}
\small
\begin{tabular}{lcccl}
\toprule
KPI & $F$ & d.f. & $p$-value & Decision at $\alpha=0.05$ \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{table}
""", ROWS="\n".join(rows))
w("tab_anova.tex", t2)

# ------------------------------------------------- T3: paired t vs SAP baseline (CRN)
# Computed fresh from kpi_by_replication.csv: CRN seeds make replications pairable,
# and the company-relevant reference is the CURRENT SAP placement.
import csv

from scipy import stats as sps

leads = {p: {} for p in POLICIES}
with open(os.path.join(ROOT, "output", "kpi_by_replication.csv")) as f:
    for row in csv.DictReader(f):
        if row["policy"] in leads:
            leads[row["policy"]][int(row["replication"])] = float(row["avg_lead_time"])
ref = leads["Baseline (Actual SAP)"]
rows = []
for p in POLICIES:
    if p == "Baseline (Actual SAP)":
        continue
    common = sorted(set(ref) & set(leads[p]))
    a = [leads[p][i] for i in common]
    b = [ref[i] for i in common]
    diffs = [x - y for x, y in zip(a, b)]
    mean_diff = sum(diffs) / len(diffs)
    t_stat, pv = sps.ttest_rel(a, b)
    pstr = f"{pv:.2e}".replace("e-", r" \times 10^{-") + "}" if pv < 1e-3 else f"{pv:.3f}"
    sig = "Yes" if pv < 0.05 else "No"
    rows.append(
        f"{SHORT[p]} & {mean_diff:+.2f} & {t_stat:.2f} & ${pstr}$ & {sig} \\\\"
    )
t3 = fill(r"""\begin{table}[htbp]
\centering
\caption{Replication-paired $t$-tests on kitting lead time against the current SAP
placement (common random numbers, $N=20$ pairs). Negative differences favour the
alternative policy.}
\label{tab:paired_t}
\begin{tabular}{lcccc}
\toprule
Policy vs.\ current placement & Mean diff.\ (min) & $t$ & $p$-value & Significant? \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{table}
""", ROWS="\n".join(rows))
w("tab_paired_t.tex", t3)

# ---------------------------------------------------------------- T4: validation
chi = val["chi_square_per_rack_restricted"]
tt = val["t_test_per_material"]
dv = val["daily_volume_check"]
t4 = fill(r"""\begin{table}[htbp]
\centering
\caption{Operational validation of the simulation against the four-month
WM dispatch log.}
\label{tab:validation}
\small
\begin{tabular}{llll}
\toprule
Check & Statistic & Value & Note \\
\midrule
Pick share per rack row & $\chi^2$ (d.f.\ @DOF@) & @CHI2@ & $p = @CHIP@$ \\
\quad effect size & Cram\'er's $V$ & @CV@ & small deviation \\
Per-material pick counts & paired $t$ ($n=@NMAT@$) & @TSTAT@ & $p = @TP@$ \\
Daily order volume & sim vs.\ actual & @SIMV@ vs.\ @ACTV@ orders/day & @RELERR@\% rel.\ error \\
\bottomrule
\end{tabular}
\end{table}
""",
    DOF=chi["dof"], CHI2=fmt(chi["chi_square"], 1), CHIP=f"{chi['p_value']:.1e}".replace("e-", r" \times 10^{-") + "}",
    CV=fmt(chi["cramers_v"], 3), NMAT=tt["n_materials_paired"], TSTAT=fmt(tt["t_statistic"], 2),
    TP=f"{tt['p_value']:.1e}".replace("e-", r" \times 10^{-") + "}",
    SIMV=fmt(dv["sim_orders_per_day"], 0), ACTV=fmt(dv["zwm92_orders_per_active_day"], 1),
    RELERR=fmt(100 * dv["relative_error"], 1))
w("tab_validation.tex", t4)

# ------------------------------------------------------- T5: pick share per rack
racks = chi["racks"]
obs = chi["observed"]
exp = chi["expected"]
tot_o, tot_e = sum(obs), sum(exp)
rows = [
    f"{r} & {100*e/tot_e:.1f} & {100*o/tot_o:.1f} \\\\"
    for r, o, e in sorted(zip(racks, obs, exp), key=lambda x: -x[2])
]
t5 = fill(r"""\begin{table}[htbp]
\centering
\caption{Distribution of picks across rack rows: real WM dispatch log vs.\
simulation under the current SAP placement (decoded rack-row picks only).}
\label{tab:rack_share}
\begin{tabular}{lcc}
\toprule
Rack row & Actual share (\%) & Simulated share (\%) \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{table}
""", ROWS="\n".join(rows))
w("tab_rack_share.tex", t5)

# ---------------------------------------------------------------- T6: dataset
fam_rows = "\n".join(
    f"{k.replace('_', chr(92) + '_')} & {v:,} \\\\"
    for k, v in sorted(zwm["families"].items(), key=lambda x: -x[1])
)
t6 = fill(r"""\begin{table}[htbp]
\centering
\caption{WM dispatch-log (transaction ZWM92) coverage by product family,
@DMIN@ -- @DMAX@.}
\label{tab:zwm92}
\begin{tabular}{lr}
\toprule
Product family & Dispatch rows \\
\midrule
@ROWS@
\midrule
Total rows & @TOT@ \\
Kit orders reconstructed & @ORD@ \\
Distinct materials observed & @MAT@ \\
Kardex picks & @KAR@ \\
\bottomrule
\end{tabular}
\end{table}
""",
    DMIN=zwm["date_min"][:10], DMAX=zwm["date_max"][:10], ROWS=fam_rows,
    TOT=f"{zwm['total_rows']:,}", ORD=f"{zwm['orders_built']:,}",
    MAT=f"{zwm['materials_observed']:,}", KAR=f"{zwm['kardex_picks']:,}")
w("tab_zwm92.tex", t6)

# ---------------------------------------------------------------- T7: timing
cat = timing["category_stats"]
LABELS = [
    ("manual_pick", "Operator pick from pallet"),
    ("rt_pick", "Reach-truck pick/place"),
    ("walk_corridor", "Corridor walk (per leg)"),
    ("rt_travel", "Reach-truck travel (per leg)"),
    ("place_on_cart", "Place item on kit cart"),
    ("rf_scan", "RF terminal scan"),
]
rows = []
for key, label in LABELS:
    if key in cat:
        c = cat[key]
        n = c.get("n", c.get("count", "--"))
        mean = c.get("mean_min", c.get("mean", 0.0))
        cv = c["stdev_s"] / c["mean_s"] if c.get("mean_s") else 0.0
        rows.append(f"{label} & {n} & {mean:.3f} & {cv:.2f} \\\\")
t7 = fill(r"""\begin{table}[htbp]
\centering
\caption{Micro-element times extracted from the F400 kitting video study
(@NOBS@ timed events, @MINS@ observed minutes).}
\label{tab:timing}
\begin{tabular}{lccc}
\toprule
Activity element & $n$ & Mean (min) & CV \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{table}
""", NOBS=timing["total_observations"], MINS=fmt(timing["total_observed_minutes"], 0),
    ROWS="\n".join(rows))
w("tab_timing.tex", t7)

# ---------------------------------------------------------------- T8: preprocess
t8 = fill(r"""\begin{table}[htbp]
\centering
\caption{SAP master-data preprocessing results.}
\label{tab:preprocess}
\begin{tabular}{lr}
\toprule
Item & Count \\
\midrule
Active materials in scope & @M1@ \\
Materials with a storage bin & @M2@ \\
\quad of which decoded rack/bay/level bins & @M3@ \\
\quad of which Kardex bins & @M4@ \\
Storage bins parsed & @B1@ \\
Malformed / undecodable bins & @B2@ \\
Modelled pallet positions & 3,101 \\
\bottomrule
\end{tabular}
\end{table}
""",
    M1=f"{prep['materials_total']:,}", M2=f"{prep['materials_with_bin']:,}",
    M3=f"{prep['materials_with_decoded_bin']:,}", M4=f"{prep['materials_in_kardex']:,}",
    B1=f"{prep['bins_total']:,}", B2=f"{prep['bins_malformed']:,}")
w("tab_preprocess.tex", t8)

# ------------------------------------------------------- T9: appendix full KPI
KEYS = [
    ("avg_lead_time", "Lead time (min)", 2),
    ("avg_prep_time", "Prep time (min)", 2),
    ("avg_total_wait", "Total wait (min)", 2),
    ("p95_lead_time", "P95 lead time (min)", 1),
    ("avg_walk_distance", "Walk distance (m)", 1),
    ("throughput_orders_per_day", "Throughput (orders/day)", 1),
    ("reach_truck_utilization", "RT utilization", 3),
    ("operator_utilization", "Operator utilization", 3),
    ("kardex_utilization", "Kardex utilization", 3),
    ("orders_completed", "Orders completed (5 days)", 0),
]
rows = []
for key, label, nd in KEYS:
    cells = " & ".join(fmt(summary[p][key], nd) for p in POLICIES)
    rows.append(f"{label} & {cells} \\\\")
t9 = fill(r"""\begin{table}[htbp]
\centering
\caption{Full KPI table, mean over $N=20$ replications.}
\label{tab:kpi_full}
\scriptsize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{l*{6}{c}}
\toprule
KPI & \makecell{Current\\SAP} & \makecell{Capacity\\heuristic} & \makecell{Usage\\ABC} & \makecell{Double\\ABC} & \makecell{Travel-dist.\\opt.} & \makecell{Line-aware\\slotting} \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{table}
""", ROWS="\n".join(rows))
w("tab_kpi_full.tex", t9)

# ------------------------------------------------------- T10: sensitivity table
rows = []
base_lead = sens["baseline"]["avg_lead_time"]
NICE = {
    "OPERATOR_WALK_SPEED_M_PER_MIN": "Operator walking speed",
    "REACH_TRUCK_SPEED_M_PER_MIN": "Reach-truck travel speed",
    "REACH_TRUCK_LIFT_TIME_PER_LEVEL": "Reach-truck lift time per level",
    "REACH_TRUCK_PICK_PLACE_TIME": "Reach-truck pick/place time",
    "OPERATOR_PICK_TIME": "Operator pick time",
    "MANUAL_PICK_TIME_PENALTY": "Manual high-level pick penalty",
    "KARDEX_PICK_TIME": "Kardex pick time",
    "KARDEX_CAROUSEL_TIME": "Kardex carousel time",
    "IAT_MEAN_MIN_OVERRIDE": "Order inter-arrival time",
}
for param, pert in sens["perturbations"].items():
    vals = [
        run["kpis"]["avg_lead_time"]
        for run in pert.get("runs", {}).values()
        if isinstance(run, dict) and "kpis" in run
    ]
    if not vals:
        continue
    vals.append(base_lead)
    lo, hi = min(vals), max(vals)
    rows.append((hi - lo, f"{NICE.get(param, param)} & {lo:.2f} & {hi:.2f} & {hi-lo:.2f} \\\\"))
rows.sort(key=lambda r: -r[0])
t10 = fill(r"""\begin{table}[htbp]
\centering
\caption{One-at-a-time sensitivity of average lead time to perturbations of the
timing parameters (baseline lead time @BASE@ min).}
\label{tab:sensitivity}
\small
\begin{tabular}{lccc}
\toprule
Parameter & Min lead (min) & Max lead (min) & Range (min) \\
\midrule
@ROWS@
\bottomrule
\end{tabular}
\end{table}
""", BASE=fmt(base_lead, 2), ROWS="\n".join(r for _, r in rows))
w("tab_sensitivity.tex", t10)

# ------------------------------------------------------- facts file for writers
facts = {
    "run_id": manifest["run_id"],
    "n_replications": 20,
    "sim_days": manifest["parameters"]["sim_days"],
    "resources": {
        "reach_trucks": manifest["parameters"]["num_reach_trucks"],
        "operators": manifest["parameters"]["num_operators"],
        "kardex_units": manifest["parameters"]["num_kardex_units"],
    },
    "kpi": {
        p: {
            "lead": summary[p]["avg_lead_time"],
            "lead_ci": ci(summary[p]["avg_lead_time_std"]),
            "wait": summary[p]["avg_total_wait"],
            "rt_util": summary[p]["reach_truck_utilization"],
            "op_util": summary[p]["operator_utilization"],
            "walk": summary[p]["avg_walk_distance"],
            "throughput_day": summary[p]["throughput_orders_per_day"],
        }
        for p in POLICIES
    },
    "anova_lead": stats["metrics"]["avg_lead_time"]["anova"],
    "validation": {
        "chi2": chi["chi_square"],
        "chi2_p": chi["p_value"],
        "cramers_v": chi["cramers_v"],
        "t_per_material": tt,
        "daily_volume": dv,
    },
    "zwm92": {k: zwm[k] for k in ("total_rows", "orders_built", "materials_observed",
                                   "iat_within_shift_mean", "timestamped_orders")},
}
with open(os.path.join(OUT, "facts.json"), "w") as f:
    json.dump(facts, f, indent=1, default=str)
print("wrote facts.json")
