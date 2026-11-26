"""Previous Race (sketch page 2): the report for the latest race with results."""
import streamlit as st

import ui
from data import site_data as sd
from race_report import render_race_report

tbl = ui.tables()
race = sd.previous_race(tbl)

st.title(race["name"])
render_race_report(tbl, race["year"], race["round"], key="prev_")
