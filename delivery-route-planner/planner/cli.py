"""Command-line interface and orchestration for the Delivery Route Planner.

This is the ONLY module that reads argv, prints to stdout/stderr,
or calls sys.exit.
"""

import argparse
import sys
from pathlib import Path

from planner.constants import (
    DEFAULT_STRATEGY,
    STRATEGY_BEST_FIT,
    STRATEGY_FIRST_FIT,
)
from planner.loader import InvalidInputFile, load_deliveries
from planner.merging import merge_compatible_trips
from planner.packing import build_trips
from planner.reporting import format_report


def _build_parser() -> argparse.ArgumentParser:
    """Create the argument parser with help text for each option."""
    parser = argparse.ArgumentParser(
        description="Organize delivery requests into vehicle trips.",
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="path to the CSV file containing delivery requests",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        default=False,
        help="disable the cross-area trip merging extension",
    )
    parser.add_argument(
        "--strategy",
        choices=[STRATEGY_BEST_FIT, STRATEGY_FIRST_FIT],
        default=DEFAULT_STRATEGY,
        help=f"packing strategy (default: {DEFAULT_STRATEGY})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the delivery route planner.

    Returns 0 on success, 1 on input errors.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        deliveries, rejected = load_deliveries(args.input_csv)
    except FileNotFoundError:
        print(f"Error: file not found: {args.input_csv}", file=sys.stderr)
        return 1
    except PermissionError:
        print(f"Error: permission denied: {args.input_csv}", file=sys.stderr)
        return 1
    except InvalidInputFile as e:
        print(f"Error: invalid input file: {e}", file=sys.stderr)
        return 1

    input_row_count = len(deliveries) + len(rejected)

    trips = build_trips(deliveries, strategy=args.strategy)

    merges_applied = 0
    if not args.no_merge:
        trips, merges_applied = merge_compatible_trips(trips)

    report = format_report(trips, rejected, input_row_count, merges_applied)
    print(report)

    return 0
