import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config
from src.data_loader import preprocess
from src.warehouse import Warehouse
from src.simulation import WarehouseSimulation
from src.slotting import (ALL_POLICIES, LineAwareSlottingPolicy,
                          RealBaselinePolicy, TravelDistancePolicy)
from src.visualize import compare_policies, plot_prep_time_distribution
from src.recorder import TimelineRecorder


def _instantiate_policy(policy_cls, data):
    if policy_cls is RealBaselinePolicy:
        return policy_cls(
            decoded_bins=data["decoded_bins"],
            kardex_materials=data["kardex_materials"],
        )
    if policy_cls is TravelDistancePolicy:
        return policy_cls(
            picks_by_material=_load_picks_by_material(),
            kardex_materials=data["kardex_materials"],
        )
    if policy_cls is LineAwareSlottingPolicy:
        return policy_cls(
            picks_by_material=_load_picks_by_material(),
            material_to_line=data["material_to_line"],
            kardex_materials=data["kardex_materials"],
        )
    return policy_cls(kardex_materials=data["kardex_materials"])


def _load_picks_by_material() -> dict[str, int]:
    """ZWM92 per-material dispatch counts → TravelDistancePolicy sort key.

    Empty dict when the cache is missing; the policy then falls back to
    the SAP consumption proxy.
    """
    path = "output/zwm92_summary.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(k): int(v) for k, v in data.get("picks_by_material", {}).items()}


def _safe_name(name: str) -> str:
    return name.lower().replace(" ", "_").replace("(", "").replace(")", "")


def _sha256(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_value(args: list[str]) -> str | None:
    try:
        proc = subprocess.run(args, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return proc.stdout.strip()


def _git_sha() -> str | None:
    return _git_value(["git", "rev-parse", "HEAD"])


def _git_dirty() -> bool | None:
    status = _git_value(["git", "status", "--porcelain"])
    if status is None:
        return None
    return bool(status)


def _write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)


def _write_policy_outputs(policy_name: str, kpi) -> None:
    # NOTE: these per-order/per-rack CSVs come from the LAST replication only
    # (distribution plots + timeline playback consistency). Cross-replication
    # KPIs live in replications.json and kpi_by_replication.csv.
    safe = _safe_name(policy_name)
    kpi.to_csv(f"output/{safe}.csv")
    kpi.picks_per_rack_csv(f"output/{safe}_picks_per_rack.csv")
    kpi.picks_per_material_csv(f"output/{safe}_picks_per_material.csv")


def _select_policies(policy_arg: str | None):
    if not policy_arg:
        return list(ALL_POLICIES.items())
    requested = policy_arg.strip()
    for name, policy_cls in ALL_POLICIES.items():
        aliases = {name, _safe_name(name), _safe_name(name).replace("-", "_")}
        if requested in aliases:
            return [(name, policy_cls)]
    valid = ", ".join(ALL_POLICIES.keys())
    raise SystemExit(f"Unknown policy '{policy_arg}'. Valid policies: {valid}")


def _build_run_manifest(
    *,
    run_id: str,
    started_at_utc: str,
    status: str,
    requested_policies: list[str],
    completed_policies: list[str],
    n_replications: int,
    route_check: dict,
) -> dict:
    input_paths = [
        config.DATA_FILE,
        "config/layout.json",
        "config/rack_mapping_dwg_to_sap.json",
        "output/zwm92_summary.json",
        "output/zwm92_orders.json",
        "output/preprocess_stats.json",
        "output/bin_validation_errors.csv",
    ]
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "status": status,
        "started_at_utc": started_at_utc,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": {
            "sha": _git_sha(),
            "dirty": _git_dirty(),
        },
        "parameters": {
            "sim_days": config.SIM_DAYS,
            "n_replications": n_replications,
            "random_seed": config.RANDOM_SEED,
            "same_seed_for_all_reps": config.SAME_SEED_FOR_ALL_REPS,
            "num_reach_trucks": config.NUM_REACH_TRUCKS,
            "num_operators": config.NUM_OPERATORS,
            "num_kardex_units": config.NUM_KARDEX_UNITS,
            "shift_mode": config.SHIFT_MODE,
        },
        "policies_requested": list(requested_policies),
        "policies_completed": list(completed_policies),
        "route_validation": {
            "status": route_check.get("status"),
            "validation_scope": route_check.get("validation_scope"),
            "validated_routes": route_check.get("validated_routes"),
            "issues": len(route_check.get("issues", [])),
            "warnings": len(route_check.get("warnings", [])),
        },
        "file_hashes": {
            path: _sha256(path)
            for path in input_paths
            if os.path.exists(path)
        },
    }


