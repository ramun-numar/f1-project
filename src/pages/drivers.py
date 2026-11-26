"""
Driver Standings (sketch page 4).

    Driver Standings                                    [Forecast 👁 synced]
    [ Winner / Favorite ]
    ┌ Driver Standings ┐  ┌ Driver Points Evolution (team's chart) ┐
    │ Pos Driver Pts Evo│  ├ Simulated Final Points Top 5 (team's) ┤
    └──────────────────┘  └────────────────────────────────────────┘

The season / "after race" selectors and both charts are the team's work;
the charts now live in visualizations/championship_charts.py so other pages
can reuse them.
"""
import streamlit as st

import ui
from data import dashboard_data as dd
from data import site_data as sd
from visualizations import championship_charts as cc

tables = ui.tables()

title_col, forecast_col = st.columns([4, 1], vertical_alignment="bottom")
title_col.title("Driver Standings")

# ── Selectors (team code) ────────────────────────────────────────────────────
seasons = [int(year) for year in dd.seasons(tables) if year >= 2020]
season_col, race_col = st.columns([1, 3])

with season_col:
    season = st.selectbox("Season", seasons, key="driver_points_season")

calendar = tables["races"].loc[tables["races"]["year"].eq(season)].sort_values("round")
season_standings = tables["driver_standings"].loc[tables["driver_standings"]["year"].eq(season)]
available_rounds = sorted(season_standings["round"].unique(), reverse=True)
race_names = calendar.set_index("round")["grandPrixId"].map(tables["grands_prix"])

with race_col:
    selected_round = st.selectbox(
        "After race",
        available_rounds,
        format_func=lambda value: f"R{value:02d} · {race_names.loc[value]}",
        key=f"driver_points_round_{season}",
    )

# One toggle drives both the table and the chart ("synced" in the sketch).
season_end = int(calendar["round"].max())
forecast = forecast_col.toggle("Forecast", key="drivers_forecast", disabled=selected_round >= season_end,
                               help="Show the championship model's projected final standings")

ui.banner(*sd.favorite(tables, season, selected_round))

# ── Body ─────────────────────────────────────────────────────────────────────
table_col, charts_col = st.columns([1, 1.3], gap="large")

with table_col:
    ui.standings_card(tables, season, selected_round, "driver", key="drivers_", forecast=forecast)

with charts_col:
    with st.container(border=True):
        cc.render_points_evolution(tables, season, selected_round, "driver",
                                   title="Driver Points Evolution", forecast=forecast)
    with st.container(border=True):
        st.subheader("Simulated Final Points :blue[Top 5]")
        cc.render_simulated_points(tables, season, selected_round)
