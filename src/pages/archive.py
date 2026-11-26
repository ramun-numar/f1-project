"""Archive (sketch page 7): the full race report for any past race."""
import streamlit as st

import ui
from data import site_data as sd
from race_report import render_race_report

tbl = ui.tables()
latest = sd.previous_race(tbl)

title_col, pick_col = st.columns([2, 1.3], vertical_alignment="bottom")
title_col.title("Archive")
with pick_col, st.container(border=True):
    year_col, race_col = st.columns([1, 2])
    seasons = [int(y) for y in sd.dd.seasons(tbl)]
    season = year_col.selectbox("Year", seasons, key="archive_year")
    races = sd.races_with_results(tbl, season)  # {round: "R05 · Monaco Grand Prix"}
    rnd = race_col.selectbox("Race", list(races), format_func=races.get, key=f"archive_race_{season}")

st.subheader(races[rnd].split(" · ", 1)[1])
render_race_report(tbl, season, rnd, archive=True, key="arch_")
