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
from visualizations.theme import TEAM_COLORS
import numpy as np
import plotly.graph_objects as go
from scipy.stats import gaussian_kde
import pandas as pd
import plotly.express as px
import streamlit as st
from data import dashboard_data as dd

runpy.run_path(str(Path(__file__).resolve().parent.parent / "app.py"))


st.header("Championship title probability")

# cache the general tables while reading saved predictions on each rerun
@st.cache_data
def load_prediction_tables():
    return dd.load_tables()

tables = load_prediction_tables()

# offer only seasons with saved championship predictions
forecast_seasons = sorted(
    {
        path.parent.parent.name
        for path in dd.CHAMPIONSHIP_DIR.glob(
            "*/after_*/driver_predictions.csv"
        )
    },
    key=int,
    reverse=True
)

# default to the current season when forecasts are available
current_year = str(pd.Timestamp.now(tz="Europe/Zurich").year)
default_index = (
    forecast_seasons.index(current_year)
    if current_year in forecast_seasons
    else 0
)

filters = st.container(border=True)
season_col, race_col = filters.columns([1, 3])

with season_col:
    season = int(st.selectbox(
        "Season",
        forecast_seasons,
        index=default_index,
        key="championship_season_picker",
    ))

timeline = pd.DataFrame(dd.championship_timeline(tables, season))

if timeline.empty:
    st.info("No championship predictions saved for this season.")
