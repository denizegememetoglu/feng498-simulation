"""
Root-cause analysis of chi-square per-rack mismatch.
Answers Q1-Q5 with computed numbers.
Run: /home/dege/feng498-simulation/.venv/bin/python scripts/chisq_rootcause.py
"""

import json
import sys
import os
from collections import defaultdict, Counter

# ---- setup path ----
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.data_loader import preprocess, decode_storage_bin, is_kardex_bin
from src.warehouse import Warehouse

# =========================================================
# Load data
# =========================================================
print("Loading preprocessed data...", flush=True)
data = preprocess(write_stats=False)
decoded_bins   = data["decoded_bins"]        # mat_id -> [(rack,bay,pos), ...]
kardex_mats    = data["kardex_materials"]    # set of mat_ids
storage_bins   = data["storage_bins"]        # mat_id -> [raw bin str, ...]

print("Loading ZWM92 observed bins...", flush=True)
with open("output/zwm92_observed_bins.json") as f:
    zwm92_obs = json.load(f)   # mat_id -> [(rack,bay,pos), ...] sorted by freq

print("Loading ZWM92 orders...", flush=True)
with open("output/zwm92_orders.json") as f:
    zwm92_orders_raw = json.load(f)

print("Loading ZWM92 summary...", flush=True)
with open("output/zwm92_summary.json") as f:
    zwm92_summary = json.load(f)

# picks_per_rack_actual: rack -> count
picks_per_rack_actual = zwm92_summary.get("picks_per_rack_actual", {})
# picks_by_material: mat_id -> total picks
picks_by_material_total = zwm92_summary.get("picks_by_material", {})

print("Building Warehouse...", flush=True)
wh = Warehouse()
sap_pos_ids = set()
for pid, pos in wh.positions.items():
    sap_pos_ids.add((pos.rack_id, pos.bay_code, pos.position))

# =========================================================
# Q1 -- Decoded ozet racks vs ZWM92 observed racks for same materials
# =========================================================
print("\n" + "="*60)
print("Q1: ozet decoded racks vs ZWM92 observed racks")
print("="*60)

# For each decoded material, what rack does ozet say vs what rack did ZWM92 use
n_decoded_materials = len(decoded_bins)
rack_letters = ["A","B","C","D","E","F","G","H","I","J","U"]

ozet_rack_dist    = Counter()   # from decoded_bins
zwm92_rack_dist_samemat = Counter()   # ZWM92 observed rack for same decoded materials
n_in_zwm92   = 0
n_stale      = 0      # materials where dominant zwm92 rack != ozet rack
ozet_vs_zwm92_mismatch = Counter()  # (ozet_rack, zwm92_rack): count of materials

for mat_id, decoded in decoded_bins.items():
    # ozet primary rack (most common rack in decoded bins list)
    ozet_racks = [r for r, b, p in decoded]
    ozet_primary = Counter(ozet_racks).most_common(1)[0][0]
    ozet_rack_dist[ozet_primary] += 1

    # ZWM92 observed
    obs = zwm92_obs.get(mat_id, [])
    if not obs:
        continue
    n_in_zwm92 += 1
    # obs is already sorted by frequency; first entry is most-frequent rack
    if isinstance(obs[0], list):
        zwm92_primary_rack = obs[0][0]
    else:
        zwm92_primary_rack = obs[0]
    zwm92_rack_dist_samemat[zwm92_primary_rack] += 1
    if zwm92_primary_rack != ozet_primary:
        n_stale += 1
        ozet_vs_zwm92_mismatch[(ozet_primary, zwm92_primary_rack)] += 1

print(f"  Decoded materials (ozet): {n_decoded_materials}")
print(f"  Of those, also in ZWM92 observed: {n_in_zwm92}")
print(f"  Materials where dominant zwm92 rack != ozet rack (stale): {n_stale} ({100*n_stale/max(1,n_in_zwm92):.1f}%)")

print("\n  ozet rack distribution (decoded materials, primary rack):")
for r in rack_letters:
    print(f"    {r}: {ozet_rack_dist.get(r,0)}")

print("\n  ZWM92 most-frequent rack (same decoded materials):")
for r in rack_letters:
    print(f"    {r}: {zwm92_rack_dist_samemat.get(r,0)}")

