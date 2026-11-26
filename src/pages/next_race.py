"""
Next Race (sketch page 3).

    "Next Race Name"   countdown                          [track map]
    ┌ Qualifying Results ┐ ┌ Predicted Outcome ┐ ┌ Weather Forecast ┐
    │ Pos Driver Q1-Q3   │ │ before/after quali│ ├ Current Standings┤
    └────────────────────┘ └───────────────────┘ └──────────────────┘
"""
import streamlit as st

import ui
from data import site_data as sd

tbl = ui.tables()
race = sd.next_race(tbl)
prev_race = sd.previous_race(tbl)

if race is None:
    st.title("Next Race")
    st.info("The season is over: there are no upcoming races in the calendar.")
    st.stop()  # st.stop() ends the script here; nothing below runs


@st.cache_data(ttl="1h", show_spinner=False)  # ttl: re-download the forecast at most once an hour
def weather(lat, lon, first, last):
    return sd.weather_forecast(lat, lon, first, last)


# ── Header: name + countdown | track map ─────────────────────────────────────
title_col, map_col = st.columns([1.5, 1])
with title_col:
    st.caption(f"ROUND {race['round']} · {race['circuit'].upper()}, {race['place'].upper()}")
    st.title(race["name"])
    ui.countdown(race["start"])
    sessions = [("Practice 1", race["fp1"]), ("Sprint", race["sprint"]),
                ("Qualifying", race["qualifying"]), ("Race", race["start"])]
    st.caption("  ·  ".join(f"**{name}** {when:%a %H:%M}" for name, when in sessions if when is not None) + " (UTC)")
with map_col:
    map_slot = st.empty()

# ── Body: three columns ──────────────────────────────────────────────────────
quali_col, pred_col, side_col = st.columns([1.25, 1.1, 1], gap="medium")

with quali_col, st.container(border=True):
    st.subheader("Qualifying :red[Results]")
    quali = sd.qualifying(tbl, race["id"])
    if quali.empty:
        st.info(f"Qualifying hasn't happened yet. It starts {race['qualifying']:%A %d %b, %H:%M} UTC.")
        st.caption("This table fills in automatically once the data is updated after qualifying.")
    else:
        st.dataframe(quali, hide_index=True, width="stretch", height=35 * (len(quali) + 1) + 3)

with pred_col, st.container(border=True):
    st.subheader("Predicted :red[Outcome]")
    after_quali = st.toggle("After qualifying", value=not quali.empty, key="after_quali",
                            help="Before: model without qualifying data. After: model including the grid. "
                                 "Evo shows how much qualifying moved each driver.")
    outcome = sd.predicted_outcome(tbl, race, after_quali)
    if outcome.empty:
        stage = "post-qualifying" if after_quali else "pre-qualifying"
        st.info(f"No {stage} prediction saved for the {race['name']} yet.")
        st.caption("Predictions are created by `python src/data/run_update.py`.")
    else:
        ui.show_table(outcome, "Driver", key="prediction")

with side_col:
    with st.container(border=True):
        st.subheader("Weather :red[Forecast]")
        try:
            days = weather(race["lat"], race["lon"], *sd.weekend_days(race))
        except Exception:
            days = []
        if not days:
            st.caption("Forecast not available yet (Open-Meteo covers ~16 days ahead).")
        for day in days:
            a, b = st.columns([1, 1.3])
            a.markdown(f"**{day['date']:%a %d}**  \n{day['sky']}")
            b.markdown(f"{day['max']:.0f}° / {day['min']:.0f}°C  \n💧 {day['rain']}% · 💨 {day['wind']:.0f} km/h")
        st.caption(f"Open-Meteo · {race['place']}")

    ui.standings_card(tbl, prev_race["year"], prev_race["round"], "driver", key="next_", top_n=10,
                      link_page="pages/drivers.py")

ui.draw_track_map(map_slot, tbl, race, height=300)
