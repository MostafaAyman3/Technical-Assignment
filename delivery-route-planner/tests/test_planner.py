"""Tests for the planner.packing and planner.merging modules."""

import ast
import inspect
from pathlib import Path

import pytest

from planner.constants import (
    STRATEGY_BEST_FIT,
    STRATEGY_FIRST_FIT,
    VEHICLE_CAPACITY_G,
)
from planner.merging import can_merge, merge_compatible_trips
from planner.models import Delivery, RejectedDelivery, Trip
from planner.packing import build_trips


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _d(delivery_id: int, area: str, priority: int, weight_g: int) -> Delivery:
    """Shorthand to build a Delivery with consistent area normalization."""
    return Delivery(
        delivery_id=delivery_id,
        area_key=area.strip().lower(),
        area_display=area.strip(),
        priority=priority,
        weight_g=weight_g,
    )


def _ids(trip: Trip) -> list[int]:
    """Extract delivery IDs from a trip, in order."""
    return [d.delivery_id for d in trip.deliveries]


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    """An empty delivery list should produce zero trips."""

    def test_empty_list_returns_no_trips(self) -> None:
        assert build_trips([]) == []

    def test_empty_list_with_first_fit(self) -> None:
        assert build_trips([], strategy=STRATEGY_FIRST_FIT) == []


# ---------------------------------------------------------------------------
# Single area, fits in one trip
# ---------------------------------------------------------------------------

class TestSingleAreaOnTrip:
    """All deliveries fit in a single trip."""

    def test_two_deliveries_one_trip(self) -> None:
        deliveries = [_d(1, "Maadi", 1, 3000), _d(2, "Maadi", 2, 4000)]
        trips = build_trips(deliveries)
        assert len(trips) == 1
        assert _ids(trips[0]) == [1, 2]
        assert trips[0].total_weight_g == 7000


# ---------------------------------------------------------------------------
# Single area, capacity overflow -> multiple trips
# ---------------------------------------------------------------------------

class TestCapacityOverflow:
    """Adding a delivery that exceeds remaining capacity opens a new trip."""

    def test_overflow_creates_new_trip(self) -> None:
        deliveries = [
            _d(1, "Maadi", 1, 6000),
            _d(2, "Maadi", 2, 6000),
        ]
        trips = build_trips(deliveries)
        assert len(trips) == 2
        assert _ids(trips[0]) == [1]
        assert _ids(trips[1]) == [2]

    def test_no_trip_exceeds_capacity(self) -> None:
        """Every trip must respect the vehicle capacity."""
        deliveries = [
            _d(i, "Maadi", 1, 3000) for i in range(1, 8)
        ]
        trips = build_trips(deliveries)
        for trip in trips:
            assert trip.total_weight_g <= VEHICLE_CAPACITY_G


# ---------------------------------------------------------------------------
# First-Fit vs Best-Fit: different results on crafted input
# ---------------------------------------------------------------------------

class TestFirstFitVsBestFit:
    """The 6kg, 7kg, 3kg, 4kg example where strategies diverge.

    First-Fit:  [6,3]=9kg, [7]=7kg, [4]=4kg  -> 3 trips
    Best-Fit:   [6,4]=10kg, [7,3]=10kg        -> 2 trips
    """

    def _deliveries(self) -> list[Delivery]:
        return [
            _d(1, "A", 1, 6000),
            _d(2, "A", 2, 7000),
            _d(3, "A", 3, 3000),
            _d(4, "A", 4, 4000),
        ]

    def test_first_fit_trip_count(self) -> None:
        trips = build_trips(self._deliveries(), strategy=STRATEGY_FIRST_FIT)
        assert len(trips) == 3

    def test_first_fit_trip_contents(self) -> None:
        trips = build_trips(self._deliveries(), strategy=STRATEGY_FIRST_FIT)
        assert _ids(trips[0]) == [1, 3]
        assert _ids(trips[1]) == [2]
        assert _ids(trips[2]) == [4]

    def test_best_fit_trip_count(self) -> None:
        trips = build_trips(self._deliveries(), strategy=STRATEGY_BEST_FIT)
        assert len(trips) == 2

    def test_best_fit_trip_contents(self) -> None:
        trips = build_trips(self._deliveries(), strategy=STRATEGY_BEST_FIT)
        assert _ids(trips[0]) == [1, 4]
        assert _ids(trips[1]) == [2, 3]