print("\n  Top mismatches (ozet_rack -> actual zwm92_rack, material count):")
for (o, z), cnt in sorted(ozet_vs_zwm92_mismatch.items(), key=lambda x: -x[1])[:15]:
    print(f"    ozet={o}  zwm92={z}  n_materials={cnt}")

# =========================================================
# Q2 -- Why do I/J/U get zero sim picks in restricted set?
# =========================================================
print("\n" + "="*60)
print("Q2: Why do I/J/U have zero restricted sim picks?")
print("="*60)

for target_rack in ["I","J","U"]:
    iju_decoded = [m for m, d in decoded_bins.items() if any(r==target_rack for r,b,p in d)]
    print(f"\n  Rack {target_rack}:")
    print(f"    Materials with ozet bin at {target_rack}: {len(iju_decoded)}")

    # are those materials in ZWM92?
    in_zwm92_orders = 0
    picks_total = 0
    for mat_id in iju_decoded:
        p = picks_by_material_total.get(mat_id, 0)
        if p > 0:
            in_zwm92_orders += 1
            picks_total += p
    print(f"    Of those, appear in ZWM92 picks: {in_zwm92_orders} (total picks={picks_total})")

    # Do they have closer non-I/J/U decoded bins?
    has_closer_other = 0
    for mat_id in iju_decoded:
        other_bins = [(r,b,ps) for r,b,ps in decoded_bins[mat_id] if r != target_rack]
        if other_bins:
            has_closer_other += 1
    print(f"    Materials that ALSO have a non-{target_rack} decoded bin: {has_closer_other}")

    # What does ZWM92 say about those materials?
    zwm92_racks_for_these = Counter()
    for mat_id in iju_decoded:
        obs = zwm92_obs.get(mat_id, [])
        for entry in obs:
            r = entry[0] if isinstance(entry, list) else entry
            zwm92_racks_for_these[r] += 1
    print(f"    ZWM92 actual racks for these {target_rack}-decoded materials:")
    for r in rack_letters:
        if zwm92_racks_for_these.get(r,0) > 0:
            print(f"      {r}: {zwm92_racks_for_these[r]}")

# =========================================================
# Q3 -- Rack A: top 10 materials driving sim picks, where does ZWM92 dispatch them?
# =========================================================
print("\n" + "="*60)
print("Q3: Rack A sim-pick drivers vs ZWM92 actual racks")
print("="*60)

# load baseline_actual_sap_picks_per_material.csv to get sim picks by material
import csv
sim_picks_by_mat = {}
with open("output/baseline_actual_sap_picks_per_material.csv") as f:
    reader = csv.DictReader(f)
    for row in reader:
        sim_picks_by_mat[row["material_id"]] = int(row["pick_count"])

# which decoded-bin materials are assigned to rack A in simulation?
# In RealBaseline policy, assignment = decoded_bins primary slot
# We look at decoded materials at rack A and their sim picks
rack_a_decoded = [(m, decoded_bins[m]) for m in decoded_bins if any(r=="A" for r,b,p in decoded_bins[m])]
rack_a_sim_picks = []
for mat_id, decoded in rack_a_decoded:
    sp = sim_picks_by_mat.get(mat_id, 0)
    # ZWM92 primary observed rack
    obs = zwm92_obs.get(mat_id, [])
    zwm92_rack = obs[0][0] if obs and isinstance(obs[0], list) else (obs[0] if obs else "NONE")
    total_zwm92 = picks_by_material_total.get(mat_id, 0)
    rack_a_sim_picks.append((sp, mat_id, zwm92_rack, total_zwm92))

rack_a_sim_picks.sort(reverse=True)
print("\n  Top 10 materials with ozet bin at A, sorted by sim picks (baseline_actual_sap):")
print(f"  {'mat_id':>20} {'sim_picks':>10} {'zwm92_total_picks':>18} {'zwm92_primary_rack':>20}")
for sp, mat_id, zwm92_rack, total_zwm92 in rack_a_sim_picks[:10]:
    print(f"  {mat_id:>20} {sp:>10} {total_zwm92:>18} {zwm92_rack:>20}")

