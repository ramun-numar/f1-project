"""
Championship charts, shared by several pages.

The chart logic below was written by the team in pages/drivers.py,
pages/teams.py and pages/predictions.py. It is moved here unchanged, only
wrapped in functions, so the same chart can appear on more than one page
(e.g. points evolution on the Standings pages *and* in the Archive).

Each `render_*` function draws straight onto the page (it calls st.*), so a
page just calls it inside whatever column/container it wants the chart in.
"""
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import gaussian_kde

from data import dashboard_data as dd
from visualizations.theme import TEAM_COLORS


# ─────────────────────────────────────────────────────────────────────────────
# Points evolution (from pages/drivers.py and pages/teams.py)
# ─────────────────────────────────────────────────────────────────────────────
def render_points_evolution(tables, season, selected_round, kind="driver", title=None, key="", forecast=None):
    """Line chart of championship points per round, with a Forecast toggle.

    kind="driver" or "team". Pass forecast=True/False to control it from a
    page-level toggle instead (the chart then draws no toggle of its own).
    """
    calendar = tables["races"].loc[tables["races"]["year"].eq(season)].sort_values("round")
    season_colors = TEAM_COLORS.get(int(season), {})
    results = tables["results"].loc[
        tables["results"]["year"].eq(season)
        & tables["results"]["round"].le(selected_round)
    ]

    if kind == "driver":
        standings = tables["driver_standings"]
        id_col, names = "driverId", tables["drivers"]
        # identify each driver's latest team for the line color
        driver_teams = (
            results.sort_values("round")
            .drop_duplicates("driverId", keep="last")
            .set_index("driverId")["constructorId"]
        )
        ids = driver_teams.index
        colors = {
            names.get(driver_id, driver_id): season_colors.get(team, "#999999")
            for driver_id, team in driver_teams.items()
        }
        timeline_fn = dd.championship_timeline
        label = "Driver"
    else:
        standings = tables["team_standings"]
        id_col, names = "constructorId", tables["teams"]
        ids = results["constructorId"].unique()
        colors = {
            names.get(team_id, team_id): season_colors.get(team_id, "#999999")
            for team_id in ids
        }
        timeline_fn = dd.constructor_timeline
        label = "Team"

    # use only standings available at the selected round
    history = standings.loc[standings["year"].eq(season) & standings["round"].le(selected_round)]

    # create one column per driver/team and carry existing points forward
    points = (
        history.pivot(index="round", columns=id_col, values="points")
        .reindex(columns=ids)
        .sort_index()
        .ffill()
        .fillna(0)
        .rename(columns=names.to_dict())
    )

    # start every line at zero points before the first race
    points.loc[0] = 0
    points = points.sort_index()

    season_end = int(calendar["round"].max())

    title_col, forecast_col = st.columns([4, 1])
    title_col.subheader(title or f"{label} Points Evolution")

    if forecast is None:
        show_forecast = forecast_col.toggle(
            "Forecast",
            value=False,
            disabled=selected_round >= season_end,
            key=f"{key}{kind}_points_forecast_{season}_{selected_round}",
        )
    else:
        show_forecast = forecast and selected_round < season_end

    fig = px.line(
        points,
        markers=True,
        color_discrete_map=colors,
        labels={"round": "Round", "value": "Championship points", id_col: label},
    )

    if show_forecast:
        # read the saved expected season-end points for the selected starting point
        timeline = pd.DataFrame(timeline_fn(tables, season))
        current = timeline.loc[timeline["round"].eq(selected_round)] if not timeline.empty else pd.DataFrame()

        if current.empty:
            st.info("No forecast saved for this starting point.")
        else:
            for _, row in current.iterrows():
                name = row["name"]
                if name not in points.columns:
                    continue
                fig.add_scatter(
                    x=[selected_round, season_end],
                    y=[points.loc[selected_round, name], row["average_final_points"]],
                    mode="lines+markers",
                    name=f"{name} forecast",
                    legendgroup=name,
                    showlegend=False,
                    line=dict(color=colors.get(name, "#999999"), dash="dash"),
                )
            st.caption(
                "Dashed lines connect current points to predicted season-end totals. "
                "Intermediate rounds are not individually forecast."
            )

    fig.update_xaxes(dtick=1, range=[0, season_end if show_forecast else selected_round])
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(legend=dict(groupclick="togglegroup"))

    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


