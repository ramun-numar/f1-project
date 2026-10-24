# NOT SURE IF NEEDED...


from pathlib import Path

import pandas as pd
import requests

# Select the race weekend
YEAR = 2026
ROUND = 1

# Define the output folder
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = (
    PROJECT_DIR / "data" / "raw"
    / str(YEAR) / f"round_{ROUND:02d}" / "Q"
)

# Request qualifying results for this specific race
URL = f"https://api.jolpi.ca/ergast/f1/{YEAR}/{ROUND}/qualifying/"

response = requests.get(
    URL,
    params={"limit": 100},
    headers={"User-Agent": "F1StudentProject/0.1"},
    timeout=30,
)

# Stop if the server returns an HTTP error
response.raise_for_status()

# Convert the JSON response into Python dictionaries
data = response.json()["MRData"]
races = data["RaceTable"]["Races"]

if not races or not races[0].get("QualifyingResults"):
    raise SystemExit(
        "No qualifying results available yet. "
        "Existing files have not been changed."
    )

race = races[0]
entries = race["QualifyingResults"]

# Check that the response contains all published entries
if len(entries) != int(data["total"]):
    raise SystemExit("The response is incomplete. No file saved.")

# Convert nested driver and team information into a flat table
rows = []

for entry in entries:
    driver = entry["Driver"]
    team = entry["Constructor"]

    rows.append({
        "year": int(race["season"]),
        "round": int(race["round"]),
        "race_name": race["raceName"],
        "driver_id": driver["driverId"],
        "driver_name": (
            f"{driver['givenName']} {driver['familyName']}"
        ),
        "constructor_id": team["constructorId"],
        "qualifying_position": entry.get("position"),
        "Q1": entry.get("Q1"),
        "Q2": entry.get("Q2"),
        "Q3": entry.get("Q3"),
    })

results = pd.DataFrame(rows)

results["qualifying_position"] = pd.to_numeric(
    results["qualifying_position"],
    errors="coerce",
)

if (
    results["driver_id"].duplicated().any()
    or results["qualifying_position"].isna().any()
):
    raise SystemExit("Duplicate drivers or missing positions. No file saved.")

results = results.sort_values("qualifying_position")
results["downloaded_at_utc"] = pd.Timestamp.now(tz="UTC").isoformat()

# Save the new table, replacing the previous version
DATA_DIR.mkdir(parents=True, exist_ok=True)
destination = DATA_DIR / "results.csv"

temporary = destination.with_suffix(".csv.tmp")
results.to_csv(temporary, index=False)
temporary.replace(destination)

print(f"Saved {len(results)} qualifying results:")
print(destination)
print(
    results[["driver_name", "qualifying_position", "Q1", "Q2", "Q3"]]
    .to_string(index=False)
)
