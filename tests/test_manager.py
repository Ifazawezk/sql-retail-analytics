"""Checks for the branch manager page, its query files and its CSV."""

import datetime as dt
import io
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import run
from dashboard import data, findings, manager

ROOT = Path(__file__).resolve().parent.parent
FIRST_DAY = dt.date(2024, 1, 1)
LAST_DAY = dt.date(2025, 12, 31)
LUSAIL_OPENED = dt.date(2024, 9, 15)
AL_SADD = 1
LUSAIL = 5


def daily(db_path, branch_id, start, end):
    return data.load_sql("manager/daily_sales.sql",
                         {"branch_id": branch_id, "start_date": start, "end_date": end}, db_path).frame


def top_products(db_path, branch_id, start, end):
    return data.load_sql("manager/top_products.sql",
                         {"branch_id": branch_id, "start_date": start, "end_date": end}, db_path).frame


def scalar(db_path, sql, *params):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Query files
# ---------------------------------------------------------------------------

def test_parameterised_files_stay_out_of_the_numbered_list():
    assert all(path.parent == run.QUERY_DIR for path in run.query_files())


def test_last_day_of_the_range_keeps_its_late_orders(db_path):
    day, late_orders = sqlite3.connect(db_path).execute("""
        SELECT date(ordered_at), COUNT(*) FROM orders
        WHERE branch_id = 1 AND time(ordered_at) >= '22:00'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1
    """).fetchone()
    assert late_orders >= 1
    frame = daily(db_path, AL_SADD, day, day)
    expected = scalar(db_path, "SELECT COUNT(*) FROM orders WHERE branch_id = 1 AND date(ordered_at) = ?", day)
    assert len(frame) == 1
    assert frame.loc[0, "orders"] == expected


def test_daily_sales_add_up_to_the_whole_branch(db_path):
    frame = daily(db_path, AL_SADD, "2024-01-01", "2025-12-31")
    revenue = scalar(db_path, """
        SELECT SUM(oi.line_total) FROM orders o JOIN order_items oi USING (order_id) WHERE o.branch_id = 1""")
    units_returned = scalar(db_path, """
        SELECT SUM(r.quantity) FROM returns r JOIN order_items oi USING (order_item_id)
        JOIN orders o USING (order_id) WHERE o.branch_id = 1""")
    orders = scalar(db_path, "SELECT COUNT(*) FROM orders WHERE branch_id = 1")
    assert frame["revenue_qar"].sum() == pytest.approx(revenue, abs=0.01 * len(frame))
    assert frame["orders"].sum() == orders
    assert frame["units_returned"].sum() == units_returned


def test_days_without_orders_are_kept_as_zero(db_path):
    frame = daily(db_path, LUSAIL, "2025-01-01", "2025-12-31")
    assert len(frame) == 365
    assert (frame["orders"] == 0).any()
    assert frame["revenue_qar"].notna().all()


def test_days_before_a_branch_opened_are_left_out(db_path):
    frame = daily(db_path, LUSAIL, "2024-09-01", "2024-09-30")
    assert frame["date"].iloc[0] == LUSAIL_OPENED.isoformat()
    assert len(frame) == 16


def test_dates_entirely_before_opening_give_no_rows(db_path):
    assert daily(db_path, LUSAIL, "2024-01-01", "2024-03-31").empty


def test_returns_are_not_double_counted(tmp_path, db_path):
    """A line returned in two parts must count once in revenue."""
    copy = tmp_path / "two_returns.db"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(copy)
    source.backup(target)
    source.close()
    item, day, branch, refund = target.execute("""
        SELECT r.order_item_id, date(o.ordered_at), o.branch_id, r.refund_amount
        FROM returns r JOIN order_items oi USING (order_item_id) JOIN orders o USING (order_id)
        LIMIT 1""").fetchone()
    before = daily(db_path, branch, day, day).iloc[0]
    target.execute("""INSERT INTO returns (order_item_id, returned_on, quantity, refund_amount, reason)
                      VALUES (?, ?, 1, 1.0, 'Second part')""", (item, day))
    target.commit()
    target.close()
    after = daily(copy, branch, day, day).iloc[0]
    assert after["revenue_qar"] == before["revenue_qar"]
    assert after["units_returned"] == before["units_returned"] + 1
    assert after["refunds_qar"] == pytest.approx(before["refunds_qar"] + 1.0)


def test_top_products_respect_branch_and_dates(db_path):
    frame = top_products(db_path, LUSAIL, "2025-03-01", "2025-03-31")
    assert 0 < len(frame) <= 10
    assert list(frame["revenue_qar"]) == sorted(frame["revenue_qar"], reverse=True)
    conn = sqlite3.connect(db_path)
    expected = conn.execute("""
        SELECT ROUND(SUM(oi.line_total), 2) FROM orders o
        JOIN order_items oi USING (order_id) JOIN products p USING (product_id)
        WHERE o.branch_id = 5 AND date(o.ordered_at) BETWEEN '2025-03-01' AND '2025-03-31' AND p.name = ?
    """, (frame.loc[0, "product"],)).fetchone()[0]
    conn.close()
    assert frame.loc[0, "revenue_qar"] == expected


