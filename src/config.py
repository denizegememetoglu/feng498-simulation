"""Simulation parameters that are not part of the physical layout.

Layout (rack geometry, coordinates, kit-corridor/RT sides) lives in
config/layout.json and is loaded by Warehouse.
"""

# Layout file (relative to project root)
LAYOUT_FILE = "config/layout.json"

# Operator can pick directly from levels < FAST_MOVER_MAX_LEVEL when the
# rack has a kit corridor side (3 lower levels, confirmed May 4 site visit).
FAST_MOVER_MAX_LEVEL = 3

# When a rack's kit_corridor_side / rt_aisle_side is "TBD" (not yet measured),
# treat the rack as having kit-corridor access on at least one side. This is
# the optimistic assumption; flip to False after May 20 if measurements show
# some racks have no kit access at all.
ASSUME_KIT_ACCESS_WHEN_TBD = True

# Resources
NUM_REACH_TRUCKS = 7
NUM_OPERATORS = 8
NUM_MILKRUN_TRAINS = 7

# Timing (minutes) — all TODO May 20 time-study
OPERATOR_WALK_SPEED_M_PER_MIN = 50.0
REACH_TRUCK_SPEED_M_PER_MIN = 100.0
REACH_TRUCK_LIFT_TIME_PER_LEVEL = 0.25
REACH_TRUCK_PICK_PLACE_TIME = 0.5
OPERATOR_PICK_TIME = 0.3

# Reach trucks live in a depot near the receiving area; from there they travel
# to the pick location. Travel time is now modeled explicitly so RT utilisation
# is not understated.
REACH_TRUCK_DEPOT_X = 5.0
REACH_TRUCK_DEPOT_Y = 35.0

# Manual pick from a non-kit-corridor aisle is possible at the lower levels
# (operator walks into the RT aisle on foot, no truck) but takes longer than a
# direct kit-corridor pick. Above this level the operator must wait for an RT.
MANUAL_PICK_MAX_LEVEL = 2
MANUAL_PICK_TIME_PENALTY = 0.5  # added to OPERATOR_PICK_TIME when no corridor

MILKRUN_CYCLE_MIN = 45.0
MILKRUN_TOURS_PER_DAY = 9
# When false the milk-run process is skipped entirely; it currently doesn't
# move kits or consume resources so leaving it off avoids confusing KPIs.
ENABLE_MILKRUN = False

# Kardex automated carousel: 2766 of 5941 materials live in Kardex per the
# özet sheet. Previously they were given a fallback rack slot and picked
# like any other rack position, which over-counted walk distance. Now
# treated as a separate resource with carousel rotation + pick time.
# All four units (KDX1-4) share a single queue.
NUM_KARDEX_UNITS = 4
KARDEX_PICK_TIME = 0.5             # operator pick from extracted tray (TBD May 20)
KARDEX_CAROUSEL_TIME = 0.4         # carousel rotation per request (TBD May 20)
ENABLE_KARDEX_RESOURCE = True      # off -> revert to legacy walk-to-rack behaviour

# Multi-bin from özet duplicates: when a material appears in özet with
# multiple distinct storage bins, place it at all of them. Without this
# the model ignores the partner's actual forward/reserve split.
ENABLE_MULTI_BIN = True

# Per-line kitting points: each order's start and end leg uses the kitting
# point for its production line (from layout.json `production_lines`).
# Falls back to the layout `kitting` centroid when the line has no
# kitting_point defined or LINE_BASED_SAMPLING is off.
PER_LINE_KITTING = True

# Race-condition fix: each position is a 1-capacity resource so two
# operators can't simultaneously pick from the same pallet slot.
ENABLE_POSITION_LOCK = True

# Shift-break schedule: list of (start_minute_of_shift, duration_min) tuples.
# Applied only when SHIFT_MODE == "daily". The current values are typical
# Turkish-industry breaks; refine after May 20.
BREAK_SCHEDULE = [(120.0, 15.0), (240.0, 30.0), (360.0, 15.0)]

# Simulation
SHIFT_DURATION_MIN = 480.0
SIM_DAYS = 5
# Warmup (excluded from KPI aggregation) lets the operator/RT queues fill up
# before we start recording. Cooldown does the same at the end so in-flight
# orders that don't finish before `duration` don't pull averages around.
WARMUP_MIN = 30.0
COOLDOWN_MIN = 30.0
# Treat the sim as a single continuous flow (24/7) or insert overnight gaps
# between shifts. Continuous is the simple default used in earlier reports;
# shift-mode is more realistic and gates orders + milkruns to working hours.
SHIFT_MODE = "continuous"  # "continuous" | "daily"

# Replications — independent runs with different seeds, needed for the
# chi-square / t-test validation the supervisor asked for.
N_REPLICATIONS = 30
RANDOM_SEED = 42  # base seed; per-rep seed is RANDOM_SEED + rep_index

# Order generation
ORDERS_PER_DAY = 300
ITEMS_PER_ORDER_MIN = 5
ITEMS_PER_ORDER_MAX = 15
# When true, each order is associated with a production line and only samples
# materials assigned to that line. Falls back to global sampling when the
# material->line join produces too few items for the line.
LINE_BASED_SAMPLING = True

# ABC thresholds
ABC_A_THRESHOLD = 0.80
ABC_B_THRESHOLD = 0.95

# Data
DATA_FILE = "data/Malzeme Girişleri_010126-170326.xlsx"
DATA_DAYS = 76  # Jan 1 - Mar 17, 2026
