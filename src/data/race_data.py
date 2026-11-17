from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pandas as pd
import yaml


#### QUALIFYING DATA ####

def load_yaml(url):
    request = Request(url)
    with urlopen(request, timeout=60) as response:
        return yaml.safe_load(response.read().decode("utf-8"))


def time_to_milliseconds(value):
    if value is None or pd.isna(value):
        return None

    minutes, seconds = str(value).split(":")
    return int((Decimal(minutes) * 60 + Decimal(seconds)) * 1000)


def load_race_data(year, race_folder, mode="post"):
    base_url = ("https://raw.githubusercontent.com/f1db/f1db/main/" +
                f"src/data/seasons/{year}/races/{race_folder}")
    race = load_yaml(f"{base_url}/race.yml")

    if mode not in {"pre", "post"}:
        raise ValueError("Prediction mode must be 'pre' or 'post'")

    # try to get to know which drivers drove last to make a prediction for the race
    if mode == "pre":
        data_dir = Path(__file__).resolve().parents[2] / "data" / "raw"

        results = pd.read_csv(
            data_dir / "f1db-races-race-results.csv"
        )
        calendar = pd.read_csv(data_dir / "f1db-races.csv")

        # use only earlier races from the same season
        history = results.merge(
            calendar[["id", "date"]],
            left_on="raceId",
            right_on="id",
            validate="many_to_one",
        )

        history = history.loc[
            history["year"].eq(year)
            & pd.to_datetime(history["date"]).lt(pd.Timestamp(race["date"]))
        ]

        # for the first race of the season we can't do a prediction with this set up,
        # as we don't know yet, which drivers will start for which teams
        if history.empty:
            raise ValueError(
                "No earlier race results available for this season"
            )

        # assume the latest available lineup remains unchanged
        latest_race_id = history.sort_values(
            ["date", "raceId"]
        )["raceId"].iloc[-1]

        drivers = history.loc[
            history["raceId"].eq(latest_race_id),
            ["driverId", "constructorId"],
        ].copy()

        if drivers["driverId"].duplicated().any():
            raise ValueError("Duplicate participant entries")

        drivers["raceId"] = race["id"]
        drivers["year"] = year
        drivers["round"] = race["round"]

        # leave current qualifying information unknown
        for column in ["qualificationPositionNumber", "q1Millis", "q2Millis", "q3Millis"]:
            drivers[column] = float("nan")

        print(
            f"Using participants from race {latest_race_id}; "
            "assuming no driver or team changes"
        )

        return race, drivers

    try:
        qualifying = load_yaml(f"{base_url}/qualifying-results.yml")
    except HTTPError as error:
        if error.code == 404:
            raise ValueError(
                "No qualifying file found. Check if the right race folder is selected or try again after F1DB has published the results.")
        raise

    if not isinstance(qualifying, list) or not qualifying:
        raise ValueError("The qualifying file contains no results.")

    drivers = pd.DataFrame(qualifying)

    drivers["raceId"] = race["id"]
    drivers["year"] = year
    drivers["round"] = race["round"]

    drivers["qualificationPositionNumber"] = pd.to_numeric(
        drivers["position"], errors="coerce")

    for stage in [1, 2, 3]:
        column = f"q{stage}"

        if column not in drivers.columns:
            drivers[column] = None

        drivers[f"{column}Millis"] = drivers[column].map(
            time_to_milliseconds).astype("Int64")

    columns = [
        "raceId",
        "year",
        "round",
        "driverId",
        "constructorId",
        "qualificationPositionNumber",
        "q1Millis",
        "q2Millis",
        "q3Millis",
    ]

    drivers = drivers[columns]

    if drivers.duplicated(["raceId", "driverId"]).any():
        raise ValueError("Duplicate qualifying entries")

    return race, drivers


#### STARTING GRID ####

def add_starting_grid(participants, grid_path):
    grid = pd.read_csv(grid_path, dtype={"gridPositionText": "string"})

    grid["gridPositionText"] = grid["gridPositionText"].str.strip().str.upper()

    drivers = participants.merge(grid[["raceId", "driverId", "gridPositionText"]],
                                 on=["raceId", "driverId"],
                                 how="outer",
                                 validate="one_to_one",
                                 # creates a helper column: _merge. She shows where the column comes from -> both, left_only or right_only
                                 indicator=True)

    if not drivers["_merge"].eq("both").all():
        raise ValueError(
            "The starting-grid file does not match the participants.")

    drivers = drivers.drop(columns="_merge")

    text = drivers["gridPositionText"]

    numbers = pd.to_numeric(text, errors="coerce")

    valid_number = numbers.ge(1) & numbers.mod(1).eq(0)
    valid_special = text.isin(["PL", "DNS", "DNQ"])

    if not (valid_number | valid_special).fillna(False).all():
        raise ValueError(
            "Fill every starting position with a positive integer PL, DNS or DNQ.")

    drivers = drivers.loc[~text.isin(["DNS", "DNQ"])].copy()

    drivers["fieldSize"] = drivers.groupby(
        "raceId")["driverId"].transform("size")

    drivers["gridPositionNumber"] = numbers.loc[drivers.index]

    drivers.loc[drivers["gridPositionText"].eq(
        "PL"), "gridPositionNumber"] = drivers["fieldSize"]

    return drivers
