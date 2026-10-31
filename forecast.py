"""A simple weekly sales forecast for each branch, tested against a baseline.

The last TEST_WEEKS full weeks are held back. The baseline and the model each
see only the weeks before that and forecast the whole test period in one go, as
they would have to in real use. The model is a straight-line fit on log revenue
with a trend and calendar effects that are known in advance. If it does not beat
the baseline, the output says so.

Usage:
    python forecast.py
    python forecast.py --db other.db
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import run
from dashboard.data import load_sql
from dashboard.findings import finish, qar

TEST_WEEKS = 13
BASELINE_WEEKS = 4
NEXT_WEEKS = 4
MODEL = "Model"
BASELINE = "Baseline"


@dataclass(frozen=True)
class Model:
    """Weights for one branch, fitted on its training weeks only."""
    weights: np.ndarray
    origin: dt.date
    correction: float

    def predict(self, weeks: list[dt.date], events: pd.DataFrame) -> np.ndarray:
        log_forecast = design_matrix(weeks, self.origin, events) @ self.weights
        return np.maximum(np.exp(log_forecast) * self.correction - 1, 0.0)


@dataclass(frozen=True)
class Backtest:
    weeks: pd.DataFrame     # branch, week_start, actual, baseline, model
    branches: pd.DataFrame  # branch, baseline_mae, model_mae, mean_actual, winner
    baseline_mae: float
    model_mae: float
    model_closer_weeks: int
    total_weeks: int
    train_end: str
    test_start: str
    test_end: str

    @property
    def model_won(self) -> bool:
        return self.model_mae < self.baseline_mae

    @property
    def branches_won(self) -> int:
        return int((self.branches["winner"] == MODEL).sum())


def to_dates(values) -> list[dt.date]:
    return [dt.date.fromisoformat(value) for value in values]


def event_days(events: pd.DataFrame, kind: str) -> set[dt.date]:
    days: set[dt.date] = set()
    for row in events[events["kind"] == kind].itertuples():
        day, last = dt.date.fromisoformat(row.start_date), dt.date.fromisoformat(row.end_date)
        while day <= last:
            days.add(day)
            day += dt.timedelta(days=1)
    return days


def calendar_features(weeks: list[dt.date], events: pd.DataFrame) -> np.ndarray:
    """Share of each week in Ramadan, Eid, the summer holidays and the days after payday."""
    ramadan, eid, summer = (event_days(events, kind) for kind in ("ramadan", "eid", "season"))
    rows = []
    for week in weeks:
        days = [week + dt.timedelta(days=i) for i in range(7)]
        rows.append([sum(d in ramadan for d in days) / 7, sum(d in eid for d in days) / 7,
                     sum(d in summer for d in days) / 7, sum(d.day <= 5 for d in days) / 7])
    return np.array(rows, dtype=float)


def design_matrix(weeks: list[dt.date], origin: dt.date, events: pd.DataFrame) -> np.ndarray:
    years_since_start = np.array([(week - origin).days / 365.25 for week in weeks])
    return np.column_stack([np.ones(len(weeks)), years_since_start, calendar_features(weeks, events)])


def fit_model(weeks: list[dt.date], revenue: np.ndarray, events: pd.DataFrame) -> Model:
    """Least squares on log revenue. Taking logs and back again would aim low on
    average, so the forecast is scaled up by the mean size of the fitted errors."""
    origin = weeks[0]
    matrix = design_matrix(weeks, origin, events)
    target = np.log1p(revenue)
    weights, *_ = np.linalg.lstsq(matrix, target, rcond=None)
    return Model(weights, origin, float(np.exp(target - matrix @ weights).mean()))


def baseline_forecast(revenue: np.ndarray, horizon: int) -> np.ndarray:
    """The average of the last few weeks before the forecast starts, held flat."""
    return np.full(horizon, float(revenue[-BASELINE_WEEKS:].mean()))


def backtest(weekly: pd.DataFrame, events: pd.DataFrame, test_weeks: int = TEST_WEEKS) -> Backtest:
    """Hold back the last test_weeks, forecast them, and score both methods."""
    all_weeks = sorted(weekly["week_start"].unique())
    held_back = all_weeks[-test_weeks:]
    cutoff = held_back[0]

    rows = []
    for branch, group in weekly.groupby("branch", sort=True):
        train = group[group["week_start"] < cutoff]
        test = group[group["week_start"] >= cutoff]
        train_weeks = to_dates(train["week_start"])
        train_revenue = train["revenue_qar"].to_numpy(dtype=float)
        held_back_dates = to_dates(test["week_start"])
        model = fit_model(train_weeks, train_revenue, events)
        rows.append(pd.DataFrame({
            "branch": branch,
            "week_start": test["week_start"].to_numpy(),
            "actual": test["revenue_qar"].to_numpy(dtype=float),
            "baseline": baseline_forecast(train_revenue, len(test)),
            "model": model.predict(held_back_dates, events),
        }))
    weeks = pd.concat(rows, ignore_index=True)
    weeks["baseline_error"] = (weeks["baseline"] - weeks["actual"]).abs()
    weeks["model_error"] = (weeks["model"] - weeks["actual"]).abs()

    branches = weeks.groupby("branch", as_index=False).agg(
        mean_actual=("actual", "mean"), baseline_mae=("baseline_error", "mean"), model_mae=("model_error", "mean"))
    branches["winner"] = np.where(branches["model_mae"] < branches["baseline_mae"], MODEL, BASELINE)

    last_train = dt.date.fromisoformat(cutoff) - dt.timedelta(days=1)
    test_end = dt.date.fromisoformat(held_back[-1]) + dt.timedelta(days=6)
    return Backtest(
        weeks=weeks,
        branches=branches,
        baseline_mae=float(weeks["baseline_error"].mean()),
        model_mae=float(weeks["model_error"].mean()),
        model_closer_weeks=int((weeks["model_error"] < weeks["baseline_error"]).sum()),
        total_weeks=len(weeks),
        train_end=last_train.isoformat(),
        test_start=cutoff,
        test_end=test_end.isoformat(),
    )


def forecast_next(weekly: pd.DataFrame, events: pd.DataFrame, use_model: bool,
                  next_weeks: int = NEXT_WEEKS) -> pd.DataFrame:
    """Forecast the weeks after the data ends, on all the weeks, with the method
    that won the held-back test."""
    last_week = dt.date.fromisoformat(weekly["week_start"].max())
    future = [last_week + dt.timedelta(days=7 * (i + 1)) for i in range(next_weeks)]
    rows = []
    for branch, group in weekly.groupby("branch", sort=True):
        revenue = group["revenue_qar"].to_numpy(dtype=float)
        if use_model:
            forecast = fit_model(to_dates(group["week_start"]), revenue, events).predict(future, events)
        else:
            forecast = baseline_forecast(revenue, next_weeks)
        rows.append(pd.DataFrame({"branch": branch, "week_start": [d.isoformat() for d in future],
                                  "forecast_qar": forecast.round(2)}))
    return pd.concat(rows, ignore_index=True)


def worst_branch(result: Backtest) -> str:
    """The branch where the model lost the most ground to the baseline."""
    gaps = result.branches["model_mae"] - result.branches["baseline_mae"]
    return result.branches.loc[gaps.idxmax(), "branch"]


def worst_branch_note(result: Backtest) -> str:
    branch = worst_branch(result)
    weeks = result.weeks[result.weeks["branch"] == branch]
    bias = 100 * (weeks["model"].sum() / weeks["actual"].sum() - 1)
    return f"Its worst branch was {branch}, where it forecast {abs(bias):.1f}% too {'high' if bias > 0 else 'low'}."


def verdict(result: Backtest) -> str:
    """The plain answer. It leads with who won and does not soften a loss."""
    change = 100 * (1 - result.model_mae / result.baseline_mae)
    numbers = (f"It was off by {qar(result.model_mae)} a week per branch on average, against "
               f"{qar(result.baseline_mae)} for the baseline")
    closer = (f"The model was closer in {result.model_closer_weeks} of {result.total_weeks} branch weeks "
              f"and won {result.branches_won} of {len(result.branches)} branches.")
    if result.model_won:
        return finish(f"The model beat the baseline on the held-back test, by {change:.1f}%. {numbers}. {closer}")
    return finish(f"The model did not beat the baseline on the held-back test. {numbers}, "
                  f"so the model was {abs(change):.1f}% worse. {closer} {worst_branch_note(result)}")


def next_weeks_finding(next_weeks: pd.DataFrame, result: Backtest) -> str:
    method = "model" if result.model_won else "baseline"
    by_branch = next_weeks.groupby("branch")["forecast_qar"].sum()
    weeks = sorted(next_weeks["week_start"].unique())
    last_day = dt.date.fromisoformat(weeks[-1]) + dt.timedelta(days=6)
    return finish(
        f"The {method} won the held-back test, so the {method} sets the forecast for {weeks[0]} to "
        f"{last_day.isoformat()}: {qar(by_branch.sum())} across all branches, with {by_branch.idxmax()} "
        f"the largest at {qar(by_branch.max())}."
    )


def load(db_path: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    weekly = load_sql("forecast/branch_weekly_revenue.sql", db_path=db_path).frame
    events = load_sql("forecast/calendar_events.sql", db_path=db_path).frame
    return weekly, events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test the weekly branch forecast against the baseline.")
    parser.add_argument("--db", default=str(run.DEFAULT_DB_PATH), help="database file (default: retail.db)")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"{db_path} not found. Create it first with: python seed.py", file=sys.stderr)
        return 1

    weekly, events = load(db_path)
    result = backtest(weekly, events)
    print(f"Trained on weeks up to {result.train_end}. Held back {result.test_start} to {result.test_end}.\n")
    table = result.branches.rename(columns={"mean_actual": "mean_weekly_revenue_qar", "baseline_mae": "baseline_mae_qar",
                                            "model_mae": "model_mae_qar"}).round(2)
    print(run.format_table(list(table.columns), [tuple(row) for row in table.astype(object).values]))
    print(f"\n{verdict(result)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
