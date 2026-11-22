# currently we use the same prediction for sprints and races but add different noise
# myb later on create sprint model

import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np
from models.features import (
    prepare_features,
    pre_race_numeric_features,
    categorical_features,
)
from models.model import create_model

#### GET THE DATA & CLEAN IT ####

# championship settings
YEAR = 2026
AS_OF_ROUND = None
RANDOM_SEED = 13

# allow the update script to select the season and latest available standings
# checks if script was started directly. 
# If championship was imported by another file, this section gets skipped
if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--year", type=int, default=YEAR)
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--as-of-round", type=int, default=AS_OF_ROUND)

    settings = parser.parse_args()

    YEAR = settings.year
    AS_OF_ROUND = settings.as_of_round

    if settings.latest:
        AS_OF_ROUND = None


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data" / "raw"


# load the calendar, results and official championship standings
races = pd.read_csv(DATA_DIR / "f1db-races.csv")
race_results = pd.read_csv(
    DATA_DIR / "f1db-races-race-results.csv",
    low_memory=False
)

driver_standings = pd.read_csv(
    DATA_DIR / "f1db-races-driver-standings.csv"
)
constructor_standings = pd.read_csv(
    DATA_DIR / "f1db-races-constructor-standings.csv"
)

season_calendar = races.loc[races["year"].eq(YEAR)].copy()

# require race results and both championship standings, s.t. we don't use races which haven't affected all standings
available_race_ids = (
    set(race_results["raceId"])
    & set(driver_standings["raceId"])
    & set(constructor_standings["raceId"])
)

completed_races = season_calendar.loc[
    season_calendar["id"].isin(available_race_ids)
].sort_values("round")


# select the requested historical starting point
if AS_OF_ROUND is not None:
    completed_races = completed_races.loc[
        completed_races["round"].eq(AS_OF_ROUND)
    ].copy()

# as we have no inoframtion, which drivers will compete, we can't make any prediction
if completed_races.empty:
    raise ValueError("No completed race with both standings available")

latest_race = completed_races.iloc[-1]
latest_race_id = int(latest_race["id"])
latest_round = int(latest_race["round"])

print(
    f"\nChampionship forecast for {YEAR} "
    f"after round {latest_round}: {latest_race['officialName']}",
    flush=True,
)

# use the same race as the starting point for both championships
current_drivers = driver_standings.loc[
    driver_standings["raceId"].eq(latest_race_id)
].copy()

# to avoid doubble countings with sprints 
current_constructors = constructor_standings.loc[
    constructor_standings["raceId"].eq(latest_race_id)
].copy()

# use the calendar rather than assuming a fixed number of races
remaining_races = season_calendar.loc[
    season_calendar["round"].gt(latest_round)
].sort_values("round").copy()

# add a vraiable for if the race has a sprint race part
remaining_races["has_sprint"] = (
    remaining_races["sprintRaceDate"].notna()
)

# print(f"Championship standings after round {latest_round}")

# print("\nDriver standings:")
# print(
#     current_drivers.sort_values("positionDisplayOrder")[
#         ["driverId", "points"]
#     ].to_string(index=False)
# )

# print("\nConstructor standings:")
# print(
#     current_constructors.sort_values("positionDisplayOrder")[
#         ["constructorId", "points"]
#     ].to_string(index=False)
# )

# print("\nRemaining races:")
# print(
#     remaining_races[
#         ["round", "date", "grandPrixId", "has_sprint"]
#     ].to_string(index=False)
# )


# select all available race results from the chosen season
season_results = race_results.loc[
    race_results["year"].eq(YEAR)
].copy()

# check source consistency when using the latest available standings
# exclude actual results after the selected championship starting point
if AS_OF_ROUND is None and season_results["round"].gt(latest_round).any():
    raise ValueError(
        "Race results are newer than the championship standings"
    )

# exclude later actual results from championship tie-breaks
season_results = season_results.loc[
    season_results["round"].le(latest_round)
].copy()


#### CREATE MODEL & PREDICTIONS ####

# train once using only information available at the starting point
cutoff = pd.Timestamp(latest_race["date"])
history = prepare_features(history_cutoff=cutoff)
history_dates = pd.to_datetime(history["date"])

training_data = history.loc[
    history_dates.le(cutoff)
    & history_dates.ge(cutoff - pd.DateOffset(years=10))
    & history["finish_fraction"].notna()
]

model_columns = pre_race_numeric_features + categorical_features

season_model = create_model(pre_race_numeric_features, categorical_features)

season_model.fit(
    training_data[model_columns],
    training_data["finish_fraction"],
)

