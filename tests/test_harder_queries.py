"""Checks for Q26 to Q30 against something outside each query.

Q26 is compared with the promotion calendar seed.py really planned. Q27 and Q30
are recomputed by hand. Q28 runs on copies of the data with sales removed, so it
has to find a stock-out that is known to be there.
"""

import datetime as dt
import random
import sqlite3
from collections import defaultdict
from contextlib import closing
from pathlib import Path

import pandas as pd
import pytest

import run
import seed
from dashboard import data


def rows_of(number, db_path):
    return data.load_query(number, db_path).frame.to_dict("records")


@pytest.fixture
def copy_db(db_path, tmp_path):
    """A private copy of the sample data that a test can change."""
    target = tmp_path / "copy.db"
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    return target


def execute(db_path, sql, *params):
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        conn.commit()
    return rows


# ---------------------------------------------------------------------------
# Q26 promotion uplift
# ---------------------------------------------------------------------------

def real_promotions():
    """The (product, ISO year, ISO week) calendar the generator planned for the default seed."""
    rng = random.Random(seed.DEFAULT_SEED)
    calendar = seed.build_calendar()
    products = seed.build_products(rng)
    seed.build_customers(rng, calendar)
    simulator = seed.OrderSimulator(rng, calendar, products)
    return {(product, *week) for week, ids in simulator.weekly_promos.items() for product in ids}


def monday(text):
    day = dt.date.fromisoformat(text)
    return day - dt.timedelta(days=day.weekday())


@pytest.fixture(scope="module")
def promotion_check(db_path):
    """Uplift worked out from the real calendar, and the way a naive reading of discounts would."""
    events = execute(db_path, "SELECT start_date, end_date FROM calendar_events WHERE kind IN ('ramadan', 'eid')")
    orders, units, discounted = defaultdict(int), defaultdict(int), set()
    for day, in execute(db_path, "SELECT date(ordered_at) FROM orders"):
        orders[monday(day)] += 1
    for day, product, quantity, discount, price in execute(db_path, """
            SELECT date(o.ordered_at), oi.product_id, oi.quantity, oi.discount_amount, oi.unit_price
            FROM orders o JOIN order_items oi USING (order_id)"""):
        units[product, monday(day)] += quantity
        if round(100 * discount / (quantity * price)) == 10:
            discounted.add((product, monday(day)))

    plain = [week for week in orders if not any(
        dt.date.fromisoformat(start) <= week + dt.timedelta(days=6) and dt.date.fromisoformat(end) >= week
        for start, end in events)]
    everything = {key[0] for key in units}
    steady = [p for p in everything if sum(units[p, week] > 0 for week in plain) >= 0.8 * len(plain)]
    promotions = real_promotions()

    def uplift(products, on_promotion):
        promo_total = normal_total = 0.0
        for product in products:
            promo_units = promo_orders = normal_units = normal_orders = 0
            for week in plain:
                if on_promotion(product, week):
                    promo_units += units[product, week]
                    promo_orders += orders[week]
                else:
                    normal_units += units[product, week]
                    normal_orders += orders[week]
            if promo_orders:
                promo_total += 100 * promo_units / promo_orders
                normal_total += 100 * normal_units / normal_orders
        return 100 * (promo_total / normal_total - 1)

    def real(product, week):
        return (product, *week.isocalendar()[:2]) in promotions

    def seen(product, week):
        return (product, week) in discounted

    return {"steady_true": uplift(steady, real), "all_true": uplift(everything, real),
            "all_naive": uplift(everything, seen)}


def test_q26_uplift_is_close_to_the_real_promotion_calendar(db_path, promotion_check):
    total = rows_of(26, db_path)[-1]
    assert total["category"] == "All steady sellers"
    assert total["unit_uplift_pct"] == pytest.approx(promotion_check["steady_true"], abs=5)


def test_reading_every_discount_would_overstate_the_uplift(promotion_check):
    """Why Q26 keeps to steady sellers: an unsold promotion week leaves no trace."""
    assert promotion_check["all_naive"] > promotion_check["all_true"] + 10


