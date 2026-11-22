"""
Predictions page: runs src/app.py unchanged.

app.py is the team's standalone app (still runnable on its own with
`streamlit run src/app.py`). This wrapper only exists so the page lives in
pages/, which is where Streamlit looks when resolving st.page_link paths.
run_path executes app.py with its own __file__, so its relative paths
(e.g. models/predict_race.py) keep working.
"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "app.py"))
