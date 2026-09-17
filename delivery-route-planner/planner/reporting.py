"""Output formatting for the Delivery Route Planner.

Pure functions that return strings. This module never prints or
performs I/O — that responsibility belongs to cli.py.
"""

from planner.constants import GRAMS_PER_KG, VEHICLE_CAPACITY_G
from planner.models import Delivery, RejectedDelivery, Trip

# Format widths for consistent column alignment.
_TRIP_LABEL_WIDTH: int = 12     # accommodates "Deliveries:" (longest trip label)
_SUMMARY_LABEL_WIDTH: int = 21  # accommodates "Average utilization:" (longest)


def _format_weight_kg(weight_g: int) -> str:
    """Convert integer grams to a kg string with 2 decimal places."""
    return f"{weight_g / GRAMS_PER_KG:.2f}"


def _format_delivery(delivery: Delivery) -> str:
    """Format one delivery for the trip detail line."""
    weight = _format_weight_kg(delivery.weight_g)
    return f"#{delivery.delivery_id} (P{delivery.priority}, {weight}kg)"


def _format_trip_section(trip: Trip, trip_number: int) -> str:
    """Format one trip as a multi-line block."""
    areas = " + ".join(trip.area_displays)
    load = (
        f"{_format_weight_kg(trip.total_weight_g)} / "
        f"{_format_weight_kg(VEHICLE_CAPACITY_G)} kg "
        f"({trip.utilization() * 100:.1f}%)"
    )
    # Display deliveries in (priority ASC, id ASC) order.
    sorted_deliveries = sorted(
        trip.deliveries, key=lambda d: (d.priority, d.delivery_id)
    )
    deliveries = ", ".join(_format_delivery(d) for d in sorted_deliveries)

    w = _TRIP_LABEL_WIDTH
    lines = [
        f"Trip {trip_number}",
        f"  {'Areas:':<{w}}{areas}",
        f"  {'Priority:':<{w}}{trip.priority}",
        f"  {'Load:':<{w}}{load}",
        f"  {'Deliveries:':<{w}}{deliveries}",
    ]
    return "\n".join(lines)


def _format_rejected_section(rejected: list[RejectedDelivery]) -> str:
    """Format the rejected deliveries section."""
    lines = ["Rejected Deliveries", "-------------------"]
    if not rejected:
        lines.append("  (none)")
    else:
        for r in rejected:
            raw_id = r.raw_row.get("id", "?")
            lines.append(f"  #{raw_id}  {r.reason}  {r.detail}")
    return "\n".join(lines)


def _format_summary(
    trips: list[Trip],
    rejected: list[RejectedDelivery],
    input_row_count: int,
    merges_applied: int,
) -> str:
    """Format the statistics summary section."""
    valid_count = sum(len(t.deliveries) for t in trips)
    total_load_g = sum(t.total_weight_g for t in trips)

    if trips:
        avg_util = sum(t.utilization() for t in trips) / len(trips)
        avg_util_str = f"{avg_util * 100:.1f}%"
    else:
        avg_util_str = "n/a"

    w = _SUMMARY_LABEL_WIDTH
    lines = [
        "Summary",
        "-------",
        f"{'Input rows:':<{w}}{input_row_count}",
        f"{'Valid deliveries:':<{w}}{valid_count}",
        f"{'Rejected:':<{w}}{len(rejected)}",
        f"{'Trips:':<{w}}{len(trips)}",
        f"{'Merges applied:':<{w}}{merges_applied}",
        f"{'Total load:':<{w}}{_format_weight_kg(total_load_g)} kg",
        f"{'Average utilization:':<{w}}{avg_util_str}",
    ]
    return "\n".join(lines)


def format_report(
    trips: list[Trip],
    rejected: list[RejectedDelivery],
    input_row_count: int,
    merges_applied: int,
) -> str:
    """Format the complete delivery route plan report.

    Returns a single deterministic string. Never prints or performs I/O.
    """
    sections: list[str] = []

    sections.append("Delivery Route Plan")
    sections.append("===================")

    if trips:
        for i, trip in enumerate(trips, start=1):
            sections.append("")
            sections.append(_format_trip_section(trip, i))
    else:
        sections.append("")
        sections.append("No trips planned.")

    sections.append("")
    sections.append(_format_rejected_section(rejected))

    sections.append("")
    sections.append(_format_summary(trips, rejected, input_row_count, merges_applied))

    return "\n".join(sections)
