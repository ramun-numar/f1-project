"""
Data for the website pages (Home, Next/Previous Race, Standings, Archive).

Builds on dashboard_data.load_tables() and the outputs the models save under
data/predictions/. Functions return DataFrames/dicts that are ready to show;
the pages only decide *where* things go.
"""
import json
from datetime import timedelta
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

from data import dashboard_data as dd

PREDICTIONS_DIR = dd.PROJECT_DIR / "data" / "predictions"

# points for P1..P10 in a Grand Prix (used to turn a predicted position into points)
RACE_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]


def load_site_tables():
    """dashboard_data tables + the extra files the website needs."""
    tables = dd.load_tables()
    tables["qualifying"] = dd._read("races-qualifying-results")
    tables["circuit_info"] = dd._read("circuits").set_index("id")  # lat/lon, place, ...
    races = tables["races"].copy()
    # one UTC timestamp per race start (f1db stores date and time separately)
    races["start"] = pd.to_datetime(races["date"] + " " + races["time"].fillna("00:00"), utc=True, errors="coerce")
    tables["races"] = races
    return tables


# ─────────────────────────────────────────────────────────────────────────────
# Races
# ─────────────────────────────────────────────────────────────────────────────
def race_info(tables, race_id):
    """Everything the pages show about one race, as a dict."""
    race = tables["races"].set_index("id").loc[race_id]
    circuit = tables["circuit_info"].loc[race["circuitId"]]

    def session(prefix):
        if pd.isna(race.get(f"{prefix}Date")):
            return None
        time = race.get(f"{prefix}Time")
        return pd.to_datetime(f"{race[f'{prefix}Date']} {'00:00' if pd.isna(time) else time}", utc=True)

    return {
        "id": int(race_id),
        "year": int(race["year"]),
        "round": int(race["round"]),
        "name": tables["grands_prix"].get(race["grandPrixId"], race["officialName"]),
        "grandPrixId": race["grandPrixId"],
        "circuitId": race["circuitId"],
        "circuit": circuit["name"],
        "place": circuit["placeName"],
        "lat": float(circuit["latitude"]),
        "lon": float(circuit["longitude"]),
        "start": race["start"],
        "date": pd.to_datetime(race["date"]),
        "fp1": session("freePractice1"),
        "qualifying": session("qualifying"),
        "sprint": session("sprintRace"),
    }


def previous_race(tables):
    """Most recent race that has results in the local data."""
    results = tables["results"]
    last = results.loc[results["year"].eq(results["year"].max())]
    race_id = last.loc[last["round"].idxmax(), "raceId"]
    return race_info(tables, race_id)


def next_race(tables, now=None):
    """Next race that hasn't started and has no results yet (None at season end)."""
    now = now or pd.Timestamp.now(tz="UTC")
    races = tables["races"]
    upcoming = races.loc[races["start"].gt(now) & ~races["id"].isin(tables["results"]["raceId"])]
    if upcoming.empty:
        return None
    return race_info(tables, upcoming.sort_values("start").iloc[0]["id"])


def races_with_results(tables, season):
    """{round: "R05 · Monaco Grand Prix"} for every finished race of a season."""
    done = tables["races"].loc[
        tables["races"]["year"].eq(season) & tables["races"]["id"].isin(tables["results"]["raceId"])
    ].sort_values("round", ascending=False)
    return {
        int(r["round"]): f"R{int(r['round']):02d} · {tables['grands_prix'].get(r['grandPrixId'], r['officialName'])}"
        for _, r in done.iterrows()
    }


def race_id_for(tables, season, rnd):
    races = tables["races"]
    return int(races.loc[races["year"].eq(season) & races["round"].eq(rnd), "id"].iloc[0])


def podium(tables, race_id, n=3):
    res = tables["results"]
    top = res.loc[res["raceId"].eq(race_id) & res["positionNumber"].le(n)].sort_values("positionNumber")
    return [
        {"pos": int(r["positionNumber"]), "name": tables["drivers"].get(r["driverId"], r["driverId"]),
         "team": tables["teams"].get(r["constructorId"], r["constructorId"])}
        for _, r in top.iterrows()
    ]


