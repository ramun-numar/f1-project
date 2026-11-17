import streamlit as st
import runpy
from pathlib import Path
import pandas as pd
from visualizations.visualizations import plot_race_results, plot_prediction_breakdown, plot_position_development
from visualizations.telemetry_animation  import telemetry_viz_2drivers_2modes, get_overtake_highlights
import tif1

# LOADING PREDICTION MODEL
# caching resource means that the function is only executed in the first run, on subsequent runs the cached result is used
@st.cache_resource
def load_model():
    predict_race_path = Path(__file__).parent / "models" / "predict_race.py"
    result = runpy.run_path(str(predict_race_path))
    return result["prediction_data"], result["race_model"]

prediction_data, race_model = load_model()


st.title("F1 Race Predictions")


race_id = st.selectbox("Select race", sorted(prediction_data["raceId"].unique()))
race_data = prediction_data[prediction_data["raceId"] == race_id]
st.plotly_chart(plot_race_results(race_data), width="stretch")

driver_id = st.selectbox("Select driver", race_data["driverId"].unique())
driver = race_data[race_data["driverId"] == driver_id].iloc[[0]]
st.plotly_chart(plot_prediction_breakdown(driver, race_model), width="stretch")


# TELEMETRY ANIMATION
mode = st.radio("Mode", ["Fastest Lap", "Overtake Highlights"], horizontal=True)

year_tel = st.selectbox("Season", range(2026, 2017, -1))
races_tel = tif1.get_events(year_tel)["EventName"].tolist()
circuit_tel = st.selectbox("Grand Prix", races_tel)

# cache fetched data to avoid repeated tif1 requests
@st.cache_data
def get_drivers(year_tel, circuit_tel):
    session = tif1.get_session(year_tel, circuit_tel, "Race")
    drivers_tel = session.drivers_df.copy()
    drivers_tel["FullName"] = drivers_tel["FirstName"] + " " + drivers_tel["LastName"]
    return dict(zip(drivers_tel["FullName"], drivers_tel["Driver"]))


if mode == "Fastest Lap":
    drivers_tel = get_drivers(year_tel, circuit_tel)
    names = sorted(drivers_tel)
    driver1_tel = st.selectbox("Driver", names)
    driver2_tel = st.selectbox("Opponent", names, index=min(1, len(names)-1))

    if driver1_tel == driver2_tel:
        st.info("🏎️ One driver, two cars? Even the FIA wouldn't allow that. Pick two different drivers!")
    else:
        try:
            fig = telemetry_viz_2drivers_2modes(year_tel, circuit_tel, drivers_tel[driver1_tel], drivers_tel[driver2_tel])
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning("🏎️ Telemetry unavailable for this combination.")
            with st.expander("Technical details"):
                st.code(str(e))

else:
    # POSITION DEVELOPMENT GRAPH
    drivers_tel = get_drivers(year_tel, circuit_tel)
    selected = st.selectbox("Highlight driver", ["All Drivers"] + sorted(drivers_tel))
    selected_driver = None if selected == "All Drivers" else drivers_tel[selected]
    fig_pos = plot_position_development(year_tel, circuit_tel, selected_driver)
    st.plotly_chart(fig_pos, width="stretch")

    @st.cache_data
    def load_highlights(year, circuit):
        return get_overtake_highlights(year, circuit)

    highlights = load_highlights(year_tel, circuit_tel)

    st.subheader("Race Highlights")
    st.caption("Potential overtakes from lap-end position changes, excluding recorded pit-stop events.")

    if highlights.empty:
        st.info("No suitable overtakes found for this race.")

    else:
        category = st.selectbox(
            "Highlight category",
            ["All"] + sorted(highlights["Category"].unique())
        )

        if category != "All":
            highlights = highlights[highlights["Category"] == category]

        for i, event in highlights.iterrows():

            lap = int(event["LapNumber"])
            driver1 = event["GainedAhead"]
            driver2 = event["FellBehind"]

            replay = (year_tel, circuit_tel, lap, driver1, driver2)

            col1, col2 = st.columns([5, 1], vertical_alignment="center")

            with col1:
                st.markdown(
                    f"**Lap {lap}** — {event['Headline']} "
                    f"(P{int(event['NewPosition'])})"
                )

            with col2:
                if st.button("▶ Replay", key=f"replay_{year_tel}_{circuit_tel}_{i}"):
                    st.session_state["replay"] = replay

            # Show animation directly below the selected event
            if st.session_state.get("replay") == replay:
                try:
                    fig = telemetry_viz_2drivers_2modes(
                        year_tel, circuit_tel, driver1, driver2,
                        fps=12, lap_number=lap
                    )
                    st.plotly_chart(fig, width="stretch")

                except Exception as e:
                    st.exception(e)

with st.expander("🤓 How does this work?"):
    if mode == "Fastest Lap":
        st.markdown("""
        **1. Telemetry & Animation**

        We retrieve the fastest-lap telemetry of both drivers using `tif1`. Since telemetry is recorded at irregular intervals, we interpolate their X/Y coordinates onto a common time grid of **20 frames per second**.

        **2. Dividing the Circuit**

        We split the circuit into sections using the `tif1` corner coordinates. Each corner is matched to the nearest telemetry point within a ±1% relative-distance window.

        **3. Comparing Section Times**

        We calculate how long each driver takes between consecutive corners. The difference tells us who gained time in each section.

        **4. Synchronizing the Messages**

        A message appears only once **both drivers have completed the section**. We use `np.searchsorted()` to match these moments to the animation frames.

        ---

        **⚠️** Corner positions and telemetry samples do not always match perfectly, so section times are approximate. Both drivers' fastest laps start at time zero; they are not necessarily from the same moment in the race.
        """)
    else:
        st.markdown("""
        We identify potential overtakes when two drivers exchange their relative order between consecutive laps, excluding laps with recorded pit entries or exits. In the replay, the cars use the same `SessionTime` clock. We locate an approximate crossing using `RelativeDistance` and show up to 10 seconds before and after it.
        """)