# ---------------------------------------------------------------------------
# Period logic
# ---------------------------------------------------------------------------

def test_period_compares_with_the_same_number_of_days_before():
    period = manager.choose_period(dt.date(2025, 3, 1), dt.date(2025, 3, 31), LUSAIL_OPENED, FIRST_DAY)
    assert period.days == 31
    assert period.previous_start == dt.date(2025, 1, 29)
    assert period.earliest == dt.date(2025, 1, 29)


def test_period_starts_when_the_branch_opened():
    period = manager.choose_period(dt.date(2024, 8, 1), dt.date(2024, 10, 31), LUSAIL_OPENED, FIRST_DAY)
    assert period.start == LUSAIL_OPENED


def test_no_comparison_when_the_earlier_period_is_cut_short():
    """Lusail's first 30 days cannot be compared with the 30 days before it opened."""
    period = manager.choose_period(LUSAIL_OPENED, LUSAIL_OPENED + dt.timedelta(days=29), LUSAIL_OPENED, FIRST_DAY)
    assert period.previous_start is None
    start_of_data = manager.choose_period(FIRST_DAY, dt.date(2024, 3, 31), dt.date(2015, 4, 12), FIRST_DAY)
    assert start_of_data.previous_start is None


def test_comparison_allowed_when_it_exactly_fits():
    start = LUSAIL_OPENED + dt.timedelta(days=30)
    period = manager.choose_period(start, start + dt.timedelta(days=29), LUSAIL_OPENED, FIRST_DAY)
    assert period.previous_start == LUSAIL_OPENED


def test_dates_before_opening_give_no_period():
    assert manager.choose_period(FIRST_DAY, dt.date(2024, 9, 14), LUSAIL_OPENED, FIRST_DAY) is None


def test_split_period_separates_current_and_previous(db_path):
    period = manager.choose_period(dt.date(2025, 3, 1), dt.date(2025, 3, 31), LUSAIL_OPENED, FIRST_DAY)
    frame = daily(db_path, LUSAIL, period.earliest.isoformat(), period.end.isoformat())
    current, previous = manager.split_period(frame, period)
    assert len(current) == len(previous) == 31
    assert previous["date"].max() < current["date"].min()


def test_starting_filters_read_a_link():
    names = ["Al Sadd", "Lusail"]
    link = {"branch": "Lusail", "start": "2025-02-01", "end": "2025-04-30"}
    assert manager.starting_filters(link, names, FIRST_DAY, LAST_DAY) == (
        "Lusail", (dt.date(2025, 2, 1), dt.date(2025, 4, 30)))


@pytest.mark.parametrize("link", [
    {"branch": "Nowhere", "start": "not-a-date", "end": "2025-13-45"},
    {"start": "2025-06-01", "end": "2025-01-01"},
    {},
])
def test_starting_filters_ignore_bad_links(link):
    branch, (start, end) = manager.starting_filters(link, ["Al Sadd", "Lusail"], FIRST_DAY, LAST_DAY)
    assert branch == "Al Sadd"
    assert (start, end) == (LAST_DAY - dt.timedelta(days=89), LAST_DAY)


def test_starting_filters_clamp_dates_to_the_data():
    _, dates = manager.starting_filters({"start": "2019-01-01", "end": "2031-01-01"},
                                        ["Al Sadd"], FIRST_DAY, LAST_DAY)
    assert dates == (FIRST_DAY, LAST_DAY)


# ---------------------------------------------------------------------------
# Totals, finding and CSV
# ---------------------------------------------------------------------------

def test_totals_handle_a_period_with_no_orders():
    empty = manager.totals(pd.DataFrame({
        "orders": [0], "delivery_orders": [0], "units_sold": [0], "revenue_qar": [0.0],
        "gross_profit_qar": [0.0], "units_returned": [0]}))
    assert empty.average_order_value is None
    assert empty.return_rate_pct is None
    shown = {m.label: m for m in manager.metrics(empty, None)}
    assert shown["Average order (QAR)"].value == "n/a"
    assert shown["Revenue (QAR)"].delta is None


def test_metrics_show_changes_only_with_a_comparison(db_path):
    frame = daily(db_path, AL_SADD, "2025-03-01", "2025-03-31")
    current = manager.totals(frame)
    assert all(m.delta is None for m in manager.metrics(current, None))
    earlier = manager.totals(daily(db_path, AL_SADD, "2025-01-29", "2025-02-28"))
    shown = {m.label: m for m in manager.metrics(current, earlier)}
    assert shown["Revenue (QAR)"].delta == f"{100 * (current.revenue / earlier.revenue - 1):+.1f}%"
    assert shown["Return rate"].delta_color == "inverse"
    assert shown["Delivery share"].delta_color == "off"