def test_q26_total_row_adds_up(db_path):
    rows = rows_of(26, db_path)
    total, categories = rows[-1], rows[:-1]
    assert sum(r["products"] for r in categories) == total["products"]
    assert sum(r["promo_weeks"] for r in categories) == total["promo_weeks"]
    assert sum(r["units_per_100_orders_promo"] for r in categories) == pytest.approx(
        total["units_per_100_orders_promo"], abs=0.05)


def test_q26_promotions_lift_units_but_a_discount_costs_margin(db_path):
    total = rows_of(26, db_path)[-1]
    assert total["unit_uplift_pct"] > 0
    assert total["profit_change_pct"] < total["unit_uplift_pct"]


def set_discount(db_path, share, condition):
    execute(db_path, f"""
        UPDATE order_items
        SET discount_amount = ROUND(quantity * unit_price * {share}, 2),
            line_total = quantity * unit_price - ROUND(quantity * unit_price * {share}, 2)
        WHERE {condition}
    """)


def test_q26_leaves_out_ramadan_weeks(copy_db):
    """10% lines inside Ramadan must not add promotion weeks."""
    before = rows_of(26, copy_db)[-1]["promo_weeks"]
    set_discount(copy_db, 0.10, """order_id IN (SELECT order_id FROM orders
                                                WHERE ordered_at >= '2025-03-03' AND ordered_at < '2025-03-10')""")
    assert rows_of(26, copy_db)[-1]["promo_weeks"] == before


def test_q26_only_counts_ten_percent_lines_as_promotions(copy_db):
    """Moving real promotion lines to 15% has to remove those promotion weeks."""
    before = rows_of(26, copy_db)[-1]["promo_weeks"]
    set_discount(copy_db, 0.15, """discount_amount > 0 AND order_id IN (
        SELECT order_id FROM orders WHERE ordered_at >= '2025-05-01' AND ordered_at < '2025-06-01')""")
    assert rows_of(26, copy_db)[-1]["promo_weeks"] < before


# ---------------------------------------------------------------------------
# Q27 customer lifetime value
# ---------------------------------------------------------------------------

def test_q27_counts_every_customer(db_path):
    assert sum(r["customers"] for r in rows_of(27, db_path)) == seed.N_CUSTOMERS


def test_q27_total_value_matches_the_database(db_path):
    expected = execute(db_path, """
        SELECT SUM(oi.line_total - oi.quantity * oi.unit_cost) - (SELECT SUM(refund_amount) FROM returns)
        FROM order_items oi""")[0][0]
    rows = rows_of(27, db_path)
    assert sum(r["customers"] * r["value_to_date_qar"] for r in rows) == pytest.approx(expected, abs=5)


def test_q27_value_builds_up_over_time(db_path):
    for row in rows_of(27, db_path):
        known = [row[c] for c in ("value_3m_qar", "value_6m_qar", "value_12m_qar") if pd.notna(row[c])]
        assert known == sorted(known)


def test_q27_young_cohorts_stay_blank(db_path):
    rows = {r["joined_quarter"]: r for r in rows_of(27, db_path)}
    assert rows["2024-Q4"]["value_12m_qar"] > 0            # the last joiner reached 12 months
    assert pd.isna(rows["2025-Q1"]["value_12m_qar"])
    assert rows["2025-Q3"]["value_3m_qar"] > 0
    assert pd.isna(rows["2025-Q4"]["value_3m_qar"])


def test_q27_customers_who_never_ordered_stay_in_the_average(copy_db):
    before = {r["joined_quarter"]: r for r in rows_of(27, copy_db)}["2024-Q1"]
    execute(copy_db, """INSERT INTO customers (first_name, last_name, gender, birth_year, area, home_branch_id, joined_on)
                        VALUES ('Test', 'Person', 'F', 1990, 'Al Sadd', 1, '2024-02-01')""")
    after = {r["joined_quarter"]: r for r in rows_of(27, copy_db)}["2024-Q1"]
    assert after["customers"] == before["customers"] + 1
    assert after["value_12m_qar"] < before["value_12m_qar"]


