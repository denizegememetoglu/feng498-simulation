"""ZWM92 SAP WM-dispatch log loader.

Each row of a ZWM92 export is one component goods-issue from a storage bin
(`Çıkılan Adres`) to a production order (`Order`) for a finished product
(`Ürün Malzeme`), with timestamp + RF user + quantity + kit + production line.

Files live in `data/zwm92/ZWM92_<range>_<FAMILY>.XLSX`; one file per product
family (F400, SM6, Okken, Premset, Mcset, AKS_PAK, Çekmece, DMK, Sepam).

This module gives the simulation three things the synthetic OrderGenerator
could not:
  1. Real order arrival times (`pick_datetime`) → trace-driven inter-arrivals.
  2. Real kit composition (group by `Order` + `KIT No`) → BOM-driven items.
  3. Real per-rack pick distribution → replaces consumption-proxy in
     validate.py's chi-square expected vector.
"""

import json
import os
import re
from collections import Counter, defaultdict

import pandas as pd

from src.data_loader import decode_storage_bin, is_kardex_bin


# Cached single load — load_zwm92_all() is expensive (~14 MB of xlsx).
_CACHED_DF: pd.DataFrame | None = None
_CACHED_ORDERS: dict[str, list[dict]] = {}
_CACHED_FITS: dict[tuple[str, str, float], dict] = {}


def load_zwm92_all(directory: str = "data/zwm92", use_cache: bool = True) -> pd.DataFrame:
    """Load all ZWM92 XLSX files in `directory`, concatenated into one DF.

    Adds `family` (from filename) and `pick_datetime` (Sayim Tarihi + Sayim
    Zamani) columns. Normalises bin codes and material IDs to stripped
    uppercase strings.
    """
    global _CACHED_DF
    if use_cache and _CACHED_DF is not None:
        return _CACHED_DF

    pattern = re.compile(r"ZWM92_\d+-\d+_(.+)\.XLSX$", re.IGNORECASE)
    frames = []
    for fn in sorted(os.listdir(directory)):
        m = pattern.match(fn)
        if not m:
            continue
        df = pd.read_excel(os.path.join(directory, fn))
        df["family"] = m.group(1)
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No ZWM92 files matched in {directory}/")
    full = pd.concat(frames, ignore_index=True)

    full["Çıkılan Adres"] = (
        full["Çıkılan Adres"].astype("string").str.strip().str.upper()
    )
    full["Bileşen Malzeme"] = full["Bileşen Malzeme"].astype("string").str.strip()
    full["Uretim Hatti"] = full["Uretim Hatti"].astype("string").str.strip()
    full["Üretime Çkş. Trh."] = pd.to_datetime(
        full["Üretime Çkş. Trh."], errors="coerce"
    )
    full["Sayim Tarihi"] = pd.to_datetime(full["Sayim Tarihi"], errors="coerce")

    def _combine(row):
        d = row["Sayim Tarihi"]
        t = row["Sayim Zamani"]
        if pd.isna(d):
            return pd.NaT
        if hasattr(t, "hour"):
            return pd.Timestamp(
                year=d.year, month=d.month, day=d.day,
                hour=t.hour, minute=t.minute, second=t.second,
            )
        return d
    full["pick_datetime"] = full.apply(_combine, axis=1)

    if use_cache:
        _CACHED_DF = full
    return full


def picks_per_rack_actual(df: pd.DataFrame) -> dict[str, int]:
    """Count per-rack picks from ZWM92 actuals (rack bins only — Kardex and
    staging codes excluded). This is the chi-square expected vector that
    replaces the consumption proxy in validate.py."""
    counts: Counter = Counter()
    for code in df["Çıkılan Adres"].dropna():
        if is_kardex_bin(code):
            continue
        d = decode_storage_bin(code)
        if d is None:
            continue
        counts[d[0]] += 1
    return dict(counts)


