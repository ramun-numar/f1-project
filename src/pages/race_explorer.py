"""
Race Explorer: runs src/app.py unchanged.

app.py is the team's standalone app (race prediction charts, telemetry and
overtake highlights). It is still runnable on its own with
`streamlit run src/app.py`. run_path executes it with its own __file__, so
its relative paths (e.g. models/predict_race.py) keep working.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "app.py"))