# ---------------------------------------------------------------------------
# Multiple areas packed independently
# ---------------------------------------------------------------------------

class TestMultipleAreas:
    """Each area is packed independently; trips are then sorted by dispatch."""

    def test_two_areas_independent_packing(self) -> None:
        deliveries = [
            _d(1, "Maadi", 2, 6000),
            _d(2, "Zamalek", 1, 5000),
            _d(3, "Maadi", 3, 5000),
        ]
        trips = build_trips(deliveries)
        # 6kg + 5kg = 11kg > 10kg, so Maadi needs 2 trips
        # Dispatch order: Zamalek (P1, id2), Maadi (P2, id1), Maadi (P3, id3)
        assert len(trips) == 3
        assert _ids(trips[0]) == [2]
        assert _ids(trips[1]) == [1]
        assert _ids(trips[2]) == [3]


# ---------------------------------------------------------------------------
# Dispatch ordering: (priority ASC, earliest_id ASC)
# ---------------------------------------------------------------------------

class TestDispatchOrdering:
    """Trips must be sorted by (priority ASC, earliest_id ASC)."""

    def test_priority_ordering(self) -> None:
        deliveries = [
            _d(10, "A", 3, 1000),
            _d(20, "B", 1, 1000),
            _d(30, "C", 2, 1000),
        ]
        trips = build_trips(deliveries)
        priorities = [t.priority for t in trips]
        assert priorities == [1, 2, 3]

    def test_id_tiebreak_within_same_priority(self) -> None:
        deliveries = [
            _d(5, "A", 1, 1000),
            _d(2, "B", 1, 1000),
        ]
        trips = build_trips(deliveries)
        # Both are P1; trip with earliest_id=2 comes first
        assert trips[0].earliest_id == 2
        assert trips[1].earliest_id == 5


# ---------------------------------------------------------------------------
# Deterministic tie-breaking on equal priority within an area
# ---------------------------------------------------------------------------

class TestDeterministicTieBreaking:
    """When priorities collide, delivery_id ASC breaks the tie."""

    def test_same_priority_sorted_by_id(self) -> None:
        deliveries = [
            _d(5, "Maadi", 1, 2000),
            _d(2, "Maadi", 1, 3000),
            _d(8, "Maadi", 1, 4000),
        ]
        trips = build_trips(deliveries)
        # All fit in one trip (9000g), sorted by ID
        assert len(trips) == 1
        assert _ids(trips[0]) == [2, 5, 8]


# ---------------------------------------------------------------------------
# Custom capacity_g
# ---------------------------------------------------------------------------

class TestCustomCapacity:
    """The algorithm must respect the capacity_g parameter."""

    def test_smaller_capacity_produces_more_trips(self) -> None:
        deliveries = [
            _d(1, "Maadi", 1, 3000),
            _d(2, "Maadi", 2, 3000),
        ]
        # Default 10kg capacity: both fit in one trip
        trips_default = build_trips(deliveries)
        assert len(trips_default) == 1

        # Custom 5kg capacity: still fits (3+3 = 6 > 5), need two trips
        trips_small = build_trips(deliveries, capacity_g=5000)
        assert len(trips_small) == 2
        assert _ids(trips_small[0]) == [1]
        assert _ids(trips_small[1]) == [2]

    def test_custom_capacity_not_exceeded(self) -> None:
        custom_cap = 4000
        deliveries = [_d(i, "A", 1, 2500) for i in range(1, 5)]
        trips = build_trips(deliveries, capacity_g=custom_cap)
        for trip in trips:
            assert trip.total_weight_g <= custom_cap


