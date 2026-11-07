from model import create_model
from features import numeric_features, categorical_features
from features import prepare_features
import pandas as pd
from pathlib import Path
import race_data


#### SUPPLEMENT THE STARTING POSITION MANUALLY ####

YEAR = 2026
RACE_FOLDER = "19-mexico"

# Path(__file__) is the path to the predict_race.py file. resolve().parent() gives its folder
PROJECT_DIR = Path(__file__).resolve().parent

race_info, participants = race_data.load_race_data(
    year=YEAR, race_folder=RACE_FOLDER)

grid_path = (PROJECT_DIR / "data" / "input" /
             str(YEAR) / RACE_FOLDER / "starting_grid.csv")

grid_path.parent.mkdir(parents=True, exist_ok=True)

if not grid_path.exists():
    starting_grid = participants[["raceId", "driverId"]].copy()
    starting_grid["gridPositionText"] = ""

    starting_grid.to_csv(grid_path, index=False)

    raise SystemExit(
        f"Starting-grid template created:\n{grid_path}\nFill in gridPositionText, save the file and run again."
    )

participants_with_grid = race_data.add_starting_grid(participants, grid_path)

#### PREPARE THE DATA ####


# crate a copy to leave paricipants_with_grid as it is, since we later on add upcoming_race
upcoming_race = participants_with_grid.copy()

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

# the training window starts 5 years before
window_start = race_date - pd.DateOffset(years=5)

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
    "gridPositionText",
    "predicted_position"
]].sort_values("predicted_position")

# index = False to leave out the index when printing
print(prediction.to_string(index=False))