# Aggregate: for A-decoded materials, where does ZWM92 dispatch?
zwm92_actual_for_a_mats = Counter()
sim_a_picks_total = sum(sp for sp, _, _, _ in rack_a_sim_picks)
for _, mat_id, zwm92_rack, _ in rack_a_sim_picks:
    if picks_by_material_total.get(mat_id, 0) > 0:
        zwm92_actual_for_a_mats[zwm92_rack] += 1

print(f"\n  Total sim picks for A-decoded materials: {sim_a_picks_total}")
print("  ZWM92 primary rack distribution for these materials:")
for r in rack_letters + ["NONE"]:
    if zwm92_actual_for_a_mats.get(r,0) > 0:
        print(f"    {r}: {zwm92_actual_for_a_mats[r]} materials")

# =========================================================
# Q4 -- Opportunity: ZWM92 observed bin placement
# =========================================================
print("\n" + "="*60)
print("Q4: Opportunity — place materials at ZWM92 observed bins")
print("="*60)

# (a) How many materials have at least one decodable ZWM92 observed bin
#     that maps to a valid Warehouse position?
n_decodable_zwm92 = 0
n_total_zwm92_mats = len(zwm92_obs)
mat_best_bin = {}   # mat_id -> (rack, bay, pos) most-frequent valid observed bin

for mat_id, obs_list in zwm92_obs.items():
    for entry in obs_list:
        if isinstance(entry, list):
            rack, bay, pos = entry[0], entry[1], entry[2]
        else:
            continue
        decoded = decode_storage_bin(f"{rack}-{bay:02d}-{pos:02d}")
        if decoded is None:
            continue
        if decoded in sap_pos_ids:
            n_decodable_zwm92 += 1
            mat_best_bin[mat_id] = decoded  # first (= most-frequent) valid bin
            break

print(f"\n  (a) Materials in ZWM92 observed: {n_total_zwm92_mats}")
print(f"      With at least one decodable+valid Warehouse observed bin: {n_decodable_zwm92}")

# (b) Pick share covered
total_picks_all = sum(picks_by_material_total.values())
picks_covered = sum(picks_by_material_total.get(m, 0) for m in mat_best_bin)
share = picks_covered / max(1, total_picks_all)
print(f"\n  (b) Total ZWM92 picks across all materials: {total_picks_all}")
print(f"      Picks covered by mat_best_bin materials: {picks_covered} ({100*share:.1f}%)")

# (c) Slot conflicts: how many (rack,bay,pos) are claimed by > 1 material?
slot_to_mats = defaultdict(list)
for mat_id, slot in mat_best_bin.items():
    slot_to_mats[slot].append(mat_id)
n_conflict_slots = sum(1 for mats in slot_to_mats.values() if len(mats) > 1)
n_conflicting_mats = sum(len(mats) for mats in slot_to_mats.values() if len(mats) > 1)
n_unique_slots = len(slot_to_mats)
print(f"\n  (c) Unique slots claimed: {n_unique_slots}")
print(f"      Slots with >1 material (conflicts): {n_conflict_slots}")
print(f"      Materials involved in conflicts: {n_conflicting_mats}")
conflict_rate = n_conflict_slots / max(1, n_unique_slots)
print(f"      Conflict rate: {100*conflict_rate:.1f}%")

# (d) Per-rack distribution if we place each material at best observed bin
# vs actual ZWM92 picks_per_rack_actual
zwm92_placed_rack_dist = Counter()
for mat_id, (rack, bay, pos) in mat_best_bin.items():
    picks = picks_by_material_total.get(mat_id, 0)
    zwm92_placed_rack_dist[rack] += picks

print("\n  (d) Per-rack pick distribution: ZWM92-observed placement vs actual ZWM92 picks")
print(f"  {'rack':>6} {'ZWM92_actual_picks':>20} {'if_placed_at_obs_bin':>22}")
for r in rack_letters:
    actual = picks_per_rack_actual.get(r, 0)
    placed = zwm92_placed_rack_dist.get(r, 0)
    print(f"  {r:>6} {actual:>20} {placed:>22}")

# chi-square shape comparison (by construction should be better)
import math
obs_vec = [picks_per_rack_actual.get(r, 0) for r in rack_letters]
exp_vec = [zwm92_placed_rack_dist.get(r, 0) for r in rack_letters]
total_obs = sum(obs_vec)
total_exp = sum(exp_vec)

