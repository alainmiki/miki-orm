#!/usr/bin/env python3
"""Test runner script for miki-orm.

Usage:
    python run_tests.py                    # run all tests
    python run_tests.py --backend=sqlite  # run only SQLite tests
    python run_tests.py --backend=postgres # run only PostgreSQL tests
    python run_tests.py --all              # run against both backends
"""

import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Run miki-orm test suite")
    parser.add_argument("--backend", choices=["sqlite", "postgres", "all"], default="all",
                        help="Backend(s) to test against")
    parser.add_argument("--async-only", action="store_true", help="Run only async tests")
    parser.add_argument("--sync-only", action="store_true", help="Run only synchronous tests")
    parser.add_argument("--unit-only", action="store_true", help="Run only unit tests")
    parser.add_argument("--migrations", action="store_true", help="Run migration tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Build pytest command
    cmd = ["pytest"]

    # Test paths
    paths = []
    if args.unit_only:
        paths.append("tests/unit")
    elif args.async_only:
        paths.append("tests/unit/test_async_crud.py")
    elif args.sync_only:
        paths.append("tests/unit/test_core_fields.py")
        paths.append("tests/unit/test_relationships.py")
        paths.append("tests/unit/test_queryset.py")
        paths.append("tests/unit/test_transactions.py")
    else:
        paths.append("tests/unit")

    if args.migrations:
        paths.append("tests/unit/test_migrations.py")

    cmd.extend(paths)

    # Backend filter
    if args.backend != "all":
        cmd.append(f"--backend={args.backend}")

    if args.verbose:
        cmd.append("-vv")

    # Always show local variables on failure for easier debugging
    cmd.append("--tb=short")
    cmd.append("-rP")

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
