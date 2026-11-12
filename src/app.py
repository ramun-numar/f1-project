import streamlit as st
import runpy
from pathlib import Path
from visualizations.visualizations import plot_race_results, plot_prediction_breakdown
from visualizations.telemetry_animation import telemetry_viz
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
driver_tel = st.selectbox("Driver", sorted(drivers_tel))

# animation
st.plotly_chart(telemetry_viz(year_tel, circuit_tel, driver_tel), width="stretch")