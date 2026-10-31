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
    "11_mom_growth.sql": ["month", "revenue_qar", "previous_month_qar", "change_qar", "mom_change_pct"],
    "12_yoy_category_growth.sql": ["category", "revenue_2024_qar", "revenue_2025_qar", "change_qar",
                                   "yoy_growth_pct"],
    "13_running_total.sql": ["month", "revenue_qar", "year_to_date_qar", "pct_of_full_year"],
    "14_branch_monthly_leader.sql": ["month", "leader", "leader_revenue_qar", "runner_up", "lead_qar",
                                     "branches_trading"],
    "15_top3_per_category.sql": ["category", "rank_in_category", "product", "units_sold", "revenue_qar",
                                 "category_unit_share_pct"],
    "16_top_customers.sql": ["customer_id", "customer", "home_branch", "orders", "lifetime_spend_qar",
                             "avg_order_value_qar", "first_order", "last_order",
                             "avg_days_between_orders"],
    "17_rfm_segments.sql": ["segment", "customers", "avg_recency_days", "avg_orders", "avg_m_score",
                            "avg_spend_qar", "revenue_share_pct"],
    "18_cohort_retention.sql": ["cohort", "customers", "month_1_pct", "month_2_pct", "month_3_pct",
                                "month_6_pct", "month_12_pct"],
    "19_basket_pairs.sql": ["product_a", "product_b", "orders_together", "support_pct",
                            "confidence_a_to_b", "lift"],
    "20_branch_scorecard.sql": ["year", "branch", "trading_days", "revenue_qar", "revenue_per_day_qar",
                                "annual_sales_per_sqm_qar", "rank_by_revenue", "rank_by_daily_revenue",
                                "rank_by_density"],
    "21_rolling_7day_peaks.sql": ["month", "peak_day", "rolling_7d_avg_qar", "events_in_window"],
    "22_overdue_customers.sql": ["customer_id", "customer", "home_branch", "orders", "avg_gap_days",
                                 "last_order", "days_since_last_order", "lifetime_spend_qar"],
    "23_discount_impact.sql": ["year", "price_type", "lines", "units", "revenue_qar", "revenue_share_pct",
                               "discount_given_qar", "avg_discount_pct", "gross_margin_pct"],
    "24_ramadan_shopping_hours.sql": ["time_band", "ramadan_orders", "ramadan_share_pct", "other_orders",
                                      "other_share_pct"],
    "25_delivery_trend.sql": ["quarter", "orders", "delivery_orders", "delivery_order_share_pct",
                              "delivery_revenue_share_pct", "share_change_pts"],
    "26_promotion_uplift.sql": ["category", "products", "promo_weeks", "units_per_100_orders_normal",
                                "units_per_100_orders_promo", "unit_uplift_pct",
                                "profit_per_100_orders_normal_qar", "profit_per_100_orders_promo_qar",
                                "profit_change_pct"],
    "27_customer_lifetime_value.sql": ["joined_quarter", "customers", "value_3m_qar", "value_6m_qar",
                                       "value_12m_qar", "value_to_date_qar", "active_last_90_days_pct"],
    "28_stockout_proxies.sql": ["branch", "product", "last_sale", "next_sale", "gap_days", "orders_in_gap",
                                "expected_sales", "revenue_at_risk_qar", "assessment"],
    "29_delivery_growth.sql": ["branch", "orders_before", "orders_now", "order_growth_pct", "revenue_before_qar",
                               "revenue_now_qar", "revenue_change_qar", "orders_effect_qar", "basket_effect_qar",
                               "new_to_delivery_revenue_pct"],
    "30_return_rates_by_channel.sql": ["category", "in_store_lines", "in_store_returned", "in_store_rate_pct",
                                       "delivery_lines", "delivery_returned", "delivery_rate_pct", "rate_ratio",
                                       "chi_square", "refunds_pct_of_gross_profit", "delivery_vs_store"],
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


# ---------------------------------------------------------------------------
# Invariants for queries 11-25
# ---------------------------------------------------------------------------

def test_mom_growth_matches_monthly_revenue(query):
    monthly = query("01_monthly_revenue.sql").column("revenue_qar")
    rows = query("11_mom_growth.sql").rows
    assert [r["revenue_qar"] for r in rows] == monthly
    assert rows[0]["previous_month_qar"] is None
    assert rows[0]["mom_change_pct"] is None
    for prev, row in zip(rows, rows[1:]):
        assert row["previous_month_qar"] == prev["revenue_qar"]
        assert row["change_qar"] == pytest.approx(row["revenue_qar"] - prev["revenue_qar"], abs=0.02)


def test_yoy_columns_add_up_to_each_year(query, totals):
    result = query("12_yoy_category_growth.sql")
    approx_sum(result.column("revenue_2024_qar"), totals["yearly_revenue"]["2024"])
    approx_sum(result.column("revenue_2025_qar"), totals["yearly_revenue"]["2025"])


def test_running_total_ends_at_each_year_total(query, totals):
    rows = query("13_running_total.sql").rows
    for year, revenue in totals["yearly_revenue"].items():
        year_rows = [r for r in rows if r["month"].startswith(year)]
        ytd = [r["year_to_date_qar"] for r in year_rows]
        assert ytd == sorted(ytd)
        assert ytd[-1] == pytest.approx(revenue, abs=0.01)
        assert year_rows[-1]["pct_of_full_year"] == 100.0


