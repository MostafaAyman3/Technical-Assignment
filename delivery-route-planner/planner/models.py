"""Domain data models: Delivery, RejectedDelivery, and Trip.

All models are dataclasses. Delivery and RejectedDelivery are frozen
(immutable). Trip is mutable because the packing module appends
deliveries to it.
"""

from dataclasses import dataclass, field

from planner.constants import VEHICLE_CAPACITY_G


@dataclass(frozen=True)
class Delivery:
    """A single validated delivery request, ready for packing."""

    delivery_id: int
    area_key: str       # normalized: trimmed + lowercased, used for grouping
    area_display: str   # first spelling seen in the file, used for output
    priority: int
    weight_g: int


@dataclass(frozen=True)
class RejectedDelivery:
    """A delivery row that failed validation."""

    raw_row: dict[str, str]   # the CSV row as read, preserved for reporting
    reason: str               # one of the REASON_* constants
    detail: str               # human-readable explanation of why it was rejected


@dataclass
class Trip:
    """A group of deliveries assigned to a single vehicle dispatch.

    All derived values are computed on access from the deliveries list,
    so they never drift out of sync. This class contains no packing
    logic — capacity enforcement lives in the packing module.
    """

    deliveries: list[Delivery] = field(default_factory=list)

    @property
    def total_weight_g(self) -> int:
        """Sum of all delivery weights in grams."""
        return sum(d.weight_g for d in self.deliveries)

    def remaining_g(self, capacity_g: int = VEHICLE_CAPACITY_G) -> int:
        """Remaining capacity in grams, against the given vehicle capacity."""
        return capacity_g - self.total_weight_g

    @property
    def priority(self) -> int:
        """Trip dispatch priority: the most urgent delivery it carries."""
        return min(d.priority for d in self.deliveries)

    @property
    def area_keys(self) -> frozenset[str]:
        """Distinct normalized area keys in this trip."""
        return frozenset(d.area_key for d in self.deliveries)

    @property
    def area_displays(self) -> list[str]:
        """Display names of areas in this trip, in first-seen order."""
        seen: dict[str, str] = {}
        for delivery in self.deliveries:
            if delivery.area_key not in seen:
                seen[delivery.area_key] = delivery.area_display
        return list(seen.values())

    @property
    def earliest_id(self) -> int:
        """Smallest delivery ID in this trip, used for dispatch tie-breaking."""
        return min(d.delivery_id for d in self.deliveries)

    def utilization(self, capacity_g: int = VEHICLE_CAPACITY_G) -> float:
        """Fraction of the given vehicle capacity used (0.0 to 1.0)."""
        return self.total_weight_g / capacity_g