# assume the latest known driver and team lineup remains unchanged
lineup = race_results.loc[
    race_results["raceId"].eq(latest_race_id),
    ["driverId", "constructorId"],
].copy()

future_score_rows = []

# as we don't need the index, we write _
for _, future_race in remaining_races.iterrows():
    upcoming = lineup.copy()
    upcoming["raceId"] = int(future_race["id"])
    upcoming["year"] = YEAR
    upcoming["round"] = int(future_race["round"])

    # add the known characteristics of the future race
    for column in [
        "date",
        "circuitId",
        "circuitType",
        "courseLength",
        "turns",
        "scheduledLaps",
    ]:
        upcoming[column] = future_race[column]

    # future qualifying results are unknown
    for column in [
        "qualificationPositionNumber",
        "q1Millis",
        "q2Millis",
        "q3Millis",
    ]:
        upcoming[column] = float("nan")

    # prepare features for each future race separately using observed history
    prepared = prepare_features(upcoming_race=upcoming, history_cutoff=cutoff)

    # create a table containing all drivers and their features for a sepcific race
    race_features = prepared.loc[
        prepared["raceId"].eq(future_race["id"])
    ].sort_values("driverId").copy()

    race_features["predicted_score"] = season_model.predict(
        race_features[model_columns]
    )

    future_score_rows.append(
        race_features[[
            "raceId",
            "date",
            "driverId",
            "constructorId",
            "predicted_score",
        ]]
    )

# combine the expected scores for all remaining races
future_predictions = (
    pd.concat(future_score_rows, ignore_index=True)
    if future_score_rows

    # happens if e.g. the season is already over, 
    # but we want our future actions with future_predictions to work no matter 
    # where we are in the season, thus we create an empty table
    else pd.DataFrame(columns=[
        "raceId",
        "date",
        "driverId",
        "constructorId",
        "predicted_score",
    ])
)

# print("\nExpected scores for remaining races:")
# print(future_predictions.head(10).to_string(index=False))
# print("Remaining races:", future_predictions["raceId"].nunique())
# print("Prediction rows:", len(future_predictions))


#### CREATE FUNCTION FOR RACE SIMULATION AND ADD UNCERTAINTY ####

# load the uncertainty estimated from walk-forward errors
validation_errors = pd.read_csv(
    PROJECT_DIR
    / "data"
    / "evaluation"
    / "pre_race_errors_2022_2024.csv"
)

# estimate uncertainty only from errors observed by the selected cutoff
validation_errors = validation_errors.loc[
    pd.to_datetime(validation_errors["date"]).le(cutoff)
].copy()


# estimate the total variation from historical prediction errors
score_noise_std = validation_errors["ranking_error"].std()

# estimate persistent team variation from average errors per team and season
team_season_errors = validation_errors.groupby(
    ["year", "constructorId"]
)["ranking_error"].mean()

team_season_noise_std = min(
    team_season_errors.std(),
    score_noise_std
)

# split the existing variance between persistent team and event variation
event_noise_std = np.sqrt(
    max(score_noise_std**2 - team_season_noise_std**2, 0)
)

# create the rng so that it continues for each season, ensuring different randomization
rng = np.random.default_rng(RANDOM_SEED)

if YEAR not in {2025, 2026}:
    raise ValueError("Check the scoring rules for this season")

# use full-distance grand prix and sprint points
race_points = {
    1: 25,
    2: 18,
    3: 15,
    4: 12,
    5: 10,
    6: 8,
    7: 6,
    8: 4,
    9: 2,
    10: 1,
}

sprint_points = {
    1: 8,
    2: 7,
    3: 6,
    4: 5,
    5: 4,
    6: 3,
    7: 2,
    8: 1,
}

# identify sprints completed after the latest grand prix standings
sprint_results = pd.read_csv(DATA_DIR / "f1db-races-sprint-race-results.csv")

# collect actual sprint results from weekends with a pending grand prix
additional_sprints = sprint_results.loc[
    sprint_results["year"].eq(YEAR)
    & sprint_results["raceId"].isin(remaining_races["id"])
]

# future sprint results were unknown immediately after the selected grand prix
if AS_OF_ROUND is not None:
    additional_sprints = additional_sprints.iloc[0:0].copy()

# remember completed sprints so the simulation can skip them later
completed_sprint_ids = set(additional_sprints["raceId"])

# add only sprint points not already included in the starting standings
driver_start_points = (
    current_drivers.set_index("driverId")["points"]
    .add(
        additional_sprints.groupby("driverId")["points"].sum(),
        fill_value=0
    )
)

