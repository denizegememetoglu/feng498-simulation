# Physical layout
NUM_MODULES = 11
LEVELS_PER_MODULE = 9
COMPARTMENTS_PER_MODULE = 12
PALLETS_PER_COMPARTMENT = 3
TOTAL_CAPACITY = NUM_MODULES * LEVELS_PER_MODULE * COMPARTMENTS_PER_MODULE * PALLETS_PER_COMPARTMENT

AISLE_WIDTH_M = 3.0
KIT_CORRIDOR_WIDTH_M = 1.6
RACK_DEPTH_M = 1.3
RACK_HEIGHT_M = 7.5
RACK_WIDTH_M = 30.0

# Aisle layout: alternating RT aisle (3m) and kit corridor (1.6m)
# Between M0-M1: RT aisle (3m)
# Between M1-M2: Kit corridor (1.6m)
# Between M2-M3: RT aisle (3m)
# Between M3-M4: Kit corridor (1.6m)
# ...
# So gaps at index i (between Mi and M(i+1)):
#   even i -> RT aisle (3m),  odd i -> Kit corridor (1.6m)

# Every module has kit corridor access on one side -> lower levels are "fast mover" pickable
# But reach truck can only come from the 3m aisle side
FAST_MOVER_MAX_LEVEL = 3  # levels 0-2 reachable by hand from kit corridor

# Resources
NUM_REACH_TRUCKS = 7
NUM_OPERATORS = 8
NUM_MILKRUN_TRAINS = 7

# Timing (minutes)
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

# Compartment width (rack_width / compartments)
COMPARTMENT_WIDTH_M = RACK_WIDTH_M / COMPARTMENTS_PER_MODULE  # 2.5m

# Level height
LEVEL_HEIGHT_M = RACK_HEIGHT_M / LEVELS_PER_MODULE  # ~0.83m

# Data
DATA_FILE = "data/Malzeme Girişleri_010126-170326.xlsx"
DATA_DAYS = 76  # Jan 1 - Mar 17, 2026
