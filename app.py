"""Streamlit dashboard for the sample grocery chain.

Run with: streamlit run app.py
"""

import streamlit as st

from dashboard.findings import SIMULATED_NOTE
from dashboard.views import PAGES

st.set_page_config(page_title="Retail analytics dashboard", layout="wide")

slugs = list(PAGES)
requested = st.query_params.get("view")
start_index = slugs.index(requested) if requested in slugs else 0

st.sidebar.title("Retail analytics")
slug = st.sidebar.radio("Page", slugs, index=start_index, format_func=lambda s: PAGES[s][0])
st.sidebar.warning(SIMULATED_NOTE)
st.sidebar.caption("Every number comes from the SQL files in `queries/`, run against a generated SQLite database.")

if requested != slug:
    st.query_params["view"] = slug

PAGES[slug][1]()