# add lineup drivers missing from the standings with zero points while preserving existing point totals
driver_start_points = driver_start_points.reindex(
    driver_start_points.index.union(
        pd.Index(lineup["driverId"].unique())
    ),
    fill_value=0
)

constructor_start_points = (
    # Teams are assigned by their constructorIds and get their current points
    current_constructors.set_index("constructorId")["points"]
    .add(
        # sums the points of the teams of the sprints
        additional_sprints.groupby("constructorId")["points"].sum(),
        fill_value=0
    )
)


def simulate_remaining_season(random_generator):
    # start each simulated season from the same official points
    driver_points = driver_start_points.copy()
    constructor_points = constructor_start_points.copy()
    event_results = []

    # draw one shared offset per team for the entire simulated season
    teams = sorted(lineup["constructorId"].unique())

    team_offsets = pd.Series(
        random_generator.normal(
            loc=0,
            scale=team_season_noise_std,
            size=len(teams),
        ),
        index=teams
    )

    for _, future_race in remaining_races.iterrows():
        race_id = int(future_race["id"])

        expected = future_predictions.loc[
            future_predictions["raceId"].eq(race_id)
        ].copy()

        # simulate an outstanding sprint before its grand prix
        events = []

        # check if the sprint might already occured whereas the race is still pending
        if future_race["has_sprint"] and race_id not in completed_sprint_ids:
            events.append(("sprint", sprint_points))

        events.append(("race", race_points))

        # take the race type (sprint or race) and its related point table
        # if there is no sprint, event will only contain race information
        for event_type, points_table in events:
            simulated = expected.copy()

            # combine the baseline score with persistent team and fresh event variation
            simulated["simulated_score"] = (
                simulated["predicted_score"]
                + simulated["constructorId"].map(team_offsets)
                + random_generator.normal(
                    loc=0,
                    scale=event_noise_std,
                    size=len(simulated),
                )
            )

            simulated = simulated.sort_values(
                ["simulated_score", "driverId"]
            ).reset_index(drop=True)

            # as simulated index start with 0 we need to add 1 to create real positions
            simulated["simulated_position"] = simulated.index + 1
            simulated["event_type"] = event_type
            simulated["race_name"] = future_race["officialName"]

            simulated["points"] = (
                simulated["simulated_position"]
                .map(points_table)
                .fillna(0)
                .astype(int)
            )

            # update both championships from the same simulated result
            driver_points = driver_points.add(
                simulated.groupby("driverId")["points"].sum(),
                fill_value=0,
            )

            constructor_points = constructor_points.add(
                simulated.groupby("constructorId")["points"].sum(),
                fill_value=0,
            )

            # retain the results for championship tie-breaks later
            event_results.append(simulated)

    return driver_points, constructor_points, event_results


#### CHANPION FUNCTION ####


# final_points: total championship points after one simulated season
# simulated_events: results of the simulated races and sprints in that season
# participant_column: "driverId" or "constructorId" to select the championship

def get_champion(final_points, simulated_events, participant_column):
    # select the driver/constructor IDs of everyone tied for the highest points total
    candidates = final_points.loc[
        final_points.eq(final_points.max())
    ].index

    # easy solution if only one has most points
    if len(candidates) == 1:
        return candidates[0]


    # add tie-breaker rules: most 1. places, then most 2. places, etc.

    # collect actual grand prix finishing positions
    # rename since the predicted pos number has a different name, 
    # therefore name both the same to add them later together
    finish_tables = [
        season_results[[
            participant_column,
            "positionNumber",
        ]].rename(columns={"positionNumber": "position"})
    ]

    # add simulated grand prix finishes without sprint results
    for event in simulated_events:
        if event["event_type"].iloc[0] == "race":
            finish_tables.append(
                event[[
                    participant_column,
                    "simulated_position",
                ]].rename(columns={"simulated_position": "position"})
            )

    finishes = pd.concat(finish_tables, ignore_index=True)

    # count wins, second places and all subsequent finishing positions
    finish_counts = pd.crosstab(
        finishes[participant_column],
        finishes["position"]
    )

    # sorted so that it starts with comparing 1st places, then 2nd, etc
    for position in sorted(finish_counts.columns):
        counts = finish_counts[position].reindex(
            candidates,
            fill_value=0
        )

        # keep only the candiates with the highest score in this categorys
        candidates = counts.loc[counts.eq(counts.max())].index

        # if this resolves the battle, return the single left candiate as winner
        if len(candidates) == 1:
            return candidates[0]

    # leave cases requiring further tie-break information unresolved
    return None


