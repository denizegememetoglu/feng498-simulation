"""Tests for the 2026-06-09 fix pass: batch arrivals, RNG stream split,
throughput KPI, tidy Minitab export, RT return leg, chi-square pooling."""

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np

from src import config
from src.kpi import KPICollector
from src.main import _TIDY_KPI_COLUMNS, _write_kpi_by_replication
from src.zwm92 import fit_distributions


def test_batch_fit_fields_and_calibration():
    fit = fit_distributions()
    assert fit["batch_size_empirical"], "batch sizes missing"
    assert fit["iat_samples"], "empirical IAT pool missing"
    assert fit["iat_cv"] > 1.0  # heavy-tailed gaps — why Exp was dropped
    # Calibration: empirical gaps + empirical batch sizes must reproduce
    # the real daily volume within ±10%.
    expected_per_day = (config.SHIFT_DURATION_MIN / fit["iat_mean_min"]
                        * fit["batch_size_mean"])
    target = fit["orders_per_active_day"]
    assert abs(expected_per_day - target) / target <= 0.10


def test_driver_batches_and_arrival_rng_isolation():
    from src.data_loader import preprocess
    from src.simulation import ZWM92DistributionDriver

    data = preprocess(write_stats=False)
    rng_a = np.random.default_rng(7)
    drv_a = ZWM92DistributionDriver(data["materials"], data["material_to_line"], rng_a)
    assert drv_a.is_distribution_driven

    iat, orders = drv_a.next_batch()
    assert iat >= 0
    assert len(orders) >= 1
    # Single-line batch invariant (99.9% of observed batches are one line).
    assert len({o["line"] for o in orders}) == 1

    # Same seed → identical arrival stream regardless of how many service
    # draws happen elsewhere (the CRN property the RNG split guarantees).
    rng_b = np.random.default_rng(7)
    drv_b = ZWM92DistributionDriver(data["materials"], data["material_to_line"], rng_b)
    iat_b, orders_b = drv_b.next_batch()
    assert iat == iat_b
    assert [o["items"] for o in orders] == [o["items"] for o in orders_b]


def test_kpi_summary_new_fields_and_throughput_math():
    kpi = KPICollector()
    kpi.orders_started = 12
    for i in range(10):
        kpi.record_order(
            order_id=i, arrival_time=40.0 + i, op_queue_wait=1.0,
            rt_queue_wait=0.5, prep_time=4.0, lead_time=5.0,
            walk_distance=80.0, num_items=4, line="F400", timestamp=50.0 + i,
        )
    kpi.add_rt_busy(10.0)
    kpi.add_op_busy(40.0)
    kpi.add_kardex_busy(5.0)
    kpi.set_sim_duration(480.0, warmup=30.0, cooldown=30.0)
    s = kpi.summary(num_reach_trucks=7, num_operators=8)

    assert s["orders_started"] == 12
    assert s["avg_total_wait"] == 1.5  # op 1.0 + rt 0.5
    assert s["avg_rt_queue_wait"] == 0.5
    # Active window = 480 - 60 = 420 min = 7 h → 10 orders / 7 h
    assert math.isclose(s["throughput_orders_per_hr"], 10 / 7.0)
    assert math.isclose(s["throughput_orders_per_day"], 10 / 7.0 * 8.0)
    assert s["kardex_utilization"] == 5.0 / (4 * 480.0)
    # summary() must be idempotent (recorder calls it repeatedly)
    s2 = kpi.summary(num_reach_trucks=7, num_operators=8)
    assert s2["util_overflow"] == s["util_overflow"] == []


def test_tidy_kpi_csv_shape(tmp_path):
    reps = {
        "Policy, With Comma": [
            {"replication": 0, "seed": 42, "avg_lead_time": 5.0,
             "avg_total_wait": 1.0, "reach_truck_utilization": 0.25,
             "throughput_orders_per_day": 400.0},
            {"replication": 1, "seed": 43, "avg_lead_time": 6.0,
             "avg_total_wait": 2.0, "reach_truck_utilization": 0.30,
             "throughput_orders_per_day": 410.0},
        ],
    }
    path = tmp_path / "kpi_by_replication.csv"
    _write_kpi_by_replication(reps, path=str(path))
    lines = path.read_text().splitlines()
    header = lines[0].split(",")
    assert header[:3] == ["policy", "replication", "seed"]
    assert set(_TIDY_KPI_COLUMNS) <= set(header)
    assert len(lines) == 3  # header + 2 reps
    for row in lines[1:]:
        assert len(row.split(",")) == len(header)  # comma in name escaped


def test_chi_square_pooling_satisfies_cochran():
    from src.validate import _chi_square_per_rack
    sim = {"A": 500, "B": 300, "C": 150, "D": 3, "E": 2, "F": 1}
    expected = {"A": 0.5, "B": 0.3, "C": 0.15, "D": 0.03, "E": 0.015, "F": 0.005}
    res = _chi_square_per_rack(sim, expected)
    assert res["cochran_warning"] is not None
    pooled = res["pooled"]
    assert pooled is not None
    assert pooled["cochran_satisfied"]
    assert sum(pooled["observed"]) == sum(res["observed"])
    assert math.isclose(sum(pooled["expected"]), sum(res["expected"]), rel_tol=1e-6)
    assert pooled["dof"] == len(pooled["racks"]) - 1


def test_rt_dispatch_records_return_leg(tmp_path):
    from src.recorder import TimelineRecorder
    rec = TimelineRecorder("Baseline (Actual SAP)", output_dir=str(tmp_path))
    rec.rt_dispatch(
        4.0, order_id=1, rt_id=1, pos_id="A-02-02-L0", queue_wait_min=0.0,
        path=[(0.0, 0.0), (1.0, 1.0)], travel_time_min=0.5,
        service_time_min=1.0, return_time_min=0.5,
    )
    rec.close()
    lines = [json.loads(l) for l in
             (tmp_path / "sim_timeline_baseline_actual_sap.jsonl").read_text().splitlines()]
    ev = lines[1]
    assert ev["return_time_min"] == 0.5
    assert ev["t_home"] == ev["t_end"] + 0.5