def test_q27_a_second_refund_on_one_line_counts_once_each(copy_db):
    before = sum(r["customers"] * r["value_to_date_qar"] for r in rows_of(27, copy_db))
    item = execute(copy_db, "SELECT order_item_id FROM returns LIMIT 1")[0][0]
    execute(copy_db, """INSERT INTO returns (order_item_id, returned_on, quantity, refund_amount, reason)
                        VALUES (?, '2025-01-01', 1, 10.0, 'Second part')""", item)
    after = sum(r["customers"] * r["value_to_date_qar"] for r in rows_of(27, copy_db))
    assert before - after == pytest.approx(10.0, abs=5)


# ---------------------------------------------------------------------------
# Q28 stock-out proxies
# ---------------------------------------------------------------------------

BEST_SELLER = (1, 13)  # Fresh Milk at Al Sadd, the most sold pair on the default seed


def remove_sales(db_path, branch, product, start, end):
    return execute(db_path, """
        DELETE FROM order_items WHERE product_id = ? AND order_id IN (
            SELECT order_id FROM orders WHERE branch_id = ? AND ordered_at >= ? AND ordered_at < ?)
    """, product, branch, start, end)


def test_q28_best_seller_is_what_the_tests_assume(db_path):
    assert execute(db_path, """
        SELECT o.branch_id, oi.product_id FROM orders o JOIN order_items oi USING (order_id)
        GROUP BY 1, 2 ORDER BY COUNT(*) DESC LIMIT 1""")[0] == BEST_SELLER


def test_q28_finds_no_stockouts_where_there_are_none(db_path):
    rows = rows_of(28, db_path)
    assert len(rows) == 15
    assert {r["assessment"] for r in rows} == {"Within normal variation"}


def test_q28_lists_the_strongest_gaps_first(db_path):
    expected = [r["expected_sales"] for r in rows_of(28, db_path)]
    assert expected == sorted(expected, reverse=True)


def test_q28_finds_a_planted_two_month_stockout(copy_db):
    remove_sales(copy_db, *BEST_SELLER, "2025-04-01", "2025-06-01")
    top = rows_of(28, copy_db)[0]
    assert top["branch"] == "Al Sadd"
    assert top["product"] == "Fresh Milk Full Fat 2L"
    assert top["assessment"] == "Likely stock-out"
    assert top["last_sale"] < "2025-04-01"
    assert top["next_sale"] >= "2025-06-01"


def test_q28_finds_a_stockout_still_open_when_the_data_ends(copy_db):
    remove_sales(copy_db, *BEST_SELLER, "2025-10-15", "2026-01-01")
    top = rows_of(28, copy_db)[0]
    assert top["product"] == "Fresh Milk Full Fat 2L"
    assert top["assessment"] == "Likely stock-out"
    assert top["next_sale"] == "2026-01-01"


def test_q28_cannot_see_a_one_month_gap(copy_db):
    """The limit in the README: a month of the best seller stays under the line."""
    remove_sales(copy_db, *BEST_SELLER, "2025-04-01", "2025-05-01")
    assert {r["assessment"] for r in rows_of(28, copy_db)} == {"Within normal variation"}


def test_q28_days_before_a_branch_opened_are_not_a_gap(db_path):
    for row in rows_of(28, db_path):
        if row["branch"] == "Lusail":
            assert row["last_sale"] >= "2024-09-15"


# ---------------------------------------------------------------------------
# Q29 delivery growth
# ---------------------------------------------------------------------------

def test_q29_effects_add_up_to_the_revenue_change(db_path):
    for row in rows_of(29, db_path):
        assert row["orders_effect_qar"] + row["basket_effect_qar"] == pytest.approx(row["revenue_change_qar"], abs=0.02)


def test_q29_total_row_adds_up(db_path):
    rows = rows_of(29, db_path)
    total, branches = rows[-1], rows[:-1]
    assert total["branch"] == "All branches"
    assert len(branches) == 5
    assert sum(r["orders_now"] for r in branches) == total["orders_now"]
    assert sum(r["orders_before"] for r in branches) == total["orders_before"]
    assert sum(r["revenue_now_qar"] for r in branches) == pytest.approx(total["revenue_now_qar"], abs=0.05)