# ---------------------------------------------------------------------------
# Unknown strategy
# ---------------------------------------------------------------------------

class TestUnknownStrategy:
    """An unrecognized strategy string must raise ValueError."""

    def test_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown packing strategy"):
            build_trips([], strategy="worst-fit")


# ---------------------------------------------------------------------------
# Every delivery appears exactly once
# ---------------------------------------------------------------------------

class TestAllDeliveriesPlaced:
    """Every input delivery must appear in exactly one trip."""

    def test_all_ids_present_once(self) -> None:
        deliveries = [
            _d(1, "A", 1, 6000),
            _d(2, "A", 2, 7000),
            _d(3, "B", 3, 3000),
            _d(4, "B", 4, 4000),
            _d(5, "C", 1, 9000),
        ]
        trips = build_trips(deliveries)
        placed_ids = [d.delivery_id for t in trips for d in t.deliveries]
        assert sorted(placed_ids) == [1, 2, 3, 4, 5]
        # No duplicates
        assert len(placed_ids) == len(set(placed_ids))


# ---------------------------------------------------------------------------
# Official sample data
# ---------------------------------------------------------------------------

class TestOfficialSample:
    """The 5-row sample from the assignment PDF."""

    def _sample(self) -> list[Delivery]:
        return [
            _d(1, "Nasr City", 2, 4500),
            _d(2, "Maadi", 1, 2000),
            _d(3, "Nasr City", 3, 1200),
            _d(4, "Zamalek", 1, 7000),
            _d(5, "Maadi", 2, 3500),
        ]

    def test_trip_count(self) -> None:
        trips = build_trips(self._sample())
        assert len(trips) == 3

    def test_dispatch_order(self) -> None:
        trips = build_trips(self._sample())
        # P1: Maadi (id2), Zamalek (id4); P2: Nasr City (id1)
        assert trips[0].area_displays == ["Maadi"]
        assert trips[0].priority == 1
        assert trips[1].area_displays == ["Zamalek"]
        assert trips[1].priority == 1
        assert trips[2].area_displays == ["Nasr City"]
        assert trips[2].priority == 2

    def test_all_deliveries_placed(self) -> None:
        trips = build_trips(self._sample())
        all_ids = sorted(d.delivery_id for t in trips for d in t.deliveries)
        assert all_ids == [1, 2, 3, 4, 5]


# ===========================================================================
# MERGING TESTS
# ===========================================================================

# ---------------------------------------------------------------------------
# can_merge predicate — each condition tested in isolation
# ---------------------------------------------------------------------------

class TestCanMerge:
    """Unit tests for the can_merge predicate."""

    def test_mergeable_trips(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 2000)])
        b = Trip([_d(2, "Zamalek", 1, 4000)])
        assert can_merge(a, b, VEHICLE_CAPACITY_G) is True

    def test_blocked_by_capacity(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 6000)])
        b = Trip([_d(2, "Zamalek", 1, 5000)])
        assert can_merge(a, b, VEHICLE_CAPACITY_G) is False

    def test_blocked_by_different_priority(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 2000)])
        b = Trip([_d(2, "Zamalek", 2, 2000)])
        assert can_merge(a, b, VEHICLE_CAPACITY_G) is False

    def test_blocked_by_too_many_areas(self) -> None:
        """Artificially constructed: trip already spanning 2 areas."""
        a = Trip([
            _d(1, "Maadi", 1, 1000),
            _d(2, "Zamalek", 1, 1000),
        ])
        b = Trip([_d(3, "Heliopolis", 1, 1000)])
        # a has 2 area keys, b has 1 different key -> union = 3 > 2
        assert can_merge(a, b, VEHICLE_CAPACITY_G) is False

    def test_same_area_mergeable(self) -> None:
        """Two trips from the same area can merge (union = 1 area)."""
        a = Trip([_d(1, "Maadi", 1, 3000)])
        b = Trip([_d(2, "Maadi", 1, 3000)])
        assert can_merge(a, b, VEHICLE_CAPACITY_G) is True

    def test_exact_capacity_is_allowed(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 5000)])
        b = Trip([_d(2, "Zamalek", 1, 5000)])
        assert can_merge(a, b, VEHICLE_CAPACITY_G) is True

    def test_custom_capacity_respected(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 3000)])
        b = Trip([_d(2, "Zamalek", 1, 3000)])
        assert can_merge(a, b, capacity_g=5000) is False
        assert can_merge(a, b, capacity_g=6000) is True


