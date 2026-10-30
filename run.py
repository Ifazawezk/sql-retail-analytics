"""Run the SQL files in queries/ against retail.db and print the results.

Usage:
    python run.py                  # every query
    python run.py 3 17             # only queries 03 and 17
    python run.py --max-rows 5     # cut long result sets short
    python run.py --db other.db    # use a different database file
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUERY_DIR = ROOT / "queries"
DEFAULT_DB_PATH = ROOT / "retail.db"


@dataclass
class QueryResult:
    path: Path
    question: str
    columns: list[str]
    rows: list[tuple]
    seconds: float


def query_files(numbers: list[int] | None = None) -> list[Path]:
    """Return query files in order, optionally only the given numbers."""
    files = sorted(QUERY_DIR.glob("[0-9][0-9]_*.sql"))
    if not numbers:
        return files
    by_number = {int(path.name[:2]): path for path in files}
    missing = [n for n in numbers if n not in by_number]
    if missing:
        raise ValueError(f"no query file for number(s): {', '.join(map(str, missing))}")
    return [by_number[n] for n in numbers]


def read_question(sql: str) -> str:
    """The question is the first comment line of the file."""
    for line in sql.splitlines():
        line = line.strip()
        if line.startswith("--"):
            return line.lstrip("-").strip()
        if line:
            break
    return "(no question given)"


def run_query(conn: sqlite3.Connection, path: Path) -> QueryResult:
    sql = path.read_text(encoding="utf-8")
    started = time.perf_counter()
    cursor = conn.execute(sql)
    rows = cursor.fetchall()
    elapsed = time.perf_counter() - started
    columns = [d[0] for d in cursor.description]
    return QueryResult(path, read_question(sql), columns, rows, elapsed)


def _decimals(value: float) -> int:
    text = repr(value)
    return len(text.split(".")[1]) if "." in text and "e" not in text else 0


def format_cell(value, decimals: int = 2, thousands: bool = True) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}" if thousands else str(value)
    if isinstance(value, float):
        return f"{value:,.{decimals}f}" if thousands else f"{value:.{decimals}f}"
    return str(value)


def format_table(columns: list[str], rows: list[tuple], max_rows: int | None = None) -> str:
    """Lay rows out as a plain text table.

    Numbers are right-aligned and every float in a column gets the same
    number of decimals (always two for *_qar money columns). Id columns
    skip the thousands separator.
    """
    shown = rows if max_rows is None else rows[:max_rows]

    numeric = []
    decimals = []
    for i, name in enumerate(columns):
        values = [row[i] for row in rows if row[i] is not None]
        numeric.append(bool(values) and all(isinstance(v, (int, float)) for v in values))
        floats = [v for v in values if isinstance(v, float)]
        if name.endswith("_qar"):
            decimals.append(2)
        else:
            decimals.append(min(max((_decimals(v) for v in floats), default=0), 3))

    cells = [
        [format_cell(row[i], decimals[i], thousands=not columns[i].endswith("_id"))
         for i in range(len(columns))]
        for row in shown
    ]
    widths = [max([len(col)] + [len(r[i]) for r in cells]) for i, col in enumerate(columns)]

    def line(values: list[str]) -> str:
        parts = [v.rjust(w) if numeric[i] else v.ljust(w) for i, (v, w) in enumerate(zip(values, widths))]
        return "  ".join(parts).rstrip()

    out = [line(columns), line(["-" * w for w in widths])]
    out.extend(line(r) for r in cells)
    if len(shown) < len(rows):
        out.append(f"... {len(rows) - len(shown)} more rows")
    return "\n".join(out)


def print_result(result: QueryResult, max_rows: int | None) -> None:
    print(result.question)
    print(f"[{result.path.name}, {len(result.rows)} rows]")
    print()
    print(format_table(result.columns, result.rows, max_rows))
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the business queries against retail.db.")
    parser.add_argument("numbers", nargs="*", type=int, help="query numbers to run (default: all)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="database file (default: retail.db)")
    parser.add_argument("--max-rows", type=int, default=None, help="show at most this many rows per query")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"{db_path} not found. Create it first with: python seed.py", file=sys.stderr)
        return 1

    try:
        files = query_files(args.numbers)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    # Open read-only so a typo in a query can never change the data.
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        total = 0.0
        for path in files:
            result = run_query(conn, path)
            total += result.seconds
            print_result(result, args.max_rows)
    finally:
        conn.close()

    noun = "query" if len(files) == 1 else "queries"
    print(f"Ran {len(files)} {noun} in {total:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
