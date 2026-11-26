"""
Constructor Standings (sketch page 5). Same layout as the Driver Standings
page; the selectors and points chart are the team's work.
"""
import streamlit as st

import ui
from data import dashboard_data as dd
from data import site_data as sd
from visualizations import championship_charts as cc

tables = ui.tables()

title_col, forecast_col = st.columns([4, 1], vertical_alignment="bottom")
title_col.title("Constructor Standings")

# ── Selectors (team code) ────────────────────────────────────────────────────
seasons = [int(year) for year in dd.seasons(tables) if year >= 2020]
season_col, race_col = st.columns([1, 3])

with season_col:
    season = st.selectbox("Season", seasons, key="team_points_season")

calendar = tables["races"].loc[tables["races"]["year"].eq(season)].sort_values("round")
season_standings = tables["team_standings"].loc[tables["team_standings"]["year"].eq(season)]
available_rounds = sorted(season_standings["round"].unique(), reverse=True)
race_names = calendar.set_index("round")["grandPrixId"].map(tables["grands_prix"])

with race_col:
    selected_round = st.selectbox(
        "After race",
        available_rounds,
        format_func=lambda value: f"R{value:02d} · {race_names.loc[value]}",
        key=f"team_points_round_{season}",
    )

season_end = int(calendar["round"].max())
forecast = forecast_col.toggle("Forecast", key="teams_forecast", disabled=selected_round >= season_end,
                               help="Show the championship model's projected final standings")

if (fav := sd.favorite_team(tables, season, selected_round)):
    ui.banner(*fav)

# ── Body ─────────────────────────────────────────────────────────────────────
table_col, charts_col = st.columns([1, 1.3], gap="large")

with table_col:
    ui.standings_card(tables, season, selected_round, "team", key="teams_", forecast=forecast)

with charts_col:
    with st.container(border=True):
        cc.render_points_evolution(tables, season, selected_round, "team",
                                   title="Constructor Points Evolution", forecast=forecast)
    with st.container(border=True):
        st.subheader("Simulated Final Points :blue[All]")
        cc.render_constructor_final_points(tables, season, selected_round)
