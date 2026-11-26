"""
Entry point for the website:  streamlit run src/main.py

This file is only a router. It registers every page and draws the sidebar
menu from the sketch:

    Home · Previous Race · Next Race · ▾ Standings (Driver, Constructor)
    · Predictions · Archive · (Race Explorer = the team's src/app.py)

How Streamlit works: every time the user clicks or changes a widget, Streamlit
re-runs the script top to bottom. With st.navigation, it runs this file first,
then the file of whichever page is selected.
"""
import streamlit as st

# set_page_config must be the first Streamlit call. layout="wide" uses the full
# browser width instead of a narrow centered column, which a dashboard needs.
st.set_page_config(page_title="F1 Analytics", page_icon="🏎️", layout="wide", initial_sidebar_state="expanded")

# Each st.Page is one page of the site. Paths are relative to this file.
# Icons use Google's Material Symbols: browse https://fonts.google.com/icons
# and write the name as ":material/<name>:".
home = st.Page("pages/home.py", title="Home", icon=":material/home:", default=True)
previous_race = st.Page("pages/previous_race.py", title="Previous Race", icon=":material/flag:")
next_race = st.Page("pages/next_race.py", title="Next Race", icon=":material/timer:")
drivers = st.Page("pages/drivers.py", title="Driver", icon=":material/person:")
teams = st.Page("pages/teams.py", title="Constructor", icon=":material/groups:")
predictions = st.Page("pages/predictions.py", title="Predictions", icon=":material/query_stats:")
archive = st.Page("pages/archive.py", title="Archive", icon=":material/inventory_2:")
race_explorer = st.Page("pages/race_explorer.py", title="Race Explorer", icon=":material/science:")

# position="hidden" registers the pages but doesn't draw Streamlit's own menu,
# because we draw our own below (Streamlit's can't do the Standings sub-menu).
nav = st.navigation(
    [home, previous_race, next_race, drivers, teams, predictions, archive, race_explorer],
    position="hidden",
)

with st.sidebar:
    st.markdown("## 🏎️ F1 :red[Analytics]")
    st.page_link(home)
    st.page_link(previous_race)
    st.page_link(next_race)
    # st.expander is a collapsible box; open it automatically on a Standings page
    with st.expander("Standings", icon=":material/leaderboard:", expanded=nav in (drivers, teams)):
        st.page_link(drivers)
        st.page_link(teams)
    st.page_link(predictions)
    st.page_link(archive)
    st.divider()
    st.page_link(race_explorer)

nav.run()
