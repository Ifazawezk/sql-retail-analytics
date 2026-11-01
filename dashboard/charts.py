"""Altair charts for the dashboard. They draw frames and hold no SQL or numbers."""

from __future__ import annotations

import altair as alt
import pandas as pd

SURFACE = "#ffffff"
INK = "#52514e"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
MUTED = "#c3c2b7"
# Colour-blind checked in this order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEK = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
RETENTION_COLUMNS = {
    "month_1_pct": "Month 1", "month_2_pct": "Month 2", "month_3_pct": "Month 3",
    "month_6_pct": "Month 6", "month_12_pct": "Month 12",
}
ROW_HEIGHT = 28
BAR_THICKNESS = 14


def finish(chart: alt.TopLevelMixin, height: int = 300) -> alt.TopLevelMixin:
    return (
        chart.properties(height=height)
        .configure_view(stroke=None)
        .configure_axis(gridColor=GRID, domainColor=BASELINE, tickColor=BASELINE, labelColor=INK,
                        titleColor=INK, labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
        .configure_legend(labelColor=INK, labelFontSize=12, orient="top", title=None)
    )


def ranked_bars(frame: pd.DataFrame, label: str, value: str, title: str, number_format: str = ",.0f",
                tooltip: list | None = None) -> alt.TopLevelMixin:
    """Horizontal bars, biggest first, with the value at the end of each bar."""
    y = alt.Y(f"{label}:N", sort=alt.EncodingSortField(field=value, order="descending"), title=None,
              axis=alt.Axis(labelLimit=320, ticks=False))
    x = alt.X(f"{value}:Q", title=title, axis=alt.Axis(format=number_format))
    base = alt.Chart(frame).encode(y=y, x=x, tooltip=tooltip or [label, alt.Tooltip(value, format=number_format)])
    bars = base.mark_bar(color=BLUE, height=BAR_THICKNESS, cornerRadiusEnd=4)
    labels = base.mark_text(align="left", dx=5, color=INK).encode(text=alt.Text(f"{value}:Q", format=number_format))
    return finish(bars + labels, height=max(160, ROW_HEIGHT * len(frame)))


def grouped_bars(frame: pd.DataFrame, group: str, series: str, value: str, title: str, *,
                 group_order: list | None = None, colors: list[str] | None = None,
                 number_format: str = ",.0f", label_expression: str = "datum.label",
                 label_angle: int = 0) -> alt.TopLevelMixin:
    """Two or more bars side by side for each group. `frame` is in long form."""
    order = list(dict.fromkeys(frame[series]))
    return finish(
        alt.Chart(frame)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(f"{group}:N", sort=group_order, title=None, scale=alt.Scale(paddingInner=0.4),
                    axis=alt.Axis(labelAngle=label_angle, labelLimit=240, ticks=False,
                                  labelExpr=label_expression)),
            xOffset=alt.XOffset(f"{series}:N", sort=order, scale=alt.Scale(paddingInner=0.08)),
            y=alt.Y(f"{value}:Q", title=title, axis=alt.Axis(format=number_format)),
            color=alt.Color(f"{series}:N", sort=order,
                            scale=alt.Scale(domain=order, range=colors or SERIES[:len(order)])),
            tooltip=[group, series, alt.Tooltip(value, format=number_format)],
        )
    )


def daily_revenue(daily: pd.DataFrame) -> alt.TopLevelMixin:
    """Each day as a quiet bar. The 7-day average starts once seven days exist."""
    data = daily.assign(
        day=pd.to_datetime(daily["date"]),
        average=daily["revenue_qar"].rolling(7).mean().round(2),
    )
    x = alt.X("day:T", title=None, axis=alt.Axis(format="%d %b %y", grid=False, labelAngle=0))
    bars = alt.Chart(data).mark_bar(color=MUTED).encode(
        x=x, y=alt.Y("revenue_qar:Q", title="Revenue (QAR)", axis=alt.Axis(format=",.0f")),
        tooltip=["date", alt.Tooltip("revenue_qar", format=",.2f", title="Revenue (QAR)"), "orders"],
    )
    line = alt.Chart(data).mark_line(color=BLUE, strokeWidth=2).encode(
        x=x, y="average:Q",
        tooltip=["date", alt.Tooltip("average", format=",.2f", title="7-day average (QAR)")],
    )
    return finish(bars + line, height=280)


def lifetime_value(value: pd.DataFrame) -> alt.TopLevelMixin:
    """Blank cells are cohorts too young for that figure, so they have no bar."""
    labels = {"value_3m_qar": "3 months", "value_6m_qar": "6 months", "value_12m_qar": "12 months"}
    data = value.melt(id_vars="joined_quarter", value_vars=list(labels), var_name="after",
                      value_name="value_qar").dropna(subset=["value_qar"])
    data["after"] = data["after"].map(labels)
    return grouped_bars(data, "joined_quarter", "after", "value_qar", "Gross profit per customer (QAR)",
                        colors=[SERIES[0], SERIES[1], SERIES[2]])


