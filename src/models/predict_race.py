# idea: also make simulations to get predictions


from models.features import (
    prepare_features,
    pre_race_numeric_features,
    post_qualifying_numeric_features,
    categorical_features,
)
from data import race_data
import pandas as pd
from models.model import create_model
import joblib
import json
import sys
from pathlib import Path

# Make src/ importable before importing project modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


#### PREDICTION SETTINGS ####

YEAR = 2026
RACE_FOLDER = "20-sao-paulo"

MODE = "post"

if MODE == "pre":
    numeric_features = pre_race_numeric_features
elif MODE == "post":
    numeric_features = post_qualifying_numeric_features
else:
    raise ValueError("Prediction mode must be 'pre' or 'post'")

# Path to project root (src/models/predict_race.py -> go up 3 levels to project root)
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent

race_info, participants = race_data.load_race_data(
    year=YEAR,
    race_folder=RACE_FOLDER,
    mode=MODE,
)

#### PREPARE THE DATA ####

# crate a copy to leave paricipants_with_grid as it is, since we later on add upcoming_race
upcoming_race = participants.copy()

# add the same race information used in the historical training data
for column in [
    "date",
    "circuitId",
    "circuitType",
    "courseLength",
    "turns",
        "scheduledLaps"]:
    upcoming_race[column] = race_info.get(column)

# since the outcome is unknown before the race, set these values to None/NaN
upcoming_race["positionDisplayOrder"] = float("nan")
upcoming_race["positionText"] = None
upcoming_race["reasonRetired"] = None

# calls the function from race data to prepare the features with the upcoming race, which is created above
# for every race the features are created
all_features = prepare_features(upcoming_race=upcoming_race)

# since we are only interested in the current race, we only select that one, with its created features
prediction_data = all_features.loc[all_features["raceId"].eq(
    race_info["id"])].copy()

# create the timestamp of the predicted race
race_date = pd.Timestamp(race_info["date"])

# the training window starts 10 years before
window_start = race_date - pd.DateOffset(years=10)

# changes the date as text into a date class object
dates = pd.to_datetime(all_features["date"])

# the data we train on is the data greater or equal to the start window and before the current race
# it also takes only the information from races where the finishing position is determiniable
train_data = all_features.loc[dates.ge(window_start) & dates.lt(
    race_date) & all_features["finish_fraction"].notna()].copy()


#### TRAIN THE RIDGE MODEL ####

features = numeric_features + categorical_features

# create the pipeline for this model
race_model = create_model(numeric_features, categorical_features)

# fit the model with finish_fraction ~ features. finish_fraction as the dependent varaible and features as the covariates
race_model.fit(train_data[features], train_data["finish_fraction"])


#### CREATE THE PREDICTIONS ####

# sort by driver ID to break tied scores independently of actual results
prediction_data = prediction_data.sort_values("driverId").copy()

# predict a finishing score for each driver
prediction_data["predicted_score"] = race_model.predict(
    prediction_data[features])

# convert scores into unique finishing positions: lower scores rank first
prediction_data["predicted_position"] = prediction_data["predicted_score"].rank(
    method="first")

# display drivers in their predicted finishing order
prediction = prediction_data[[
    "driverId",
    "constructorId",
    "predicted_position"
]].sort_values("predicted_position")

# index = False to leave out the index when printing
print(prediction.to_string(index=False))

# create a separate folder for each prediction run
created_at = pd.Timestamp.now(tz="UTC")
run_id = created_at.strftime("%Y%m%dT%H%M%SZ")

output_dir = (
    PROJECT_DIR / "data" / "predictions" /
    str(YEAR) / RACE_FOLDER / MODE / run_id
)

output_dir.mkdir(parents=True, exist_ok=False)

# save the complete prediction table for dashboard use
prediction_data.sort_values("predicted_position").to_csv(
    output_dir / "prediction.csv", index=False)

# preserve the exact training data used in this run
train_data.to_csv(output_dir / "training_data.csv", index=False)

# save the fitted pipeline for predictions and feature explanations
joblib.dump(race_model, output_dir / "model.joblib")

# distinguish the creation time from the date of the predicted race
metadata = {
    "created_at": created_at.isoformat(),
    "race_date": race_date.isoformat(),
    "race_id": int(race_info["id"]),
    "year": YEAR,
    "race_folder": RACE_FOLDER,
    "mode": MODE,
    "training_start": train_data["date"].min(),
    "training_end": train_data["date"].max(),
    "numeric_features": numeric_features,
    "categorical_features": categorical_features,
    "model_type": "Ridge",
    "alpha": race_model.named_steps["regression"].alpha,
}

with (output_dir / "metadata.json").open("w", encoding="utf-8") as file:
    json.dump(metadata, file, indent=2, default=str)

print(f"Prediction saved to: {output_dir}")
