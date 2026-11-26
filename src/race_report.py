"""
The race report shared by the Previous Race and Archive pages.

Both sketches show the same core: standings after the race, the overtake
(position) plot, telemetry and the model's error. The Archive adds the
points-evolution plot and the championship simulations (archive=True).
"""
import streamlit as st

import ui
from data import site_data as sd
from visualizations import championship_charts as cc


@st.cache_data(show_spinner=False)
def _position_plot(year, event_name):
    from visualizations.visualizations import plot_position_development
    return plot_position_development(year, event_name)


@st.cache_data(show_spinner=False)
def _top_two(year, event_name):
    import tif1
    results = tif1.get_session(year, event_name, "Race").results.sort_values("Position")
    return results["Abbreviation"].head(2).tolist(), results["FullName"].head(2).tolist()


def _telemetry(year, event_name, key):
    """Team's fastest-lap telemetry animation, winner vs. P2 (loaded on demand)."""
    if not st.toggle("Fastest-lap telemetry: winner vs. P2", key=f"tel_{key}"):
        st.caption("Turn on to load the animated telemetry comparison (takes a while).")
        return
    from visualizations.telemetry_animation import telemetry_viz_2drivers_2modes
    try:
        with st.spinner("Loading telemetry…"):
            (d1, d2), names = _top_two(year, event_name)
            st.caption(f"{names[0]} vs. {names[1]}")
            st.plotly_chart(telemetry_viz_2drivers_2modes(year, event_name, d1, d2), width="stretch")
    except Exception as error:
        st.warning(f"Telemetry unavailable for this race ({error.__class__.__name__}).")


def render_race_report(tbl, season, rnd, archive=False, key=""):
    from visualizations.track_map import tif1_event_name, TIF1_FIRST_YEAR

    race = sd.race_info(tbl, sd.race_id_for(tbl, season, rnd))
    podium = " · ".join(f"P{p['pos']} {p['name']}" for p in sd.podium(tbl, race["id"]))
    st.caption(f"Round {race['round']} · {race['date']:%d %b %Y} · {race['circuit']}, {race['place']}  \n🏆 {podium}")

    has_tif1 = season >= TIF1_FIRST_YEAR
    left, right = st.columns([2, 1.1], gap="large")

    with left:
        st.markdown("##### Standings after the race")
        drivers_col, teams_col = st.columns(2)
        with drivers_col:
            ui.show_table(sd.standings_table(tbl, season, rnd, "driver"), "Driver", key=f"{key}d")
        with teams_col:
            teams = sd.standings_table(tbl, season, rnd, "team")
            if teams.empty:
                st.info("No constructors' championship this season.")
            else:
                ui.show_table(teams, "Constructor", key=f"{key}t")

    with right:
        st.markdown("##### Telemetry")
        map_slot = st.empty()  # filled at the end (slow download)
        if has_tif1:
            _telemetry(season, tif1_event_name(season, rnd), key)
        st.markdown("##### Overtake Plot")
        overtake_slot = st.empty()

    if archive:
        st.markdown("##### Point Evolution")
        cc.render_points_evolution(tbl, season, rnd, "driver", title="Driver points", key=f"{key}arch_")

        st.markdown("##### Simulations")
        probs_col, sims_col = st.columns([1, 2])
        with probs_col:
            ui.title_probability_card(tbl, season, rnd)
        with sims_col:
            with st.container(border=True):
                st.markdown("**Simulated top 5 final points**")
                cc.render_simulated_points(tbl, season, rnd)

        st.markdown("##### Model Discussion")

    error_col, _ = st.columns([2, 1.1])
    with error_col:
        ui.model_error_card(tbl, race)

    # ── slow parts last: everything above is already on screen ──
    if not has_tif1:
        map_slot.caption("Track and lap data are only available from 2018.")
        overtake_slot.caption("Lap-by-lap positions are only available from 2018.")
        return
    ui.draw_track_map(map_slot, tbl, race, height=240, before_race_id=race["id"])
    with overtake_slot.container():
        try:
            with st.spinner("Loading lap positions…"):
                st.plotly_chart(_position_plot(season, tif1_event_name(season, rnd)), width="stretch",
                                key=f"{key}pos")
        except Exception as error:
            st.caption(f"Position data unavailable ({error.__class__.__name__}).")
