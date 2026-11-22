from pathlib import Path
import os
import subprocess
import sys
from urllib.error import HTTPError

import pandas as pd
from data.race_data import load_yaml


PROJECT_DIR = Path(__file__).resolve().parents[2]


def run_script(relative_path, *arguments):
    # make project modules available to the child process
    environment = os.environ.copy()
    environment["PYTHONPATH"] = (
        str(PROJECT_DIR / "src")
        + os.pathsep
        + environment.get("PYTHONPATH", "")
    )

    # use the same python interpreter and stop if the script fails
    subprocess.run(
        [
            sys.executable,
            str(PROJECT_DIR / "src" / relative_path),
            *arguments,
        ],
        cwd=PROJECT_DIR,
        env=environment,
        check=True
    )


def main():
    # download the latest available data
    run_script("data/update_data.py")

    races = pd.read_csv(
        PROJECT_DIR / "data" / "raw" / "f1db-races.csv"
    )
    results = pd.read_csv(
        PROJECT_DIR / "data" / "raw" / "f1db-races-race-results.csv",
        low_memory=False
    )

    # select the current season
    now = pd.Timestamp.now(tz="UTC")
    year = int(now.year)

    season = races.loc[races["year"].eq(year)].copy()

    if season.empty:
        print(f"No calendar available for {year}")
        return

    # combine the calendar date and time using utc
    season["race_start"] = pd.to_datetime(
        season["date"] + " " + season["time"].fillna("00:00"),
        utc=True,
        errors="coerce"
    )

    # select the next race that has not started and has no recorded result
    upcoming = season.loc[
        season["race_start"].gt(now)
        & ~season["id"].isin(results["raceId"])
    ].sort_values("race_start")

    # as we again don't know who will drive, until the first race of the season is recorded
    has_previous_race = results["year"].eq(year).any()

    if not upcoming.empty:
        race = upcoming.iloc[0]
        race_folder = (
            f"{int(race['round']):02d}-{race['grandPrixId']}"
        )

        arguments = [
            "--year",
            str(year),
            "--race-folder",
            race_folder
        ]

        #  flush = True: appering in the terminal output as soon as executed, not only at the end
        print(f"Next race: {race['officialName']}", flush=True)

        # the current pre-race participant loader needs an earlier season race
        if has_previous_race:
            run_script(
                "models/predict_race.py",
                *arguments,
                "--mode",
                "pre"
            )
        else:
            print("Pre-race forecast requires an earlier race in this season")

        # check current qualifying separately from the csv release
        qualifying_url = (
            "https://raw.githubusercontent.com/f1db/f1db/main/"
            f"src/data/seasons/{year}/races/{race_folder}/"
            "qualifying-results.yml"
        )

        try:
            qualifying = load_yaml(qualifying_url)
        except HTTPError as error:
            if error.code != 404:
                raise
            qualifying = None

        if qualifying is None or qualifying == []:
            print("Qualifying not yet available; skipping post forecast")
        elif not isinstance(qualifying, list):
            raise ValueError("Unexpected qualifying data format")
        else:
            run_script(
                "models/predict_race.py",
                *arguments,
                "--mode",
                "post",
            )
    else:
        print("No upcoming race found in this season")

    # update both championships using the latest available standings
    if has_previous_race:
        run_script(
            "models/championship.py",
            "--year",
            str(year),
            "--latest",
        )
    else:
        print("Championship forecast requires completed race standings")

    print("Update finished")


if __name__ == "__main__":
    main()