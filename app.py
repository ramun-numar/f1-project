import streamlit as st
import runpy
from visualizations.visualizations import plot_race_results, plot_prediction_breakdown

# LOADING PREDICTION MODEL
# caching resource means that the function is only executed in the first run, on subsequent runs the cached result is used
@st.cache_resource
def load_model():
    result = runpy.run_path("predict_race.py")
    return result["prediction_data"], result["race_model"]

prediction_data, race_model = load_model()


st.title("F1 Race Predictions")


race_id = st.selectbox("Select race", sorted(prediction_data["raceId"].unique()))
race_data = prediction_data[prediction_data["raceId"] == race_id]
st.plotly_chart(plot_race_results(race_data), width="stretch")

driver_id = st.selectbox("Select driver", race_data["driverId"].unique())
driver = race_data[race_data["driverId"] == driver_id].iloc[[0]]
st.plotly_chart(plot_prediction_breakdown(driver, race_model), width="stretch")