"""The dashboard pages. Each one shows query results and a computed finding."""

from __future__ import annotations

import datetime as dt

import streamlit as st

import forecast
from dashboard import charts, findings, manager
from dashboard.data import Loaded, ensure_database, load_query, load_sql


@st.cache_data(max_entries=40, show_spinner=False)
def _load(number: int, stamp: tuple[str, int]) -> Loaded:
    return load_query(number)


def query(number: int) -> Loaded:
    """Run a query file once per database build."""
    path = ensure_database()
    return _load(number, (str(path), path.stat().st_mtime_ns))


@st.cache_data(max_entries=40, show_spinner=False)
def _load_sql(name: str, params: tuple, stamp: tuple[str, int]) -> Loaded:
    return load_sql(name, dict(params))


def sql_file(name: str, **params) -> Loaded:
    """Run a parameterised query file, keeping only the latest few results."""
    path = ensure_database()
    return _load_sql(name, tuple(sorted(params.items())), (str(path), path.stat().st_mtime_ns))


def show_finding(text: str) -> None:
    st.info(text)


def show_chart(chart, description: str) -> None:
    st.altair_chart(chart, width="stretch", theme=None, alt=description)


def show_sources(*loaded: Loaded) -> None:
    """Every chart has a table behind it and names the file it came from."""
    with st.expander("Show the numbers"):
        for item in loaded:
            st.markdown(f"**{item.question}**")
            st.dataframe(item.frame, hide_index=True)
    st.caption("Source: " + ", ".join(f"`queries/{item.file}`" for item in loaded))


def revenue_page() -> None:
    st.header("Revenue")
    monthly, categories = query(1), query(4)
    frame = monthly.frame
    total_revenue, total_orders = frame["revenue_qar"].sum(), frame["orders"].sum()

    first, second, third = st.columns(3)
    first.metric("Revenue, two years", findings.qar(total_revenue))
    second.metric("Orders", f"{total_orders:,}")
    third.metric("Average order value", findings.qar(total_revenue / total_orders))

    show_finding(findings.revenue(frame))
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Monthly revenue by year")
        show_chart(charts.monthly_revenue(frame), "Line chart of monthly revenue for each year.")
    with right:
        st.subheader("Share of revenue by category")
        show_chart(charts.ranked_bars(categories.frame, "category", "revenue_share_pct",
                                      "Share of revenue (%)", ".1f"),
                   "Bar chart of revenue share by category.")
    show_sources(monthly, categories)


def seasonal_page() -> None:
    st.header("Ramadan and weekends")
    by_period, hours, by_weekday = query(10), query(24), query(5)

    st.subheader("Ramadan")
    show_finding(findings.ramadan(by_period.frame))
    left, right = st.columns(2)
    with left:
        st.markdown("**Average daily revenue**")
        show_chart(charts.ramadan_daily_revenue(by_period.frame),
                   "Bars of average daily revenue in Ramadan and the rest of each year.")
    with right:
        st.markdown("**When people shop**")
        show_chart(charts.ramadan_hours(hours.frame),
                   "Bars of the share of orders by time of day in Ramadan and the rest of the year.")
    show_sources(by_period, hours)

    st.subheader("Weekends")
    show_finding(findings.weekend(by_weekday.frame))
    show_chart(charts.weekday_revenue(by_weekday.frame, findings.WEEKEND),
               "Bars of average daily revenue for each day of the week.")
    show_sources(by_weekday)


def branches_page() -> None:
    st.header("Branch ranking")
    scorecard, summary = query(20), query(2)
    show_finding(findings.branches(scorecard.frame, summary.frame))

    years = sorted(scorecard.frame["year"].unique(), reverse=True)
    year = st.selectbox("Year", years)
    rows = scorecard.frame[scorecard.frame["year"] == year]
    left, right = st.columns(2)
    with left:
        st.subheader("Revenue per trading day")
        show_chart(charts.ranked_bars(rows, "branch", "revenue_per_day_qar", "QAR per trading day"),
                   "Branches ranked by revenue per trading day.")
    with right:
        st.subheader("Yearly sales per square metre")
        show_chart(charts.ranked_bars(rows, "branch", "annual_sales_per_sqm_qar", "QAR per square metre"),
                   "Branches ranked by sales per square metre.")
    st.caption("Lusail opened in September 2024, so its 2024 figures cover only the days it was open.")
    show_sources(scorecard, summary)


def customers_page() -> None:
    st.header("Customers")
    segments, retention = query(17), query(18)

    st.subheader("RFM segments")
    show_finding(findings.rfm(segments.frame))
    show_chart(charts.rfm_shares(segments.frame), "Bars of customer share and revenue share by RFM segment.")
    show_sources(segments)

    st.subheader("Cohort retention")
    show_finding(findings.cohorts(retention.frame))
    show_chart(charts.cohort_heatmap(retention.frame),
               "Heatmap of the share of each monthly cohort that shopped 1, 2, 3, 6 and 12 months later.")
    st.caption("Each cell is the share who shopped in that exact month. Blank cells fall after the end of the "
               "data. Late cohorts are small, so read them with care.")
    show_sources(retention)


def baskets_page() -> None:
    st.header("Basket pairs")
    pairs = query(19)
    show_finding(findings.baskets(pairs.frame))
    frame = pairs.frame.assign(pair=pairs.frame["product_a"] + " + " + pairs.frame["product_b"])
    show_chart(charts.ranked_bars(frame, "pair", "lift", "Lift (1.0 means no link)", ".1f",
                                  tooltip=["pair", "orders_together", "support_pct", "confidence_a_to_b", "lift"]),
               "Product pairs ranked by lift.")
    st.caption("`seed.py` adds many of these pairs on purpose, so the query is finding patterns that were put there.")
    show_sources(pairs)


