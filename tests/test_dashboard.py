"""Checks for the Streamlit dashboard.

The findings are recomputed by hand from the same query results, the pages are
run through Streamlit's test runner, and the code is searched for stray SQL.
"""

import importlib.util
import re
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import run
import seed
from dashboard import data, findings
from dashboard.views import PAGES

ROOT = Path(__file__).resolve().parent.parent
USED_QUERIES = [1, 2, 4, 5, 10, 17, 18, 19, 20, 24]


@pytest.fixture
def app_db(db_path, monkeypatch):
    """Point the dashboard at the test database."""
    monkeypatch.setenv(data.DB_ENV_VAR, str(db_path))
    return db_path


@pytest.fixture(scope="session")
def other_seed_db(tmp_path_factory):
    path = tmp_path_factory.mktemp("other") / "retail.db"
    seed.build_database(path, seed=7)
    return path


def frame(number, db_path):
    return data.load_query(number, db_path).frame


def all_findings(db_path):
    return {
        "revenue": findings.revenue(frame(1, db_path)),
        "ramadan": findings.ramadan(frame(10, db_path)),
        "weekend": findings.weekend(frame(5, db_path)),
        "branches": findings.branches(frame(20, db_path), frame(2, db_path)),
        "rfm": findings.rfm(frame(17, db_path)),
        "cohorts": findings.cohorts(frame(18, db_path)),
        "baskets": findings.baskets(frame(19, db_path)),
    }


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("number", USED_QUERIES)
def test_dashboard_data_matches_the_query_file(db_path, number):
    path = run.query_files([number])[0]
    with closing(run.connect_read_only(db_path)) as conn:
        expected = run.run_query(conn, path)
    loaded = data.load_query(number, db_path)
    assert loaded.file == path.name
    assert list(loaded.frame.columns) == expected.columns
    actual = [tuple(row) for row in loaded.frame.astype(object).where(loaded.frame.notna(), None).values]
    assert actual == expected.rows


def test_python_code_holds_no_sql():
    pattern = re.compile(r"\bSELECT\b.+?\bFROM\b", re.DOTALL)
    for path in [ROOT / "app.py", ROOT / "forecast.py", *sorted((ROOT / "dashboard").glob("*.py"))]:
        assert not pattern.search(path.read_text(encoding="utf-8")), path.name


def test_missing_database_is_built_on_first_use(tmp_path, monkeypatch):
    target = tmp_path / "fresh.db"
    monkeypatch.setenv(data.DB_ENV_VAR, str(target))
    assert data.database_path() == target
    assert not data.load_query(1).frame.empty
    assert target.exists()


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def test_every_finding_says_the_data_is_simulated(db_path):
    for name, text in all_findings(db_path).items():
        assert text.endswith(findings.SIMULATED_NOTE), name


def test_findings_are_computed_not_typed_in(db_path, other_seed_db):
    default, other = all_findings(db_path), all_findings(other_seed_db)
    for name in default:
        assert default[name] != other[name], name


def test_revenue_finding_numbers(db_path):
    monthly = frame(1, db_path)
    totals = monthly.groupby(monthly["month"].str[:4])["revenue_qar"].sum()
    growth = 100 * (totals["2025"] / totals["2024"] - 1)
    text = findings.revenue(monthly)
    assert f"QAR {totals['2025']:,.0f} in 2025" in text
    assert f"up {growth:.1f}% on 2024" in text


def test_revenue_finding_says_down_when_revenue_falls():
    monthly = pd.DataFrame({"month": ["2024-01", "2025-01"], "revenue_qar": [200.0, 100.0]})
    assert "down 50.0% on 2024" in findings.revenue(monthly)


def test_ramadan_finding_numbers(db_path):
    by_period = frame(10, db_path)
    text = findings.ramadan(by_period)
    ramadan = by_period[by_period["period"] == "Ramadan"].set_index("year")
    assert f"{ramadan.loc['2025', 'revenue_uplift_pct']:.1f}% more" in text
    assert f"({ramadan.loc['2024', 'revenue_uplift_pct']:.1f}% more in 2024)" in text


def test_weekend_is_friday_and_saturday_and_weighted_by_days(db_path):
    by_weekday = frame(5, db_path).set_index("weekday")
    weekend = by_weekday.loc[["Friday", "Saturday"]]
    others = by_weekday.drop(["Friday", "Saturday"])
    weekend_avg = (weekend["avg_revenue_qar"] * weekend["days"]).sum() / weekend["days"].sum()
    other_avg = (others["avg_revenue_qar"] * others["days"]).sum() / others["days"].sum()
    text = findings.weekend(by_weekday.reset_index())
    assert f"averaged QAR {weekend_avg:,.0f} a day" in text
    assert f"against QAR {other_avg:,.0f} from Sunday to Thursday" in text


def test_branch_finding_uses_the_latest_year(db_path):
    scorecard = frame(20, db_path)
    latest = scorecard[scorecard["year"] == "2025"].sort_values("rank_by_daily_revenue")
    text = findings.branches(scorecard, frame(2, db_path))
    assert text.startswith(f"In 2025 {latest.iloc[0]['branch']} ranked first")
    assert "The newest branch, Lusail" in text


def test_rfm_finding_handles_a_missing_segment(db_path):
    segments = frame(17, db_path)
    without_fading = segments[~segments["segment"].isin(["At risk", "Lost"])]
    assert "At risk and Lost" in findings.rfm(segments)
    assert "At risk and Lost" not in findings.rfm(without_fading)


def test_cohort_finding_skips_blank_months_and_weights_by_size(db_path):
    retention = frame(18, db_path)
    known = retention[retention["month_12_pct"].notna()]
    assert len(known) < len(retention)
    expected = (known["month_12_pct"] * known["customers"]).sum() / known["customers"].sum()
    assert f"{expected:.1f}% twelve months after" in findings.cohorts(retention)


def test_basket_finding_names_the_strongest_pair(db_path):
    pairs = frame(19, db_path)
    top = pairs.iloc[0]
    text = findings.baskets(pairs)
    assert text.startswith(f"{top['product_a']} and {top['product_b']} appear together {top['lift']:.1f} times")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def open_page(slug):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["view"] = slug
    return app.run()


@pytest.mark.parametrize("slug", list(PAGES))
def test_page_renders_with_a_simulated_finding(app_db, slug):
    app = open_page(slug)
    assert not app.exception
    assert app.header[0].value == PAGES[slug][0]
    assert len(app.info) >= 1
    for box in app.info:
        assert box.value.endswith(findings.SIMULATED_NOTE)


def test_sidebar_always_warns_about_simulated_data(app_db):
    app = open_page("revenue")
    assert app.sidebar.warning[0].value == findings.SIMULATED_NOTE


def test_unknown_view_falls_back_to_the_first_page(app_db):
    app = open_page("no-such-page")
    assert not app.exception
    assert app.header[0].value == "Revenue"


def test_screenshot_tool_only_opens_real_pages():
    spec = importlib.util.spec_from_file_location("take_screenshots", ROOT / "tools" / "take_screenshots.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    for query in tool.SHOTS.values():
        assert parse_qs(query)["view"][0] in PAGES


def test_branch_page_year_filter(app_db):
    app = open_page("branches")
    app.selectbox[0].set_value("2024").run()
    assert not app.exception
