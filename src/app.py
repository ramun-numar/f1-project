import streamlit as st
import runpy
from pathlib import Path
from visualizations.visualizations import plot_race_results, plot_prediction_breakdown
from visualizations.telemetry_animation import telemetry_viz_2drivers_messages_subplot
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
year_tel = st.selectbox("Season", range(2026, 2017, -1))
races_tel = tif1.get_events(year_tel)["EventName"].tolist() # fetch eventnames from tif1
circuit_tel = st.selectbox("Grand Prix", races_tel)

# cache fetched data to avoid repeated tif1 requests
@st.cache_data 
def get_drivers(year_tel, circuit_tel):
    # load race session according to inputs from above
    session = tif1.get_session(year_tel, circuit_tel, "Race")
    drivers_tel = session.drivers_df.copy()
    # get full driver names for selectbox and map them to their abbreviations needed for the animation
    drivers_tel["FullName"] = drivers_tel["FirstName"] + " " + drivers_tel["LastName"]
    return dict(zip(drivers_tel["FullName"], drivers_tel["Driver"]))

drivers_tel = get_drivers(year_tel, circuit_tel)
driver1_tel = st.selectbox("Driver", sorted(drivers_tel))
driver2_tel = st.selectbox("Opponent", sorted(drivers_tel), index=1)

# animation
if driver1_tel == driver2_tel:
    st.info("🏎️ One driver, two cars? Even the FIA wouldn't allow that. Pick two different drivers!")

else:
    try:
        fig = telemetry_viz_2drivers_messages_subplot(
            year_tel, circuit_tel,
            drivers_tel[driver1_tel], drivers_tel[driver2_tel]
        )
        st.plotly_chart(fig, width="stretch")

    except Exception as e:
        st.warning(
            "🏎️ Oops! Looks like the telemetry couldn't keep up. "
            "There might not be enough data for this race and driver combination "
            "to produce our fabulous animation. Try another combination!"
        )

        with st.expander("Technical details"):
            st.code(str(e))


with st.expander("🤓 How does this work?"):

    st.markdown("""
    **1. Telemetry & Animation**

    We retrieve the fastest-lap telemetry of both drivers using `tif1`. Since telemetry is recorded at irregular intervals, we interpolate their X/Y coordinates onto a common time grid of **20 frames per second**.

    **2. Dividing the Circuit**

    We split the circuit into sections using the `tif1` corner coordinates. Each corner is matched to the nearest telemetry point within a ±1% relative-distance window (to account for nearest points on a different part of the track).

    **3. Comparing Section Times**

    We calculate how long each driver takes between consecutive corners. The difference tells us who gained time in each section.

    **4. Synchronizing the Messages**

    A message appears only once **both drivers have completed the section**. We use `np.searchsorted()` to match these moments to the animation frames.

    ---

    **⚠️**

    Corner positions and telemetry samples do not always match perfectly. Section times are therefore approximations rather than official timing measurements.

    Also, we're comparing each driver's *fastest lap*, not necessarily laps driven at the same moment in the race.
    """)