# ---------------------------------------------------------------------------
# merge_compatible_trips — full algorithm
# ---------------------------------------------------------------------------

class TestMergeCompatibleTrips:
    """Tests for the merge pass algorithm."""

    def test_empty_input(self) -> None:
        trips, count = merge_compatible_trips([])
        assert trips == []
        assert count == 0

    def test_single_trip_unchanged(self) -> None:
        t = Trip([_d(1, "Maadi", 1, 5000)])
        trips, count = merge_compatible_trips([t])
        assert len(trips) == 1
        assert count == 0

    def test_successful_merge(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 2000)])
        b = Trip([_d(2, "Zamalek", 1, 4000)])
        trips, count = merge_compatible_trips([a, b])
        assert len(trips) == 1
        assert count == 1
        assert _ids(trips[0]) == [1, 2]
        assert trips[0].total_weight_g == 6000

    def test_merge_blocked_by_priority(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 2000)])
        b = Trip([_d(2, "Zamalek", 2, 2000)])
        trips, count = merge_compatible_trips([a, b])
        assert len(trips) == 2
        assert count == 0

    def test_merge_blocked_by_capacity(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 6000)])
        b = Trip([_d(2, "Zamalek", 1, 5000)])
        trips, count = merge_compatible_trips([a, b])
        assert len(trips) == 2
        assert count == 0

    def test_no_cascading(self) -> None:
        """A merged trip must not participate in further merges."""
        a = Trip([_d(1, "Maadi", 1, 2000)])
        b = Trip([_d(2, "Zamalek", 1, 2000)])
        c = Trip([_d(3, "Heliopolis", 1, 2000)])
        trips, count = merge_compatible_trips([a, b, c])
        # a+b merge (6kg, 2 areas). c could fit by weight but a+b is
        # consumed. c stays alone. Only 1 merge, not 2.
        assert count == 1
        assert len(trips) == 2

    def test_merge_count_matches(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 2000)])
        b = Trip([_d(2, "Zamalek", 1, 4000)])
        c = Trip([_d(3, "Nasr City", 1, 3000)])
        d = Trip([_d(4, "Heliopolis", 1, 3000)])
        trips, count = merge_compatible_trips([a, b, c, d])
        # a+b = 6kg, c+d = 6kg -> 2 merges
        assert count == 2
        assert len(trips) == 2

    def test_dispatch_order_after_merge(self) -> None:
        a = Trip([_d(1, "Maadi", 1, 2000)])
        b = Trip([_d(3, "Zamalek", 2, 2000)])
        c = Trip([_d(2, "Heliopolis", 1, 2000)])
        # a and c have same priority (1), a.earliest_id=1, c.earliest_id=2
        trips, count = merge_compatible_trips([a, b, c])
        # a+c merge -> P1, earliest_id=1; b stays -> P2
        assert count == 1
        assert trips[0].priority == 1
        assert trips[1].priority == 2


# ---------------------------------------------------------------------------
# Merge safety: completeness + no delivery delayed
# ---------------------------------------------------------------------------

