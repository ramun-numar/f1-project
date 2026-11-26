"""
Championship Predictions (sketch page 6).

    ┌ Title Probabilities ┐
    │ Driver | Const.     │
    ├ Evolution of drivers' title probability ─────────┤   (team's chart)
    ├ Evolution of constructors' title probability ────┤   (team's chart)

The season / "forecast after" selectors and both charts are the team's work.
Their simulated-points chart moved to the Driver Standings page (sketch 4),
and the race prediction explorer (src/app.py) now has its own page,
pages/race_explorer.py.
"""
import pandas as pd
import streamlit as st

import ui
from data import dashboard_data as dd
from visualizations import championship_charts as cc

st.title("Championship :red[Predictions]")

tables = ui.tables()

# ── Selectors (team code) ────────────────────────────────────────────────────
# offer only seasons with saved championship predictions
forecast_seasons = sorted(
    {path.parent.parent.name for path in dd.CHAMPIONSHIP_DIR.glob("*/after_*/driver_predictions.csv")},
    key=int,
    reverse=True,
)

# default to the current season when forecasts are available
current_year = str(pd.Timestamp.now(tz="Europe/Zurich").year)
default_index = forecast_seasons.index(current_year) if current_year in forecast_seasons else 0

filters = st.container(border=True)
season_col, race_col = filters.columns([1, 3])

with season_col:
    season = int(st.selectbox("Season", forecast_seasons, index=default_index, key="championship_season_picker"))

timeline = pd.DataFrame(dd.championship_timeline(tables, season))

if timeline.empty:
    st.info("No championship predictions saved for this season.")
    st.stop()

# put the latest saved starting point first
available_rounds = sorted(timeline["round"].unique(), reverse=True)
race_labels = {}
for _, race in tables["races"].loc[tables["races"]["year"].eq(season)].iterrows():
    round_number = int(race["round"])
    race_name = tables["grands_prix"].get(race["grandPrixId"], race["officialName"])
    race_labels[round_number] = f"R{round_number:02d} · {race_name}"

with race_col:
    selected_round = st.selectbox(
        "Forecast after",
        options=available_rounds,
        index=0,
        format_func=lambda value: race_labels[value],
        key=f"championship_race_picker_{season}",
    )

# ── Body ─────────────────────────────────────────────────────────────────────
probs_col, _ = st.columns([1, 1])
with probs_col:
    ui.title_probability_card(tables, season, selected_round)

with st.container(border=True):
    st.subheader("Evolution of Drivers' :red[Title Probability]")
    cc.render_driver_title_probability(tables, season, selected_round)

with st.container(border=True):
    st.subheader("Evolution of Constructors' :red[Title Probability]")
    cc.render_constructor_title_probability(tables, season, selected_round)