else:
    # put the latest saved starting point first
    available_rounds = sorted(timeline["round"].unique(), reverse=True)
    race_labels = {}

    for _, race in tables["races"].loc[
        tables["races"]["year"].eq(season)
    ].iterrows():
        round_number = int(race["round"])
        race_name = tables["grands_prix"].get(
            race["grandPrixId"], race["officialName"]
        )
        race_labels[round_number] = f"R{round_number:02d} · {race_name}"

    with race_col:
        selected_round = st.selectbox(
            "Forecast after",
            options=available_rounds,
            index=0,
            format_func=lambda value: race_labels[value],
            key=f"championship_race_picker_{season}",
        )

    # rank all drivers at the selected round before applying the display filter
    current = timeline.loc[timeline["round"].eq(selected_round)].sort_values(
        ["title_probability_pct", "average_final_points", "driverId"],
        ascending=[False, False, True]
    )

    # select one leading driver per team at this starting point
    team_leaders = set(current.drop_duplicates("constructorId")["driverId"])

    # use the team colors from the selected season
    season_colors = TEAM_COLORS.get(int(season), {})

    driver_colors = {driver["name"]: season_colors.get(driver["constructorId"], "#999999")
        for _, driver in current.iterrows()
    }

    driver_dashes = {driver["name"]: ("solid" if driver["driverId"] in team_leaders else "dash")
        for _, driver in current.iterrows()
    }

    # automatically show the top five at the selected starting point
    selected_drivers = current.head(5)["name"].tolist()

    if not selected_drivers:
        st.info("Select at least one driver.")
    else:
        # display only forecasts up to the selected starting point
        selected = timeline.loc[
            timeline["round"].le(selected_round)
            & timeline["name"].isin(selected_drivers)
        ].sort_values(["round", "driverId"])

        fig = px.line(
            selected,
            x="round",
            y="title_probability_pct",
            color="name",
            color_discrete_map=driver_colors,
            line_dash="name",
            line_dash_map=driver_dashes,
            markers=True,
            labels={
                "round": "After round",
                "title_probability_pct": "Title probability",
                "name": "Driver"
            }
        )

        fig.update_yaxes(range=[0, 100], ticksuffix="%")
        fig.update_xaxes(
            dtick=1,
            range=[selected["round"].min(), max(selected_round, selected["round"].min() + 1)],
        )

        st.plotly_chart(fig, width="stretch")

        st.caption(
            f"Line styles reflect title probabilities after round {selected_round}. "
            "The leading driver per team has a solid line; teammates have dashed lines. "
            "Equal probabilities are ordered by expected final points, then driver ID."
        )

        st.caption(
            "Historical forecasts reconstructed with our current model. "
            "Each dot represents a saved forecast after a race."
        )

    # determine the final round of the selected season
    final_round = int(
        tables["races"].loc[
            tables["races"]["year"].eq(season), "round"
        ].max()
    )

    simulations = None

    # load and display forecasts only while races remain
    if selected_round < final_round:
        st.subheader("Simulated final points — Top 5")
        simulations = dd.championship_simulations(season, selected_round)

        if simulations is None:
            st.info("Simulation results have not been saved for this round yet.")

    if simulations is not None:
        # select the top five by expected final points at the selected round
        top_five = current.sort_values(
            ["average_final_points", "driverId"],
            ascending=[False, True],
        ).head(5)

        # count the remaining races at the selected starting point
        remaining_count = len(tables["races"].loc[
            tables["races"]["year"].eq(season)
            & tables["races"]["round"].gt(selected_round)
        ])

        # use exact frequencies when at most three races remain
        show_bars = remaining_count <= 3

        fig_points = go.Figure()

        for _, driver in top_five.iterrows():
            name = driver["name"]
            points = simulations[driver["driverId"]].dropna().to_numpy()

            # show exact simulated frequencies when few races remain
            if show_bars and np.unique(points).size > 1:
                frequencies = pd.Series(points).value_counts(
                    normalize=True
                ).sort_index()

                fig_points.add_trace(go.Bar(
                    x=frequencies.index,
                    y=frequencies.values,
                    name=name,
                    width=0.8,
                    opacity=0.8,
                    marker_color=driver_colors[name],
                    marker_pattern_shape=(
                        "/" if driver_dashes[name] == "dash" else ""
                    ),
                    hovertemplate=(
                        "Final points: %{x:.0f}<br>"
                        "Share of simulations: %{y:.1%}"
                        "<extra>%{fullData.name}</extra>"
                    ),
                ))
                continue

            # show a fixed outcome as a dot when every simulation agrees
            if np.unique(points).size == 1:
                fig_points.add_trace(go.Scatter(
                    x=[points[0]],
                    y=[0],
                    mode="markers",
                    name=name,
                    marker=dict(
                        color=driver_colors[name],
                        size=12,
                        symbol="diamond",
                    ),
                    hovertemplate=(
                        "%{x:.0f} points in every simulation"
                        "<extra>%{fullData.name}</extra>"
                    ),
                ))
                continue

            # estimate a smooth density from the simulated final points
            point_range = np.linspace(points.min(), points.max(), 300)
            density = gaussian_kde(points)

            fig_points.add_trace(go.Scatter(
                x=point_range,
                y=density(point_range),
                mode="lines",
                name=name,
                line=dict(
                    color=driver_colors[name],
                    dash=driver_dashes[name],
                    width=3,
                ),
                hovertemplate=(
                    "Final points: %{x:.0f}<br>"
                    "Density: %{y:.4f}"
                    "<extra>%{fullData.name}</extra>"
                ),
            ))

        fig_points.update_layout(
            template="plotly_dark",
            xaxis_title="Final championship points",
            yaxis_title="Share of simulations" if show_bars else "Density",
            barmode="overlay",
            legend_title_text="Driver",
        )

        fig_points.update_yaxes(
            rangemode="tozero",
            tickformat=".0%" if show_bars else ".3f",
        )

        # fit the horizontal axis to the displayed drivers' simulated points
        displayed_points = simulations[top_five["driverId"]]
        left_edge = displayed_points.min().min()
        right_edge = displayed_points.max().max()

        # leave room for the full bar width
        padding = 0.5 if show_bars else 0

        fig_points.update_xaxes(
            range=[left_edge - padding, right_edge + padding]
        )

        st.plotly_chart(fig_points, width="stretch")
        
        st.caption(
            f"Based on {len(simulations):,} season simulations "
            f"starting after round {selected_round}. "
            f"Remaining races: {remaining_count}."
        )

        if show_bars:
            st.caption(
                "Bars show the share of simulations ending at each point total. "
                "Striped bars identify the dashed-line drivers from the timeline. "
                "Fixed outcomes are shown as diamonds."
            )
        else:
            st.caption(
                "Curves show smoothed distributions of simulated final points. "
                "Fixed outcomes are shown as diamonds."
            )

        # identify drivers excluded by the unchanged-lineup assumption
        active_ids = set(tables["results"].loc[
            tables["results"]["year"].eq(season)
            & tables["results"]["round"].eq(selected_round),
            "driverId",
        ])

        inactive_names = top_five.loc[
            ~top_five["driverId"].isin(active_ids), "name"
        ].tolist()

        if remaining_count > 0 and inactive_names:
            st.caption(
                "Lineup assumption: " + ", ".join(inactive_names)
                + " did not appear in the latest race results. "
                "The model keeps that lineup unchanged, so their points stay fixed."
            )

    st.subheader("Constructors' title probability")

    constructor_history = pd.DataFrame(
        dd.constructor_timeline(tables, season)
    )

    if constructor_history.empty:
        st.info("No constructor predictions saved for this season.")
    else:
        # rank teams using the selected forecast starting point
        constructor_current = constructor_history.loc[
            constructor_history["round"].eq(selected_round)
        ].sort_values(
            ["title_probability_pct", "average_final_points", "constructorId"],
            ascending=[False, False, True],
        )

        selected_teams = constructor_current.head(5)["constructorId"]

        constructor_colors = {
            team["name"]: season_colors.get(
                team["constructorId"], "#999999"
            )
            for _, team in constructor_current.iterrows()
        }

        # show only forecasts available up to the selected round
        selected_history = constructor_history.loc[
            constructor_history["round"].le(selected_round)
            & constructor_history["constructorId"].isin(selected_teams)
        ]

        fig_constructors = px.line(
            selected_history,
            x="round",
            y="title_probability_pct",
            color="name",
            color_discrete_map=constructor_colors,
            markers=True,
            labels={
                "round": "After round",
                "title_probability_pct": "Title probability",
                "name": "Constructor",
            },
        )

        fig_constructors.update_yaxes(range=[0, 100], ticksuffix="%")
        fig_constructors.update_xaxes(
            dtick=1,
            range=[
                selected_history["round"].min(),
                max(selected_round, selected_history["round"].min() + 1),
            ]
        )

        st.plotly_chart(fig_constructors, width="stretch")

        st.caption(
            "Historical forecasts reconstructed with our current model. "
            "Each dot represents a saved forecast after a race."
        )