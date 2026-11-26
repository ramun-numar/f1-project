"""
Home (sketch page 1).

    ┌──────────────────────────────────────────┬──────────────────┐
    │ Next Race   countdown            [map]   │ Previous Race    │
    │ → Next race page                         │ 1. 2. 3.         │
    │                                          │ + Other races    │
    ├────────────────────────┬─────────────────┴──────────────────┤
    │ Driver Standings  [Forecast]  │ Constructor Standings [Forecast] │
    └────────────────────────┴────────────────────────────────────┘
"""
import streamlit as st

import ui
from data import site_data as sd

tbl = ui.tables()
next_race = sd.next_race(tbl)
prev_race = sd.previous_race(tbl)
season, rnd = prev_race["year"], prev_race["round"]

# ── Row 1: Next Race | Previous Race ─────────────────────────────────────────
next_col, prev_col = st.columns([2.2, 1], gap="medium")

with next_col, st.container(border=True, height="stretch"):
    if next_race is None:
        st.header("Season complete")
        st.caption("No upcoming races in the calendar.")
        map_slot = None
    else:
        text, map_col = st.columns([1.4, 1])
        with text:
            st.caption(f"NEXT RACE · ROUND {next_race['round']}")
            st.header(next_race["name"])
            st.caption(f"{next_race['start']:%a %d %b · %H:%M} UTC · {next_race['circuit']}")
            ui.countdown(next_race["start"])
            st.page_link("pages/next_race.py", label="Race preview", icon=":material/arrow_forward:")
        with map_col:
            map_slot = st.empty()

with prev_col, st.container(border=True, height="stretch"):
    st.caption(f"PREVIOUS RACE · ROUND {prev_race['round']}")
    st.subheader(prev_race["name"])
    for p in sd.podium(tbl, prev_race["id"]):
        st.markdown(f"**{p['pos']}.** {p['name']} :gray[· {p['team']}]")
    st.page_link("pages/previous_race.py", label="Race report", icon=":material/arrow_forward:")
    st.page_link("pages/archive.py", label="Other races (Archive)", icon=":material/add:")

st.space("small")

# ── Row 2: standings ─────────────────────────────────────────────────────────
drivers_col, teams_col = st.columns(2, gap="medium")
with drivers_col:
    ui.standings_card(tbl, season, rnd, "driver", key="home_", link_page="pages/drivers.py")
with teams_col:
    ui.standings_card(tbl, season, rnd, "team", key="home_", link_page="pages/teams.py")

# ── Slow part last (see ui.draw_track_map) ───────────────────────────────────
if map_slot is not None:
    ui.draw_track_map(map_slot, tbl, next_race, height=230, show_corners=False)
