"""CSV loading, validation, and normalization of delivery data.

Reads a CSV file and returns validated Delivery objects plus a list of
rejected rows. Never prints — error reporting is the CLI layer's job.
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from planner.constants import (
    GRAMS_PER_KG,
    REASON_DUPLICATE_ID,
    REASON_EXCEEDS_CAPACITY,
    REASON_INVALID_PRIORITY,
    REASON_INVALID_WEIGHT,
    REASON_MALFORMED_ROW,
    UNKNOWN_AREA,
    VEHICLE_CAPACITY_G,
)
from planner.models import Delivery, RejectedDelivery

# Expected CSV column names, in order.
_EXPECTED_COLUMNS: list[str] = ["id", "area", "priority", "weight_kg"]


class InvalidInputFile(Exception):
    """Raised when the CSV file has missing or incorrect headers."""


def _parse_weight_g(raw_weight: str) -> int:
    """Convert a weight string in kg to an integer gram count.

    Uses Decimal to avoid float representation errors. Raises ValueError
    if the value is not a positive whole number of grams.
    """
    weight_decimal = Decimal(raw_weight.strip()) * GRAMS_PER_KG
    if weight_decimal != int(weight_decimal):
        raise ValueError(f"weight {raw_weight.strip()} kg is not a whole number of grams")
    weight_g = int(weight_decimal)
    if weight_g <= 0:
        raise ValueError(f"weight must be positive, got {raw_weight.strip()} kg")
    return weight_g


def _normalize_area(
    raw_area: str,
    area_display_map: dict[str, str],
) -> tuple[str, str]:
    """Normalize an area string and track the first-seen display name.

    Returns (area_key, area_display).
    """
    trimmed = raw_area.strip()
    if not trimmed:
        return UNKNOWN_AREA.lower(), UNKNOWN_AREA

    area_key = trimmed.lower()
    if area_key not in area_display_map:
        area_display_map[area_key] = trimmed
    return area_key, area_display_map[area_key]


def _validate_row(
    row: dict[str, str | None],
    seen_ids: set[int],
    area_display_map: dict[str, str],
) -> Delivery | RejectedDelivery:
    """Validate a single CSV row and return a Delivery or RejectedDelivery.

    Checks are applied in a fixed order; the first failure wins.
    """
    raw_row = {k: (v if v is not None else "") for k, v in row.items()}

    # 1. Missing or extra fields, or any required field is None.
    if None in row.values() or any(k not in row for k in _EXPECTED_COLUMNS):
        return RejectedDelivery(
            raw_row=raw_row,
            reason=REASON_MALFORMED_ROW,
            detail="row has missing or extra columns",
        )

    # 2. ID must be a positive integer.
    raw_id = row["id"]
    try:
        delivery_id = int(raw_id)  # type: ignore[arg-type]
        if delivery_id <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return RejectedDelivery(
            raw_row=raw_row,
            reason=REASON_MALFORMED_ROW,
            detail=f"id {raw_id!r} is not a positive integer",
        )

    # 3. Priority must be an integer >= 1.
    raw_priority = row["priority"]
    try:
        priority = int(raw_priority)  # type: ignore[arg-type]
        if priority < 1:
            raise ValueError
    except (ValueError, TypeError):
        return RejectedDelivery(
            raw_row=raw_row,
            reason=REASON_INVALID_PRIORITY,
            detail=f"priority {raw_priority!r} is not an integer >= 1",
        )

    # 4-5. Weight must be a positive Decimal and a whole number of grams.
    raw_weight = row["weight_kg"]
    try:
        weight_g = _parse_weight_g(raw_weight)  # type: ignore[arg-type]
    except (ValueError, InvalidOperation):
        return RejectedDelivery(
            raw_row=raw_row,
            reason=REASON_INVALID_WEIGHT,
            detail=f"weight {raw_weight!r} is not a valid positive weight in whole grams",
        )

    # 6. Weight must not exceed vehicle capacity.
    if weight_g > VEHICLE_CAPACITY_G:
        weight_kg_str = f"{weight_g / GRAMS_PER_KG:.2f}"
        cap_kg_str = f"{VEHICLE_CAPACITY_G / GRAMS_PER_KG:.0f}"
        return RejectedDelivery(
            raw_row=raw_row,
            reason=REASON_EXCEEDS_CAPACITY,
            detail=f"weight {weight_kg_str} kg exceeds the {cap_kg_str} kg vehicle capacity",
        )

    # 7. Duplicate ID — first occurrence wins.
    if delivery_id in seen_ids:
        return RejectedDelivery(
            raw_row=raw_row,
            reason=REASON_DUPLICATE_ID,
            detail=f"delivery id {delivery_id} already exists",
        )
    seen_ids.add(delivery_id)

    # All checks passed — normalize area and build Delivery.
    area_key, area_display = _normalize_area(
        row["area"], area_display_map  # type: ignore[arg-type]
    )

    return Delivery(
        delivery_id=delivery_id,
        area_key=area_key,
        area_display=area_display,
        priority=priority,
        weight_g=weight_g,
    )


def load_deliveries(
    path: Path,
) -> tuple[list[Delivery], list[RejectedDelivery]]:
    """Read and validate deliveries from a CSV file.

    Returns (accepted_deliveries, rejected_deliveries) in file order.
    Raises InvalidInputFile if headers are wrong. Lets OSError propagate
    for missing/unreadable files (the CLI layer handles those).
    """
    accepted: list[Delivery] = []
    rejected: list[RejectedDelivery] = []
    seen_ids: set[int] = set()
    area_display_map: dict[str, str] = {}

    # utf-8-sig strips a BOM if Excel produced the file.
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            return [], []

        actual_columns = [c.strip().lower() for c in reader.fieldnames]
        if actual_columns != _EXPECTED_COLUMNS:
            raise InvalidInputFile(
                f"Expected CSV columns {_EXPECTED_COLUMNS}, "
                f"got {list(reader.fieldnames)}"
            )

        for row in reader:
            result = _validate_row(row, seen_ids, area_display_map)
            if isinstance(result, Delivery):
                accepted.append(result)
            else:
                rejected.append(result)

    return accepted, rejected