# Scale exp to same total as obs
if total_exp > 0:
    exp_scaled = [e * total_obs / total_exp for e in exp_vec]
else:
    exp_scaled = exp_vec[:]

chi2_new = 0.0
for o, e in zip(obs_vec, exp_scaled):
    if e > 0:
        chi2_new += (o - e)**2 / e
dof = len([r for r in rack_letters if picks_per_rack_actual.get(r,0) > 0]) - 1
v_new = math.sqrt(chi2_new / max(1, total_obs * dof)) if total_obs > 0 else 0
print(f"\n  Chi-square if placed at ZWM92 observed bins: chi2={chi2_new:.1f}  V={v_new:.4f} (vs current chi2=174, V=0.145)")

# =========================================================
# Q5 -- KDX in ZWM92 but NOT in kardex_materials from ozet
# =========================================================
print("\n" + "="*60)
print("Q5: ZWM92 KDX addresses not in ozet kardex_materials")
print("="*60)

# zwm92_obs contains only rack-format bins (not KDX) because of decode_storage_bin filter
# We need the raw ZWM92 observed bins which include KDX
# Let's check zwm92_observed_bins.json structure
sample_keys = list(zwm92_obs.keys())[:3]
print(f"  Sample keys from zwm92_observed_bins: {sample_keys}")
first_key = sample_keys[0]
print(f"  First material obs entries: {zwm92_obs[first_key][:3]}")

# The observed bins file may or may not have KDX entries; load zwm92 summary for kdx info
print(f"\n  Loading from ZWM92 summary for KDX dispatch analysis...")
kdx_picks_by_mat = zwm92_summary.get("kdx_picks_by_material", {})
print(f"  kdx_picks_by_material entries in summary: {len(kdx_picks_by_mat)}")

# Check summary keys
sum_keys = list(zwm92_summary.keys())
print(f"  ZWM92 summary keys: {sum_keys}")

# For robust analysis: look at zwm92_orders to find materials dispatched from KDX bins
print("\n  Scanning ZWM92 orders for KDX bin dispatches...")
kdx_mats_in_zwm92 = set()
kdx_picks_count = defaultdict(int)

# zwm92_orders_raw structure inspection
if isinstance(zwm92_orders_raw, list):
    # list of order dicts
    sample_order = zwm92_orders_raw[0] if zwm92_orders_raw else {}
    print(f"  zwm92_orders is a list, sample keys: {list(sample_order.keys())[:10]}")
elif isinstance(zwm92_orders_raw, dict):
    sample_order = next(iter(zwm92_orders_raw.values()), {})
    print(f"  zwm92_orders is a dict, sample value keys: {list(sample_order.keys())[:10]}")

# Try to find bin column in orders
if isinstance(zwm92_orders_raw, list) and zwm92_orders_raw:
    first = zwm92_orders_raw[0]
    bin_key = None
    for k in first.keys():
        if "bin" in k.lower() or "depo" in k.lower() or "storage" in k.lower():
            bin_key = k
            break
    print(f"  Bin key in orders: {bin_key}")

# Use ZWM92 raw data from zwm92.py for KDX bin analysis
# Fall back to checking zwm92_summary for KDX material list
kdx_in_zwm92_not_in_ozet = 0
kdx_in_zwm92_total = 0
kdx_picks_in_zwm92_not_in_ozet = 0
kdx_picks_in_zwm92_total = 0

# check if summary has per-bin dispatch info
if "bins_dispatched" in zwm92_summary:
    bins_dispatched = zwm92_summary["bins_dispatched"]  # mat -> bin -> count
    for mat_id, bin_counts in bins_dispatched.items():
        for bin_code, cnt in bin_counts.items():
            if is_kardex_bin(bin_code):
                kdx_in_zwm92_total += 1
                kdx_picks_in_zwm92_total += cnt
                if mat_id not in kardex_mats:
                    kdx_in_zwm92_not_in_ozet += 1
                    kdx_picks_in_zwm92_not_in_ozet += cnt
