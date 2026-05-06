import json
import os
import re

import openpyxl

from src.config import DATA_FILE


_VALID_RACKS = frozenset({"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "U"})
# Accept optional 'BR' prefix; özet uses both 'BRA-02-02' and 'A-02-02' interchangeably.
_BIN_RE = re.compile(r"^(?:BR)?([A-Z])-(\d{1,2})-(\d{1,2})$")
# Kardex automated storage — not in rack layout, tracked separately.
_KDX_RE = re.compile(r"^KDX\d*$")


def _resolve_data_path():
    """Find the actual Excel file in data/ regardless of unicode normalization."""
    data_dir = os.path.dirname(DATA_FILE)
    for f in os.listdir(data_dir):
        if f.endswith(".xlsx"):
            return os.path.join(data_dir, f)
    raise FileNotFoundError(f"No .xlsx file found in {data_dir}/")


def _open_workbook(filepath=None):
    path = filepath or _resolve_data_path()
    return openpyxl.load_workbook(path, read_only=True, data_only=True)


def load_abc_analizi(filepath=None):
    """Load ABC Analizi sheet: 6011 rows of material classification + consumption."""
    wb = _open_workbook(filepath)
    ws = wb["ABC Analizi"]
    materials = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        mat_id, se_class, consumption, _team_abc_raw, pareto, abc, _se_abc_raw, _match_raw = row[:8]
        if not mat_id or not consumption or consumption <= 0:
            continue
        se_class = str(se_class).strip() if se_class else "CR"
        if len(se_class) < 2 or se_class[0] not in "ABC" or se_class[1] not in "FMRD":
            continue
        consumption = float(consumption)
        pareto = float(pareto) if pareto else 0.0
        if abc and str(abc).strip() in ("A", "B", "C"):
            team_abc = str(abc).strip()
        elif pareto <= 0.80:
            team_abc = "A"
        elif pareto <= 0.95:
            team_abc = "B"
        else:
            team_abc = "C"

        se_abc = se_class[0]
        se_fmr = se_class[1]

        materials.append({
            "material_id": str(mat_id).strip(),
            "se_class": se_class,
            "se_abc": se_abc,
            "se_fmr": se_fmr,
            "consumption": consumption,
            "pareto": pareto,
            "team_abc": team_abc,
            "abc_match": 1 if team_abc == se_abc else 0,
        })
    wb.close()
    materials.sort(key=lambda m: m["consumption"], reverse=True)
    return materials


def load_consumption(filepath=None):
    """Load zppq11 sheet: Material | Material number | Plnt | material-plant | TOTAL."""
    wb = _open_workbook(filepath)
    ws = wb["zppq11"]
    result: dict[str, float] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) < 5:
            continue
        mat_id = row[0]
        total = row[4]
        if not mat_id or total is None:
            continue
        try:
            t = float(total)
        except (TypeError, ValueError):
            continue
        if t > 0:
            result[str(mat_id).strip()] = t
    wb.close()
    return result


def load_sap_master(filepath=None):
    """Load zppq16_copy sheet: SAP material master data."""
    wb = _open_workbook(filepath)
    ws = wb["zppq16_copy"]
    result = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        mat_id, plant, abc_ind, purch_grp, mrp_ctrl, desc = row[:6]
        if not mat_id:
            continue
        result[str(mat_id).strip()] = {
            "plant": str(plant) if plant else "",
            "abc_indicator": str(abc_ind) if abc_ind else "",
            "purchasing_group": str(purch_grp) if purch_grp else "",
            "mrp_controller": str(mrp_ctrl) if mrp_ctrl else "",
            "description": str(desc) if desc else "",
        }
    wb.close()
    return result


def load_storage_bins(filepath=None):
    """Load özet sheet: material -> SAP storage bin code (e.g., 'BRA-02-02').

    The özet sheet has 10458 rows; only rows with a non-empty Storage Bin
    are returned. When a material appears multiple times the last seen
    bin wins (özet is the canonical source per the May 4 visit).
    """
    wb = _open_workbook(filepath)
    ws = wb["özet"]
    result: dict[str, str] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        # Material | Plant | MRP Controller | MRP Tanımı | ABC Ind | Storage Bin
        if len(row) < 6:
            continue
        mat_id = row[0]
        bin_code = row[5]
        if not mat_id or not bin_code:
            continue
        result[str(mat_id).strip()] = str(bin_code).strip()
    wb.close()
    return result


def is_kardex_bin(bin_code: str) -> bool:
    """Kardex automated storage (KDX, KDX2, KDX3, KDX4). Not in rack layout."""
    if not bin_code:
        return False
    return bool(_KDX_RE.match(str(bin_code).strip().upper()))


def decode_storage_bin(bin_code: str) -> tuple[str, int, int] | None:
    """Parse 'BRA-02-02' or 'A-02-02' into ('A', 2, 2). Returns None for malformed
    codes or codes with rack letters outside the documented 11 racks {A..I, J, U}.

    The convention was confirmed May 6 against the rack PDFs: optional 'BR'
    prefix, then the rack letter, then a 1-2 digit bay code, then a 1-2 digit
    position within the bay. Kardex codes (KDX*) are not racks and return None
    here — use is_kardex_bin to detect them separately.
    """
    if not bin_code:
        return None
    m = _BIN_RE.match(str(bin_code).strip().upper())
    if not m:
        return None
    rack = m.group(1)
    if rack not in _VALID_RACKS:
        return None
    bay = int(m.group(2))
    pos = int(m.group(3))
    return rack, bay, pos


def load_mrpc(filepath=None) -> dict[str, str]:
    """Load mrpc sheet: MRP-Controller code -> production line name (Açıklama)."""
    wb = _open_workbook(filepath)
    ws = wb["mrpc"]
    result: dict[str, str] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        # Plant | MRP-C | plant-mrpc | Açıklama
        if len(row) < 4:
            continue
        mrpc = row[1]
        line = row[3]
        if not mrpc or not line:
            continue
        result[str(mrpc).strip()] = str(line).strip()
    wb.close()
    return result


def preprocess(filepath=None, layout_path: str = None, write_stats: bool = True) -> dict:
    """Run all loaders, decode storage bins, join material -> line, and emit
    audit stats. Returns a single dict consumed by main.py.
    """
    materials = load_abc_analizi(filepath)
    consumption = load_consumption(filepath)
    sap_master = load_sap_master(filepath)
    storage_bins = load_storage_bins(filepath)
    mrp_to_line = load_mrpc(filepath)

    # Resolve layout for cross-validation (which (rack, bay) actually exist).
    from src.warehouse import Warehouse
    wh = Warehouse(layout_path)
    valid_rack_bays: set[tuple[str, int]] = set()
    for pid, p in wh.positions.items():
        valid_rack_bays.add((p.rack_id, p.bay_code))

    decoded_bins: dict[str, tuple[str, int, int]] = {}
    kardex_materials: set[str] = set()
    bins_unknown_rack = 0
    bins_unmapped_position = 0
    bins_malformed = 0
    bins_kardex = 0

    for mat_id, bin_code in storage_bins.items():
        if is_kardex_bin(bin_code):
            kardex_materials.add(mat_id)
            bins_kardex += 1
            continue
        decoded = decode_storage_bin(bin_code)
        if decoded is None:
            # Either format-mismatch (RST, #N/A, SEVK, KRIT, ...) or unknown rack
            # letter (T, Q, ...). Bucket both under malformed; the unknown-rack
            # counter is reserved for the case decode returns a rack we then
            # can't find in the layout.
            bins_malformed += 1
            continue
        rack, bay, pos = decoded
        if (rack, bay) not in valid_rack_bays:
            bins_unmapped_position += 1
            continue
        decoded_bins[mat_id] = decoded

    # Join material -> line via sap_master.mrp_controller -> mrp_to_line
    material_to_line: dict[str, str] = {}
    for mat_id, master in sap_master.items():
        mrp = master.get("mrp_controller", "").strip()
        if not mrp:
            continue
        line = mrp_to_line.get(mrp)
        if line:
            material_to_line[mat_id] = line

    stats = {
        "materials_total": len(materials),
        "materials_with_bin": sum(1 for m in materials if m["material_id"] in storage_bins),
        "materials_with_decoded_bin": sum(1 for m in materials if m["material_id"] in decoded_bins),
        "materials_in_kardex": sum(1 for m in materials if m["material_id"] in kardex_materials),
        "bins_total": len(storage_bins),
        "bins_decoded": len(decoded_bins),
        "bins_kardex": bins_kardex,
        "bins_malformed": bins_malformed,
        "bins_unknown_rack": bins_unknown_rack,
        "bins_unmapped_position": bins_unmapped_position,
        "materials_with_line": sum(1 for m in materials if m["material_id"] in material_to_line),
        "mrp_controllers_total": len(mrp_to_line),
        "warehouse_positions": len(wh.positions),
        "warehouse_pdf_capacity": wh.pallet_capacity_from_pdf,
    }

    if write_stats:
        os.makedirs("output", exist_ok=True)
        with open("output/preprocess_stats.json", "w") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    return {
        "materials": materials,
        "consumption": consumption,
        "sap_master": sap_master,
        "storage_bins": storage_bins,
        "decoded_bins": decoded_bins,
        "kardex_materials": kardex_materials,
        "mrp_to_line": mrp_to_line,
        "material_to_line": material_to_line,
        "stats": stats,
    }


# Backwards-compat shim for any caller that still imports load_all_data.
def load_all_data(filepath=None):
    return {
        "abc_analizi": load_abc_analizi(filepath),
        "consumption": load_consumption(filepath),
        "sap_master": load_sap_master(filepath),
    }
