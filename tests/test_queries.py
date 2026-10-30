"""Run every query in queries/ against a freshly seeded database.

Each query must run, return rows and expose the columns listed below. On top
of that, a set of invariants checks that the numbers hang together: revenue
totals agree across queries, shares add up to 100, and the seasonal patterns
built into the sample data show up where they should.
"""

import re
import sqlite3
from pathlib import Path
from typing import NamedTuple

import pytest

QUERY_DIR = Path(__file__).resolve().parent.parent / "queries"
QUERY_FILES = sorted(QUERY_DIR.glob("*.sql"))

EXPECTED_COLUMNS = {
    "01_monthly_revenue.sql": ["month", "orders", "revenue_qar", "avg_order_value_qar"],
    "02_branch_summary.sql": ["branch", "opened_on", "orders", "customers", "revenue_qar",
                              "revenue_share_pct", "gross_margin_pct"],
    "03_top_products.sql": ["product", "category", "units_sold", "revenue_qar", "gross_margin_pct"],
    "04_category_share.sql": ["category", "units_sold", "revenue_qar", "revenue_share_pct",
                              "profit_share_pct", "gross_margin_pct"],
    "05_weekday_pattern.sql": ["weekday", "days", "avg_orders", "avg_revenue_qar"],
    "06_payment_mix.sql": ["year", "payment_method", "orders", "share_pct"],
    "07_basket_by_channel.sql": ["channel", "orders", "avg_lines", "avg_units",
                                 "avg_order_value_qar", "largest_order_qar"],
    "08_new_vs_returning.sql": ["month", "active_customers", "new_customers",
                                "returning_customers", "customers_to_date"],
    "09_returns_by_category.sql": ["category", "units_sold", "units_returned", "return_rate_pct",
                                   "refunds_qar", "top_reason"],
    "10_ramadan_vs_rest.sql": ["year", "period", "days", "avg_daily_orders", "avg_daily_revenue_qar",
                               "avg_order_value_qar", "revenue_uplift_pct"],
}

DAYS_IN_DATA = 731  # 2024 is a leap year, so 366 + 365


class Result(NamedTuple):
    columns: list[str]
    rows: list[dict]

    def column(self, name):
        return [row[name] for row in self.rows]


@pytest.fixture(scope="session")
def query(db_path):
    """Return a function that runs a query file once and caches the result."""
    conn = sqlite3.connect(db_path)
    cache = {}

    def run(name):
        if name not in cache:
            cursor = conn.execute((QUERY_DIR / name).read_text(encoding="utf-8"))
            columns = [d[0] for d in cursor.description]
            cache[name] = Result(columns, [dict(zip(columns, row)) for row in cursor.fetchall()])
        return cache[name]

    yield run
    conn.close()


@pytest.fixture(scope="session")
def totals(db_path):
    conn = sqlite3.connect(db_path)
    try:
        revenue, = conn.execute("SELECT SUM(line_total) FROM order_items").fetchone()
        orders, customers = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT customer_id) FROM orders").fetchone()
        returned_units, = conn.execute("SELECT SUM(quantity) FROM returns").fetchone()
        yearly = dict(conn.execute("""
            SELECT strftime('%Y', o.ordered_at), SUM(oi.line_total)
            FROM orders o JOIN order_items oi USING (order_id)
            GROUP BY 1
        """).fetchall())
    finally:
        conn.close()
    return {"revenue": revenue, "orders": orders, "customers": customers,
            "returned_units": returned_units, "yearly_revenue": yearly}


def approx_sum(values, expected):
    """Each value is rounded to 2 decimals, so allow a cent of drift per row."""
    assert sum(values) == pytest.approx(expected, abs=0.01 * max(len(values), 1))


# ---------------------------------------------------------------------------
# Every query
# ---------------------------------------------------------------------------

def test_query_files_are_numbered_in_sequence():
    names = [p.name for p in QUERY_FILES]
    assert names, "no query files found"
    for name in names:
        assert re.fullmatch(r"\d{2}_[a-z0-9_]+\.sql", name), name
    numbers = [int(name[:2]) for name in names]
    assert numbers == list(range(1, len(names) + 1))


