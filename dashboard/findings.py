"""Short written findings, computed from query results.

Nothing here is typed in by hand: names and numbers are read from the frames
the query files return, so a different seed gives different sentences. Every
finding ends with SIMULATED_NOTE because the sample data is generated.
"""

from __future__ import annotations

import pandas as pd

SIMULATED_NOTE = "Simulated data, not a real business."
WEEKEND = ("Friday", "Saturday")  # the weekend in Qatar
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December")


def finish(text: str) -> str:
    return f"{text} {SIMULATED_NOTE}"


def qar(value: float) -> str:
    return f"QAR {value:,.0f}"


def more_or_less(pct: float) -> str:
    return f"{abs(pct):.1f}% {'more' if pct >= 0 else 'less'}"


def up_or_down(pct: float) -> str:
    return f"{'up' if pct >= 0 else 'down'} {abs(pct):.1f}%"


def month_name(month: str) -> str:
    return f"{MONTH_NAMES[int(month[5:7]) - 1]} {month[:4]}"


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    return float((values * weights).sum() / weights.sum())


def revenue(monthly: pd.DataFrame) -> str:
    """From Q01."""
    by_year = monthly.groupby(monthly["month"].str[:4])["revenue_qar"].sum()
    best = monthly.loc[monthly["revenue_qar"].idxmax()]
    text = f"Revenue reached {qar(by_year.iloc[-1])} in {by_year.index[-1]}"
    if len(by_year) > 1:
        growth = 100 * (by_year.iloc[-1] / by_year.iloc[-2] - 1)
        text += f", {up_or_down(growth)} on {by_year.index[-2]}"
    text += f". The best month was {month_name(best['month'])} at {qar(best['revenue_qar'])}."
    return finish(text)


def ramadan(by_period: pd.DataFrame) -> str:
    """From Q10. The split into orders and basket uses the latest year."""
    ramadan_rows = by_period[by_period["period"] == "Ramadan"].sort_values("year")
    latest = ramadan_rows.iloc[-1]
    rest = by_period[(by_period["year"] == latest["year"]) & (by_period["period"] == "Rest of year")].iloc[0]
    order_lift = 100 * (latest["avg_daily_orders"] / rest["avg_daily_orders"] - 1)
    basket_lift = 100 * (latest["avg_order_value_qar"] / rest["avg_order_value_qar"] - 1)
    driver = "More orders" if order_lift > basket_lift else "Bigger baskets"
    text = (f"An average Ramadan day in {latest['year']} brought in {qar(latest['avg_daily_revenue_qar'])}, "
            f"{more_or_less(latest['revenue_uplift_pct'])} than the rest of that year")
    if len(ramadan_rows) > 1:
        earlier = ramadan_rows.iloc[-2]
        text += f" ({more_or_less(earlier['revenue_uplift_pct'])} in {earlier['year']})"
    text += (f". Daily orders were {up_or_down(order_lift)} and average order value was "
             f"{up_or_down(basket_lift)}. {driver} did more of the work.")
    return finish(text)


def weekend(by_weekday: pd.DataFrame) -> str:
    """From Q05. Averages are weighted by the number of days behind each row."""
    is_weekend = by_weekday["weekday"].isin(WEEKEND)
    weekend_days = by_weekday[is_weekend]
    other_days = by_weekday[~is_weekend]
    weekend_avg = weighted_mean(weekend_days["avg_revenue_qar"], weekend_days["days"])
    other_avg = weighted_mean(other_days["avg_revenue_qar"], other_days["days"])
    best = by_weekday.loc[by_weekday["avg_revenue_qar"].idxmax()]
    worst = by_weekday.loc[by_weekday["avg_revenue_qar"].idxmin()]
    lift = 100 * (weekend_avg / other_avg - 1)
    return finish(
        f"Friday and Saturday, the weekend in Qatar, averaged {qar(weekend_avg)} a day against "
        f"{qar(other_avg)} from Sunday to Thursday, {more_or_less(lift)}. "
        f"The strongest day was {best['weekday']} at {qar(best['avg_revenue_qar'])} and the "
        f"weakest was {worst['weekday']} at {qar(worst['avg_revenue_qar'])}."
    )


def branches(scorecard: pd.DataFrame, summary: pd.DataFrame) -> str:
    """From Q20 for the ranks and Q02 for the opening dates."""
    year = scorecard["year"].max()
    rows = scorecard[scorecard["year"] == year]
    leader = rows.sort_values("rank_by_daily_revenue").iloc[0]
    densest = rows.sort_values("rank_by_density").iloc[0]
    newest = summary.sort_values("opened_on").iloc[-1]["branch"]
    newest_rank = int(rows.loc[rows["branch"] == newest, "rank_by_daily_revenue"].iloc[0])
    text = (f"In {year} {leader['branch']} ranked first on revenue per trading day at "
            f"{qar(leader['revenue_per_day_qar'])}. ")
    if densest["branch"] == leader["branch"]:
        text += "It also led on sales per square metre. "
    else:
        text += f"{densest['branch']} led on sales per square metre. "
    text += f"The newest branch, {newest}, came {ordinal(newest_rank)} of {len(rows)} on daily revenue."
    return finish(text)


def rfm(segments: pd.DataFrame) -> str:
    """From Q17."""
    total = segments["customers"].sum()
    top = segments.sort_values("revenue_share_pct", ascending=False).iloc[0]
    text = (f"{top['segment']} are {top['customers']} of {total} customers "
            f"({100 * top['customers'] / total:.1f}%) and bring {top['revenue_share_pct']:.1f}% of revenue.")
    fading = segments[segments["segment"].isin(("At risk", "Lost"))]
    if not fading.empty:
        text += (f" At risk and Lost customers together are {100 * fading['customers'].sum() / total:.1f}% "
                 f"of customers and {fading['revenue_share_pct'].sum():.1f}% of revenue.")
    return finish(text)


def cohorts(retention: pd.DataFrame) -> str:
    """From Q18. A blank cell is a month after the end of the data, so it is
    left out, and each cohort counts in proportion to its size."""
    def rate(column: str) -> float:
        known = retention[retention[column].notna()]
        return weighted_mean(known[column], known["customers"])

    return finish(
        f"Weighted by cohort size, {rate('month_1_pct'):.1f}% of customers shopped in the month after "
        f"their first order, {rate('month_3_pct'):.1f}% three months after and "
        f"{rate('month_12_pct'):.1f}% twelve months after. Each figure counts only cohorts old enough "
        f"to have reached that month."
    )


def baskets(pairs: pd.DataFrame) -> str:
    """From Q19, which returns the strongest pairs by lift."""
    top = pairs.sort_values("lift", ascending=False).iloc[0]
    common = pairs.sort_values("orders_together", ascending=False).iloc[0]
    return finish(
        f"{top['product_a']} and {top['product_b']} appear together {top['lift']:.1f} times more often "
        f"than chance would suggest, in {top['orders_together']} orders. Among the {len(pairs)} strongest "
        f"pairs the most frequent is {common['product_a']} with {common['product_b']}, "
        f"in {common['orders_together']} orders."
    )
