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

MILKRUN_CYCLE_MIN = 45.0
MILKRUN_TOURS_PER_DAY = 9

# Simulation
SHIFT_DURATION_MIN = 480.0
SIM_DAYS = 5
RANDOM_SEED = 42

# Order generation
ORDERS_PER_DAY = 300
ITEMS_PER_ORDER_MIN = 5
ITEMS_PER_ORDER_MAX = 15

# ABC thresholds
ABC_A_THRESHOLD = 0.80
ABC_B_THRESHOLD = 0.95

# Data
DATA_FILE = "data/Malzeme Girişleri_010126-170326.xlsx"
DATA_DAYS = 76  # Jan 1 - Mar 17, 2026