def delivery_effects(growth: pd.DataFrame) -> alt.TopLevelMixin:
    labels = {"orders_effect_qar": "More orders", "basket_effect_qar": "Basket size"}
    rows = growth[growth["branch"] != "All branches"]
    data = rows.melt(id_vars="branch", value_vars=list(labels), var_name="effect", value_name="change_qar")
    data["effect"] = data["effect"].map(labels)
    return grouped_bars(data, "branch", "effect", "change_qar", "Change in delivery revenue (QAR)",
                        colors=[BLUE, MUTED])


def return_rates(rates: pd.DataFrame) -> alt.TopLevelMixin:
    labels = {"in_store_rate_pct": "In store", "delivery_rate_pct": "Delivery"}
    rows = rates[rates["category"] != "All categories"]
    data = rows.melt(id_vars="category", value_vars=list(labels), var_name="channel", value_name="rate_pct")
    data["channel"] = data["channel"].map(labels)
    return grouped_bars(data, "category", "channel", "rate_pct", "Lines returned (%)",
                        group_order=list(rows["category"]), colors=[MUTED, BLUE], number_format=".1f",
                        label_angle=-30)


def forecast_errors(branches: pd.DataFrame) -> alt.TopLevelMixin:
    data = branches.melt(id_vars="branch", value_vars=["baseline_mae", "model_mae"],
                         var_name="method", value_name="error_qar")
    data["method"] = data["method"].map({"baseline_mae": "Baseline", "model_mae": "Model"})
    return grouped_bars(data, "branch", "method", "error_qar", "Average weekly error (QAR)",
                        colors=[MUTED, BLUE])


def forecast_weeks(history: pd.DataFrame, held_back: pd.DataFrame) -> alt.TopLevelMixin:
    """Actual revenue, then the two forecasts over the held-back weeks."""
    actual = history.rename(columns={"revenue_qar": "revenue"}).assign(series="Actual")
    forecasts = held_back.melt(id_vars="week_start", value_vars=["baseline", "model"],
                               var_name="series", value_name="revenue")
    forecasts["series"] = forecasts["series"].map({"baseline": "Baseline", "model": "Model"})
    data = pd.concat([actual[["week_start", "series", "revenue"]], forecasts], ignore_index=True)
    data["week"] = pd.to_datetime(data["week_start"])
    return finish(
        alt.Chart(data)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("week:T", title="Week starting", axis=alt.Axis(format="%d %b %y", grid=False, labelAngle=0)),
            y=alt.Y("revenue:Q", title="Weekly revenue (QAR)", axis=alt.Axis(format=",.0f")),
            color=alt.Color("series:N", sort=["Actual", "Baseline", "Model"],
                            scale=alt.Scale(domain=["Actual", "Baseline", "Model"], range=[INK, SERIES[1], BLUE])),
            tooltip=["week_start", "series", alt.Tooltip("revenue", format=",.2f", title="Revenue (QAR)")],
        ),
        height=300,
    )


def category_change(changes: pd.DataFrame) -> alt.TopLevelMixin:
    """Bars either side of zero, biggest move first. Side and sign show the direction
    as well as the colour, so it never rests on colour alone."""
    rise, fall = "Rose", "Fell"
    data = changes.assign(direction=[rise if value >= 0 else fall for value in changes["change_qar"]])
    room = 1.3  # keeps the value labels inside the plot
    extent = [min(0.0, data["change_qar"].min() * room), max(0.0, data["change_qar"].max() * room)]
    base = alt.Chart(data).encode(
        y=alt.Y("category:N", sort=list(data["category"]), title=None,
                axis=alt.Axis(labelLimit=240, ticks=False, domain=False)),
        x=alt.X("change_qar:Q", title="Change in revenue (QAR)", axis=alt.Axis(format=",.0f", tickCount=6),
                scale=alt.Scale(domain=extent, nice=False)),
        tooltip=["category", alt.Tooltip("revenue_before_qar", format=",.2f", title="Before (QAR)"),
                 alt.Tooltip("revenue_now_qar", format=",.2f", title="Now (QAR)"),
                 alt.Tooltip("change_qar", format="+,.2f", title="Change (QAR)"),
                 alt.Tooltip("main_product", title="Main product"),
                 alt.Tooltip("main_product_change_qar", format="+,.2f", title="Its change (QAR)")],
    )
    bars = base.mark_bar(height=BAR_THICKNESS, cornerRadiusEnd=4).encode(
        color=alt.Color("direction:N", sort=[rise, fall], scale=alt.Scale(domain=[rise, fall], range=[BLUE, SERIES[1]])))
    rises = base.transform_filter(alt.datum.change_qar >= 0).mark_text(align="left", dx=5, color=INK)
    falls = base.transform_filter(alt.datum.change_qar < 0).mark_text(align="right", dx=-5, color=INK)
    label = alt.Text("change_qar:Q", format="+,.0f")
    zero = alt.Chart(pd.DataFrame({"zero": [0]})).mark_rule(color=BASELINE).encode(x="zero:Q")
    return finish(bars + zero + rises.encode(text=label) + falls.encode(text=label),
                  height=max(160, ROW_HEIGHT * len(data)))