def test_finding_uses_the_filtered_numbers(db_path):
    period = manager.choose_period(dt.date(2025, 3, 1), dt.date(2025, 3, 31), LUSAIL_OPENED, FIRST_DAY)
    frame = daily(db_path, LUSAIL, period.earliest.isoformat(), period.end.isoformat())
    current_days, previous_days = manager.split_period(frame, period)
    products = top_products(db_path, LUSAIL, "2025-03-01", "2025-03-31")
    current, previous = manager.totals(current_days), manager.totals(previous_days)
    text = manager.finding("Lusail", period, current, previous, current_days, products)
    change = 100 * (current.revenue / previous.revenue - 1)
    assert text.startswith(f"Lusail took QAR {current.revenue:,.0f} from {current.orders} orders")
    assert f"{abs(change):.1f}% {'more' if change >= 0 else 'less'} than the 31 days before" in text
    assert products.iloc[0]["product"] in text
    assert text.endswith(findings.SIMULATED_NOTE)


def test_finding_for_a_period_with_no_orders_is_still_labelled():
    period = manager.Period(dt.date(2025, 1, 1), dt.date(2025, 1, 1), None)
    empty = manager.Totals(1, 0, 0, 0, 0.0, 0.0, 0)
    text = manager.finding("Al Khor", period, empty, None, pd.DataFrame(), pd.DataFrame())
    assert "had no orders" in text
    assert text.endswith(findings.SIMULATED_NOTE)


def test_csv_round_trip_matches_the_filtered_days(db_path):
    frame = daily(db_path, AL_SADD, "2025-05-01", "2025-05-31")
    parsed = pd.read_csv(io.BytesIO(manager.daily_csv(frame)))
    assert len(parsed) == 31
    assert parsed["date"].iloc[0] == "2025-05-01"
    assert parsed["date"].iloc[-1] == "2025-05-31"
    assert parsed["revenue_qar"].sum() == pytest.approx(frame["revenue_qar"].sum())
    assert set(parsed[manager.CSV_NOTE_COLUMN]) == {findings.SIMULATED_NOTE}


def test_csv_name_is_safe_for_a_file():
    period = manager.Period(dt.date(2025, 1, 1), dt.date(2025, 1, 31), None)
    assert manager.csv_name("Al Sadd", period) == "al_sadd_daily_sales_2025-01-01_to_2025-01-31.csv"


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

@pytest.fixture
def app_db(db_path, monkeypatch):
    monkeypatch.setenv(data.DB_ENV_VAR, str(db_path))


def open_manager(**link):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["view"] = "manager"
    for key, value in link.items():
        app.query_params[key] = value
    return app.run()


def finding_of(app):
    return app.info[0].value


def test_page_opens_with_a_default_branch_and_a_csv_button(app_db):
    app = open_manager()
    assert not app.exception
    assert app.selectbox[0].value == "Al Khor"
    assert finding_of(app).endswith(findings.SIMULATED_NOTE)
    assert len(app.get("download_button")) == 1


def test_link_opens_the_chosen_branch_and_dates(app_db):
    app = open_manager(branch="Lusail", start="2025-02-01", end="2025-04-30")
    assert not app.exception
    assert app.selectbox[0].value == "Lusail"
    assert "between 2025-02-01 and 2025-04-30" in finding_of(app)


def test_changing_the_branch_changes_the_finding(app_db):
    app = open_manager(branch="Lusail")
    before = finding_of(app)
    app.selectbox[0].set_value("Al Sadd").run()
    assert not app.exception
    assert finding_of(app).startswith("Al Sadd took")
    assert before != finding_of(app)


def test_changing_the_dates_changes_the_finding(app_db):
    app = open_manager(branch="Al Sadd")
    app.date_input[0].set_value((dt.date(2025, 3, 1), dt.date(2025, 3, 10))).run()
    assert not app.exception
    assert "between 2025-03-01 and 2025-03-10" in finding_of(app)


def test_half_finished_date_selection_does_not_crash(app_db):
    app = open_manager()
    app.date_input[0].set_value((dt.date(2025, 3, 1),)).run()
    assert not app.exception
    assert app.warning[0].value == "Pick an end date to see the results."
    assert len(app.get("download_button")) == 0


def test_dates_before_lusail_opened_show_a_message(app_db):
    app = open_manager(branch="Lusail", start="2024-01-01", end="2024-06-30")
    assert not app.exception
    assert "opened on 2024-09-15" in app.warning[0].value
    assert len(app.get("download_button")) == 0


def test_range_across_the_opening_starts_on_opening_day_without_a_comparison(app_db):
    app = open_manager(branch="Lusail", start="2024-09-01", end="2024-10-14")
    assert not app.exception
    assert "between 2024-09-15 and 2024-10-14" in finding_of(app)
    assert "days before" not in finding_of(app)
    assert any("no full period" in caption.value for caption in app.caption)
