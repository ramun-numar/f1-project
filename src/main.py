"""
Entry point for the full multi-page app:  streamlit run src/main.py

This file is only a router. It defines which pages exist and draws the nav
bar; it doesn't change any existing code. The original single-page app
(src/app.py) is included unchanged as the "Predictions" page (via
pages/predictions.py), and can still be
run on its own with `streamlit run src/app.py`.

How Streamlit works: every time the user clicks or changes a widget, Streamlit
re-runs the script top to bottom. With st.navigation, it runs this file first,
then the file of whichever page is selected.
"""
import streamlit as st

# set_page_config must be the first Streamlit call. layout="wide" uses the full
# browser width instead of a narrow centered column, which a dashboard needs.
st.set_page_config(page_title="F1 Analytics", page_icon="🏎️", layout="wide")

# Each st.Page is one entry in the nav. Paths are relative to this file.
# Icons use Google's Material Symbols: browse https://fonts.google.com/icons
# and write the name as ":material/<name>:".
dashboard = st.Page("pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True)
drivers = st.Page("pages/drivers.py", title="Drivers", icon=":material/person:")
teams = st.Page("pages/teams.py", title="Teams", icon=":material/groups:")
predictions = st.Page("pages/predictions.py", title="Predictions", icon=":material/query_stats:")

# position="top" puts the nav in a horizontal bar across the top, like the
# reference site. The default is a sidebar.
nav = st.navigation([dashboard, drivers, teams, predictions], position="top")
nav.run()