class TestMergeSafety:
    """Verify that merging preserves all deliveries and never delays any."""

    def test_all_deliveries_preserved(self) -> None:
        """Every delivery ID present before merge must be present after."""
        trips_before = [
            Trip([_d(1, "Maadi", 1, 2000)]),
            Trip([_d(2, "Zamalek", 1, 4000)]),
            Trip([_d(3, "Nasr City", 2, 3000)]),
        ]
        ids_before = {d.delivery_id for t in trips_before for d in t.deliveries}
        trips_after, _ = merge_compatible_trips(trips_before)
        ids_after = {d.delivery_id for t in trips_after for d in t.deliveries}
        assert ids_before == ids_after

    def test_no_delivery_dispatched_later(self) -> None:
        """An equal-priority merge must never move a delivery to a later
        dispatch position."""
        trips_before = [
            Trip([_d(1, "Maadi", 1, 2000)]),       # position 0
            Trip([_d(2, "Zamalek", 1, 4000)]),      # position 1
            Trip([_d(3, "Nasr City", 2, 3000)]),     # position 2
            Trip([_d(4, "Heliopolis", 2, 3000)]),    # position 3
        ]

        # Record each delivery's dispatch position before merge.
        pos_before: dict[int, int] = {}
        for pos, trip in enumerate(trips_before):
            for delivery in trip.deliveries:
                pos_before[delivery.delivery_id] = pos

        trips_after, _ = merge_compatible_trips(trips_before)

        # Record each delivery's dispatch position after merge.
        pos_after: dict[int, int] = {}
        for pos, trip in enumerate(trips_after):
            for delivery in trip.deliveries:
                pos_after[delivery.delivery_id] = pos

        # Every delivery must be at the same or an earlier position.
        for did, old_pos in pos_before.items():
            new_pos = pos_after[did]
            assert new_pos <= old_pos, (
                f"Delivery {did} moved from position {old_pos} to {new_pos}"
            )


# ---------------------------------------------------------------------------
# Module isolation: merging must not import from packing
# ---------------------------------------------------------------------------