def show_period_metrics(current: manager.Totals, previous: manager.Totals | None) -> None:
    columns = st.columns(6)
    for column, metric in zip(columns, manager.metrics(current, previous)):
        column.metric(metric.label, metric.value, delta=metric.delta, delta_color=metric.delta_color)


def manager_page() -> None:
    st.header("Branch manager")
    branches = sql_file("manager/branch_list.sql").frame
    first_day = dt.date.fromisoformat(branches["first_order_day"].min())
    last_day = dt.date.fromisoformat(branches["last_order_day"].max())
    names = list(branches["branch"])

    # Links can open the page on a branch and dates. They only set the starting
    # point, so afterwards the filters belong to the person using them.
    if "manager_branch" not in st.session_state:
        st.session_state["manager_branch"], st.session_state["manager_dates"] = manager.starting_filters(
            st.query_params, names, first_day, last_day)

    left, right = st.columns([1, 2])
    branch = left.selectbox("Branch", names, key="manager_branch")
    dates = right.date_input("Dates", key="manager_dates", min_value=first_day, max_value=last_day)
    if len(dates) != 2:
        st.warning("Pick an end date to see the results.")
        return

    row = branches[branches["branch"] == branch].iloc[0]
    period = manager.choose_period(dates[0], dates[1], dt.date.fromisoformat(row["opened_on"]), first_day)
    if period is None:
        st.warning(f"{branch} opened on {row['opened_on']}, after these dates. Pick later dates.")
        return
    if period.start > dates[0]:
        st.caption(f"{branch} opened on {row['opened_on']}, so the figures start on that day.")

    params = {"branch_id": int(row["branch_id"]), "end_date": period.end.isoformat()}
    daily = sql_file("manager/daily_sales.sql", start_date=period.earliest.isoformat(), **params)
    products = sql_file("manager/top_products.sql", start_date=period.start.isoformat(), **params)
    current_days, previous_days = manager.split_period(daily.frame, period)
    current = manager.totals(current_days)
    previous = None if previous_days is None else manager.totals(previous_days)

    show_period_metrics(current, previous)
    if previous is None:
        st.caption("There is no full period of the same length before these dates, so changes are not shown.")
    else:
        st.caption(f"Changes compare with the {period.days} days before.")
    show_finding(manager.finding(branch, period, current, previous, current_days, products.frame))

    st.subheader("Revenue by day")
    show_chart(charts.daily_revenue(current_days), "Daily revenue with a 7-day average line.")

    st.subheader("Top products")
    if products.frame.empty:
        st.caption("No products were sold in these dates.")
    else:
        show_chart(charts.ranked_bars(products.frame, "product", "revenue_qar", "Revenue (QAR)",
                                      tooltip=["product", "category", "units_sold", "revenue_qar",
                                               "gross_margin_pct"]),
                   "The top products at this branch by revenue.")

    st.download_button("Download daily sales as CSV", manager.daily_csv(current_days),
                       file_name=manager.csv_name(branch, period), mime="text/csv")
    st.caption("The file has one row per day the branch was open in these dates. Its last column says the "
               "data is simulated.")
    show_sources(daily, products)


def forecast_page() -> None:
    st.header("Sales forecast")
    weekly, events = sql_file("forecast/branch_weekly_revenue.sql"), sql_file("forecast/calendar_events.sql")
    result = forecast.backtest(weekly.frame, events.frame)
    next_weeks = forecast.forecast_next(weekly.frame, events.frame, use_model=result.model_won)

    show_finding(forecast.verdict(result))
    first, second, third = st.columns(3)
    first.metric("Baseline error (QAR a week)", f"{result.baseline_mae:,.0f}")
    second.metric("Model error (QAR a week)", f"{result.model_mae:,.0f}")
    third.metric("Model closer", f"{result.model_closer_weeks} of {result.total_weeks} weeks")
    st.caption(f"Both forecasts were made from data up to {result.train_end} and scored on the "
               f"{forecast.TEST_WEEKS} weeks from {result.test_start} to {result.test_end}. Error is the average "
               f"gap between forecast and actual revenue for one branch in one week. The baseline is the average "
               f"of the last {forecast.BASELINE_WEEKS} weeks before the test.")

    st.subheader("Error by branch")
    show_chart(charts.forecast_errors(result.branches), "Average weekly forecast error by branch and method.")

    st.subheader("Held-back weeks")
    names = list(result.branches["branch"])
    branch = st.selectbox("Branch", names, index=names.index(forecast.worst_branch(result)), key="forecast_branch")
    history = weekly.frame[weekly.frame["branch"] == branch].tail(forecast.TEST_WEEKS * 2)
    held_back = result.weeks[result.weeks["branch"] == branch]
    show_chart(charts.forecast_weeks(history, held_back), "Actual weekly revenue with both forecasts.")

    st.subheader("Next four weeks")
    show_finding(forecast.next_weeks_finding(next_weeks, result))
    table = next_weeks.pivot(index="branch", columns="week_start", values="forecast_qar").reset_index()
    st.dataframe(table, hide_index=True)
    st.caption("Forecast revenue in QAR for the week starting on each date. The sample calendar stops at the end "
               "of 2025, so the forecast only goes four weeks ahead.")
    show_sources(weekly, events)


PAGES = {
    "revenue": ("Revenue", revenue_page),
    "seasonal": ("Ramadan and weekends", seasonal_page),
    "branches": ("Branch ranking", branches_page),
    "customers": ("Customers", customers_page),
    "baskets": ("Basket pairs", baskets_page),
    "manager": ("Branch manager", manager_page),
    "forecast": ("Sales forecast", forecast_page),
}