# ─────────────────────────────────────────────────────────────────────────────
# Title probability + simulations (from pages/predictions.py)
# ─────────────────────────────────────────────────────────────────────────────
def _driver_context(tables, season, selected_round):
    """Shared setup: ranking, colors and line styles at the selected round."""
    timeline = pd.DataFrame(dd.championship_timeline(tables, season))
    if timeline.empty:
        return timeline, pd.DataFrame(), {}, {}

    # rank all drivers at the selected round before applying the display filter
    current = timeline.loc[timeline["round"].eq(selected_round)].sort_values(
        ["title_probability_pct", "average_final_points", "driverId"],
        ascending=[False, False, True],
    )
    # select one leading driver per team at this starting point
    team_leaders = set(current.drop_duplicates("constructorId")["driverId"])
    season_colors = TEAM_COLORS.get(int(season), {})
    driver_colors = {d["name"]: season_colors.get(d["constructorId"], "#999999") for _, d in current.iterrows()}
    driver_dashes = {d["name"]: ("solid" if d["driverId"] in team_leaders else "dash") for _, d in current.iterrows()}
    return timeline, current, driver_colors, driver_dashes


def render_driver_title_probability(tables, season, selected_round):
    timeline, current, driver_colors, driver_dashes = _driver_context(tables, season, selected_round)
    if timeline.empty:
        st.info("No championship predictions saved for this season.")
        return

    # automatically show the top five at the selected starting point
    selected_drivers = current.head(5)["name"].tolist()
    if not selected_drivers:
        st.info("No forecast saved for this starting point.")
        return

    # display only forecasts up to the selected starting point
    selected = timeline.loc[
        timeline["round"].le(selected_round) & timeline["name"].isin(selected_drivers)
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
        labels={"round": "After round", "title_probability_pct": "Title probability", "name": "Driver"},
    )
    fig.update_yaxes(range=[0, 100], ticksuffix="%")
    fig.update_xaxes(dtick=1, range=[selected["round"].min(), max(selected_round, selected["round"].min() + 1)])
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


def render_simulated_points(tables, season, selected_round):
    """Distribution of simulated final points for the top 5 drivers."""
    timeline, current, driver_colors, driver_dashes = _driver_context(tables, season, selected_round)

    # determine the final round of the selected season
    final_round = int(tables["races"].loc[tables["races"]["year"].eq(season), "round"].max())
    if timeline.empty or current.empty:
        st.info("No championship forecast saved for this starting point.")
        return
    if selected_round >= final_round:
        st.info("Season complete: nothing left to simulate.")
        return

    simulations = dd.championship_simulations(season, selected_round)
    if simulations is None:
        st.info("Simulation results have not been saved for this round yet.")
        return

    # select the top five by expected final points at the selected round
    top_five = current.sort_values(["average_final_points", "driverId"], ascending=[False, True]).head(5)

    # count the remaining races at the selected starting point
    remaining_count = len(tables["races"].loc[
        tables["races"]["year"].eq(season) & tables["races"]["round"].gt(selected_round)
    ])

    # use exact frequencies when at most three races remain
    show_bars = remaining_count <= 3

    fig_points = go.Figure()

    for _, driver in top_five.iterrows():
        name = driver["name"]
        points = simulations[driver["driverId"]].dropna().to_numpy()

        # show exact simulated frequencies when few races remain
        if show_bars and np.unique(points).size > 1:
            frequencies = pd.Series(points).value_counts(normalize=True).sort_index()
            fig_points.add_trace(go.Bar(
                x=frequencies.index,
                y=frequencies.values,
                name=name,
                width=0.8,
                opacity=0.8,
                marker_color=driver_colors[name],
                marker_pattern_shape=("/" if driver_dashes[name] == "dash" else ""),
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
                marker=dict(color=driver_colors[name], size=12, symbol="diamond"),
                hovertemplate="%{x:.0f} points in every simulation<extra>%{fullData.name}</extra>",
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
            line=dict(color=driver_colors[name], dash=driver_dashes[name], width=3),
            hovertemplate="Final points: %{x:.0f}<br>Density: %{y:.4f}<extra>%{fullData.name}</extra>",
        ))

    fig_points.update_layout(
        template="plotly_dark",
        xaxis_title="Final championship points",
        yaxis_title="Share of simulations" if show_bars else "Density",
        barmode="overlay",
        legend_title_text="Driver",
    )
    fig_points.update_yaxes(rangemode="tozero", tickformat=".0%" if show_bars else ".3f")

    # fit the horizontal axis to the displayed drivers' simulated points
    displayed_points = simulations[top_five["driverId"]]
    padding = 0.5 if show_bars else 0  # leave room for the full bar width
    fig_points.update_xaxes(range=[displayed_points.min().min() - padding, displayed_points.max().max() + padding])

    st.plotly_chart(fig_points, width="stretch")

    st.caption(
        f"Based on {len(simulations):,} season simulations "
        f"starting after round {selected_round}. Remaining races: {remaining_count}."
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
        tables["results"]["year"].eq(season) & tables["results"]["round"].eq(selected_round), "driverId"
    ])
    inactive_names = top_five.loc[~top_five["driverId"].isin(active_ids), "name"].tolist()
    if remaining_count > 0 and inactive_names:
        st.caption(
            "Lineup assumption: " + ", ".join(inactive_names)
            + " did not appear in the latest race results. "
            "The model keeps that lineup unchanged, so their points stay fixed."
        )