class TestMergeModuleIsolation:
    """Verify that planner.merging does not depend on planner.packing."""

    def test_no_import_from_packing(self) -> None:
        source = inspect.getsource(merge_compatible_trips)
        module_source = inspect.getmodule(merge_compatible_trips)
        assert module_source is not None
        full_source = inspect.getsource(module_source)
        tree = ast.parse(full_source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or "packing" not in node.module, (
                    "merging.py must not import from packing"
                )


# ===========================================================================
# REPORTING TESTS
# ===========================================================================

from planner.reporting import format_report


class TestFormatReportOfficialSample:
    """Snapshot test against the official 5-row sample."""

    def _trips(self) -> list[Trip]:
        return [
            Trip([_d(2, "Maadi", 1, 2000), _d(5, "Maadi", 2, 3500)]),
            Trip([_d(4, "Zamalek", 1, 7000)]),
            Trip([_d(1, "Nasr City", 2, 4500), _d(3, "Nasr City", 3, 1200)]),
        ]

    def test_header_present(self) -> None:
        report = format_report(self._trips(), [], 5, 0)
        assert report.startswith("Delivery Route Plan\n===================")

    def test_trip_count_in_output(self) -> None:
        report = format_report(self._trips(), [], 5, 0)
        assert "Trip 1" in report
        assert "Trip 2" in report
        assert "Trip 3" in report
        assert "Trip 4" not in report

    def test_weight_formatting(self) -> None:
        report = format_report(self._trips(), [], 5, 0)
        assert "5.50 / 10.00 kg (55.0%)" in report
        assert "7.00 / 10.00 kg (70.0%)" in report

    def test_delivery_listing(self) -> None:
        report = format_report(self._trips(), [], 5, 0)
        assert "#2 (P1, 2.00kg), #5 (P2, 3.50kg)" in report

    def test_summary_values(self) -> None:
        report = format_report(self._trips(), [], 5, 0)
        assert "Input rows:          5" in report
        assert "Valid deliveries:    5" in report
        assert "Rejected:            0" in report
        assert "Trips:               3" in report
        assert "Total load:          18.20 kg" in report
        assert "Average utilization: 60.7%" in report

    def test_no_rejected_section(self) -> None:
        report = format_report(self._trips(), [], 5, 0)
        assert "(none)" in report


class TestFormatReportEmptyInput:
    """Zero trips should show 'No trips planned.' and 'n/a' utilization."""

    def test_no_trips_message(self) -> None:
        report = format_report([], [], 0, 0)
        assert "No trips planned." in report

    def test_utilization_na(self) -> None:
        report = format_report([], [], 0, 0)
        assert "Average utilization: n/a" in report

    def test_zero_totals(self) -> None:
        report = format_report([], [], 0, 0)
        assert "Trips:               0" in report
        assert "Total load:          0.00 kg" in report


class TestFormatReportWithRejections:
    """Rejected deliveries should appear with reason and detail."""

    def test_rejected_entries_shown(self) -> None:
        rejected = [
            RejectedDelivery(
                raw_row={"id": "2", "area": "Maadi", "priority": "1", "weight_kg": "12.0"},
                reason="EXCEEDS_CAPACITY",
                detail="weight 12.00 kg exceeds the 10 kg vehicle capacity",
            ),
        ]
        report = format_report([], rejected, 1, 0)
        assert "#2  EXCEEDS_CAPACITY" in report
        assert "weight 12.00 kg exceeds the 10 kg vehicle capacity" in report
        assert "(none)" not in report


class TestFormatReportMergedTrip:
    """A merged trip should show multiple areas joined with ' + '."""

    def test_merged_areas_display(self) -> None:
        trip = Trip([
            _d(1, "Maadi", 1, 2000),
            _d(2, "Zamalek", 1, 4000),
        ])
        report = format_report([trip], [], 2, 1)
        assert "Maadi + Zamalek" in report
        assert "Merges applied:      1" in report


# ===========================================================================
# LOADER TESTS
# ===========================================================================

from planner.loader import InvalidInputFile, load_deliveries


def _write_csv(tmp_path: Path, content: str) -> Path:
    """Write CSV content to a temp file and return its path."""
    p = tmp_path / "test.csv"
    p.write_text(content, encoding="utf-8")
    return p


class TestLoaderHappyPath:
    """Valid CSV rows produce correct Delivery objects in file order."""

    def test_official_sample(self, tmp_path: Path) -> None:
        csv = (
            "id,area,priority,weight_kg\n"
            "1,Nasr City,2,4.5\n"
            "2,Maadi,1,2.0\n"
        )
        accepted, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert len(accepted) == 2
        assert len(rejected) == 0
        assert accepted[0].delivery_id == 1
        assert accepted[0].weight_g == 4500
        assert accepted[1].delivery_id == 2
        assert accepted[1].weight_g == 2000

    def test_file_order_preserved(self, tmp_path: Path) -> None:
        csv = (
            "id,area,priority,weight_kg\n"
            "5,A,1,1.0\n"
            "3,A,1,1.0\n"
            "7,A,1,1.0\n"
        )
        accepted, _ = load_deliveries(_write_csv(tmp_path, csv))
        assert [d.delivery_id for d in accepted] == [5, 3, 7]


class TestLoaderEmptyFile:
    """Empty files (header only or completely empty) return empty lists."""

    def test_header_only(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n"
        accepted, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert accepted == []
        assert rejected == []

    def test_completely_empty(self, tmp_path: Path) -> None:
        accepted, rejected = load_deliveries(_write_csv(tmp_path, ""))
        assert accepted == []
        assert rejected == []


class TestLoaderRejectionReasons:
    """Each validation rule produces the correct rejection reason."""

    def test_malformed_row_missing_column(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,2\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert len(rejected) == 1
        assert rejected[0].reason == "MALFORMED_ROW"

    def test_malformed_row_bad_id(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\nabc,Maadi,1,2.0\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert len(rejected) == 1
        assert rejected[0].reason == "MALFORMED_ROW"

    def test_malformed_row_negative_id(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n-1,Maadi,1,2.0\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "MALFORMED_ROW"

    def test_invalid_priority(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,abc,2.0\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "INVALID_PRIORITY"

    def test_invalid_priority_zero(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,0,2.0\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "INVALID_PRIORITY"

    def test_invalid_weight_zero(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,1,0\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "INVALID_WEIGHT"

    def test_invalid_weight_negative(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,1,-3.0\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "INVALID_WEIGHT"

    def test_invalid_weight_not_whole_grams(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,1,2.0015\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "INVALID_WEIGHT"

    def test_exceeds_capacity(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,1,12.0\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "EXCEEDS_CAPACITY"

    def test_exact_capacity_accepted(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,Maadi,1,10.0\n"
        accepted, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert len(accepted) == 1
        assert len(rejected) == 0
        assert accepted[0].weight_g == 10000

    def test_duplicate_id_first_wins(self, tmp_path: Path) -> None:
        csv = (
            "id,area,priority,weight_kg\n"
            "1,Nasr City,2,4.5\n"
            "1,Maadi,1,3.0\n"
        )
        accepted, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert len(accepted) == 1
        assert accepted[0].area_display == "Nasr City"
        assert len(rejected) == 1
        assert rejected[0].reason == "DUPLICATE_ID"


class TestLoaderAreaNormalization:
    """Area key and display name handling."""

    def test_trimming_and_lowercasing(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1, Maadi ,1,2.0\n"
        accepted, _ = load_deliveries(_write_csv(tmp_path, csv))
        assert accepted[0].area_key == "maadi"
        assert accepted[0].area_display == "Maadi"

    def test_first_spelling_is_display(self, tmp_path: Path) -> None:
        csv = (
            "id,area,priority,weight_kg\n"
            "1, maadi ,1,2.0\n"
            "2,MAADI,1,3.0\n"
        )
        accepted, _ = load_deliveries(_write_csv(tmp_path, csv))
        # Both share key "maadi"; display is first seen = "maadi" (trimmed)
        assert accepted[0].area_display == "maadi"
        assert accepted[1].area_display == "maadi"

    def test_empty_area_becomes_unknown(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,,1,2.0\n"
        accepted, _ = load_deliveries(_write_csv(tmp_path, csv))
        assert accepted[0].area_key == "unknown"
        assert accepted[0].area_display == "UNKNOWN"


class TestLoaderWeightDecimal:
    """Weight parsing uses Decimal, never float."""

    def test_whole_kg(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,A,1,3.0\n"
        accepted, _ = load_deliveries(_write_csv(tmp_path, csv))
        assert accepted[0].weight_g == 3000

    def test_fractional_kg_whole_grams(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,A,1,1.234\n"
        accepted, _ = load_deliveries(_write_csv(tmp_path, csv))
        assert accepted[0].weight_g == 1234

    def test_non_whole_grams_rejected(self, tmp_path: Path) -> None:
        csv = "id,area,priority,weight_kg\n1,A,1,1.2345\n"
        _, rejected = load_deliveries(_write_csv(tmp_path, csv))
        assert rejected[0].reason == "INVALID_WEIGHT"


class TestLoaderBadHeaders:
    """Wrong or missing headers should raise InvalidInputFile."""

    def test_wrong_columns(self, tmp_path: Path) -> None:
        csv = "name,location,urgency,mass\n1,A,1,2.0\n"
        with pytest.raises(InvalidInputFile):
            load_deliveries(_write_csv(tmp_path, csv))


class TestLoaderEdgeCasesFile:
    """Integration test against data/sample_edge_cases.csv."""

    def test_five_accepted_five_rejected(self) -> None:
        accepted, rejected = load_deliveries(
            Path("data/sample_edge_cases.csv")
        )
        assert len(accepted) == 5
        assert len(rejected) == 5

    def test_rejection_reasons_match(self) -> None:
        _, rejected = load_deliveries(
            Path("data/sample_edge_cases.csv")
        )
        reasons = [r.reason for r in rejected]
        assert reasons == [
            "DUPLICATE_ID",
            "EXCEEDS_CAPACITY",
            "INVALID_WEIGHT",
            "INVALID_PRIORITY",
            "MALFORMED_ROW",
        ]