def run_policy(policy_name, policy_cls, data, n_reps=None):
    """Run a policy `n_reps` times with independent seeds. Returns a dict with
    aggregate summary (mean + std across reps), the KPI of the LAST run for
    distribution plots, and a list of per-rep summaries."""
    n_reps = n_reps if n_reps is not None else config.N_REPLICATIONS
    print(f"  Running: {policy_name} ({n_reps} replications)...")
    if getattr(config, "SAME_SEED_FOR_ALL_REPS", False) and n_reps > 1:
        print("    WARN: SAME_SEED_FOR_ALL_REPS=True with n_reps>1 — every "
              "replication is the identical trajectory; all std values will "
              "be 0 by construction and CIs/ANOVA are meaningless.")

    materials = data["materials"]
    material_to_line = data["material_to_line"]
    rep_summaries = []
    last_kpi = None
    last_warehouse = None

    for rep in range(n_reps):
        warehouse = Warehouse()
        policy = _instantiate_policy(policy_cls, data)
        policy.assign(materials, warehouse)
        rack_material_ids = {
            m["material_id"] for m in materials
            if m["material_id"] not in data["kardex_materials"]
        }
        unplaced = rack_material_ids - set(warehouse.material_locations)

        seed = (config.RANDOM_SEED
                if getattr(config, "SAME_SEED_FOR_ALL_REPS", False)
                else config.RANDOM_SEED + rep)
        # JSONL recorder is created only when explicitly enabled. Last rep
        # is the one whose timeline we keep on disk (consistent with
        # last_kpi semantics below — playback then matches the displayed KPIs).
        recorder = None
        if getattr(config, "RECORD_TIMELINE", False) and rep == n_reps - 1:
            recorder = TimelineRecorder(
                policy_name=policy_name,
                output_dir=getattr(config, "TIMELINE_OUTPUT_DIR", "output"),
                kpi_interval_min=getattr(config, "TIMELINE_KPI_SNAPSHOT_INTERVAL_MIN", 10.0),
            )
        sim = WarehouseSimulation(
            warehouse, materials,
            material_to_line=material_to_line,
            kardex_materials=data["kardex_materials"],
            seed=seed,
            recorder=recorder,
        )
        try:
            sim.run()
        finally:
            if recorder is not None:
                recorder.close()
                print(f"    Timeline → {recorder.path}  "
                      f"({recorder.n_events:,} events)")
        summary = sim.kpi.summary(
            num_reach_trucks=config.NUM_REACH_TRUCKS,
            num_operators=config.NUM_OPERATORS,
        )
        summary["replication"] = rep
        summary["seed"] = seed
        summary["sim_days"] = config.SIM_DAYS
        if isinstance(policy, RealBaselinePolicy):
            summary.update({
                "sap_materials_placed": policy.placed_from_sap,
                "sap_slots_assigned": policy.sap_slots_assigned,
                "kardex_materials_routed": policy.placed_kardex,
                "heuristic_fallback_materials": policy.placed_fallback,
            })
        summary["unplaced_rack_materials"] = len(unplaced)
        rep_summaries.append(summary)
        last_kpi = sim.kpi
        last_warehouse = warehouse
        if isinstance(policy, RealBaselinePolicy) and rep == 0:
            print(
                f"    SAP fidelity: {policy.placed_from_sap} from SAP bin, "
                f"{policy.placed_kardex} Kardex routed, "
                f"{policy.placed_fallback} heuristic fallback"
            )
        if rep == 0 and unplaced:
            print(f"    WARN: {len(unplaced)} rack materials unplaced (capacity/input mismatch surfaced)")

    aggregate = _aggregate_summaries(rep_summaries)
    print(f"    Mean orders={aggregate['orders_completed']:.0f}  "
          f"prep={aggregate['avg_prep_time']:.2f}m  "
          f"lead={aggregate['avg_lead_time']:.2f}m  "
          f"walk={aggregate['avg_walk_distance']:.1f}m  "
          f"RT_util={aggregate['reach_truck_utilization'] * 100:.1f}%")
    if aggregate.get("util_overflow"):
        print(f"    WARN: util overflow events: {aggregate['util_overflow']}")
    return aggregate, last_kpi, last_warehouse, rep_summaries