#### SIMULATION LOOP ####

n_simulations = 2000

driver_titles = pd.Series(0, index=driver_start_points.index)
constructor_titles = pd.Series(0, index=constructor_start_points.index)

driver_runs = []
constructor_runs = []

unresolved_driver_ties = 0
unresolved_constructor_ties = 0

# simulate different remaining seasons using the existing generator
for _ in range(n_simulations):
    driver_totals, constructor_totals, simulated_events = (
        simulate_remaining_season(rng)
    )

    driver_runs.append(driver_totals)
    constructor_runs.append(constructor_totals)

    driver_champion = get_champion(
        driver_totals,
        simulated_events,
        "driverId",
    )

    constructor_champion = get_champion(
        constructor_totals,
        simulated_events,
        "constructorId",
    )

    # count title wins without assigning unresolved ties arbitrarily
    if driver_champion is None:
        unresolved_driver_ties += 1
    else:
        driver_titles.loc[driver_champion] += 1

    if constructor_champion is None:
        unresolved_constructor_ties += 1
    else:
        constructor_titles.loc[constructor_champion] += 1

# calculate title probabilities and retain average final points
driver_summary = pd.DataFrame({
    "title_probability_pct": driver_titles / n_simulations * 100,
    "average_final_points": pd.DataFrame(driver_runs).mean(),
}).sort_values(
    ["title_probability_pct", "average_final_points"],
    ascending=[False, False],
)

constructor_summary = pd.DataFrame({
    "title_probability_pct": constructor_titles / n_simulations * 100,
    "average_final_points": pd.DataFrame(constructor_runs).mean(),
}).sort_values(
    ["title_probability_pct", "average_final_points"],
    ascending=[False, False],
)


print("\nDriver championship predictions:")
print(driver_summary.round(2).to_string())

print("\nConstructor championship predictions:")
print(constructor_summary.round(2).to_string())

print(
    "\nUnresolved driver ties (%):",
    unresolved_driver_ties / n_simulations * 100
)
print(
    "Unresolved constructor ties (%):",
    unresolved_constructor_ties / n_simulations * 100
)


#### STORAGE ####

# name the prediction after the grand prix used as the starting point
created_at = pd.Timestamp.now(tz="UTC")


race_name = latest_race["grandPrixId"]
relative_folder = (
    Path("championship")
    / str(YEAR)
    / f"after_{race_name}"
)

# save directly to the readable prediction folder
output_dir = PROJECT_DIR / "data" / "predictions" / relative_folder
output_dir.mkdir(parents=True, exist_ok=True)

# save both championship prediction tables
driver_summary.to_csv(
    output_dir / "driver_predictions.csv",
    index_label="driverId"
)

constructor_summary.to_csv(
    output_dir / "constructor_predictions.csv",
    index_label="constructorId"
)

# preserve the simulation inputs
future_predictions.to_csv(
    output_dir / "future_scores.csv",
    index=False
)

remaining_races.to_csv(
    output_dir / "remaining_races.csv",
    index=False
)

season_results.to_csv(
    output_dir / "historical_race_results.csv",
    index=False
)

# record the information state and simulation settings
metadata = {
    "created_at": created_at.isoformat(),
    "year": YEAR,
    "starting_round": latest_round,
    "starting_race_id": latest_race_id,
    "history_cutoff": cutoff.isoformat(),
    "mode": "historical" if AS_OF_ROUND is not None else "latest",
    "n_simulations": n_simulations,
    "random_seed": RANDOM_SEED,
    "score_noise_std": float(score_noise_std),
    "team_season_noise_std": float(team_season_noise_std),
    "event_noise_std": float(event_noise_std),
    "model_type": "Ridge",
    "alpha": float(season_model.named_steps["regression"].alpha),
    "driver_start_points": driver_start_points.to_dict(),
    "constructor_start_points": constructor_start_points.to_dict(),
    "completed_sprint_ids": sorted(
        int(race_id) for race_id in completed_sprint_ids
    ),
    "unresolved_driver_ties": unresolved_driver_ties,
    "unresolved_constructor_ties": unresolved_constructor_ties,
    "assumptions": [
        "baseline scores remain fixed with a shared team offset per simulated season",
        "the latest known lineup remains unchanged",
        "sprints use grand prix scores and the same noise scale",
        "future events award full points"
    ]
}

with (output_dir / "metadata.json").open("w", encoding="utf-8") as file:
    json.dump(metadata, file, indent=2, default=str)

print(f"\nLatest championship predictions saved to: {output_dir}")