def test_q29_compares_the_right_months(db_path):
    total = rows_of(29, db_path)[-1]
    count = "SELECT COUNT(*) FROM orders WHERE channel = 'delivery' AND ordered_at >= ? AND ordered_at < ?"
    assert total["orders_now"] == execute(db_path, count, "2025-10-01", "2026-01-01")[0][0]
    assert total["orders_before"] == execute(db_path, count, "2024-10-01", "2025-01-01")[0][0]


def test_q29_new_to_delivery_share_is_a_share(db_path):
    for row in rows_of(29, db_path):
        assert 0 <= row["new_to_delivery_revenue_pct"] <= 100


# ---------------------------------------------------------------------------
# Q30 return rates by channel
# ---------------------------------------------------------------------------

def chi_square(a, b, c, d):
    n = a + b + c + d
    return n * (a * d - b * c) ** 2 / ((a + b) * (c + d) * (a + c) * (b + d))


def test_q30_totals_match_the_database(db_path):
    rows = rows_of(30, db_path)
    total, categories = rows[-1], rows[:-1]
    assert total["category"] == "All categories"
    assert len(categories) == 13
    lines = execute(db_path, "SELECT COUNT(*) FROM order_items")[0][0]
    returned = execute(db_path, "SELECT COUNT(DISTINCT order_item_id) FROM returns")[0][0]
    assert total["in_store_lines"] + total["delivery_lines"] == lines
    assert total["in_store_returned"] + total["delivery_returned"] == returned
    assert sum(r["delivery_returned"] for r in categories) == total["delivery_returned"]


def test_q30_chi_square_matches_a_hand_calculation(db_path):
    for row in rows_of(30, db_path):
        a, c = row["in_store_returned"], row["delivery_returned"]
        b, d = row["in_store_lines"] - a, row["delivery_lines"] - c
        assert row["chi_square"] == pytest.approx(chi_square(a, b, c, d), abs=0.01)


def test_q30_recovers_the_delivery_effect_built_into_the_generator(db_path):
    total = rows_of(30, db_path)[-1]
    assert total["rate_ratio"] == pytest.approx(1.5, abs=0.3)
    assert total["delivery_vs_store"] == "Higher on delivery"


def test_q30_labels_follow_the_rules(db_path):
    for row in rows_of(30, db_path):
        back = row["in_store_returned"] + row["delivery_returned"]
        lines = row["in_store_lines"] + row["delivery_lines"]
        expected = back * row["delivery_lines"] / lines
        if expected < 5:
            assert row["delivery_vs_store"] == "Too few returns to say"
        elif row["chi_square"] < 3.84:
            assert row["delivery_vs_store"] == "No clear difference"
        else:
            assert row["delivery_vs_store"] in ("Higher on delivery", "Lower on delivery")


def test_q30_a_category_with_no_delivery_returns_does_not_break(db_path):
    rows = rows_of(30, db_path)
    assert any(r["delivery_returned"] == 0 for r in rows)


def test_readme_states_the_real_numbers(db_path, promotion_check):
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    promotions = rows_of(26, db_path)[-1]
    delivery = rows_of(29, db_path)[-1]
    returns = rows_of(30, db_path)
    unclear = sum(r["delivery_vs_store"] == "Too few returns to say" for r in returns[:-1])
    for claim in (f"Q26 gives {promotions['unit_uplift_pct']:.1f}% against a true {promotion_check['steady_true']:.1f}%",
                  f"{promotion_check['all_naive']:.1f}% against a true {promotion_check['all_true']:.1f}%",
                  f"falls {abs(promotions['profit_change_pct']):.1f}%",
                  f"Orders went from {delivery['orders_before']} to {delivery['orders_now']}",
                  f"{returns[-1]['rate_ratio']:.2f} times as often"):
        assert claim in readme
    assert unclear == 11 and "Eleven of the 13 categories" in readme


def test_all_queries_still_run_through_run_py(db_path):
    with closing(run.connect_read_only(db_path)) as conn:
        for path in run.query_files([26, 27, 28, 29, 30]):
            assert run.run_query(conn, path).rows
