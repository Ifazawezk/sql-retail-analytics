"""Checks for the weekly forecast, its baseline and the held-back test."""

import datetime as dt
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import forecast
from dashboard import data, findings

ROOT = Path(__file__).resolve().parent.parent
EVENTS = pd.DataFrame({
    "name": ["Ramadan 2025", "Eid 2025", "Summer 2025"],
    "kind": ["ramadan", "eid", "season"],
    "start_date": ["2025-03-01", "2025-03-30", "2025-07-01"],
    "end_date": ["2025-03-29", "2025-04-01", "2025-08-31"],
})


@pytest.fixture(scope="session")
def loaded(db_path):
    return forecast.load(db_path)


@pytest.fixture(scope="session")
def result(loaded):
    return forecast.backtest(*loaded)


def mondays(first, count):
    start = dt.date.fromisoformat(first)
    return [start + dt.timedelta(days=7 * i) for i in range(count)]


def weekly_frame(branch, weeks, revenue):
    return pd.DataFrame({"branch": branch, "week_start": [w.isoformat() for w in weeks],
                         "orders": 10, "revenue_qar": revenue})


def backtest_from(branches):
    """A Backtest built by hand from {branch: (mean_actual, baseline_mae, model_mae)}."""
    rows, weeks = [], []
    for name, (actual, baseline_mae, model_mae) in branches.items():
        rows.append({"branch": name, "mean_actual": actual, "baseline_mae": baseline_mae, "model_mae": model_mae,
                     "winner": forecast.MODEL if model_mae < baseline_mae else forecast.BASELINE})
        weeks.append({"branch": name, "week_start": "2025-01-06", "actual": actual,
                      "baseline": actual + baseline_mae, "model": actual + model_mae})
    table = pd.DataFrame(rows)
    return forecast.Backtest(
        weeks=pd.DataFrame(weeks), branches=table,
        baseline_mae=float(table["baseline_mae"].mean()), model_mae=float(table["model_mae"].mean()),
        model_closer_weeks=1, total_weeks=len(table), train_end="2025-01-05",
        test_start="2025-01-06", test_end="2025-01-12",
    )


# ---------------------------------------------------------------------------
# Weekly data
# ---------------------------------------------------------------------------

def test_every_week_starts_on_a_monday(loaded):
    weekly, _ = loaded
    days = pd.to_datetime(weekly["week_start"])
    assert (days.dt.day_of_week == 0).all()


def test_part_weeks_are_left_out(loaded):
    weekly, _ = loaded
    assert weekly["week_start"].max() == "2025-12-22"  # the last 3 days of 2025 are not a full week
    lusail = weekly[weekly["branch"] == "Lusail"]
    assert lusail["week_start"].min() == "2024-09-16"  # opened on Sunday 2024-09-15


def test_weekly_revenue_matches_the_orders(loaded, db_path):
    weekly, _ = loaded
    row = weekly[(weekly["branch"] == "Al Sadd") & (weekly["week_start"] == "2025-03-03")].iloc[0]
    conn = sqlite3.connect(db_path)
    orders, revenue = conn.execute("""
        SELECT COUNT(DISTINCT o.order_id), SUM(oi.line_total) FROM orders o
        JOIN order_items oi USING (order_id) JOIN branches b USING (branch_id)
        WHERE b.name = 'Al Sadd' AND date(o.ordered_at) BETWEEN '2025-03-03' AND '2025-03-09'
    """).fetchone()
    conn.close()
    assert row["orders"] == orders
    assert row["revenue_qar"] == pytest.approx(revenue, abs=0.01)


def test_only_the_part_weeks_are_missing_from_the_total(loaded, db_path):
    weekly, _ = loaded
    conn = sqlite3.connect(db_path)
    outside, = conn.execute("""
        SELECT SUM(oi.line_total) FROM orders o JOIN order_items oi USING (order_id)
        WHERE date(o.ordered_at) >= '2025-12-29'
           OR (o.branch_id = 5 AND date(o.ordered_at) < '2024-09-16')
    """).fetchone()
    total, = conn.execute("SELECT SUM(line_total) FROM order_items").fetchone()
    conn.close()
    assert weekly["revenue_qar"].sum() + outside == pytest.approx(total, abs=0.01 * len(weekly))


