import os
import openpyxl
from src.config import DATA_FILE


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
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        mat_id, se_class, consumption, team_abc_raw, pareto, abc, se_abc_raw, match_raw = row
        if not mat_id or not consumption or consumption <= 0:
            continue
        se_class = str(se_class).strip() if se_class else "CR"
        if len(se_class) < 2 or se_class[0] not in "ABC" or se_class[1] not in "FMRD":
            continue
        consumption = float(consumption)
        pareto = float(pareto) if pareto else 0.0
        # Derive ABC from pareto if not available
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
    """Load zppq11 sheet: material -> total consumption."""
    wb = _open_workbook(filepath)
    ws = wb["zppq11"]
    result = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        mat_id, total = row[:2]
        if mat_id and total and float(total) > 0:
            result[str(mat_id).strip()] = float(total)
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


def load_all_data(filepath=None):
    return {
        "abc_analizi": load_abc_analizi(filepath),
        "consumption": load_consumption(filepath),
        "sap_master": load_sap_master(filepath),
    }