def render_constructor_title_probability(tables, season, selected_round):
    constructor_history = pd.DataFrame(dd.constructor_timeline(tables, season))
    if constructor_history.empty:
        st.info("No constructor predictions saved for this season.")
        return

    season_colors = TEAM_COLORS.get(int(season), {})

    # rank teams using the selected forecast starting point
    constructor_current = constructor_history.loc[constructor_history["round"].eq(selected_round)].sort_values(
        ["title_probability_pct", "average_final_points", "constructorId"],
        ascending=[False, False, True],
    )
    selected_teams = constructor_current.head(5)["constructorId"]
    constructor_colors = {
        team["name"]: season_colors.get(team["constructorId"], "#999999")
        for _, team in constructor_current.iterrows()
    }

    # show only forecasts available up to the selected round
    selected_history = constructor_history.loc[
        constructor_history["round"].le(selected_round)
        & constructor_history["constructorId"].isin(selected_teams)
    ]
    if selected_history.empty:
        st.info("No constructor forecast saved for this starting point.")
        return

    fig_constructors = px.line(
        selected_history,
        x="round",
        y="title_probability_pct",
        color="name",
        color_discrete_map=constructor_colors,
        markers=True,
        labels={"round": "After round", "title_probability_pct": "Title probability", "name": "Constructor"},
    )
    fig_constructors.update_yaxes(range=[0, 100], ticksuffix="%")
    fig_constructors.update_xaxes(
        dtick=1,
        range=[selected_history["round"].min(), max(selected_round, selected_history["round"].min() + 1)],
    )
    st.plotly_chart(fig_constructors, width="stretch")
    st.caption(
        "Historical forecasts reconstructed with our current model. "
        "Each dot represents a saved forecast after a race."
    )


def render_constructor_final_points(tables, season, selected_round):
    """'Simulated Final Points: All' for constructors.

    Only driver-level simulation runs are saved, so this shows each team's
    *average* simulated final points (constructor_predictions.csv) as bars.
    """
    history = pd.DataFrame(dd.constructor_timeline(tables, season))
    current = history.loc[history["round"].eq(selected_round)] if not history.empty else history
    if current.empty:
        st.info("No constructor forecast saved for this starting point.")
        return

    season_colors = TEAM_COLORS.get(int(season), {})
    current = current.sort_values("average_final_points")
    fig = go.Figure(go.Bar(
        x=current["average_final_points"],
        y=current["name"],
        orientation="h",
        marker_color=[season_colors.get(t, "#999999") for t in current["constructorId"]],
        text=current["average_final_points"].round().astype(int),
        textposition="outside",
        hovertemplate="%{y}: %{x:.0f} projected points<extra></extra>",
    ))
    fig.update_layout(template="plotly_dark", xaxis_title="Average simulated final points",
                      height=max(300, 32 * len(current)), margin=dict(l=0, r=40, t=10, b=0))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.caption(f"Average over all season simulations starting after round {selected_round}.")
