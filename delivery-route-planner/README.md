# Delivery Route Planner

A command-line tool that organizes delivery requests into vehicle trips.
It reads a CSV file, validates each row, packs deliveries into
capacity-respecting trips grouped by area, and optionally merges
under-filled trips across areas.

## Requirements

- **Python 3.10+** (uses `match`-free syntax, but requires `X | Y` union types)
- **No runtime dependencies** — standard library only
- **pytest** — required only for running the test suite (`pip install pytest`)

## Input Format

The program reads a CSV file with these columns:

| Column      | Type    | Description                              |
|-------------|---------|------------------------------------------|
| `id`        | integer | Unique delivery identifier (positive)    |
| `area`      | string  | Delivery destination area                |
| `priority`  | integer | Urgency level (1 = most urgent)          |
| `weight_kg` | decimal | Package weight in kilograms              |

Example:

```csv
id,area,priority,weight_kg
1,Nasr City,2,4.5
2,Maadi,1,2.0
3,Nasr City,3,1.2
4,Zamalek,1,7.0
5,Maadi,2,3.5
```

### Sample Data Files

Five sample files are provided in `data/`:

| File                       | Purpose                                                  |
|----------------------------|----------------------------------------------------------|
| `sample_deliveries.csv`    | The assignment's 5-row example (3 areas, 5 deliveries)   |
| `sample_strategy_demo.csv` | Crafted input where Best-Fit and First-Fit diverge       |
| `sample_merge_demo.csv`    | Five single-area trips, two pairs merge on equal priority |
| `sample_edge_cases.csv`    | Hits every rejection reason (5 accepted, 5 rejected)     |
| `sample_empty.csv`         | Header row only — zero deliveries                        |

## How to Run

```bash
python main.py data/sample_deliveries.csv
```

Output:

```
Delivery Route Plan
===================

Trip 1
  Areas:      Maadi
  Priority:   1
  Load:       5.50 / 10.00 kg (55.0%)
  Deliveries: #2 (P1, 2.00kg), #5 (P2, 3.50kg)

Trip 2
  Areas:      Zamalek
  Priority:   1
  Load:       7.00 / 10.00 kg (70.0%)
  Deliveries: #4 (P1, 7.00kg)

Trip 3
  Areas:      Nasr City
  Priority:   2
  Load:       5.70 / 10.00 kg (57.0%)
  Deliveries: #1 (P2, 4.50kg), #3 (P3, 1.20kg)

Rejected Deliveries
-------------------
  (none)

Summary
-------
Input rows:          5
Valid deliveries:    5
Rejected:            0
Trips:               3
Merges applied:      0
Total load:          18.20 kg
Average utilization: 60.7%
```

### CLI Flags

| Flag                          | Effect                                       |
|-------------------------------|----------------------------------------------|
| `--strategy first-fit`        | Use First-Fit instead of Best-Fit (default)  |
| `--no-merge`                  | Disable the cross-area merge extension       |

```bash
# First-Fit packing, no merge
python main.py data/sample_strategy_demo.csv --strategy first-fit --no-merge

# Default Best-Fit packing, merge disabled
python main.py data/sample_merge_demo.csv --no-merge
```

## How to Run the Tests

```bash
pip install pytest
python -m pytest tests/test_planner.py -v
```

89 tests cover loading, validation, packing, merging, reporting, and
end-to-end integration across all sample files.

---

## Approach (Q1)

The program processes deliveries in six stages:

1. **Load & validate** — read the CSV, reject malformed or invalid rows
   (bad IDs, non-positive weights, over-capacity packages, duplicate IDs),
   and collect both accepted deliveries and rejected rows with reasons.
2. **Normalize areas** — trim whitespace, lowercase for grouping key,
   preserve the first-seen spelling as the display name. Empty areas
   become `UNKNOWN`.
3. **Group by area** — partition deliveries by area key, preserving
   file/insertion order.
4. **Sort within each area** — sort by `(priority ASC, delivery_id ASC)`.
   The ID tie-break ensures deterministic output when priorities collide.
5. **Greedy pack per area** — walk the sorted list and place each delivery
   into an existing trip (selected by Best-Fit or First-Fit) or open a
   new trip if none has enough remaining capacity.
6. **Dispatch ordering** — sort all trips by `(trip_priority ASC,
   earliest_id ASC)` to produce the final dispatch sequence.