def test_a_full_week_with_no_orders_stays_in_as_zero(loaded):
    weekly, _ = loaded
    assert (weekly["revenue_qar"] == 0).any()


# ---------------------------------------------------------------------------
# Calendar features
# ---------------------------------------------------------------------------

def test_calendar_features_are_shares_of_the_week():
    weeks = [dt.date(2025, 2, 24), dt.date(2025, 3, 3), dt.date(2025, 3, 31), dt.date(2025, 7, 7),
             dt.date(2025, 5, 12)]
    features = forecast.calendar_features(weeks, EVENTS)
    assert features[0, 0] == pytest.approx(2 / 7)   # 1 and 2 March fall in Ramadan
    assert features[1, 0] == 1
    assert features[2, 1] == pytest.approx(2 / 7)   # the last 2 days of Eid
    assert features[3, 2] == 1
    assert features[4].sum() == 0                   # an ordinary week after the 5th
    assert features[1, 3] == pytest.approx(3 / 7)   # 3, 4 and 5 March follow payday


# ---------------------------------------------------------------------------
# Held-back test
# ---------------------------------------------------------------------------

def test_the_test_period_is_held_back(result):
    assert result.total_weeks == 5 * forecast.TEST_WEEKS
    assert result.train_end < result.test_start
    assert result.test_start == "2025-09-29"
    assert result.test_end == "2025-12-28"
    assert (result.weeks.groupby("branch").size() == forecast.TEST_WEEKS).all()


def test_changing_the_held_back_weeks_changes_neither_forecast(loaded, result):
    weekly, events = loaded
    tampered = weekly.copy()
    held_back = tampered["week_start"] >= result.test_start
    tampered.loc[held_back, "revenue_qar"] *= 10
    changed = forecast.backtest(tampered, events)
    assert changed.weeks["baseline"].tolist() == pytest.approx(result.weeks["baseline"].tolist())
    assert changed.weeks["model"].tolist() == pytest.approx(result.weeks["model"].tolist())
    assert changed.weeks["actual"].sum() == pytest.approx(10 * result.weeks["actual"].sum())


def test_baseline_is_the_last_four_training_weeks(loaded, result):
    weekly, _ = loaded
    train = weekly[(weekly["branch"] == "Lusail") & (weekly["week_start"] < result.test_start)]
    expected = train["revenue_qar"].tail(4).mean()
    assert set(result.weeks.loc[result.weeks["branch"] == "Lusail", "baseline"].round(6)) == {round(expected, 6)}


def test_errors_are_computed_from_forecast_and_actual(result):
    weeks = result.weeks
    assert result.model_mae == pytest.approx((weeks["model"] - weeks["actual"]).abs().mean())
    assert result.baseline_mae == pytest.approx((weeks["baseline"] - weeks["actual"]).abs().mean())
    closer = ((weeks["model"] - weeks["actual"]).abs() < (weeks["baseline"] - weeks["actual"]).abs()).sum()
    assert result.model_closer_weeks == closer


def test_model_finds_a_planted_summer_dip_and_beats_the_baseline():
    """On clean data with a known pattern the model must win, or it is broken."""
    weeks = mondays("2024-01-01", 91)
    events = pd.DataFrame({"name": ["Summer 2024", "Summer 2025"], "kind": ["season", "season"],
                           "start_date": ["2024-07-01", "2025-07-01"], "end_date": ["2024-08-31", "2025-08-31"]})
    summer = forecast.calendar_features(weeks, events)[:, 2]
    revenue = 1000 * np.exp(0.2 * np.arange(91) / 52 - 0.5 * summer)
    outcome = forecast.backtest(weekly_frame("Test", weeks, revenue), events)
    assert outcome.model_won
    assert outcome.model_mae < 0.05 * outcome.baseline_mae
    assert "beat the baseline" in forecast.verdict(outcome)
    assert "did not beat" not in forecast.verdict(outcome)


def test_forecast_is_never_negative():
    weeks = mondays("2024-01-01", 60)
    revenue = np.linspace(500, 0, 60)
    model = forecast.fit_model(weeks, revenue, EVENTS)
    assert (model.predict(mondays("2026-06-01", 8), EVENTS) >= 0).all()


# ---------------------------------------------------------------------------
# Saying who won
# ---------------------------------------------------------------------------