def picks_per_material_per_day(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """Per-material per-day pick counts, used by validate.py paired t-test."""
    sub = df.dropna(subset=["Sayim Tarihi", "Bileşen Malzeme"])
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    days = sub["Sayim Tarihi"].dt.strftime("%Y-%m-%d")
    for mat, day in zip(sub["Bileşen Malzeme"], days):
        out[str(mat).strip()][day] += 1
    return {m: dict(v) for m, v in out.items()}


def observed_bin_per_material(df: pd.DataFrame) -> dict[str, list[tuple[str, int, int]]]:
    """For each material, the rack bins observed in ZWM92 ordered by frequency.

    Used by RealBaselinePolicy to refine ground truth: özet gives the *assigned*
    bin per material, while ZWM92 gives the *actually used* bins. When they
    disagree, the ZWM92 mode is the truth on the floor.
    """
    counts: dict[str, Counter] = defaultdict(Counter)
    sub = df.dropna(subset=["Bileşen Malzeme", "Çıkılan Adres"])
    for mat, code in zip(sub["Bileşen Malzeme"], sub["Çıkılan Adres"]):
        if is_kardex_bin(code):
            continue
        d = decode_storage_bin(code)
        if d is None:
            continue
        counts[str(mat).strip()][d] += 1
    return {m: [b for b, _ in c.most_common()] for m, c in counts.items()}


def build_orders(df: pd.DataFrame, family_filter: list[str] | None = None) -> list[dict]:
    """Group ZWM92 rows by (Order, KIT No) → one simulation order per kit.

    Returns list of dicts sorted by arrival time:
      {
        'id': int,                    # 1-indexed sequential
        'order_sap': str,             # SAP order number
        'kit_id': str,                # KIT No
        'line': str,                  # Uretim Hatti
        'family': str,                # product family
        'arrival_dt': pd.Timestamp,
        'items': list[material_id],   # one per pick, may repeat by qty
      }
    """
    if family_filter:
        df = df[df["family"].isin(family_filter)]

    sub = df.dropna(subset=["Order", "KIT No", "Bileşen Malzeme"])
    sub = sub.copy()
    sub["qty"] = pd.to_numeric(sub.get("Çıkılan Miktar", 1), errors="coerce").fillna(1).astype(int).clip(lower=1)

    orders = []
    for (order_sap, kit_id), g in sub.groupby(["Order", "KIT No"], dropna=False):
        items: list[str] = []
        for mat, qty in zip(g["Bileşen Malzeme"], g["qty"]):
            mid = str(mat).strip()
            items.extend([mid] * int(qty))
        if not items:
            continue
        # H5 fix: split picks (qty-expanded) from distinct materials. A
        # kit row with qty=20 is ONE pick event on ONE material, not 20.
        distinct = list(dict.fromkeys(items))
        arrival = g["pick_datetime"].min()
        line_series = g["Uretim Hatti"].dropna()
        line = str(line_series.iloc[0]) if len(line_series) else None
        family = str(g["family"].iloc[0])
        orders.append({
            "order_sap": str(order_sap),
            "kit_id": str(kit_id),
            "line": line,
            "family": family,
            "arrival_dt": arrival,
            "items": items,
            "distinct_materials": distinct,
        })
    orders.sort(key=lambda o: o["arrival_dt"] if pd.notna(o["arrival_dt"]) else pd.Timestamp.max)
    for i, o in enumerate(orders, start=1):
        o["id"] = i
    return orders


def orders_to_inter_arrivals(orders: list[dict]) -> list[dict]:
    """Add `inter_arrival_min` to each order = minutes since previous order.

    First order gets `inter_arrival_min` = 0. NaT arrival_dt orders are
    placed at the end with inter_arrival = 0 (rare; dropped before sim).
    """
    last_dt = None
    out = []
    for o in orders:
        dt = o["arrival_dt"]
        if pd.isna(dt):
            iat = 0.0
        elif last_dt is None:
            iat = 0.0
        else:
            iat = max(0.0, (dt - last_dt).total_seconds() / 60.0)
        o2 = {**o, "inter_arrival_min": iat}
        if pd.notna(dt):
            last_dt = dt
        out.append(o2)
    return out


def cache_zwm92_views(directory: str = "data/zwm92", output_dir: str = "output") -> dict:
    """Compute + cache all derived views to output/zwm92_*.json. Returns summary."""
    df = load_zwm92_all(directory, use_cache=False)
    os.makedirs(output_dir, exist_ok=True)

    rack_picks = picks_per_rack_actual(df)
    obm = observed_bin_per_material(df)
    orders_raw = build_orders(df)
    # M4 fix: drop orders with no production line. They would otherwise
    # collapse into an UNKNOWN line bucket in fit_distributions and skew
    # the line-conditional material weights.
    orders = [o for o in orders_raw if o.get("line")]
    orders_dropped_no_line = len(orders_raw) - len(orders)
    for i, o in enumerate(orders, start=1):
        o["id"] = i
    orders = orders_to_inter_arrivals(orders)

    # H2 fix: report two IAT means side-by-side.
    # within_shift filters out overnight/weekend gaps (60-min cap) — right
    # for the Arena driver, which models in-shift cadence. calendar uses
    # raw wall-clock spread / (n_orders - 1) — the actual arrival rate
    # including downtime, useful for capacity calculations.
    iats_within = [o["inter_arrival_min"] for o in orders[1:]
                   if 0 < o["inter_arrival_min"] <= 60.0]
    iat_within_shift_mean = (sum(iats_within) / len(iats_within)) if iats_within else None
    # Batch structure (2026-06-09): consecutive same-timestamp orders form a
    # dispatch batch. Only timestamped orders carry IAT info; volume uses all.
    _ts = [o for o in orders if pd.notna(o["arrival_dt"])]
    _batches: list[int] = []
    _cur = 1
    for _a, _b in zip(_ts, _ts[1:]):
        if (_b["arrival_dt"] - _a["arrival_dt"]).total_seconds() <= 0:
            _cur += 1
        else:
            _batches.append(_cur)
            _cur = 1
    _batches.append(_cur)
    _active_days = len({o["arrival_dt"].date() for o in _ts}) or 1
    if df["pick_datetime"].notna().any() and len(orders) > 1:
        span_min = (df["pick_datetime"].max() - df["pick_datetime"].min()).total_seconds() / 60.0
        iat_calendar_mean = span_min / (len(orders) - 1)
    else:
        iat_calendar_mean = None

    # H5: distinct-per-kit vs qty-expanded picks-per-kit. The driver should
    # sample distinct (Arena: one sample = one distinct material per pick
    # event), not qty-expanded — qty=20 is a single pick of 20 units.
    n_picks_per_kit = [len(o["items"]) for o in orders if o["items"]]
    n_distinct_per_kit = [len(o.get("distinct_materials", []))
                          for o in orders if o.get("distinct_materials")]

    # C3 helper: per-material dispatch count → TravelDistancePolicy sort key.
    # 2026-06-10 fix: per-material PICK frequency must count DISTINCT kit
    # lines (one pick event per material per kit), not qty-expanded units —
    # the simulation executes one pick per distinct material. The qty-
    # expanded counter is kept alongside for transparency/disclosure.
    mat_counts: Counter = Counter()
    mat_counts_qty: Counter = Counter()
    for o in orders:
        for mid in o.get("distinct_materials") or dict.fromkeys(o["items"]):
            mat_counts[mid] += 1
        for mid in o["items"]:
            mat_counts_qty[mid] += 1

    summary = {
        "total_rows": int(len(df)),
        "date_min": (df["Sayim Tarihi"].min().isoformat()
                     if df["Sayim Tarihi"].notna().any() else None),
        "date_max": (df["Sayim Tarihi"].max().isoformat()
                     if df["Sayim Tarihi"].notna().any() else None),
        "families": df["family"].value_counts().to_dict(),
        "lines": df["Uretim Hatti"].dropna().value_counts().to_dict(),
        "picks_per_rack_actual": rack_picks,
        "materials_observed": len(obm),
        "orders_built": len(orders),
        "orders_dropped_no_line": orders_dropped_no_line,
        "kardex_picks": int(df["Çıkılan Adres"].dropna().apply(is_kardex_bin).sum()),
        "iat_within_shift_mean": iat_within_shift_mean,
        "iat_within_shift_n": len(iats_within),
        "iat_calendar_mean": iat_calendar_mean,
        "timestamped_orders": len(_ts),
        "n_batches": len(_batches),
        "batch_size_mean": (sum(_batches) / len(_batches)) if _batches else None,
        "batch_size_max": max(_batches) if _batches else None,
        "active_days": _active_days,
        "orders_per_active_day": len(orders) / _active_days,
        "n_picks_per_kit_mean": ((sum(n_picks_per_kit) / len(n_picks_per_kit))
                                  if n_picks_per_kit else None),
        "n_distinct_per_kit_mean": ((sum(n_distinct_per_kit) / len(n_distinct_per_kit))
                                     if n_distinct_per_kit else None),
        "picks_by_material": dict(mat_counts),
        "picks_by_material_qty": dict(mat_counts_qty),
    }

    with open(f"{output_dir}/zwm92_summary.json", "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

    orders_jsonable = [{
        "id": o["id"],
        "order_sap": o["order_sap"],
        "kit_id": o["kit_id"],
        "line": o["line"],
        "family": o["family"],
        "arrival_iso": (o["arrival_dt"].isoformat()
                        if pd.notna(o["arrival_dt"]) else None),
        "inter_arrival_min": o["inter_arrival_min"],
        "items": o["items"],
        "distinct_materials": o.get("distinct_materials", []),
    } for o in orders]
    with open(f"{output_dir}/zwm92_orders.json", "w") as f:
        json.dump(orders_jsonable, f, ensure_ascii=False, default=str)

    obm_jsonable = {m: [list(b) for b in bins] for m, bins in obm.items()}
    with open(f"{output_dir}/zwm92_observed_bins.json", "w") as f:
        json.dump(obm_jsonable, f, ensure_ascii=False, default=str)

    return summary


def load_orders_cached(path: str = "output/zwm92_orders.json") -> list[dict]:
    """Reload orders prepared by cache_zwm92_views()."""
    cache_key = os.path.abspath(path)
    if cache_key in _CACHED_ORDERS:
        return _CACHED_ORDERS[cache_key]
    with open(path) as f:
        raw = json.load(f)
    out = []
    for r in raw:
        out.append({
            "id": r["id"],
            "order_sap": r["order_sap"],
            "kit_id": r["kit_id"],
            "line": r["line"],
            "family": r["family"],
            "arrival_dt": pd.to_datetime(r["arrival_iso"]) if r["arrival_iso"] else pd.NaT,
            "inter_arrival_min": float(r["inter_arrival_min"]),
            "items": r["items"],
            "distinct_materials": r.get("distinct_materials", []),
        })
    _CACHED_ORDERS[cache_key] = out
    return out


def fit_distributions(orders_path: str = "output/zwm92_orders.json",
                      summary_path: str = "output/zwm92_summary.json",
                      iat_cap_min: float = 60.0) -> dict:
    """Fit Arena-style sampling distributions from ZWM92.

    Returns a dict the simulation driver can use to sample independent
    orders per replication (rather than replaying the raw trace):

      {
        "iat_mean_min":      float,            # Exponential parameter
        "n_items_empirical": list[int],        # per-order item count, sample with replacement
        "material_ids":      list[str],        # categorical support
        "material_weights":  list[float],      # P(material) — sums to 1
        "line_names":        list[str],        # categorical support
        "line_weights":      list[float],      # P(line) — sums to 1
        "per_line_material_ids":     dict[line, list[str]],
        "per_line_material_weights": dict[line, list[float]],
        "summary":           {...},            # human-readable provenance
      }
    """
    cache_key = (os.path.abspath(orders_path), os.path.abspath(summary_path), float(iat_cap_min))
    if cache_key in _CACHED_FITS:
        return _CACHED_FITS[cache_key]
    orders = load_orders_cached(orders_path)

    # 1) Arrival process — batch structure (2026-06-09 fix). Kit-orders are
    # dispatched in bursts: consecutive orders sharing one timestamp form a
    # batch. Only timestamped orders carry IAT information (Mcset/Premset/
    # SM6/DMK/Sepam exports lack the time-of-day column), so the batch and
    # gap fits use that subset; the VOLUME calibration uses all orders.
    ts_orders = [o for o in orders if pd.notna(o["arrival_dt"])]
    batch_sizes: list[int] = []
    iats: list[float] = []
    cur = 1
    for prev, nxt in zip(ts_orders, ts_orders[1:]):
        gap = (nxt["arrival_dt"] - prev["arrival_dt"]).total_seconds() / 60.0
        if gap <= 0:
            cur += 1
            continue
        batch_sizes.append(cur)
        cur = 1
        if gap <= iat_cap_min:  # drop overnight / weekend gaps
            iats.append(gap)
    batch_sizes.append(cur)
    iat_mean = sum(iats) / len(iats) if iats else 5.0
    if len(iats) > 1:
        _m = iat_mean
        iat_std = (sum((x - _m) ** 2 for x in iats) / (len(iats) - 1)) ** 0.5
    else:
        iat_std = 0.0
    iat_cv = (iat_std / iat_mean) if iat_mean else 0.0
    batch_mean = (sum(batch_sizes) / len(batch_sizes)) if batch_sizes else 1.0
    # Daily-volume calibration target: ALL built orders over the active
    # day count. ASSUMPTION (documented, ASSUMPTIONS §24.1): all families
    # share the warehouse's single operating calendar, and the timestamped
    # subset reveals it — 103 active days = 87 weekdays + 16 Saturdays over
    # the 2026-01-02..05-18 span (97 weekdays total), i.e. the facility's
    # actual working days. The untimestamped family exports (Mcset, Premset,
    # SM6, DMK, Sepam) carry no date-times, so their own day count cannot be
    # observed; a single-facility warehouse dispatching all families on the
    # same days makes the shared-calendar reading the natural one. With
    # empirical gaps + empirical batch sizes the sim produces
    # SHIFT/iat_mean * batch_mean orders/day; validate.py checks this lands
    # within ±10% of orders_per_active_day.
    active_days = len({o["arrival_dt"].date() for o in ts_orders}) or 1
    orders_per_active_day = len(orders) / active_days

    # 2) Items per order: keep the empirical distribution rather than fit a
    # parametric — kit sizes are bursty, mode at 1-2, heavy right tail.
    # Clip at 50 to suppress SAP qty entries like "134012" that blow up sim.
    # H5 fix: sample DISTINCT-per-kit (one entry per material), not qty-
    # expanded picks. A kit row with qty=20 is one pick of 20 units, not 20
    # pick events. Driver uses n_items_emp; n_picks_emp kept for reference.
    n_picks_emp = [min(len(o["items"]), 50) for o in orders if o["items"]]
    n_distinct_emp = [min(len(o.get("distinct_materials") or o["items"]), 50)
                      for o in orders if o["items"]]
    n_items_emp = n_distinct_emp if n_distinct_emp else n_picks_emp

    # 3) Material weights: frequency-of-pick across the trace.
    from collections import Counter
    mat_counts: Counter = Counter()
    line_counts: Counter = Counter()
    per_line_mat: dict[str, Counter] = {}
    for o in orders:
        line = (o.get("line") or "UNKNOWN")
        line_counts[line] += 1
        # 2026-06-10 fix: weights over DISTINCT kit lines (one pick event
        # per material per kit) — pairing them with the distinct-based
        # n_items empirical keeps the sampled kit composition faithful to
        # real kits. Qty-expanded weights overweighted bulk materials.
        for mid in o.get("distinct_materials") or dict.fromkeys(o["items"]):
            mat_counts[mid] += 1
            per_line_mat.setdefault(line, Counter())[mid] += 1

    total = sum(mat_counts.values()) or 1
    material_ids = list(mat_counts.keys())
    material_weights = [mat_counts[m] / total for m in material_ids]

    total_lines = sum(line_counts.values()) or 1
    line_names = list(line_counts.keys())
    line_weights = [line_counts[l] / total_lines for l in line_names]

    per_line_ids: dict[str, list[str]] = {}
    per_line_w: dict[str, list[float]] = {}
    for line, ctr in per_line_mat.items():
        tot = sum(ctr.values()) or 1
        ids = list(ctr.keys())
        ws = [ctr[m] / tot for m in ids]
        per_line_ids[line] = ids
        per_line_w[line] = ws

    fit = {
        "iat_mean_min": iat_mean,
        "iat_std_min": iat_std,
        "iat_cv": iat_cv,
        "iat_cap_min": iat_cap_min,
        "iat_samples": iats,
        "batch_size_empirical": batch_sizes,
        "batch_size_mean": batch_mean,
        "active_days": active_days,
        "orders_per_active_day": orders_per_active_day,
        "n_items_empirical": n_items_emp,
        "n_picks_empirical": n_picks_emp,
        "n_distinct_empirical": n_distinct_emp,
        "material_ids": material_ids,
        "material_weights": material_weights,
        "line_names": line_names,
        "line_weights": line_weights,
        "per_line_material_ids": per_line_ids,
        "per_line_material_weights": per_line_w,
        "summary": {
            "n_orders": len(orders),
            "n_timestamped_orders": len(ts_orders),
            "n_iat_samples": len(iats),
            "iat_mean_min": iat_mean,
            "iat_cv": iat_cv,
            "n_batches": len(batch_sizes),
            "batch_size_mean": batch_mean,
            "active_days": active_days,
            "orders_per_active_day": orders_per_active_day,
            "n_materials_in_pool": len(material_ids),
            "n_lines": len(line_names),
            "items_per_order_mean": (sum(n_items_emp) / len(n_items_emp)) if n_items_emp else 0,
            "items_per_order_max": max(n_items_emp) if n_items_emp else 0,
            "picks_per_order_mean": (sum(n_picks_emp) / len(n_picks_emp)) if n_picks_emp else 0,
            "distinct_per_order_mean": (sum(n_distinct_emp) / len(n_distinct_emp)) if n_distinct_emp else 0,
        },
    }
    _CACHED_FITS[cache_key] = fit
    return fit


if __name__ == "__main__":
    s = cache_zwm92_views()
    print(json.dumps(s, indent=2, ensure_ascii=False, default=str))