def _aggregate_summaries(summaries):
    if not summaries:
        return {}
    numeric_keys = [
        "orders_started", "orders_completed", "orders_total",
        "orders_with_no_locations",
        "throughput_orders_per_hr", "throughput_orders_per_day",
        "avg_prep_time", "median_prep_time",
        "p95_prep_time", "avg_lead_time", "p95_lead_time", "avg_op_queue_wait",
        "avg_wait_time", "avg_rt_queue_wait", "avg_total_wait",
        "p95_total_wait", "total_wait_time", "avg_walk_distance",
        "total_walk_distance", "reach_truck_utilization", "operator_utilization",
        "kardex_utilization",
        "unplaced_rack_materials", "sap_materials_placed", "sap_slots_assigned",
        "kardex_materials_routed", "heuristic_fallback_materials",
    ]
    out = {}
    for k in numeric_keys:
        vals = [s.get(k, 0.0) for s in summaries if k in s]
        if vals:
            out[k] = statistics.mean(vals)
            out[k + "_std"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
    overflow_events = []
    for s in summaries:
        overflow_events.extend(s.get("util_overflow", []))
    if overflow_events:
        out["util_overflow"] = overflow_events
    return out


# Tidy, Minitab-ready KPI export: one row per (policy, replication).
# Column order: the four advisor KPIs first, then supporting metrics.
_TIDY_KPI_COLUMNS = [
    "avg_lead_time", "avg_total_wait", "reach_truck_utilization",
    "throughput_orders_per_day",
    "throughput_orders_per_hr", "avg_op_queue_wait", "avg_rt_queue_wait",
    "avg_prep_time", "p95_lead_time", "avg_walk_distance",
    "operator_utilization", "kardex_utilization",
    "orders_started", "orders_completed", "orders_total",
    "orders_with_no_locations",
]


def _write_kpi_by_replication(rep_details: dict[str, list[dict]],
                              path: str = "output/kpi_by_replication.csv"):
    """Row = (policy, replication, seed); columns = KPIs. This is the
    before/after export the team loads into Minitab for hypothesis tests."""
    with open(path, "w") as f:
        f.write("policy,replication,seed," + ",".join(_TIDY_KPI_COLUMNS) + "\n")
        for policy, reps in rep_details.items():
            for s in reps:
                row = [str(policy).replace(",", ";"),
                       str(s.get("replication", "")), str(s.get("seed", ""))]
                for col in _TIDY_KPI_COLUMNS:
                    v = s.get(col)
                    row.append(f"{v:.6f}" if isinstance(v, float) else str(v if v is not None else ""))
                f.write(",".join(row) + "\n")


def _parse_cli_args(argv=None):
    p = argparse.ArgumentParser(description="Run all slotting policies + KPIs.")
    p.add_argument("--policy",
                   help="Run only one policy by display name or safe key, e.g. "
                        "'Baseline (Actual SAP)' or baseline_actual_sap.")
    p.add_argument("--sim-days", type=float,
                   help="Override src.config.SIM_DAYS for this run.")
    p.add_argument("--n-reps", type=int,
                   help="Override src.config.N_REPLICATIONS for this run.")
    p.add_argument("--record-timeline", action="store_true",
                   help="Write output/sim_timeline_<policy>.jsonl for "
                        "sim_v2.html playback (M3 — AD-2). Opt-in.")
    p.add_argument("--skip-charts", action="store_true",
                   help="Skip PNG chart generation for fast validation runs.")
    return p.parse_args(argv)


def _mirror_web_outputs():
    """Keep browser mirrors in sync with the latest output/ run.

    The simulation source of truth stays in output/. web/data and docs/data are
    static-browser mirrors only, so stale dashboard numbers do not silently beat
    freshly generated KPIs.
    """
    files = [
        "policy_summary.json",
        "policy_stats.json",
        "kpi_by_replication.csv",
        "validation_report.json",
        "validation_report.txt",
        "preprocess_stats.json",
        "replications.json",
        "run_manifest.json",
        "bin_validation_errors.csv",
        "baseline_heuristic_picks_per_rack.csv",
        "baseline_actual_sap_picks_per_rack.csv",
        "usage-based_abc_picks_per_rack.csv",
        "double_abc_picks_per_rack.csv",
        "travel-distance_optimized_picks_per_rack.csv",
        "line-aware_slotting_picks_per_rack.csv",
        # X14 re-slotting table in the Defense tab joins these two.
        "baseline_actual_sap_picks_per_material.csv",
        "travel-distance_optimized_picks_per_material.csv",
        "line-aware_slotting_picks_per_material.csv",
    ]
    for base in ("web/data", "docs/data"):
        os.makedirs(base, exist_ok=True)
        for name in files:
            src = os.path.join("output", name)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(base, name))
    timeline_files = [
        name for name in os.listdir("output")
        if name.startswith("sim_timeline_") and name.endswith(".jsonl")
    ] if os.path.isdir("output") else []
    for base in ("web/timeline", "docs/timeline"):
        os.makedirs(base, exist_ok=True)
        for name in timeline_files:
            shutil.copyfile(os.path.join("output", name), os.path.join(base, name))
    for target in ("web/route_debug.json", "docs/route_debug.json"):
        if os.path.exists("output/route_debug.json"):
            shutil.copyfile("output/route_debug.json", target)


