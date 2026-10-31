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


def promotions(uplift: pd.DataFrame) -> str:
    """From Q26. The total row is the reliable one, as single categories are thin."""
    total = uplift[uplift["category"] == "All steady sellers"].iloc[0]
    change = total["profit_change_pct"]
    answer = "more than covered the discount" if change > 0 else "did not cover the discount"
    return finish(
        f"In a promotion week, steady sellers sold {more_or_less(total['unit_uplift_pct'])} units per 100 orders, "
        f"while gross profit per 100 orders was {up_or_down(change)}. The extra volume {answer}. "
        f"This covers {total['products']} products and {total['promo_weeks']} promotion weeks."
    )


def lifetime_value(value: pd.DataFrame) -> str:
    """From Q27. Only cohorts old enough for a 12-month figure are compared."""
    known = value[value["value_12m_qar"].notna()]
    best = known.loc[known["value_12m_qar"].idxmax()]
    worst = known.loc[known["value_12m_qar"].idxmin()]
    average = weighted_mean(known["value_12m_qar"], known["customers"])
    return finish(
        f"A customer was worth {qar(average)} in gross profit after refunds over their first 12 months, "
        f"across the {len(known)} cohorts old enough to measure. The {best['joined_quarter']} joiners were worth "
        f"the most at {qar(best['value_12m_qar'])} and the {worst['joined_quarter']} joiners the least at "
        f"{qar(worst['value_12m_qar'])}."
    )


def stockouts(gaps: pd.DataFrame) -> str:
    """From Q28. The generator has no stock-outs, so a flag here is a false alarm."""
    top = gaps.iloc[0]
    flagged = int((gaps["assessment"] == "Likely stock-out").sum())
    return finish(
        f"The most surprising gap was {top['product']} at {top['branch']}, with no sale in {top['gap_days']} days "
        f"against {top['expected_sales']:.1f} expected. {flagged} of the {len(gaps)} strongest gaps cross the line "
        f"for a likely stock-out. The generator never takes a product off the shelf, so these gaps are chance."
    )


def delivery(growth: pd.DataFrame) -> str:
    """From Q29. Branch counts are small, so this reads the total row."""
    total = growth[growth["branch"] == "All branches"].iloc[0]
    return finish(
        f"Delivery revenue went from {qar(total['revenue_before_qar'])} to {qar(total['revenue_now_qar'])} "
        f"and orders from {total['orders_before']} to {total['orders_now']}. More orders account for "
        f"{qar(total['orders_effect_qar'])} of the change and basket size for {qar(total['basket_effect_qar'])}. "
        f"Customers new to delivery brought {total['new_to_delivery_revenue_pct']:.1f}% of the latest revenue."
    )


def returns_by_channel(rates: pd.DataFrame) -> str:
    """From Q30. Most categories have too few returns to judge on their own."""
    total = rates[rates["category"] == "All categories"].iloc[0]
    categories = rates[rates["category"] != "All categories"]
    unclear = int((categories["delivery_vs_store"] == "Too few returns to say").sum())
    costliest = categories.loc[categories["refunds_pct_of_gross_profit"].idxmax()]
    return finish(
        f"Delivered lines came back at {total['delivery_rate_pct']:.2f}% against {total['in_store_rate_pct']:.2f}% "
        f"in store, {total['rate_ratio']:.2f} times as often. {unclear} of {len(categories)} categories have too "
        f"few returns to judge alone. Refunds cost the most in {costliest['category']}, at "
        f"{costliest['refunds_pct_of_gross_profit']:.1f}% of its gross profit."
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