def qualifying(tables, race_id):
    """Qualifying table (Pos, Driver, Team, Q1, Q2, Q3) or an empty frame."""
    q = tables["qualifying"].loc[tables["qualifying"]["raceId"].eq(race_id)].sort_values("positionDisplayOrder")
    return pd.DataFrame({
        "Pos": q["positionText"],
        "Driver": q["driverId"].map(lambda d: tables["drivers"].get(d, d)),
        "Team": q["constructorId"].map(lambda t: tables["teams"].get(t, t)),
        "Q1": q["q1"].fillna(""),
        "Q2": q["q2"].fillna(""),
        "Q3": q["q3"].fillna(""),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Standings tables (Pos, Driver/Constructor, Points, Evo)
# ─────────────────────────────────────────────────────────────────────────────
def _names(tables, kind):
    return (tables["drivers"], "driverId", "driver_standings") if kind == "driver" \
        else (tables["teams"], "constructorId", "team_standings")


def standings_table(tables, season, rnd, kind="driver"):
    """Official standings after `rnd`. Evo = places gained since the previous round."""
    names, id_col, key = _names(tables, kind)
    s = tables[key]
    s = s.loc[s["year"].eq(season) & s["round"].eq(rnd)].sort_values("positionDisplayOrder")
    return pd.DataFrame({
        "id": s[id_col].values,
        "Pos": s["positionText"].values,
        "Name": s[id_col].map(lambda i: names.get(i, i)).values,
        "Points": s["points"].values,
        "Evo": s["positionsGained"].fillna(0).astype(int).values,
    })


def _championship_runs(season):
    """{starting_round: run folder} for every saved championship forecast."""
    runs = {}
    for meta in (dd.CHAMPIONSHIP_DIR / str(season)).glob("after_*/metadata.json"):
        runs[int(json.loads(meta.read_text(encoding="utf-8"))["starting_round"])] = meta.parent
    return runs


def forecast_round(season, rnd):
    """Latest saved forecast starting at or before `rnd` (None if there is none)."""
    rounds = [r for r in _championship_runs(season) if r <= rnd]
    return max(rounds) if rounds else None


def forecast_table(tables, season, rnd, kind="driver"):
    """Projected final standings from the championship model.

    Pos/Points are the simulated season-end values; Evo = places the model
    expects them to gain from their current position.
    """
    names, id_col, _ = _names(tables, kind)
    start = forecast_round(season, rnd)
    if start is None:
        return pd.DataFrame(), None
    file = "driver_predictions.csv" if kind == "driver" else "constructor_predictions.csv"
    f = pd.read_csv(_championship_runs(season)[start] / file)
    f = f.sort_values(["average_final_points", "title_probability_pct"], ascending=False).reset_index(drop=True)
    current = standings_table(tables, season, start, kind)
    current_pos = dict(zip(current["id"], range(1, len(current) + 1)))
    return pd.DataFrame({
        "id": f[id_col],
        "Pos": [str(i) for i in range(1, len(f) + 1)],
        "Name": f[id_col].map(lambda i: names.get(i, i)),
        "Points": f["average_final_points"].round(1),
        "Evo": [current_pos.get(i, len(f)) - (n + 1) for n, i in enumerate(f[id_col])],
        "Title %": f["title_probability_pct"],
    }), start


def title_probabilities(tables, season, rnd, kind="driver", top_n=3):
    """Top-n title chances plus the combined chance of everyone else."""
    table, start = forecast_table(tables, season, rnd, kind)
    if table.empty:
        return None
    # stable sort keeps the projected-points order among equal probabilities
    table = table.sort_values("Title %", ascending=False, kind="stable")
    return {
        "after_round": start,
        "top": list(zip(table["Name"].head(top_n), table["Title %"].head(top_n))),
        "rest": float(table["Title %"].iloc[top_n:].sum()),
    }


def favorite(tables, season, rnd):
    """('Champion'|'Favorite', name, detail) for the Standings banner."""
    final_round = int(tables["races"].loc[tables["races"]["year"].eq(season), "round"].max())
    if rnd >= final_round:
        top = standings_table(tables, season, rnd).iloc[0]
        return "Champion", top["Name"], f"{top['Points']:g} points"
    probs = title_probabilities(tables, season, rnd, top_n=1)
    if probs:
        name, pct = probs["top"][0]
        return "Favorite", name, f"{pct:.0f}% title chance (simulated after round {probs['after_round']})"
    top = standings_table(tables, season, rnd).iloc[0]
    return "Leader", top["Name"], f"{top['Points']:g} points"


def favorite_team(tables, season, rnd):
    final_round = int(tables["races"].loc[tables["races"]["year"].eq(season), "round"].max())
    table = standings_table(tables, season, rnd, "team")
    if table.empty:
        return None
    if rnd >= final_round:
        return "Champion", table.iloc[0]["Name"], f"{table.iloc[0]['Points']:g} points"
    probs = title_probabilities(tables, season, rnd, kind="team", top_n=1)
    if probs:
        name, pct = probs["top"][0]
        return "Favorite", name, f"{pct:.0f}% title chance (simulated after round {probs['after_round']})"
    return "Leader", table.iloc[0]["Name"], f"{table.iloc[0]['Points']:g} points"


# ─────────────────────────────────────────────────────────────────────────────
# Race predictions (saved by src/models/predict_race.py)
# ─────────────────────────────────────────────────────────────────────────────
def _prediction_file(race, mode):
    """data/predictions/<year>/<gp>/<mode>/prediction.csv, or the newest run in
    the older <round>-<gp>/<mode>/<timestamp>/ layout."""
    base = PREDICTIONS_DIR / str(race["year"])
    direct = base / race["grandPrixId"] / mode / "prediction.csv"
    if direct.is_file():
        return direct
    older = sorted(base.glob(f"*{race['grandPrixId']}/{mode}/*/prediction.csv"))
    return older[-1] if older else None


def race_prediction(tables, race, mode):
    """Predicted finishing order ('pre' = before qualifying, 'post' = after)."""
    path = _prediction_file(race, mode)
    if path is None:
        return pd.DataFrame()
    p = pd.read_csv(path).sort_values("predicted_position")
    pos = p["predicted_position"].astype(int)
    return pd.DataFrame({
        "id": p["driverId"].values,
        "Pos": pos.values,
        "Driver": p["driverId"].map(lambda d: tables["drivers"].get(d, d)).values,
        "Const.": p["constructorId"].map(lambda t: tables["teams"].get(t, t)).values,
        "Points": [RACE_POINTS[i - 1] if i <= 10 else 0 for i in pos],
        "Grid": p["qualificationPositionNumber"].values,
    })


def predicted_outcome(tables, race, after_quali):
    """Table for the 'Predicted Outcome' card.

    Evo = how many places the qualifying data moved the driver
    (pre-qualifying position minus post-qualifying position).
    """
    pre = race_prediction(tables, race, "pre")
    post = race_prediction(tables, race, "post")
    shown = post if after_quali else pre
    if shown.empty:
        return shown
    shown = shown.drop(columns=["Grid"])
    if after_quali and not pre.empty:
        before = dict(zip(pre["id"], pre["Pos"]))
        shown["Evo"] = [before.get(i, p) - p for i, p in zip(shown["id"], shown["Pos"])]
    return shown


def model_errors(tables, race):
    """Mean absolute position error of the saved predictions vs. the result.

    Baseline = "finish where you qualified" (grid position as the prediction).
    Returns {} when the race has no results or no saved predictions.
    """
    res = tables["results"]
    actual = res.loc[res["raceId"].eq(race["id"])].set_index("driverId")["positionDisplayOrder"]
    if actual.empty:
        return {}
    out = {}
    for label, mode in [("Pre-qualifying model", "pre"), ("Post-qualifying model", "post")]:
        pred = race_prediction(tables, race, mode)
        if not pred.empty:
            pred = pred.set_index("id")
            common = pred.index.intersection(actual.index)
            out[label] = float((pred.loc[common, "Pos"] - actual[common]).abs().mean())
    grid = tables["qualifying"].loc[tables["qualifying"]["raceId"].eq(race["id"])].set_index("driverId")["positionDisplayOrder"]
    common = grid.index.intersection(actual.index)
    if len(common) and out:
        out["Baseline (finish = grid)"] = float((grid[common] - actual[common]).abs().mean())
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Weather (Open-Meteo: free, no API key, ~16 days ahead)
# ─────────────────────────────────────────────────────────────────────────────
WEATHER_CODES = {0: "☀️ Clear", 1: "🌤️ Mostly clear", 2: "⛅ Partly cloudy", 3: "☁️ Overcast",
                 45: "🌫️ Fog", 48: "🌫️ Fog", 51: "🌦️ Drizzle", 53: "🌦️ Drizzle", 55: "🌦️ Drizzle",
                 61: "🌧️ Rain", 63: "🌧️ Rain", 65: "🌧️ Heavy rain", 80: "🌦️ Showers", 81: "🌧️ Showers",
                 82: "⛈️ Heavy showers", 95: "⛈️ Thunderstorm", 96: "⛈️ Thunderstorm", 99: "⛈️ Thunderstorm"}


def weather_forecast(lat, lon, first_day, last_day):
    """Daily forecast between two dates, or [] if they're out of range."""
    query = urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
        "start_date": first_day.strftime("%Y-%m-%d"), "end_date": last_day.strftime("%Y-%m-%d"),
    })
    with urlopen(f"https://api.open-meteo.com/v1/forecast?{query}", timeout=15) as response:
        daily = json.loads(response.read())["daily"]
    return [
        {"date": pd.to_datetime(d), "sky": WEATHER_CODES.get(code, "🌡️"), "max": tmax, "min": tmin,
         "rain": rain, "wind": wind}
        for d, code, tmax, tmin, rain, wind in zip(
            daily["time"], daily["weather_code"], daily["temperature_2m_max"], daily["temperature_2m_min"],
            daily["precipitation_probability_max"], daily["wind_speed_10m_max"])
    ]


def weekend_days(race):
    """First practice day .. race day."""
    first = (race["fp1"] or race["start"] - timedelta(days=2)).normalize()
    return first, race["start"].normalize()
