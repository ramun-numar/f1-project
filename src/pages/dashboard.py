"""
Dashboard: the main page. Layout modeled on f1analytics.online/dashboard.

    ┌────────────────────────────────────────────┬─────────────────┐
    │ Dashboard                       [season ▾] │                 │
    ├────────────────────────────────────────────┼─────────────────┤
    │ Team Standings      (2x2 metric cards)     │ Race Analytics  │
    │ Driver Standings    (2x2 metric cards)     │ (stacked cards) │
    └────────────────────────────────────────────┴─────────────────┘

The file has three parts:
  1. DATA: load the f1db tables (see src/data/dashboard_data.py).
  2. HELPERS: small functions that draw one repeated piece (a header, a card).
  3. LAYOUT: arranges the helpers into columns.
"""
import streamlit as st

from data import dashboard_data as dd

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA
# ─────────────────────────────────────────────────────────────────────────────
# Remember that Streamlit re-runs this file on every click. @st.cache_data means
# the CSVs are read from disk only the first time; later runs reuse the result.
@st.cache_data
def load_tables():
    return dd.load_tables()


tables = load_tables()


# ─────────────────────────────────────────────────────────────────────────────
# 2. HELPERS: write a piece of UI once and call it as many times as needed.
# ─────────────────────────────────────────────────────────────────────────────
def section_header(first_word, accent_word, link_page=None, link_label=None):
    """Two-tone heading ("Team **Standings**") with an optional link on the right.

    Streamlit markdown can color text with  :red[some text]  so no HTML is
    needed. Two columns put the title on the left and the link on the right.
    """
    left, right = st.columns([3, 1], vertical_alignment="bottom")
    left.subheader(f"{first_word} :red[{accent_word}]")
    if link_page:
        # st.page_link jumps to another page in the app. The path must match
        # one registered in app.py.
        right.page_link(link_page, label=link_label, icon=":material/arrow_forward:")


def standings_grid(rows):
    """Draw standings as a 2-wide grid of metric cards.

    st.metric is a built-in "KPI tile": small label, big value, and a colored
    delta arrow (green when up). border=True draws the card outline.
    """
    for i in range(0, len(rows), 2):          # step through the rows two at a time
        cols = st.columns(2)                    # one row = two side-by-side columns
        for col, row in zip(cols, rows[i:i + 2]):
            col.metric(
                label=f"P{row['position']} · {row['name']}",
                value=f"{row['points']} PTS",
                # None hides the arrow when they scored nothing that round
                delta=f"{row['change']} last round" if row["change"] else None,
                border=True,
            )


def race_card(race):
    """st.container(border=True) is a box you can put any elements into.
    Anything written inside `with ...:` lands in the box."""
    with st.container(border=True):
        st.markdown(f"#### {race['name']}")
        st.caption(f"Round {race['round']} · {race['date']}, {race['circuit']}")
        st.markdown(f":material/emoji_events: Winner: **{race['winner']}**")


# ─────────────────────────────────────────────────────────────────────────────
# 3. LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

# Page header: title on the left, season picker on the right.
title_col, season_col = st.columns([4, 1], vertical_alignment="bottom")
with title_col:
    st.title("Dashboard")
with season_col:
    # A selectbox returns the chosen value. When the user picks another season,
    # Streamlit re-runs this file and every section below uses the new `season`.
    # label_visibility="collapsed" hides the label above the box.
    season = st.selectbox("Season", dd.seasons(tables), label_visibility="collapsed")
st.caption(f"{season} Season Overview · standings after round {dd.last_round(tables, season)}")

st.space("medium")  # vertical breathing room

# Main body: a wide left column (2 parts) and a narrow right column (1 part).
main_col, side_col = st.columns([2, 1], gap="large")

with main_col:
    section_header("Team", "Standings", "pages/teams.py", "See full standings")
    teams = dd.team_standings(tables, season)
    if teams:
        standings_grid(teams)
    else:
        st.info("No constructors' championship this season (it started in 1958).")

    st.space("medium")
    section_header("Driver", "Standings", "pages/drivers.py", "See full standings")
    standings_grid(dd.driver_standings(tables, season))

    # Championship Outlook: output of src/models/championship.py, if a run
    # exists for this season.
    outlook = dd.championship_prediction(tables, season)
    if outlook:
        st.space("medium")
        section_header("Championship", "Outlook")
        st.caption(f"Simulated from round {outlook['after_round']} to the end of the season")
        for col, (title, rows) in zip(st.columns(2), [("Drivers", outlook["drivers"]),
                                                      ("Constructors", outlook["teams"])]):
            with col:
                st.markdown(f"**{title}**")
                # st.dataframe turns a list of dicts (or a pandas DataFrame) into a
                # table. column_config controls how each column is displayed:
                # here title_pct becomes a bar instead of a plain number.
                st.dataframe(
                    rows,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "name": "Name",
                        "title_pct": st.column_config.ProgressColumn(
                            "Title chance", format="%.0f%%", min_value=0, max_value=100),
                        "final_points": st.column_config.NumberColumn("Proj. points"),
                    },
                )

with side_col:
    section_header("Race", "Analytics", "pages/predictions.py", "View all races")
    for race in dd.recent_races(tables, season):
        race_card(race)