An optional merge pass (enabled by default) then combines under-filled
trips from different areas when doing so is safe. See [Extension](#extension-cross-area-merge-pass).

**Interpretation of "handled first":** The assignment states that lower
priority numbers represent more urgent deliveries and should be "handled
first." We interpreted this as *trip dispatch order* rather than
per-package scheduling: trips containing more urgent deliveries are
dispatched earlier. The assignment asks us to organize deliveries into
trips, not to schedule individual packages, and it leaves the choice to
us and asks us to explain it. Within a trip, deliveries are listed in
priority order as well.

## Design Decisions

| Decision | Rationale | Source |
|----------|-----------|--------|
| Vehicle capacity: 10 kg | Stated in the problem description | Required by the assignment |
| Trip must never exceed capacity | Stated in the requirements | Required by the assignment |
| Group deliveries by area | "Deliveries going to the same area should be grouped together where reasonably possible" | Required by the assignment |
| Lower priority number = more urgent, dispatched first | "Lower priority numbers represent more urgent deliveries and should be handled first" | Required by the assignment |
| Every valid delivery appears in exactly one trip | Stated in the requirements | Required by the assignment |
| CSV input format | The assignment allows CSV, JSON, or plain text | Our decision |
| Weights stored as integer grams internally | Avoids float precision errors (e.g. `4.5 + 3.5 + 2.0` must equal exactly `10.000` kg). `Decimal(str) * 1000` is used during parsing; grams-to-kg conversion happens only at the display boundary | Our decision |
| Over-capacity packages rejected (not silently dropped) | The assignment says to handle the edge case "sensibly"; rejecting with a clear reason is more useful than silently ignoring | Our decision |
| Duplicate IDs: first occurrence wins, second rejected | The assignment does not specify; keeping the first is deterministic and simple | Our decision |
| Priority must be an integer ≥ 1 | The assignment's sample data uses small positive integers; we reject non-positive or non-integer values rather than guessing intent | Our decision |
| Empty area → `UNKNOWN` (accepted, not rejected) | The assignment does not list empty area as an error condition | Our decision |
| Area normalization: `strip().lower()` for key, first spelling for display | Makes "Maadi", " maadi ", and "MAADI" group together deterministically | Our decision |
| Best-Fit as the default packing strategy | Produced tighter packing on the included comparison case; remains a heuristic, not a proven improvement | Our decision |
| Merged trips limited to ≤ 2 distinct areas | The assignment says to group by area "where reasonably possible." The phrase is undefined, so we chose a bounded merge with a two-area policy guard to keep merged trips geographically reasonable | Our decision |
| Equal trip-priority required for merge | Our semantic policy to avoid mixing urgency levels in a single trip; not explicitly stated by the assignment | Our decision |

## Packing Strategy

Two greedy bin-packing strategies are available:

- **First-Fit** — place each delivery in the *first* open trip that has
  enough remaining capacity.
- **Best-Fit** — place each delivery in the open trip that will have the
  *least* remaining capacity after insertion (ties broken by trip order).

Both share the same asymptotic complexity and the same known worst-case
approximation bound, so Best-Fit is an empirical preference, not a proven
improvement.

**Counterexample** (one area, priorities 1–4, weights 6, 7, 3, 4 kg):

| Strategy   | Trips | Contents             |
|------------|-------|----------------------|
| First-Fit  | 3     | [6,3], [7], [4]      |
| Best-Fit   | 2     | [6,4], [7,3]         |

The packer defaults to Best-Fit. First-Fit is available via
`--strategy first-fit` so the trade-off can be measured rather than
asserted.

## Rejected Alternatives

| Approach | Why we rejected it |
|----------|--------------------|
| Global priority sort then pack | Destroys area grouping entirely. A P1 delivery in Maadi and a P2 delivery in Zamalek would end up in the same trip |
| Strict priority buckets (pack each priority level separately) | Wastes capacity. The assignment's own sample data has Maadi P1 2.00 kg and P2 3.50 kg, which fit one 5.50 kg trip together. Strict buckets would create two trips |
| First-Fit-Decreasing / Best-Fit-Decreasing (sort by weight descending) | Better bin-packing but breaks priority semantics. Example: an area with P1 1 kg, P2 1 kg, P3 1 kg, P4 9 kg. Weight-descending puts P4 in the first trip alongside P1, so the least urgent package appears in an earlier dispatch trip than P2 and P3, which are pushed to the second trip |
| Exact optimization (ILP / DP / backtracking) | Bin packing is NP-hard. The assignment asks for clear reasoning, not an optimizer |

## Extension: Cross-Area Merge Pass

Our one added feature is a **cross-area trip merging pass** that runs
after packing. It combines under-filled trips from different areas into
fewer, better-utilized trips when doing so is safe.

### Merge Conditions

Two trips may merge only if **all three** conditions hold:

1. Combined weight ≤ vehicle capacity (10 kg)
2. Union of area keys ≤ 2 distinct areas (policy guard)
3. Both trips share the same dispatch priority

### Safety Argument

Merging two trips with equal `trip_priority` cannot delay any delivery.
The merged trip inherits the smaller `earliest_id` of the two, so it
takes the earlier of their two dispatch positions. Deliveries from the
later trip move forward; deliveries from the earlier trip stay put; and
every trip after them moves one position earlier because the total trip
count drops by one.

### Algorithm

A single bounded pass iterates trips in dispatch order. Each trip scans
forward for the first compatible partner. Once a trip participates in a
merge (as either partner), it is marked consumed and cannot merge again
in this pass. No cascading merges occur.

### Example (`sample_merge_demo.csv`)

| Mode         | Trips | Utilization |
|--------------|-------|-------------|
| `--no-merge` | 5     | 43.0%       |
| default      | 3     | 71.7%       |

```bash
# See the difference:
python main.py data/sample_merge_demo.csv --no-merge
python main.py data/sample_merge_demo.csv
```

---

## Hardest Part (Q2)

Not the code. The hardest part was resolving ambiguity in the assignment:

- **"Handled first"** — does this mean per-package scheduling or trip
  dispatch order? The assignment asks us to organize deliveries into
  trips, not to route individual packages, so we chose dispatch order
  and documented why.
- **"Where reasonably possible"** — the assignment does not define what
  level of area grouping is "reasonable." We chose a bounded merge
  extension and limited merged trips to at most two distinct areas as a
  policy guard, keeping merged trips geographically reasonable while
  still reducing trip count.

Both decisions required a judgment call rather than a lookup in the spec.

## Suboptimal Groupings (Q3)

Three concrete cases where our algorithm does not produce the optimal
result:

**(a) Priority order prevents weight-optimal packing.**
One area, six deliveries with weights 2, 2, 2, 6, 6, 6 kg in that
priority order. Our algorithm produces 4 trips: `[2,2,2]`, `[6]`, `[6]`,
`[6]`. The optimal packing is 3 trips: `[6,2,2]`, `[6,2]`, `[6]`. We
pay this cost because priority-ordered processing forbids us from sorting
by weight.

**(b) Area grouping can dispatch lower-urgency deliveries earlier.**
Area A holds P1 and P5 deliveries; area B holds a single P2 delivery.
The P5 delivery appears in an earlier dispatch trip than the P2 delivery,
because area grouping at build time places both A deliveries in the same
trip (dispatched at P1 priority), while B's P2 delivery is in a separate,
later trip.

**(c) Merge-disabled leaves capacity unused.**
Several small single-package areas each create their own trip. With
merging disabled (`--no-merge`), these trips cannot be combined even when
they share the same priority and have ample remaining capacity.

## Scaling to 1,000,000 Requests (Q4)

### Current Implementation

- **Memory:** The full CSV is read into memory and all delivery/trip
  structures are kept in memory throughout. Memory usage grows linearly
  with input size (O(n)).
- **Packing:** Each delivery is placed by linearly scanning the list of
  open trips for that area. In the worst case (one area dominates), this
  degenerates toward O(n × t) where t is the number of open trips —
  approaching O(n²) if many trips stay open.
- **Merge pass:** The current implementation uses a nested scan over all
  trips, giving O(t²) worst case.
- **Output:** The full report string is built in memory before printing.

### Possible Future Improvements

- **Stream the input** rather than loading the entire file. Because areas
  are packed independently, the program could process one area at a time
  and only keep that area's deliveries in memory.
- **Index open trips by remaining capacity.** Best-Fit maps cleanly to an
  ordered structure (e.g. a balanced BST or sorted list), giving O(log t)
  lookups per delivery and reducing the packing step to O(n log n) overall.
- **Bucket the merge pass** by priority and remaining capacity to avoid
  the quadratic scan.
- **Write output in streaming fashion** rather than building the full
  report string.
- **Parallelize across areas.** Because areas are packed independently,
  the work is trivially parallelizable.

## One More Day (Q5)

- **Real distance data** instead of treating an area as an atomic unit.
  A proper routing model would consider travel time between delivery
  points, not just area labels.
- **A pluggable packing policy** benchmarked over generated datasets, so
  the choice of strategy is backed by data rather than a single
  counterexample.
- **Property-based tests** (e.g. with Hypothesis) asserting the two core
  invariants across random inputs: no trip exceeds capacity, and the
  multiset of delivery IDs is preserved end to end.

## Project Structure

```
delivery-route-planner/
├── main.py                  # Entry point: 3 lines
├── planner/
│   ├── __init__.py
│   ├── constants.py         # Named constants (12 values)
│   ├── models.py            # Delivery, RejectedDelivery, Trip
│   ├── loader.py            # CSV parsing, validation, normalization
│   ├── packing.py           # Group → sort → greedy pack → dispatch order
│   ├── merging.py           # Cross-area merge pass (isolated module)
│   ├── reporting.py         # Pure formatting, returns strings, never prints
│   └── cli.py               # argparse, orchestration, error handling, printing
├── tests/
│   └── test_planner.py      # 89 tests (loader, packing, merging, reporting, E2E)
└── data/
    ├── sample_deliveries.csv
    ├── sample_strategy_demo.csv
    ├── sample_merge_demo.csv
    ├── sample_edge_cases.csv
    └── sample_empty.csv
```

**Module separation:** `reporting.py` formats and returns strings — it
never prints. `cli.py` is the only module that reads `argv`, prints to
`stdout`/`stderr`, or returns exit codes. `merging.py` does not import
from `packing.py`; deleting it and skipping the merge call leaves the
rest of the program correct.

## Use of AI

An AI assistant was used for design discussion and code review, as the
assignment permits. I understand and can explain every part of this
submission.