def test_every_query_has_expected_columns_listed():
    assert {p.name for p in QUERY_FILES} == set(EXPECTED_COLUMNS)


@pytest.mark.parametrize("path", QUERY_FILES, ids=lambda p: p.stem)
def test_query_starts_with_its_question(path):
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    match = re.fullmatch(r"-- Q(\d{2})\. .+\?", first_line)
    assert match, f"{path.name} should start with '-- Qnn. <question>?'"
    assert match.group(1) == path.name[:2]


@pytest.mark.parametrize("name", sorted(EXPECTED_COLUMNS))
def test_query_runs_and_returns_expected_columns(query, name):
    result = query(name)
    assert result.columns == EXPECTED_COLUMNS[name]
    assert len(result.rows) > 0


# ---------------------------------------------------------------------------
# Invariants for queries 01-10
# ---------------------------------------------------------------------------

def test_revenue_totals_agree_across_queries(query, totals):
    for name in ["01_monthly_revenue.sql", "02_branch_summary.sql", "04_category_share.sql"]:
        approx_sum(query(name).column("revenue_qar"), totals["revenue"])


def test_monthly_revenue_covers_two_full_years(query, totals):
    result = query("01_monthly_revenue.sql")
    assert len(result.rows) == 24
    assert result.rows[0]["month"] == "2024-01"
    assert result.rows[-1]["month"] == "2025-12"
    assert sum(result.column("orders")) == totals["orders"]


def test_branch_and_category_shares_add_up_to_100(query):
    assert sum(query("02_branch_summary.sql").column("revenue_share_pct")) == pytest.approx(100, abs=0.5)
    categories = query("04_category_share.sql")
    assert sum(categories.column("revenue_share_pct")) == pytest.approx(100, abs=0.5)
    assert sum(categories.column("profit_share_pct")) == pytest.approx(100, abs=0.5)


def test_branch_orders_add_up(query, totals):
    assert sum(query("02_branch_summary.sql").column("orders")) == totals["orders"]


def test_top_products_are_sorted_and_limited(query):
    revenue = query("03_top_products.sql").column("revenue_qar")
    assert len(revenue) == 10
    assert revenue == sorted(revenue, reverse=True)


def test_weekend_is_busiest(query):
    result = query("05_weekday_pattern.sql")
    assert sum(result.column("days")) == DAYS_IN_DATA
    assert set(result.column("weekday")[:2]) == {"Friday", "Saturday"}


def test_payment_shares_add_up_within_each_year(query, totals):
    result = query("06_payment_mix.sql")
    assert sum(result.column("orders")) == totals["orders"]
    for year in ("2024", "2025"):
        shares = [r["share_pct"] for r in result.rows if r["year"] == year]
        assert sum(shares) == pytest.approx(100, abs=0.5)


def test_channel_baskets(query, totals):
    result = query("07_basket_by_channel.sql")
    assert set(result.column("channel")) == {"in_store", "delivery"}
    assert sum(result.column("orders")) == totals["orders"]
    for row in result.rows:
        assert row["avg_units"] >= row["avg_lines"] >= 1


def test_new_and_returning_customers(query, totals):
    rows = query("08_new_vs_returning.sql").rows
    assert rows[0]["returning_customers"] == 0
    assert rows[-1]["customers_to_date"] == totals["customers"]
    for row in rows:
        assert row["active_customers"] == row["new_customers"] + row["returning_customers"]


def test_return_rates_are_plausible(query, totals):
    result = query("09_returns_by_category.sql")
    assert sum(result.column("units_returned")) == totals["returned_units"]
    for rate in result.column("return_rate_pct"):
        assert 0 <= rate < 10


def test_ramadan_days_are_busier(query):
    result = query("10_ramadan_vs_rest.sql")
    assert sum(result.column("days")) == DAYS_IN_DATA
    ramadan = [r for r in result.rows if r["period"] == "Ramadan"]
    assert len(ramadan) == 2
    for row in ramadan:
        assert row["revenue_uplift_pct"] > 0