def test_a_loss_is_stated_plainly_and_names_the_worst_branch():
    outcome = backtest_from({"North": (1000.0, 100.0, 300.0), "South": (500.0, 80.0, 70.0)})
    text = forecast.verdict(outcome)
    assert not outcome.model_won
    assert text.startswith("The model did not beat the baseline")
    assert "worse" in text
    assert "Its worst branch was North, where it forecast 30.0% too high." in text
    assert text.endswith(findings.SIMULATED_NOTE)


def test_a_tie_does_not_count_as_a_win():
    outcome = backtest_from({"North": (1000.0, 100.0, 100.0)})
    assert not outcome.model_won
    assert "did not beat" in forecast.verdict(outcome)


def test_a_win_is_labelled_as_simulated_too():
    text = forecast.verdict(backtest_from({"North": (1000.0, 300.0, 100.0)}))
    assert text.startswith("The model beat the baseline")
    assert text.endswith(findings.SIMULATED_NOTE)


def test_verdict_matches_the_real_numbers(result):
    text = forecast.verdict(result)
    assert f"QAR {result.model_mae:,.0f} a week" in text
    assert f"QAR {result.baseline_mae:,.0f} for the baseline" in text
    assert ("did not beat" in text) == (not result.model_won)
    assert text.endswith(findings.SIMULATED_NOTE)


def test_readme_states_the_real_result(result):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert ("**The model did not beat the baseline.**" in readme) == (not result.model_won)
    assert f"by QAR {result.model_mae:,.0f} a week per branch on average" in readme
    assert f"against QAR {result.baseline_mae:,.0f} for the baseline" in readme


# ---------------------------------------------------------------------------
# Next weeks
# ---------------------------------------------------------------------------

def test_next_weeks_follow_the_last_full_week(loaded):
    next_weeks = forecast.forecast_next(*loaded, use_model=False)
    assert sorted(next_weeks["week_start"].unique()) == ["2025-12-29", "2026-01-05", "2026-01-12", "2026-01-19"]
    assert len(next_weeks) == 5 * forecast.NEXT_WEEKS


def test_next_weeks_use_the_baseline_unless_the_model_won(loaded):
    weekly, events = loaded
    flat = forecast.forecast_next(weekly, events, use_model=False)
    sadd = flat[flat["branch"] == "Al Sadd"]["forecast_qar"]
    expected = weekly[weekly["branch"] == "Al Sadd"]["revenue_qar"].tail(4).mean()
    assert set(sadd) == {round(expected, 2)}
    fitted = forecast.forecast_next(weekly, events, use_model=True)
    assert fitted[fitted["branch"] == "Al Sadd"]["forecast_qar"].nunique() > 1


def test_next_weeks_finding_names_the_method_that_won(loaded, result):
    next_weeks = forecast.forecast_next(*loaded, use_model=result.model_won)
    text = forecast.next_weeks_finding(next_weeks, result)
    assert f"The {'model' if result.model_won else 'baseline'} won the held-back test" in text
    assert "2025-12-29 to 2026-01-25" in text
    assert text.endswith(findings.SIMULATED_NOTE)


# ---------------------------------------------------------------------------
# Command line and page
# ---------------------------------------------------------------------------

def test_command_line_prints_the_verdict(db_path, capsys):
    assert forecast.main(["--db", str(db_path)]) == 0
    out = capsys.readouterr().out
    assert "Held back 2025-09-29 to 2025-12-28" in out
    assert findings.SIMULATED_NOTE in out
    for branch in ("Al Sadd", "Lusail"):
        assert branch in out


def test_command_line_reports_a_missing_database(tmp_path, capsys):
    assert forecast.main(["--db", str(tmp_path / "missing.db")]) == 1
    assert "python seed.py" in capsys.readouterr().err


def test_page_leads_with_the_verdict(db_path, monkeypatch, result):
    monkeypatch.setenv(data.DB_ENV_VAR, str(db_path))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["view"] = "forecast"
    app.run()
    assert not app.exception
    assert app.info[0].value == forecast.verdict(result)
    assert len(app.info) == 2
    assert app.selectbox[0].value == forecast.worst_branch(result)
    assert app.info[1].value.endswith(findings.SIMULATED_NOTE)
    app.selectbox[0].set_value("Lusail").run()
    assert not app.exception
