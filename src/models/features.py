from pathlib import Path
import pandas as pd

categorical_features = [
    "driverId",
    "constructorId",
    "circuitId",
    "circuitType"]

numeric_features = [
    "gridPositionNumber",
    "qualificationPositionNumber",
    "grid_fraction",
    "qualifying_fraction",
    "pit_lane",
    "street",
    "grid_street",
    "qualifying_street",
    "courseLength",
    "turns",
    "scheduledLaps",
    "q1_gap",
    # "q2_gap",
    # "q3_gap",
    "driver_std_5",
    "driver_std_10",
    "driver_experience",
    "driver_circuit_form",
    "driver_circuit_experience",
    "team_circuit_form",
    "circuit_dnf_history",
    "driver_team_difference",
    "quali_vs_recent",
    "team_quali_vs_recent"]

rolling_window_features = [
    "driver_finish",
    "driver_quali",
    "driver_dnf",
    "team_finish",
    "team_quali",
    "team_dnf"]

for window in [3, 5, 10, 20]:
    for name in rolling_window_features:
        numeric_features.append(f"{name}_{window}")


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data" / "raw"


def prepare_features(upcoming_race=None):

    #### IMPORT DATA ####

    race_results = pd.read_csv(
        # low_memory = Fale: to get rid fo the DtypeWarning
        DATA_DIR / "f1db-races-race-results.csv", low_memory=False)

    races = pd.read_csv(DATA_DIR / "f1db-races.csv")

    quali_results = pd.read_csv(
        DATA_DIR / "f1db-races-qualifying-results.csv", low_memory=False)

    # Keep data from 2010 onwards without a fixed end year, since the model should be able to model ongoing races, not only until 2026
    races = races[races["year"].ge(2010)].copy()
    race_results = race_results[race_results["year"].ge(2010)].copy()
    quali_results = quali_results[quali_results["year"].ge(2010)].copy()

    #### MERGE DATA ####

    model_data = race_results.merge(
        races[[
            "id",
            "date",
            "circuitId",
            "circuitType",
            "courseLength",
            "turns",
            "scheduledLaps"]],
        left_on="raceId",
        right_on="id",
        how="inner",
        validate="many_to_one"
    ).drop(columns="id")

    model_data = model_data.merge(
        quali_results[[
            "raceId",
            "driverId",
            "q1Millis",
            "q2Millis",
            "q3Millis"]],
        on=["raceId", "driverId"],
        how="left",
        validate="one_to_one")

    # Add one upcoming race before calculating historical features, so the model
    # receives the same features as during training, based only on past race results.
    if upcoming_race is not None:       # should always be true
        # leave the upcoming as it is, i.e. no side effects as we change its copy
        upcoming = upcoming_race.copy()

        # for more or less than one different race in upcoming a ValueError is raised
        if upcoming.empty or upcoming["raceId"].nunique() != 1:
            raise ValueError("Provide participants for exactly one race.")

        # create a date class object out of the date column
        upcoming_dates = pd.to_datetime(upcoming["date"])

        # if the dates differ or aren't available raise a ValueError
        if upcoming_dates.isna().any() or upcoming_dates.nunique() != 1:
            raise ValueError(
                "All participants must have the same valid race date.")

        # takes the date of the first row, which doesn't matter as all are the same
        race_date = upcoming_dates.iloc[0]

        # keep only races completed before the race being predicted
        # this also removes its real results when testing a past race
        historical_dates = pd.to_datetime(model_data["date"])
        model_data = model_data.loc[historical_dates.lt(race_date)].copy()

        # never use the target race's actual outcome
        upcoming["positionDisplayOrder"] = float("nan")
        upcoming["positionText"] = None
        upcoming["reasonRetired"] = None

        # extends the model_data with the upcoming race and creates new indizes, s.t. the upcoming doesn't start with 0 again
        model_data = pd.concat([model_data, upcoming], ignore_index=True)

        # use a consistent date format and chronological order, as the csv has it as text and the yaml can contain time class objects
        # thus all are firstly chnaged to date class objects and then back to text in the form of 2026-11-07
        model_data["date"] = pd.to_datetime(
            model_data["date"]).dt.strftime("%Y-%m-%d")

        # sorts the data again for date, raceId, then driverId.
        # This automatically solves the problem we earlier had where the ML-model was trained in such a way to create ties,
        # because of the leak of informarion through data sets being sorted after finishing position
        model_data = model_data.sort_values(
            ["date", "raceId", "driverId"]).reset_index(drop=True)

    #### HANDLING MISSING VALUES ####

    model_data = model_data[model_data["gridPositionText"].notna()]

    model_data["fieldSize"] = model_data.groupby(
        "raceId")["driverId"].transform("size")

    model_data.loc[model_data["gridPositionText"] == "PL",
                   "gridPositionNumber"] = model_data["fieldSize"]

    #### FEARTURE SELECTION ####

    columns_needed = [
        "raceId",
        "fieldSize",
        "year",
        "round",
        "date",
        "driverId",
        "constructorId",
        "circuitId",
        "circuitType",
        "courseLength",
        "turns",
        "scheduledLaps",
        "gridPositionNumber",
        "gridPositionText",
        "qualificationPositionNumber",
        "q1Millis",
        "q2Millis",
        "q3Millis",
        "positionDisplayOrder",
        "positionText",
        "reasonRetired"]

    model_data = model_data[columns_needed]

    #### FEATURE CREATION ####

    # Normalizing the positions
    model_data["qualifying_fraction"] = (
        model_data["qualificationPositionNumber"] - 1) / (model_data["fieldSize"] - 1)

    model_data["grid_fraction"] = (
        model_data["gridPositionNumber"] - 1) / (model_data["fieldSize"] - 1)

    model_data["finish_fraction"] = (
        model_data["positionDisplayOrder"] - 1) / (model_data["fieldSize"] - 1)

    model_data["driver_finish_5"] = model_data.groupby("driverId")[
        "finish_fraction"].transform(
            lambda x: x.shift(1).rolling(5, min_periods=1).mean())

    model_data["driver_quali_5"] = (
        model_data.groupby("driverId")["qualifying_fraction"]
        .transform(lambda x:
                   x.shift(1).rolling(5, min_periods=1).mean()))

    model_data["quali_vs_recent"] = model_data["qualifying_fraction"] - \
        model_data["driver_quali_5"]

    model_data["failure"] = model_data["positionText"].eq(
        "DNF") | model_data["reasonRetired"].notna()

    model_data["failure_rate"] = (
        model_data.groupby("driverId")["failure"]
        .transform(
            lambda failrate:
            failrate.shift(1).rolling(10, min_periods=5).mean()
        )
    )

    for window in [3, 5, 10, 20]:
        for source, name in [("finish_fraction", "finish"), ("qualifying_fraction", "quali"), ("failure", "failure_rate")]:
            model_data[f"driver_{name}_{window}"] = (
                model_data.groupby("driverId")[source]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=1).mean()))

    for window in [5, 10]:
        model_data[f"driver_std_{window}"] = (
            model_data.groupby("driverId")["finish_fraction"]
            .transform(
                lambda x: x.shift(1).rolling(
                    window, min_periods=2
                ).std()
            )
        )

    model_data["driver_experience"] = model_data.groupby("driverId").cumcount()

    model_data["driver_circuit_experience"] = model_data.groupby(
        ["driverId", "circuitId"]).cumcount()

    model_data["driver_circuit_form"] = (
        model_data.groupby(
            ["driverId", "circuitId"]
        )["finish_fraction"]
        .transform(
            lambda x: x.shift(1).rolling(3, min_periods=1).mean()
        )
    )

    for window in [3, 5, 10, 20]:
        model_data[f"driver_dnf_{window}"] = (
            model_data.groupby("driverId")["failure"]
            .transform(
                lambda x: x.shift(1).rolling(
                    window, min_periods=1
                ).mean()
            )
        )

    team_data = (
        model_data.groupby(
            ["raceId", "constructorId", "circuitId"],
            as_index=False)
        .agg(
            team_finish=("finish_fraction", "mean"),
            team_quali=("qualifying_fraction", "mean"),
            team_dnf=("failure", "mean")
        )
    )

    for window in [3, 5, 10, 20]:
        for source in ["team_finish", "team_quali", "team_dnf"]:
            team_data[f"{source}_{window}"] = (
                team_data.groupby("constructorId")[source]
                .transform(
                    lambda x: x.shift(1).rolling(
                        window, min_periods=1
                    ).mean()
                )
            )

    team_data["team_circuit_form"] = (
        team_data.groupby(
            ["constructorId", "circuitId"]
        )["team_finish"]
        .transform(
            lambda x: x.shift(1).rolling(3, min_periods=1).mean()
        )
    )

    team_features = [
        f"{name}_{window}"
        for window in [3, 5, 10, 20]
        for name in ["team_finish", "team_quali", "team_dnf"]
    ] + ["team_circuit_form"]

    model_data = model_data.merge(
        team_data[["raceId", "constructorId"] + team_features],
        on=["raceId", "constructorId"],
        how="left",
        validate="many_to_one"
    )

    model_data["driver_team_difference"] = model_data["driver_finish_5"] - \
        model_data["team_finish_5"]

    model_data["team_quali_vs_recent"] = (
        model_data.groupby(
            ["raceId", "constructorId"]
        )["qualifying_fraction"].transform("mean")
        - model_data["team_quali_5"]
    )

    for stage in [1, 2, 3]:
        column = f"q{stage}Millis"

        best_time = model_data.groupby("raceId")[column].transform("min")

        model_data[f"q{stage}_gap"] = (
            model_data[column] / best_time - 1) * 100

    model_data["street"] = model_data["circuitType"].eq("STREET").astype(int)

    model_data["grid_street"] = model_data["grid_fraction"] * \
        model_data["street"]

    model_data["qualifying_street"] = model_data["qualifying_fraction"] * \
        model_data["street"]

    model_data["pit_lane"] = model_data["gridPositionText"].eq(
        "PL").astype(int)

    circuit_data = (
        model_data.groupby(
            ["raceId", "circuitId"], as_index=False)
        .agg(circuit_dnf=("failure", "mean")))

    circuit_data["circuit_dnf_history"] = (
        circuit_data.groupby("circuitId")["circuit_dnf"]
        .transform(
            lambda x: x.shift(1).rolling(5, min_periods=1).mean()))

    model_data = model_data.merge(
        circuit_data[["raceId", "circuit_dnf_history"]],
        on="raceId",
        how="left",
        validate="many_to_one")

    return model_data
