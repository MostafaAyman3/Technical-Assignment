"""Cross-area trip merging extension.

Merges under-filled trips from different areas when doing so is safe
and does not violate capacity or priority constraints. This module is
fully isolated — deleting it leaves the rest of the program correct.

Does NOT import from planner.packing.
"""

from planner.constants import MAX_AREAS_PER_MERGED_TRIP, VEHICLE_CAPACITY_G
from planner.models import Trip


def can_merge(trip_a: Trip, trip_b: Trip, capacity_g: int) -> bool:
    """Return True if two trips may be merged.

    All three conditions must hold:
      (a) combined weight fits within vehicle capacity
      (b) union of area keys has at most MAX_AREAS_PER_MERGED_TRIP areas
      (c) both trips share the same dispatch priority
    """
    if trip_a.total_weight_g + trip_b.total_weight_g > capacity_g:
        return False

    # Currently a structural invariant (core packing produces single-area
    # trips and we don't cascade), but kept as an explicit guard against
    # future changes to the merge algorithm.
    if len(trip_a.area_keys | trip_b.area_keys) > MAX_AREAS_PER_MERGED_TRIP:
        return False

    if trip_a.priority != trip_b.priority:
        return False

    return True


def _build_merged_trip(trip_a: Trip, trip_b: Trip) -> Trip:
    """Combine two trips into one, with deliveries in deterministic order."""
    merged_deliveries = sorted(
        trip_a.deliveries + trip_b.deliveries,
        key=lambda d: (d.priority, d.delivery_id),
    )
    return Trip(deliveries=merged_deliveries)


# Safety argument: merging two trips with equal trip_priority cannot delay
# any delivery. The merged trip inherits the smaller earliest_id of the two,
# so it takes the earlier of their two dispatch positions; deliveries of the
# later trip move forward, deliveries of the earlier trip stay put, and every
# trip after them moves one position earlier because the total count drops by
# one.
def merge_compatible_trips(
    trips: list[Trip],
    capacity_g: int = VEHICLE_CAPACITY_G,
) -> tuple[list[Trip], int]:
    """Merge under-filled trips from different areas in a single pass.

    Returns the new trip list and the number of merges performed.
    """
    if len(trips) <= 1:
        return list(trips), 0

    # Cascading is prevented by the single-pass algorithm and the consumed
    # set: once a trip participates in a merge (as either partner), it is
    # marked consumed and cannot be selected again in this pass.
    consumed: set[int] = set()
    result: list[Trip] = []
    merge_count = 0

    for i in range(len(trips)):
        if i in consumed:
            continue

        merged = trips[i]
        # Scan forward for the first compatible, unconsumed partner.
        for j in range(i + 1, len(trips)):
            if j in consumed:
                continue
            if can_merge(merged, trips[j], capacity_g):
                merged = _build_merged_trip(merged, trips[j])
                consumed.add(j)
                merge_count += 1
                break

        result.append(merged)

    result.sort(key=lambda t: (t.priority, t.earliest_id))
    return result, merge_count