def test_branch_leader_beats_runner_up(query):
    rows = query("14_branch_monthly_leader.sql").rows
    assert len(rows) == 24
    for row in rows:
        assert row["leader"] != row["runner_up"]
        assert row["lead_qar"] >= 0
        # Lusail opened on 2024-09-15, so it trades from September 2024.
        assert row["branches_trading"] == (5 if row["month"] >= "2024-09" else 4)


def test_top3_per_category(query, db_path):
    rows = query("15_top3_per_category.sql").rows
    conn = sqlite3.connect(db_path)
    n_categories, = conn.execute("SELECT COUNT(*) FROM categories").fetchone()
    conn.close()
    by_category = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row)
    assert len(by_category) == n_categories
    for products in by_category.values():
        assert [p["rank_in_category"] for p in products] == [1, 2, 3]
        units = [p["units_sold"] for p in products]
        assert units == sorted(units, reverse=True)


def test_top_customers_sorted_by_spend(query):
    rows = query("16_top_customers.sql").rows
    assert len(rows) == 10
    spend = [r["lifetime_spend_qar"] for r in rows]
    assert spend == sorted(spend, reverse=True)
    for row in rows:
        assert row["first_order"] <= row["last_order"]


def test_rfm_segments_cover_every_customer(query, totals):
    result = query("17_rfm_segments.sql")
    assert sum(result.column("customers")) == totals["customers"]
    assert sum(result.column("revenue_share_pct")) == pytest.approx(100, abs=0.5)
    assert set(result.column("segment")) <= {
        "Champions", "Loyal", "Promising", "Needs attention", "At risk", "Lost"}
    by_segment = {r["segment"]: r for r in result.rows}
    assert by_segment["Champions"]["avg_recency_days"] < by_segment["Lost"]["avg_recency_days"]


def test_cohort_retention(query, totals):
    rows = query("18_cohort_retention.sql").rows
    assert sum(r["customers"] for r in rows) == totals["customers"]
    pct_columns = ["month_1_pct", "month_2_pct", "month_3_pct", "month_6_pct", "month_12_pct"]
    for row in rows:
        for col in pct_columns:
            assert row[col] is None or 0 <= row[col] <= 100
    # The first cohort can be followed for a full year; the last cannot.
    assert rows[0]["cohort"] == "2024-01" and rows[0]["month_12_pct"] is not None
    assert rows[-1]["cohort"] == "2025-12" and rows[-1]["month_1_pct"] is None


def test_basket_pairs_are_real_associations(query):
    rows = query("19_basket_pairs.sql").rows
    assert 0 < len(rows) <= 15
    lifts = [r["lift"] for r in rows]
    assert lifts == sorted(lifts, reverse=True)
    for row in rows:
        assert row["lift"] > 1
        assert 0 < row["confidence_a_to_b"] <= 1
        assert row["orders_together"] >= 15


def test_branch_scorecard_counts_trading_days(query, totals):
    rows = query("20_branch_scorecard.sql").rows
    assert len(rows) == 10
    days = {(r["year"], r["branch"]): r["trading_days"] for r in rows}
    assert days[("2024", "Lusail")] == 108
    assert days[("2024", "Al Sadd")] == 366
    assert days[("2025", "Lusail")] == 365
    approx_sum([r["revenue_qar"] for r in rows if r["year"] == "2024"], totals["yearly_revenue"]["2024"])


def test_rolling_peaks_fall_in_their_month(query):
    rows = query("21_rolling_7day_peaks.sql").rows
    assert len(rows) == 24
    for row in rows:
        assert row["peak_day"].startswith(row["month"])
        assert row["rolling_7d_avg_qar"] > 0
    march_2025 = next(r for r in rows if r["month"] == "2025-03")
    assert "Ramadan 2025" in march_2025["events_in_window"]


def test_overdue_customers_meet_the_rule(query):
    rows = query("22_overdue_customers.sql").rows
    assert len(rows) <= 15
    for row in rows:
        assert row["orders"] >= 5
        assert row["days_since_last_order"] >= 30
        assert row["days_since_last_order"] > 3 * row["avg_gap_days"] - 0.1


def test_discount_split_adds_up(query, totals):
    rows = query("23_discount_impact.sql").rows
    approx_sum([r["revenue_qar"] for r in rows], totals["revenue"])
    for row in rows:
        if row["price_type"] == "Full price":
            assert row["discount_given_qar"] == 0
        else:
            assert row["discount_given_qar"] > 0
            assert row["gross_margin_pct"] < next(
                r["gross_margin_pct"] for r in rows
                if r["year"] == row["year"] and r["price_type"] == "Full price")


def test_ramadan_shifts_shopping_later(query):
    rows = {r["time_band"]: r for r in query("24_ramadan_shopping_hours.sql").rows}
    assert sum(r["ramadan_share_pct"] for r in rows.values()) == pytest.approx(100, abs=0.5)
    assert sum(r["other_share_pct"] for r in rows.values()) == pytest.approx(100, abs=0.5)
    late = rows["Late night (22:00-23:59)"]
    before_iftar = rows["Late afternoon (16:00-18:59)"]
    assert late["ramadan_share_pct"] > late["other_share_pct"]
    assert before_iftar["ramadan_share_pct"] < before_iftar["other_share_pct"]


def test_delivery_trend(query, totals):
    rows = query("25_delivery_trend.sql").rows
    assert len(rows) == 8
    assert rows[0]["quarter"] == "2024-Q1" and rows[-1]["quarter"] == "2025-Q4"
    assert sum(r["orders"] for r in rows) == totals["orders"]
    assert rows[-1]["delivery_order_share_pct"] > rows[0]["delivery_order_share_pct"]
