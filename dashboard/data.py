"""Load dashboard data by running the real files in queries/.

No SQL lives in the Python code. Every number on the dashboard comes from a
.sql file, the same file `python run.py` prints, so the two cannot drift apart.
"""

from __future__ import annotations

import os
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import run
import seed

DB_ENV_VAR = "RETAIL_DB"


@dataclass(frozen=True)
class Loaded:
    file: str
    question: str
    frame: pd.DataFrame


def database_path() -> Path:
    return Path(os.environ.get(DB_ENV_VAR) or run.DEFAULT_DB_PATH)


def ensure_database(path: Path | None = None) -> Path:
    """Build the sample database on first use, since retail.db is not committed."""
    path = path or database_path()
    if not path.exists():
        seed.build_database(path)
    return path


def _run_file(path: Path, params: dict | None, db_path: Path | None) -> Loaded:
    with closing(run.connect_read_only(ensure_database(db_path))) as conn:
        result = run.run_query(conn, path, params)
    name = path.relative_to(run.QUERY_DIR).as_posix()
    return Loaded(name, result.question, pd.DataFrame(result.rows, columns=result.columns))


def load_query(number: int, db_path: Path | None = None) -> Loaded:
    """Run one numbered query file and return its rows as a DataFrame."""
    return _run_file(run.query_files([number])[0], None, db_path)


def load_sql(name: str, params: dict | None = None, db_path: Path | None = None) -> Loaded:
    """Run a query file by its path inside queries/, with optional parameters."""
    return _run_file(run.QUERY_DIR / name, params, db_path)
