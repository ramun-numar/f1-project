"""
Data for the dashboard page, built from the f1db CSVs in data/raw/.
(Run src/data/update_data.py to refresh them.)

Every public function returns a plain list of dicts, the shape the dashboard's
card helpers expect, so the page code never deals with pandas.
"""
from pathlib import Path
import json
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
# written by src/models/championship.py:
#   <season>/after_round_<N>/<timestamp>/{driver,constructor}_predictions.csv
CHAMPIONSHIP_DIR = PROJECT_DIR / "data" / "predictions" / "championship"


def _read(name):
    return pd.read_csv(RAW_DIR / f"f1db-{name}.csv", low_memory=False)


def load_tables():
    """Read every CSV the dashboard needs once. The page caches the result."""
    return {
        "races": _read("races"),
        "results": _read("races-race-results"),
        "driver_standings": _read("races-driver-standings"),
        "team_standings": _read("races-constructor-standings"),
        "drivers": _read("drivers").set_index("id")["name"],          # id -> "Max Verstappen"
        "teams": _read("constructors").set_index("id")["name"],       # id -> "Red Bull"
        "grands_prix": _read("grands-prix").set_index("id")["fullName"],
        "circuits": _read("circuits").set_index("id")["name"],
    }


def seasons(tables):
    """Seasons that have at least one finished race, newest first."""
    return sorted(tables["driver_standings"]["year"].unique(), reverse=True)


def last_round(tables, season):
    """Most recent round of `season` that has race results.

    The standings files can be downloaded more recently than the race-results
    file, so we cap at the latest round present in *both*. That keeps the
    standings and the Race Analytics cards in step.
    """
    standings_max = tables["driver_standings"].query("year == @season")["round"].max()
    results_max = tables["results"].query("year == @season")["round"].max()
    return int(min(standings_max, results_max))


def _standings(tables, standings, names, id_col, season, top_n):
    """Shared logic for driver and team standings.

    f1db stores the championship table after *every* round, so:
      - total points = the row for the latest round
      - "change" = points scored that round = latest total minus previous total
    These totals include sprint points.
    """
    season_rows = standings[standings["year"] == season]
    if season_rows.empty:
        return []
    rnd = last_round(tables, season)
    now = season_rows[season_rows["round"] == rnd].sort_values("positionDisplayOrder")
    before = season_rows[season_rows["round"] == rnd - 1].set_index(id_col)["points"]

    rows = []
    for _, r in now.head(top_n).iterrows():
        prev = before.get(r[id_col], 0)
        rows.append({
            "position": r["positionText"],
            "name": names.get(r[id_col], r[id_col]),
            "points": int(r["points"]) if float(r["points"]).is_integer() else r["points"],
            "change": int(r["points"] - prev),
        })
    return rows


def driver_standings(tables, season, top_n=4):
    return _standings(tables, tables["driver_standings"], tables["drivers"], "driverId", season, top_n)


def team_standings(tables, season, top_n=4):
    # Constructor championship only exists from 1958 onward -> [] for earlier seasons.
    return _standings(tables, tables["team_standings"], tables["teams"], "constructorId", season, top_n)


def recent_races(tables, season, n=4):
    """The last `n` races of the season that have results, newest first."""
    results = tables["results"]
    winners = results[(results["year"] == season) & (results["positionNumber"] == 1)]
    races = tables["races"]
    done = races[races["id"].isin(winners["raceId"])].sort_values("round", ascending=False)

    out = []
    for _, race in done.head(n).iterrows():
        winner_id = winners.loc[winners["raceId"] == race["id"], "driverId"].iloc[0]
        out.append({
            "name": tables["grands_prix"].get(race["grandPrixId"], race["officialName"]),
            "round": int(race["round"]),
            "date": pd.to_datetime(race["date"]).strftime("%b %-d"),
            "circuit": tables["circuits"].get(race["circuitId"], race["circuitId"]),
            "winner": tables["drivers"].get(winner_id, winner_id),
        })
    return out


def championship_prediction(tables, season, top_n=4):
    """Latest saved run of the championship model for `season`, or None.

    Picks the run with the highest round, then the newest timestamp folder
    (timestamps sort correctly as text, e.g. 20261119T192336Z).
    """
    # read the starting round from the prediction metadata
    def run_key(path):
        metadata = json.loads((path.parent / "metadata.json").read_text(encoding="utf-8"))
        return metadata["starting_round"]

    runs = sorted((CHAMPIONSHIP_DIR / str(season)).glob("after_*/driver_predictions.csv"), key=run_key)

    if not runs:
        return None
    
    run_dir = runs[-1].parent
    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))

    def rows(file, id_col, names):
        df = pd.read_csv(run_dir / file).sort_values("average_final_points", ascending=False)
        return [
            {
                "name": names.get(r[id_col], r[id_col]),
                "title_pct": float(r["title_probability_pct"]),
                "final_points": round(float(r["average_final_points"])),
            }
            for _, r in df.head(top_n).iterrows()
        ]

    return {
        "after_round": int(metadata["starting_round"]),
        "drivers": rows("driver_predictions.csv", "driverId", tables["drivers"]),
        "teams": rows("constructor_predictions.csv", "constructorId", tables["teams"]),
    }