def main():
    args = _parse_cli_args()
    if args.sim_days is not None:
        if args.sim_days <= 0:
            raise SystemExit("--sim-days must be positive")
        config.SIM_DAYS = float(args.sim_days)
    n_replications = args.n_reps if args.n_reps is not None else config.N_REPLICATIONS
    if n_replications <= 0:
        raise SystemExit("--n-reps must be positive")
    selected_policies = _select_policies(args.policy)
    requested_policies = [name for name, _ in selected_policies]
    completed_policies: list[str] = []

    if args.record_timeline:
        config.RECORD_TIMELINE = True
        print(f"[main] Timeline recording ON → {config.TIMELINE_OUTPUT_DIR}/sim_timeline_*.jsonl")
    print("Preprocessing data...")
    data = preprocess()
    stats = data["stats"]
    print(f"  Materials: {stats['materials_total']} total, "
          f"{stats['materials_with_decoded_bin']} with rack bin, "
          f"{stats['materials_in_kardex']} in Kardex, "
          f"{stats['materials_with_line']} with production line")
    print(f"  Bins: {stats['bins_decoded']} decoded, "
          f"{stats['bins_kardex']} kardex, "
          f"{stats['bins_malformed']} malformed, "
          f"{stats['bins_unmapped_position']} unmapped, "
          f"{stats.get('bins_invalid_position', 0)} invalid-position, "
          f"{stats['bin_duplicates']} duplicates ({stats['bin_conflicts']} conflicts)")
    print(f"  Warehouse: {stats['warehouse_positions']} modeled positions "
          f"vs {stats['warehouse_pdf_capacity']} PDF capacity")
    route_wh = Warehouse()
    route_check = route_wh.validate_route_model()
    os.makedirs("output", exist_ok=True)
    route_wh.write_route_debug("output/route_debug.json", route_check)
    if route_check["issues"]:
        raise SystemExit(
            "Route model failed before simulation; see output/route_debug.json"
        )
    if route_check["warnings"]:
        print(f"  Route model: WARN ({len(route_check['warnings'])} assumptions/TODOs), "
              f"{route_check['validation_scope']} scope / {route_check['validated_routes']} routes, "
              "debug written to output/route_debug.json")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    started_at = datetime.now(timezone.utc).isoformat()
    _write_json(
        "output/run_manifest.json",
        _build_run_manifest(
            run_id=run_id,
            started_at_utc=started_at,
            status="partial",
            requested_policies=requested_policies,
            completed_policies=completed_policies,
            n_replications=n_replications,
            route_check=route_check,
        ),
    )

    results = {}
    last_kpis = {}
    last_warehouses = {}
    rep_details: dict[str, list[dict]] = {}

    for name, policy_cls in selected_policies:
        summary, kpi, wh, reps = run_policy(name, policy_cls, data, n_reps=n_replications)
        results[name] = summary
        last_kpis[name] = kpi
        last_warehouses[name] = wh
        rep_details[name] = reps
        completed_policies.append(name)
        _write_policy_outputs(name, kpi)
        _write_json("output/replications.json", rep_details)
        _write_json("output/policy_summary.json", results)
        _write_kpi_by_replication(rep_details)
        _write_json(
            "output/run_manifest.json",
            _build_run_manifest(
                run_id=run_id,
                started_at_utc=started_at,
                status="partial" if len(completed_policies) < len(requested_policies) else "complete",
                requested_policies=requested_policies,
                completed_policies=completed_policies,
                n_replications=n_replications,
                route_check=route_check,
            ),
        )

    if not args.skip_charts:
        print("\nGenerating charts...")
        compare_policies(results)
        plot_prep_time_distribution(last_kpis)

    _mirror_web_outputs()

    print("\nDone! Results in output/")


if __name__ == "__main__":
    main()
