"""Logic for the branch manager page. Nothing here needs Streamlit to run."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from dashboard.findings import SIMULATED_NOTE, finish, more_or_less, qar

DEFAULT_DAYS = 90
CSV_NOTE_COLUMN = "data_note"
SEASON_NAMES = {"ramadan": "Ramadan", "eid": "Eid", "season": "Summer holidays"}
UNEVEN_SHARE = 0.1  # of the days in the period


@dataclass(frozen=True)
class Period:
    start: dt.date
    end: dt.date
    previous_start: dt.date | None  # None when no full earlier period exists

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def earliest(self) -> dt.date:
        return self.previous_start or self.start


@dataclass(frozen=True)
class Totals:
    days: int
    orders: int
    delivery_orders: int
    units_sold: int
    revenue: float
    gross_profit: float
    units_returned: int

    @property
    def average_order_value(self) -> float | None:
        return self.revenue / self.orders if self.orders else None

    @property
    def gross_margin_pct(self) -> float | None:
        return 100 * self.gross_profit / self.revenue if self.revenue else None

    @property
    def delivery_share_pct(self) -> float | None:
        return 100 * self.delivery_orders / self.orders if self.orders else None

    @property
    def return_rate_pct(self) -> float | None:
        return 100 * self.units_returned / self.units_sold if self.units_sold else None


@dataclass(frozen=True)
class Metric:
    label: str
    value: str
    delta: str | None = None
    delta_color: str = "normal"


@dataclass(frozen=True)
class ChangeSplit:
    """A change in revenue, split exactly into what orders and basket size did."""
    total: float
    orders_effect: float
    basket_effect: float


def _read_date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def starting_filters(query_params: Mapping[str, str], names: list[str], first_day: dt.date,
                     last_day: dt.date) -> tuple[str, tuple[dt.date, dt.date]]:
    """Read the filters from a link. Anything missing or invalid gets a default,
    and dates are kept inside the data because the date picker rejects others."""
    branch = query_params.get("branch")
    if branch not in names:
        branch = names[0]
    default_start = max(first_day, last_day - dt.timedelta(days=DEFAULT_DAYS - 1))
    start = _read_date(query_params.get("start")) or default_start
    end = _read_date(query_params.get("end")) or last_day
    start = min(max(start, first_day), last_day)
    end = min(max(end, first_day), last_day)
    if start > end:
        start, end = default_start, last_day
    return branch, (start, end)


def choose_period(start: dt.date, end: dt.date, opened_on: dt.date, first_day: dt.date) -> Period | None:
    """Trim the dates to when the branch was open and find the period before.

    The earlier period only counts if the whole of it has data. Comparing with a
    period cut short by the opening date, or by the start of the data, would
    report a large growth figure that means nothing.
    """
    start = max(start, opened_on)
    if start > end:
        return None
    previous_start = start - dt.timedelta(days=(end - start).days + 1)
    return Period(start, end, previous_start if previous_start >= max(opened_on, first_day) else None)


def split_period(daily: pd.DataFrame, period: Period) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    is_current = daily["date"] >= period.start.isoformat()
    current = daily[is_current].reset_index(drop=True)
    return current, None if period.previous_start is None else daily[~is_current].reset_index(drop=True)


def totals(daily: pd.DataFrame) -> Totals:
    return Totals(
        days=len(daily),
        orders=int(daily["orders"].sum()),
        delivery_orders=int(daily["delivery_orders"].sum()),
        units_sold=int(daily["units_sold"].sum()),
        revenue=float(daily["revenue_qar"].sum()),
        gross_profit=float(daily["gross_profit_qar"].sum()),
        units_returned=int(daily["units_returned"].sum()),
    )


def _percent_change(now: float | None, before: float | None) -> str | None:
    if not now or not before:
        return None
    return f"{100 * (now / before - 1):+.1f}%"


def _point_change(now: float | None, before: float | None) -> str | None:
    if now is None or before is None:
        return None
    return f"{now - before:+.1f} pts"


def _shown(value: float | None, pattern: str) -> str:
    return "n/a" if value is None else pattern.format(value)


def metrics(current: Totals, previous: Totals | None) -> list[Metric]:
    before = previous or Totals(0, 0, 0, 0, 0.0, 0.0, 0)
    return [
        Metric("Revenue (QAR)", f"{current.revenue:,.0f}", _percent_change(current.revenue, before.revenue)),
        Metric("Orders", f"{current.orders:,}", _percent_change(current.orders, before.orders)),
        Metric("Average order (QAR)", _shown(current.average_order_value, "{:,.0f}"),
               _percent_change(current.average_order_value, before.average_order_value)),
        Metric("Gross margin", _shown(current.gross_margin_pct, "{:.1f}%"),
               _point_change(current.gross_margin_pct, before.gross_margin_pct)),
        Metric("Delivery share", _shown(current.delivery_share_pct, "{:.1f}%"),
               _point_change(current.delivery_share_pct, before.delivery_share_pct), "off"),
        Metric("Return rate", _shown(current.return_rate_pct, "{:.2f}%"),
               _point_change(current.return_rate_pct, before.return_rate_pct), "inverse"),
    ]


def finding(branch: str, period: Period, current: Totals, previous: Totals | None,
            daily: pd.DataFrame, products: pd.DataFrame) -> str:
    dates = f"between {period.start.isoformat()} and {period.end.isoformat()}"
    if current.orders == 0:
        return finish(f"{branch} had no orders {dates}.")
    text = f"{branch} took {qar(current.revenue)} from {current.orders:,} orders {dates}"
    if previous is not None and previous.revenue:
        change = 100 * (current.revenue / previous.revenue - 1)
        text += f", {more_or_less(change)} than the {period.days} days before"
    best = daily.loc[daily["revenue_qar"].idxmax()]
    text += f". The best day was {best['date']} at {qar(best['revenue_qar'])}."
    if not products.empty:
        top = products.iloc[0]
        text += f" The top product was {top['product']} at {qar(top['revenue_qar'])}."
    return finish(text)


def split_change(current: Totals, previous: Totals) -> ChangeSplit | None:
    """The orders effect is the orders gained or lost at the earlier average order.
    The basket effect is the change in average order on the orders taken now."""
    if not previous.orders:
        return None
    total = current.revenue - previous.revenue
    orders_effect = (current.orders - previous.orders) * previous.revenue / previous.orders
    return ChangeSplit(total, orders_effect, total - orders_effect)


def split_metrics(split: ChangeSplit) -> list[Metric]:
    return [
        Metric("Change in revenue (QAR)", f"{split.total:+,.0f}"),
        Metric("From the number of orders (QAR)", f"{split.orders_effect:+,.0f}"),
        Metric("From basket size (QAR)", f"{split.basket_effect:+,.0f}"),
    ]


def _effect(value: float, gained: str, lost: str) -> str:
    return f"{gained} added {qar(value)}" if value >= 0 else f"{lost} took away {qar(-value)}"


def change_finding(split: ChangeSplit, period: Period, changes: pd.DataFrame) -> str:
    """Say what moved revenue, naming the category that moved furthest the same way."""
    orders = _effect(split.orders_effect, "More orders", "Fewer orders")
    baskets = _effect(split.basket_effect, "bigger baskets", "smaller baskets")
    text = (f"Revenue {'rose' if split.total >= 0 else 'fell'} {qar(abs(split.total))} compared with the "
            f"{period.days} days before. {orders} and {baskets}.")
    same_way = changes[(changes["change_qar"] >= 0) == (split.total >= 0)]
    if not same_way.empty:
        top = same_way.iloc[0]
        direction = "up" if top["change_qar"] >= 0 else "down"
        text += (f" {top['category']} moved furthest, {direction} {qar(abs(top['change_qar']))}, "
                 f"mainly {top['main_product']} at {qar(abs(top['main_product_change_qar']))}.")
    return finish(text)


def season_note(seasons: pd.DataFrame, period: Period) -> str | None:
    """A warning when the two periods hold very different amounts of a season. Ramadan
    in only one of them can move revenue more than anything a branch did. A difference
    of a day or two in a month changes little, and a warning there would soon be ignored."""
    gap = (seasons["days_before"] - seasons["days_now"]).abs()
    uneven = seasons[(gap > 0) & (gap >= UNEVEN_SHARE * period.days)]
    if uneven.empty:
        return None
    counts = ". ".join(f"{SEASON_NAMES[row.kind]}: {row.days_before} of the days before, {row.days_now} of these days"
                       for row in uneven.itertuples())
    return finish(f"These dates are not a like-for-like match for the {period.days} days before. {counts}. "
                  "Part of this change is the calendar, not the branch.")


def daily_csv(daily: pd.DataFrame) -> bytes:
    """The note travels with the data, so a saved file still says it is simulated."""
    return daily.assign(**{CSV_NOTE_COLUMN: SIMULATED_NOTE}).to_csv(index=False).encode("utf-8")


def csv_name(branch: str, period: Period) -> str:
    slug = branch.lower().replace(" ", "_")
    return f"{slug}_daily_sales_{period.start.isoformat()}_to_{period.end.isoformat()}.csv"