def monthly_revenue(monthly: pd.DataFrame) -> alt.TopLevelMixin:
    data = monthly.assign(
        year=monthly["month"].str[:4],
        month_label=[MONTHS[int(m[5:7]) - 1] for m in monthly["month"]],
    )
    base = alt.Chart(data).encode(
        x=alt.X("month_label:N", sort=MONTHS, title=None, axis=alt.Axis(labelAngle=0, grid=False)),
        y=alt.Y("revenue_qar:Q", title="Revenue (QAR)", axis=alt.Axis(format=",.0f")),
        color=alt.Color("year:N", scale=alt.Scale(range=SERIES[:2])),
        tooltip=["month", alt.Tooltip("revenue_qar", format=",.2f", title="Revenue (QAR)"), "orders"],
    )
    lines = base.mark_line(strokeWidth=2)
    points = base.mark_point(size=64, filled=True, opacity=1, stroke=SURFACE, strokeWidth=2)
    return finish(lines + points, height=320)


def ramadan_daily_revenue(by_period: pd.DataFrame) -> alt.TopLevelMixin:
    return grouped_bars(by_period, "year", "period", "avg_daily_revenue_qar", "Average daily revenue (QAR)",
                        colors=[BLUE, MUTED])


def ramadan_hours(hours: pd.DataFrame) -> alt.TopLevelMixin:
    data = hours.melt(id_vars="time_band", value_vars=["ramadan_share_pct", "other_share_pct"],
                      var_name="period", value_name="share_pct")
    data["period"] = data["period"].map({"ramadan_share_pct": "Ramadan", "other_share_pct": "Rest of year"})
    return grouped_bars(data, "time_band", "period", "share_pct", "Share of orders (%)",
                        group_order=list(hours["time_band"]), colors=[BLUE, MUTED], number_format=".1f",
                        # "Morning (07:00-11:59)" becomes two lines so the labels do not collide.
                        label_expression="split(replace(replace(datum.label, ' (', '|'), ')', ''), '|')")


def weekday_revenue(by_weekday: pd.DataFrame, weekend: tuple[str, ...]) -> alt.TopLevelMixin:
    data = by_weekday.assign(
        part=["Weekend" if day in weekend else "Sunday to Thursday" for day in by_weekday["weekday"]]
    )
    return finish(
        alt.Chart(data)
        .mark_bar(size=34, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("weekday:N", sort=WEEK, title=None, axis=alt.Axis(labelAngle=0, ticks=False)),
            y=alt.Y("avg_revenue_qar:Q", title="Average daily revenue (QAR)", axis=alt.Axis(format=",.0f")),
            color=alt.Color("part:N", scale=alt.Scale(domain=["Weekend", "Sunday to Thursday"],
                                                      range=[BLUE, MUTED])),
            tooltip=["weekday", alt.Tooltip("avg_revenue_qar", format=",.2f", title="Average daily revenue (QAR)"),
                     alt.Tooltip("avg_orders", title="Average orders")],
        )
    )


def rfm_shares(segments: pd.DataFrame) -> alt.TopLevelMixin:
    data = segments.assign(customer_share_pct=100 * segments["customers"] / segments["customers"].sum())
    data = data.melt(id_vars="segment", value_vars=["customer_share_pct", "revenue_share_pct"],
                     var_name="measure", value_name="share_pct")
    data["measure"] = data["measure"].map({"customer_share_pct": "Share of customers",
                                           "revenue_share_pct": "Share of revenue"})
    return grouped_bars(data, "segment", "measure", "share_pct", "Share (%)",
                        group_order=list(segments["segment"]), colors=[MUTED, BLUE], number_format=".1f")


def cohort_heatmap(retention: pd.DataFrame) -> alt.TopLevelMixin:
    """Blank cells are months after the end of the data, so they stay blank."""
    data = retention.assign(label=retention["cohort"] + " (" + retention["customers"].astype(str) + ")")
    data = data.melt(id_vars=["label", "cohort", "customers"], value_vars=list(RETENTION_COLUMNS),
                     var_name="column", value_name="retained_pct").dropna(subset=["retained_pct"])
    data["months_later"] = data["column"].map(RETENTION_COLUMNS)
    return finish(
        alt.Chart(data)
        .mark_rect(cornerRadius=2, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("months_later:N", sort=list(RETENTION_COLUMNS.values()), title=None,
                    axis=alt.Axis(labelAngle=0, orient="top", ticks=False, domain=False)),
            y=alt.Y("label:N", sort=None, title="First order month (customers)",
                    axis=alt.Axis(ticks=False, domain=False)),
            color=alt.Color("retained_pct:Q", title="Shopped that month (%)",
                            scale=alt.Scale(range=["#cde2fb", "#0d366b"], domainMin=0),
                            legend=alt.Legend(orient="right", title="Retained (%)")),
            tooltip=["cohort", "customers", "months_later",
                     alt.Tooltip("retained_pct", title="Retained (%)", format=".1f")],
        ),
        height=22 * len(retention),
    )
