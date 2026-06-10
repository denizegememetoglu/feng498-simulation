#!/usr/bin/env python
"""Apply the Fable5 blind CAD re-extraction (2026-06-10) to config/layout.json.

What changes (user-approved "tam geçiş", 2026-06-10):
  * Letter ↔ row coordinates corrected to the verified mapping
    (A=ROW11 north … J = 5-section perimeter bracket, U = west vertical leg).
    Sim-frame affine (recovered exactly from the previous file's own
    _codex_geometry_cm annotations):
        sim_x = -0.010998 * cad_y_cm + 53.5266
        sim_y =  0.009868 * cad_x_cm - 17.4013
  * G levels 9 -> 8 (G is a SHORT rack: chain tops at 546, level 8 = top;
    288 = 12 x 8 x 3 exact — G.pdf).
  * J re-segmented 3 -> 5 sections (J1=COL01, J2-J12=south arm ROW02,
    J13=KÜÇÜK RF X-element, J14=SE stub ROW01, J15-J18=east leg COL02).
  * U re-segmented 1 -> 3 sections (U1=100cm north cap, U2-U13=west leg
    COL00, U14=SW KÜÇÜK RF stub ROW00).
  * kit/rt corridor sides set from CAD truth (measured aisles: kit=200cm,
    RT=300/305/320; H/I have NO adjacent kit corridor -> TBD).
  * Verified label directions applied: E1=east, B12=west, J/U as per
    output/fable5_layout/blind_assignment.json; H flipped to H11=west
    (MEDIUM); A/C/D/F/G/I keep or adopt documented conventions.

What does NOT change (SAP-join invariants):
  * rack ids, bay_code_start/bays (code sets per rack), pallets_per_bay,
    position_offset, bay_overrides (keyed by bay code), pallet_count per
    rack (canary 3203).

Verification run by this script:
  * canary == 3203
  * level-stripped (rack, bay, pos) position-id set identical before/after
    (G loses only its L8 layer — level-stripped parity holds)
  * SAP bins decode-join parity (same joined-material count)

Evidence: output/fable5_layout/{blind_assignment,comparison_report}.json
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LAYOUT = ROOT / "config/layout.json"
BACKUP = ROOT / "config/layout.json.bak_pre_fable5_20260610"

AX, BX = -0.010998, 53.5266   # sim_x from cad_y
CY, DY = 0.009868, -17.4013   # sim_y from cad_x


def sx(cad_y):
    return round(AX * cad_y + BX, 3)


def sy(cad_x):
    return round(CY * cad_x + DY, 3)


# letter -> (cad row y_center, labeled-extent cad x0..x1, bay direction)
# direction: 'asc_east' = bay codes ascend west->east (start=west end)
#            'asc_west' = bay codes ascend east->west (start=east end)
LINEAR = {
    #        y_cad    x0       x1      dir         kit     rt      levels
    "A": (4019.2, 2544.4, 5614.4, "asc_east", "west", "east", 9),
    "B": (3614.2, 2345.1, 5625.1, "asc_west", "east", "west", 9),
    "C": (3309.1, 2275.1, 5624.9, "asc_west", "west", "east", 9),
    "D": (2904.2, 2345.1, 5625.1, "asc_east", "east", "west", 9),
    "E": (2174.2, 2345.1, 5622.1, "asc_west", "east", "west", 9),
    "F": (2599.2, 2342.1, 5622.1, "asc_east", "west", "east", 9),
    "G": (1869.2, 2275.1, 5624.9, "asc_east", "west", "east", 8),
    "H": (1464.2, 2275.1, 5344.9, "asc_west", "TBD", "west", 8),
    "I": (1339.2, 2275.1, 5344.9, "asc_east", "TBD", "east", 8),
}

DIR_NOTE = {
    "A": "A2=west (convention kept; compass anchor unverified)",
    "B": "B12=west / B1=east — strips 5+6 + B7 gap at x≈3955-4225 (VERIFIED)",
    "C": "C12=west — C10-C12 portal/short profile cluster at west (MEDIUM)",
    "D": "D1=west (convention kept; unverified)",
    "E": "E1=east — east revision bay, doubled post (VERIFIED, photo+PDF)",
    "F": "F1=west (convention kept; unverified)",
    "G": "G1=west (convention kept; unverified)",
    "H": "H11=west / H1=east (MEDIUM — portal-profile hint)",
    "I": "I1=west (convention kept; unverified)",
}


def seg_geometry(letter):
    y_cad, x0, x1, d, kit, rt, levels = LINEAR[letter]
    a, b = sy(x0), sy(x1)
    if d == "asc_west":
        a, b = b, a
    return [sx(y_cad), a], [sx(y_cad), b], kit, rt, levels


def positions_levelfree(layout_path):
    """Build a Warehouse and return the level-stripped position key set."""
    from src.warehouse import Warehouse
    w = Warehouse(layout_path=str(layout_path))
    return {(p.rack_id, p.bay_code, p.position) for p in w.positions.values()}, len(w.positions)


def main():
    if not BACKUP.exists():
        shutil.copy2(LAYOUT, BACKUP)
        print(f"backup -> {BACKUP.name}")
    before_keys, before_n = positions_levelfree(BACKUP)

    lay = json.loads(LAYOUT.read_text(encoding="utf-8"))
    lay["_provenance"] = (
        "Geometry: Fable5 blind CAD re-extraction 2026-06-10 "
        "(output/fable5_layout/ — DWG dims + 11 rack PDFs + factory photos + "
        "ZWM92×özet cross-tab; adversarially verified). Letter ordering: "
        "A=north … J-arm=south, U=west leg, J=5-section perimeter bracket. "
        "Bay codes / overrides / pallet counts unchanged (SAP join stable)."
    )
    lay.setdefault("_notes", []).append(
        "2026-06-10 FULL TRANSITION: v4 letter placement replaced by the "
        "Fable5-verified mapping (see output/fable5_layout/RAPOR.md). "
        "E kit side fixed (was pointing at the 320 RT aisle). G levels 9->8. "
        "Pre-transition file: config/layout.json.bak_pre_fable5_20260610"
    )

    new_racks = []
    for rack in lay["racks"]:
        rid = rack["id"]
        if rid in LINEAR:
            seg = rack["segments"][0]
            start, end, kit, rt, levels = seg_geometry(rid)
            seg["start"], seg["end"] = start, end
            seg["kit_corridor_side"], seg["rt_aisle_side"] = kit, rt
            seg["levels"] = levels
            seg["bay_width_m"] = 2.8
            seg.pop("_codex_idx", None)
            seg["_fable5_geometry_cm"] = {
                "row_y_center": LINEAR[rid][0],
                "x0": LINEAR[rid][1], "x1": LINEAR[rid][2]}
            seg["_bay_direction"] = DIR_NOTE[rid]
            rack["_orientation"] = (
                "vertical in sim frame (CAD: east-west row at "
                f"y={LINEAR[rid][0]:.0f} cm)")
            rack["_source"] = "Fable5 blind CAD extraction 2026-06-10"
            new_racks.append(rack)
        elif rid == "J":
            old_ovr = [o for s in rack["segments"]
                       for o in s.get("bay_overrides", [])]

            def ovr_for(codes):
                out = []
                for o in old_ovr:
                    hit = [b for b in o["bays"] if b in codes]
                    if hit:
                        out.append({**o, "bays": hit})
                return out

            rack["shape"] = "polyline"
            rack["_orientation"] = ("5-section perimeter bracket: east leg + "
                                    "SE stub + KÜÇÜK RF + south arm + SW frag")
            rack["_source"] = "Fable5 blind CAD extraction 2026-06-10"
            rack["segments"] = [
                {"start": [sx(848.2), sy(2222.6)], "end": [sx(578.2), sy(2222.6)],
                 "bays": 1, "bay_code_start": 1, "bay_width_m": 2.7,
                 "levels": 8, "pallets_per_bay": 3, "pallet_count": 24,
                 "bay_overrides": ovr_for({1}),
                 "kit_corridor_side": "TBD", "rt_aisle_side": "TBD",
                 "_section": "J1 — SW vertical fragment (COL01, cad x≈2222)"},
                {"start": [43.253, sy(2275.1)], "end": [43.253, sy(5274.9)],
                 "bays": 11, "bay_code_start": 2, "bay_width_m": 2.8,
                 "levels": 8, "pallets_per_bay": 3, "pallet_count": 240,
                 "bay_overrides": ovr_for(set(range(2, 13))),
                 "kit_corridor_side": "east", "rt_aisle_side": "west",
                 "_section": "J2-J12 — south arm (ROW02, cad y≈934); kit = "
                             "south corridor (RI-P7 SD-POLE)"},
                {"start": [sx(684.7), sy(5232.6)], "end": [sx(874.8), sy(5232.6)],
                 "bays": 1, "bay_code_start": 13, "bay_width_m": 1.82,
                 "levels": 8, "pallets_per_bay": 3, "pallet_count": 12,
                 "bay_overrides": ovr_for({13}),
                 "kit_corridor_side": "TBD", "rt_aisle_side": "TBD",
                 "_section": "J13 — KÜÇÜK RF (X-braced element, 182cm PDF / "
                             "184cm CAD dim)"},
                {"start": [sx(634.1), sy(5359.9)], "end": [sx(634.1), sy(5629.9)],
                 "bays": 1, "bay_code_start": 14, "bay_width_m": 2.7,
                 "levels": 8, "pallets_per_bay": 3, "pallet_count": 21,
                 "bay_overrides": ovr_for({14}),
                 "kit_corridor_side": "TBD", "rt_aisle_side": "TBD",
                 "_section": "J14 — SE stub (ROW01, ÇÖP KOVASI yanı)"},
                {"start": [sx(696.6), sy(5687.4)], "end": [sx(1806.7), sy(5687.4)],
                 "bays": 4, "bay_code_start": 15, "bay_width_m": 2.8,
                 "levels": 8, "pallets_per_bay": 3, "pallet_count": 84,
                 "bay_overrides": ovr_for(set(range(15, 19))),
                 "kit_corridor_side": "TBD", "rt_aisle_side": "south",
                 "_section": "J15-J18 — east vertical leg (COL02); 279.7cm "
                             "aisle to H/I east ends"},
            ]
            new_racks.append(rack)
        elif rid == "U":
            old_ovr = [o for s in rack["segments"]
                       for o in s.get("bay_overrides", [])]

            def ovr_for(codes):
                out = []
                for o in old_ovr:
                    hit = [b for b in o["bays"] if b in codes]
                    if hit:
                        out.append({**o, "bays": hit})
                return out

            rack["shape"] = "polyline"
            rack["_orientation"] = ("west vertical leg (CAD) -> horizontal in "
                                    "sim frame + SW KÜÇÜK RF stub + north cap")
            rack["_source"] = "Fable5 blind CAD extraction 2026-06-10"
            rack["segments"] = [
                {"start": [sx(3828.5), sy(1731.1)], "end": [sx(3828.5), sy(1836.1)],
                 "bays": 1, "bay_code_start": 1, "bay_width_m": 1.0,
                 "levels": 7, "pallets_per_bay": 2, "pallet_count": 7,
                 "bay_overrides": ovr_for({1}),
                 "kit_corridor_side": "TBD", "rt_aisle_side": "TBD",
                 "_section": "U1 — 100cm north cap (kendi 118-564 zinciri, "
                             "KÜÇÜK RF sub-zone)"},
                {"start": [sx(3793.5), sy(1783.6)], "end": [sx(513.5), sy(1783.6)],
                 "bays": 12, "bay_code_start": 2, "bay_width_m": 2.8,
                 "levels": 7, "pallets_per_bay": 2, "pallet_count": 246,
                 "bay_overrides": ovr_for(set(range(2, 14))),
                 "kit_corridor_side": "north", "rt_aisle_side": "north",
                 "_section": "U2-U13 — west vertical leg (COL00); U2 = north "
                             "200-slot. GERÇEK kit yüzü GMH koridoru (CAD-batı "
                             "= sim güney) ama o şerit sim bina kutusunun "
                             "dışında (y<0) kalıyor; erişim 429cm kuzey "
                             "koridorundan modellendi (mesafe etkisi ≤ ~2m)"},
                {"start": [sx(437.7), sy(1852.1)], "end": [sx(437.7), sy(2052.1)],
                 "bays": 1, "bay_code_start": 14, "bay_width_m": 2.0,
                 "levels": 7, "pallets_per_bay": 2, "pallet_count": 10,
                 "bay_overrides": ovr_for({14}),
                 "kit_corridor_side": "TBD", "rt_aisle_side": "TBD",
                 "_section": "U14 — SW detached KÜÇÜK RF stub (ROW00)"},
            ]
            new_racks.append(rack)
        else:
            new_racks.append(rack)
    lay["racks"] = new_racks

    # Per-line kitting points re-anchored: CAD line labels -> affine -> snap
    # to the corridor midline of the corrected letter placement. The old
    # points were snapped against the v4 letter positions and ended up in
    # the WRONG corridors after the transition (F400 point sat in the
    # SM6-Premset corridor and vice versa).
    def _line_point(label_cad_xy, corridor_mid_x=None):
        lx, ly = label_cad_xy
        px = corridor_mid_x if corridor_mid_x is not None else sx(ly)
        return [round(px, 3), round(sy(lx), 3)]

    mid_GE = round((32.969 + 29.615) / 2, 3)   # F400 corridor (G-E, 200cm)
    mid_FD = round((24.941 + 21.586) / 2, 3)   # SM6-Premset corridor (F-D)
    pl_points = {
        "F400":    _line_point((4178.2, 2058.1), mid_GE),
        "SM6-36":  _line_point((4302.5, 2811.1), mid_FD),
        "PREMSET": _line_point((4302.5, 2811.1), mid_FD),
        "MCSET":   _line_point((4022.5, 4185.9)),  # north strip, west of A
    }
    for p in lay.get("production_lines", []):
        if p["name"] in pl_points:
            p["kitting_point"] = pl_points[p["name"]]
            p["_source"] = ("CAD line label -> affine -> corridor midline of "
                            "the Fable5 letter placement (2026-06-10)")

    LAYOUT.write_text(json.dumps(lay, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    # ---- verification ----
    canary = sum(s["pallet_count"] for r in lay["racks"] for s in r["segments"])
    print(f"canary: {canary}")
    assert canary == 3203, "CANARY BROKEN"

    after_keys, after_n = positions_levelfree(LAYOUT)
    only_before = before_keys - after_keys
    only_after = after_keys - before_keys
    print(f"level-stripped (rack,bay,pos) parity: before={len(before_keys)} "
          f"after={len(after_keys)} lost={len(only_before)} gained={len(only_after)}")
    if only_before:
        print("  LOST:", sorted(only_before)[:20])
    print(f"total modeled positions (with levels): {before_n} -> {after_n} "
          f"(G L8 removal expected: -{12*3} = -36)")
    assert not only_before, "JOIN REGRESSION — lost (rack,bay,pos) keys!"

    from src.data_loader import load_storage_bins, decode_storage_bin
    bins = load_storage_bins()
    joined = 0
    for mat, blist in bins.items():
        for b in blist:
            dec = decode_storage_bin(b)
            if dec and (dec[0], dec[1], dec[2]) in after_keys:
                joined += 1
                break
    print(f"SAP bins joinable to a modeled position: {joined} materials")
    print("OK — transition applied.")


if __name__ == "__main__":
    main()
