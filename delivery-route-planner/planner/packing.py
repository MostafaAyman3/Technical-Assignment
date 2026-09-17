"""Core packing algorithm: group deliveries by area and pack into trips.

Does NOT handle cross-area merging — that lives in planner.merging.
"""

from planner.constants import (
    DEFAULT_STRATEGY,
    STRATEGY_BEST_FIT,
    STRATEGY_FIRST_FIT,
    VEHICLE_CAPACITY_G,
)
from planner.models import Delivery, Trip


# ---------------------------------------------------------------------------
# Step 1: Group by area
# ---------------------------------------------------------------------------

def group_by_area(
    deliveries: list[Delivery],
) -> dict[str, list[Delivery]]:
    """Group deliveries by their normalized area key.

    Returns a plain dict whose iteration order matches first appearance
    in the input list — Python dicts preserve insertion order.
    """
    groups: dict[str, list[Delivery]] = {}
    for delivery in deliveries:
        groups.setdefault(delivery.area_key, []).append(delivery)
    return groups


# ---------------------------------------------------------------------------
# Step 2: Sort within each area for packing
# ---------------------------------------------------------------------------

def sort_for_packing(area_deliveries: list[Delivery]) -> list[Delivery]:
    """Sort deliveries by (priority ASC, delivery_id ASC).

    The ID tie-break makes the result deterministic when priorities
    collide, which is a stated requirement.
    """
    return sorted(area_deliveries, key=lambda d: (d.priority, d.delivery_id))


# ---------------------------------------------------------------------------
# Step 3: Trip selection strategies (identical signatures)
# ---------------------------------------------------------------------------

def select_trip_first_fit(
    open_trips: list[Trip],
    delivery: Delivery,
    capacity_g: int,
) -> Trip | None:
    """Return the first open trip that can fit this delivery, or None."""
    for trip in open_trips:
        if trip.total_weight_g + delivery.weight_g <= capacity_g:
            return trip
    return None


def select_trip_best_fit(
    open_trips: list[Trip],
    delivery: Delivery,
    capacity_g: int,
) -> Trip | None:
    """Return the open trip that will have the least remaining capacity.

    Among ties, the earliest trip in list order wins — this keeps the
    result deterministic and mirrors first-fit's preference for older trips.
    """
    best: Trip | None = None
    best_remaining: int = capacity_g + 1  # worse than any valid remaining

    for trip in open_trips:
        remaining_after = trip.total_weight_g + delivery.weight_g
        if remaining_after > capacity_g:
            continue
        remaining = capacity_g - remaining_after
        if remaining < best_remaining:
            best = trip
            best_remaining = remaining

    return best


# ---------------------------------------------------------------------------
# Step 4: Strategy dispatcher
# ---------------------------------------------------------------------------

# Type alias for the select function signature.
SelectFn = type(select_trip_first_fit)

_STRATEGIES: dict[str, SelectFn] = {
    STRATEGY_FIRST_FIT: select_trip_first_fit,
    STRATEGY_BEST_FIT: select_trip_best_fit,
}


def _get_select_fn(strategy: str) -> SelectFn:
    """Map a strategy name to its select function.

    Raises ValueError if the strategy is not recognized.
    """
    select_fn = _STRATEGIES.get(strategy)
    if select_fn is None:
        valid = ", ".join(sorted(_STRATEGIES))
        raise ValueError(
            f"Unknown packing strategy {strategy!r}. "
            f"Valid strategies: {valid}"
        )
    return select_fn


# ---------------------------------------------------------------------------
# Step 5: Pack one area
# ---------------------------------------------------------------------------

# Back-filling safety invariant: deliveries are processed in priority order
# (most urgent first). A delivery placed into an existing trip is therefore
# equal- or less-urgent than everything already in that trip. Back-filling
# can advance a non-urgent delivery but can never delay an urgent one.
def pack_area(
    sorted_deliveries: list[Delivery],
    select_fn: SelectFn,
    capacity_g: int,
) -> list[Trip]:
    """Pack a single area's deliveries into trips using the given strategy.

    Only deliveries from ONE area should be passed in — cross-area
    placement is structurally impossible at this level.
    """
    open_trips: list[Trip] = []

    for delivery in sorted_deliveries:
        trip = select_fn(open_trips, delivery, capacity_g)
        if trip is None:
            trip = Trip()
            open_trips.append(trip)
        trip.deliveries.append(delivery)

    return open_trips


# ---------------------------------------------------------------------------
# Step 6: Public entry point
# ---------------------------------------------------------------------------

def build_trips(
    deliveries: list[Delivery],
    strategy: str = DEFAULT_STRATEGY,
    capacity_g: int = VEHICLE_CAPACITY_G,
) -> list[Trip]:
    """Organize deliveries into capacity-respecting trips.

    Each area is packed independently, then all trips are sorted
    by dispatch order: (priority ASC, earliest_id ASC).
    """
    select_fn = _get_select_fn(strategy)
    area_groups = group_by_area(deliveries)

    all_trips: list[Trip] = []
    for area_deliveries in area_groups.values():
        sorted_deliveries = sort_for_packing(area_deliveries)
        area_trips = pack_area(sorted_deliveries, select_fn, capacity_g)
        all_trips.extend(area_trips)

    all_trips.sort(key=lambda t: (t.priority, t.earliest_id))
    return all_trips
