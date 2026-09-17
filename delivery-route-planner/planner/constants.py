"""Named constants for the Delivery Route Planner.

Every constant documents whether it originates from the assignment
specification or is our own design decision.
"""

# --- Vehicle constraints ---

# From spec: "A vehicle can carry a maximum of 10 kg per trip."
VEHICLE_CAPACITY_G: int = 10_000

# Conversion factor, standard definition.
GRAMS_PER_KG: int = 1_000

# --- Area handling ---

# Our decision: deliveries with an empty area field are assigned this label
# rather than being rejected, since the spec does not list empty area as
# an error condition.
UNKNOWN_AREA: str = "UNKNOWN"

# Our decision: the merge extension may combine trips from at most this many
# distinct areas. Keeps merged trips geographically reasonable.
MAX_AREAS_PER_MERGED_TRIP: int = 2

# --- Rejection reason codes ---

# From spec: "A package is heavier than the vehicle's 10 kg capacity."
REASON_EXCEEDS_CAPACITY: str = "EXCEEDS_CAPACITY"

# Our decision: weight must be a positive whole number of grams.
REASON_INVALID_WEIGHT: str = "INVALID_WEIGHT"

# Our decision: first occurrence wins, duplicates are rejected.
REASON_DUPLICATE_ID: str = "DUPLICATE_ID"

# Our decision: priority must be an integer >= 1.
REASON_INVALID_PRIORITY: str = "INVALID_PRIORITY"

# Our decision: row has missing/extra columns or a non-positive-integer ID.
REASON_MALFORMED_ROW: str = "MALFORMED_ROW"

# --- Packing strategies ---

# Our decision: two strategies available via CLI flag.
STRATEGY_BEST_FIT: str = "best-fit"
STRATEGY_FIRST_FIT: str = "first-fit"

# Our decision: best-fit is the default because it produced tighter packing on
# the included comparison case. It remains a heuristic and is not guaranteed
# to be optimal.
DEFAULT_STRATEGY: str = STRATEGY_BEST_FIT