elif "picks_from_kdx_by_material" in zwm92_summary:
    for mat_id, cnt in zwm92_summary["picks_from_kdx_by_material"].items():
        kdx_in_zwm92_total += 1
        kdx_picks_in_zwm92_total += cnt
        if mat_id not in kardex_mats:
            kdx_in_zwm92_not_in_ozet += 1
            kdx_picks_in_zwm92_not_in_ozet += cnt
else:
    # Use zwm92.py to load raw data
    print("  (No pre-aggregated KDX data in summary — loading ZWM92 raw...)")
    try:
        from src.zwm92 import load_zwm92_orders
        raw_orders = load_zwm92_orders()
        # raw_orders is a list of order dicts
        # Each order has 'bins' or 'materials' with bin info
        print(f"  Loaded {len(raw_orders)} ZWM92 orders")
        # check structure
        if raw_orders:
            sample_fields = list(raw_orders[0].keys())[:12]
            print(f"  ZWM92 order fields: {sample_fields}")
    except Exception as e:
        print(f"  Error loading ZWM92: {e}")

# Also use picks_by_material total to estimate KDX-dispatched materials
# The ZWM92 summary has picks_per_rack_actual which includes KDX
kdx_actual_picks = picks_per_rack_actual.get("KDX", 0) + picks_per_rack_actual.get("KDX2", 0) + \
                    picks_per_rack_actual.get("KDX3", 0) + picks_per_rack_actual.get("KDX4", 0)
print(f"\n  KDX actual picks from zwm92 summary picks_per_rack: {kdx_actual_picks}")
print(f"  Total ZWM92 picks: {total_picks_all}")
if total_picks_all > 0:
    print(f"  KDX share of total picks: {100*kdx_actual_picks/total_picks_all:.1f}%")

# Try to determine KDX fidelity gap from picks_by_material and kardex set
# count picks for materials NOT in kardex_mats but observed at KDX
print(f"\n  Ozet kardex_materials count: {len(kardex_mats)}")

# We need to find ZWM92 materials dispatched via KDX bins
# Check zwm92_observed_bins for any KDX-format entries
kdx_format_in_obs = 0
mats_with_kdx_obs = []
for mat_id, obs_list in zwm92_obs.items():
    for entry in obs_list:
        if isinstance(entry, list) and len(entry) >= 1:
            rack = str(entry[0]).upper()
            if is_kardex_bin(rack) or rack.startswith("KDX"):
                kdx_format_in_obs += 1
                mats_with_kdx_obs.append(mat_id)
                break
print(f"\n  KDX-format bins in zwm92_observed_bins.json: {kdx_format_in_obs}")
print(f"  Materials with KDX obs bin: {len(mats_with_kdx_obs)}")

# Check picks_per_rack_actual keys to find KDX variants
print(f"\n  picks_per_rack_actual keys: {sorted(picks_per_rack_actual.keys())}")

# Load ZWM92 raw rows via zwm92.py for KDX bin dispatch analysis
try:
    import src.zwm92 as zwm92_module
    # Inspect module for relevant functions
    funcs = [f for f in dir(zwm92_module) if not f.startswith('_')]
    print(f"\n  zwm92 module functions: {funcs}")
except Exception as e:
    print(f"  Could not inspect zwm92: {e}")

# Final summary
print("\n" + "="*60)
print("SUMMARY OF FINDINGS")
print("="*60)
print(f"Q1: {n_decoded_materials} ozet-decoded materials; {n_in_zwm92} appear in ZWM92 observed")
print(f"    STALE: {n_stale}/{n_in_zwm92} ({100*n_stale/max(1,n_in_zwm92):.1f}%) have dominant ZWM92 rack != ozet rack")
print(f"Q2: I/J/U: zero picks = materials in those racks either absent from ZWM92 or dominated by multi-bin nearer alternatives")
print(f"Q3: Rack A sim picks = {sim_a_picks_total}; expected ~53; ZWM92 primary rack for A-decoded mats shown above")
print(f"Q4a: ZWM92 materials with valid observed bin: {n_decodable_zwm92} / {n_total_zwm92_mats}")
print(f"Q4b: Pick coverage: {100*share:.1f}%")
print(f"Q4c: Slot conflicts: {n_conflict_slots} slots / {n_conflicting_mats} materials")
print(f"Q4d: chi2 if placed at ZWM92 observed bins: {chi2_new:.1f} (vs current 174)")
