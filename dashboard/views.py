"""The dashboard pages. Each one shows query results and a computed finding."""

from __future__ import annotations

import streamlit as st

from dashboard import charts, findings
from dashboard.data import Loaded, ensure_database, load_query


@st.cache_data(max_entries=40, show_spinner=False)
def _load(number: int, stamp: tuple[str, int]) -> Loaded:
    return load_query(number)


def query(number: int) -> Loaded:
    """Run a query file once per database build."""
    path = ensure_database()
    return _load(number, (str(path), path.stat().st_mtime_ns))


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


PAGES = {
    "revenue": ("Revenue", revenue_page),
    "seasonal": ("Ramadan and weekends", seasonal_page),
    "branches": ("Branch ranking", branches_page),
    "customers": ("Customers", customers_page),
    "baskets": ("Basket pairs", baskets_page),
}
