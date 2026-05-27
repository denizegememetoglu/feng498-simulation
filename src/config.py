"""Simulation parameters that are not part of the physical layout.

Layout (rack geometry, coordinates, kit-corridor/RT sides) lives in
config/layout.json and is loaded by Warehouse.
"""

# Layout file (relative to project root)
LAYOUT_FILE = "config/layout.json"

# Operator can pick directly from levels < FAST_MOVER_MAX_LEVEL when the
# rack has a kit corridor side (3 lower levels, confirmed May 4 site visit).
FAST_MOVER_MAX_LEVEL = 3

# When a rack's kit_corridor_side is "TBD" (not yet measured), do not treat it
# as confirmed kit access. Earlier runs used an optimistic assumption here; the
# audit keeps TBD as a conservative assumption so routing and manual-pick KPIs
# do not quietly depend on an unverified corridor.
ASSUME_KIT_ACCESS_WHEN_TBD = False

# Conservative rectilinear routing. Rack bodies are blockers, and picks happen
# from an aisle-side service point offset from the rack face.
ROUTE_CLEARANCE_M = 0.60
ROUTE_FAIL_ON_INTERSECTION = True

# Resources
NUM_REACH_TRUCKS = 7
NUM_OPERATORS = 8
NUM_MILKRUN_TRAINS = 7

# Timing (minutes). Source: F400 Kit Cansu Nehir video time-motion study
# (output/timing_study_f400.json, src/timing_study.py). 2,319 micro-events
# observed across 296.6 min of footage. F400 is the largest line (~48k
# goods-issues in ZWM92); these constants are extrapolated to all lines
# until per-line studies exist — see ASSUMPTIONS.md §18.
OPERATOR_WALK_SPEED_M_PER_MIN = 50.0       # book value (no video pace data)
REACH_TRUCK_SPEED_M_PER_MIN = 100.0        # book value
REACH_TRUCK_LIFT_TIME_PER_LEVEL = 0.25     # book value (no RT lift footage)
REACH_TRUCK_PICK_PLACE_TIME = 0.11         # mean rt_pick (n=69, 6.6 s)
# Operator pick = at-bin scan + grab. Mean of (rf_scan, manual_pick) ≈ 6.78s.
OPERATOR_PICK_TIME = 0.113

# Stochastic timing: when STOCHASTIC_PICK_TIMES is True, every operator and
# RT pick samples its duration from Lognormal(mean=constant, sigma=...).
# The sigma values come from the F400 video category stats (stdev_s / mean_s
# converted to log-scale via the lognormal moment-matching formula).
STOCHASTIC_PICK_TIMES = True
OPERATOR_PICK_TIME_SIGMA = 1.30       # F400 rf_scan+manual_pick CV ≈ 1.7
REACH_TRUCK_PICK_TIME_SIGMA = 1.20    # F400 rt_pick CV ≈ 1.37
MANUAL_PICK_PENALTY_SIGMA = 1.40      # F400 walk_corridor CV ≈ 1.92
KARDEX_PICK_TIME_SIGMA = 1.30
KARDEX_CAROUSEL_SIGMA = 0.30          # book value — no carousel video

# Reach trucks live in a depot near the receiving area; from there they travel
# to the pick location. Travel time is now modeled explicitly so RT utilisation
# is not understated. Depot coords (5,35) are approximate — kitting NW zone at
# layout.json x=8/y=0 with depot ~3m west; CAD-rebuild deferred (ASSUMPTIONS §22).
REACH_TRUCK_DEPOT_X = 5.0
REACH_TRUCK_DEPOT_Y = 35.0

# Manual pick from a non-kit-corridor aisle is possible at the lower levels
# (operator walks into the RT aisle on foot, no truck) but takes longer than a
# direct kit-corridor pick. Above this level the operator must wait for an RT.
MANUAL_PICK_MAX_LEVEL = 2
# MANUAL_PICK_TIME_PENALTY: conservative UPPER-bound proxy (F400 video full
# corridor traversal time). Real marginal penalty over baseline pick is
# smaller — proxy overestimates by ~30%. See ASSUMPTIONS.md §19.
MANUAL_PICK_TIME_PENALTY = 0.102  # F400 video walk_corridor mean ≈6.1 s

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
KARDEX_PICK_TIME = 0.113           # mirrors OPERATOR_PICK_TIME (no Kardex video)
KARDEX_CAROUSEL_TIME = 0.4         # carousel rotation per request (book value)
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
# Applied ONLY when SHIFT_MODE == "daily" (currently inactive — see comment
# at SHIFT_MODE below). Values are typical Turkish-industry breaks; refine
# after a site visit if SHIFT_MODE flips back to "daily".
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
# BREAK_SCHEDULE above is applied ONLY when this is "daily"; with "continuous"
# the break list is inert (see ASSUMPTIONS §23).
SHIFT_MODE = "continuous"  # "continuous" | "daily"

# Replications + seeding.
# Advisor decision (May 26): use a single fixed seed for every replication
# so the run is fully reproducible. With same seed and Arena-style fitted
# distributions, every rep produces an identical trajectory — so N=1 is
# sufficient. Validation comes from chi-square / paired t-test against
# ZWM92 actuals (src/validate.py), not from replication variance.
# Flip SAME_SEED_FOR_ALL_REPS to False to revert to the prior
# (seed = RANDOM_SEED + rep_index) Sargent-replication setup.
N_REPLICATIONS = 1
RANDOM_SEED = 42
SAME_SEED_FOR_ALL_REPS = True

# Trace-driven mode: replay real ZWM92 dispatch orders instead of generating
# synthetic ones. The synthetic OrderGenerator is kept as a fallback that
# kicks in automatically if the cache is missing.
TRACE_DRIVEN = True
ZWM92_ORDERS_CACHE = "output/zwm92_orders.json"
# Cap inter-arrival times at this value (minutes) so overnight / weekend
# gaps in the ZWM92 trace don't waste sim time. 60 min ≈ one shift-pause.
# Set to None to use raw timestamps.
MAX_TRACE_IAT_MIN: float | None = 60.0

# Override the fitted IAT mean (output/zwm92_summary.json::iat_within_shift_mean)
# at runtime. Used by src/sensitivity.py to sweep the arrival rate without
# regenerating the ZWM92 cache. None → use the cached fit value.
IAT_MEAN_MIN_OVERRIDE: float | None = None

# Order generation — used only when TRACE_DRIVEN is False.
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

# Timeline recorder (sim_v2.html playback feed) — opt-in via --record-timeline
# CLI flag in src.main, or by toggling RECORD_TIMELINE = True here. When False
# (default), no recorder is instantiated and the sim path has zero overhead.
# See src/recorder.py for the AD-2 schema.
RECORD_TIMELINE = False
TIMELINE_OUTPUT_DIR = "output"
TIMELINE_KPI_SNAPSHOT_INTERVAL_MIN = 10.0

# Data
DATA_FILE = "data/Malzeme Girişleri_010126-170326.xlsx"
DATA_DAYS = 76  # Jan 1 - Mar 17, 2026
