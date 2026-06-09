import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data_loader import decode_storage_bin, preprocess
from src.recorder import TimelineRecorder
from src.warehouse import Warehouse


def test_decode_storage_bin_canary():
    assert decode_storage_bin("BRA-02-02") == ("A", 2, 2)
    assert decode_storage_bin("A-02-02") == ("A", 2, 2)
    assert decode_storage_bin("KDX") is None


def test_preprocess_keeps_only_layout_valid_decoded_bins():
    data = preprocess(write_stats=False)
    wh = Warehouse()
    stats = data["stats"]

    assert wh.sap_position_ids("A", 2, 2)
    assert wh.sap_position_ids("A", 2, 2)[0].endswith("-L0")
    assert "bins_invalid_position" in stats
    assert "bin_validation_errors" in stats
    assert stats["decoded_bin_slots_total"] == sum(
        len(v) for v in data["decoded_bins"].values()
    )

    for bin_list in data["decoded_bins"].values():
        for rack, bay, position in bin_list:
            assert wh.sap_position_id(rack, bay, position) is not None


def test_timeline_recorder_writes_interval_fields(tmp_path):
    rec = TimelineRecorder("Baseline (Actual SAP)", output_dir=str(tmp_path))
    rec.op_move(
        2.5,
        order_id=1,
        op_id=1,
        from_xy=(0.0, 0.0),
        to_xy=(1.0, 2.0),
        dist_m=3.0,
        start_t=1.5,
    )
    rec.rt_dispatch(
        4.0,
        order_id=1,
        rt_id=1,
        pos_id="A-02-02-L0",
        queue_wait_min=0.25,
        path=[(0.0, 0.0), (1.0, 1.0)],
        travel_time_min=0.5,
        service_time_min=1.25,
    )
    rec.close()

    lines = [
        json.loads(line)
        for line in (tmp_path / "sim_timeline_baseline_actual_sap.jsonl").read_text().splitlines()
    ]
    assert lines[0]["schema_version"] == "1.1"
    assert lines[0]["coord_system"] == "layout_m"
    assert lines[1]["t_start"] == 1.5
    assert lines[1]["t_end"] == 2.5
    assert lines[2]["t_arrive"] == 4.5
    assert lines[2]["t_end"] == 5.75
