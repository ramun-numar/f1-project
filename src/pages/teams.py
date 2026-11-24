import streamlit as st
import pandas as pd
import plotly.express as px

from data import dashboard_data as dd
from visualizations.theme import TEAM_COLORS


st.title("Teams")
st.caption("Full constructor standings: coming soon.")


#----------------------------------------------------------------#
### FEEL FREE TO MOVE THIS GRAFIC WHERE YOU THINK IT FITS BEST ###
#----------------------------------------------------------------#


@st.cache_data
def load_team_tables():
    return dd.load_tables()


tables = load_team_tables()
seasons = [int(year) for year in dd.seasons(tables) if year >= 2020]
season_col, race_col = st.columns([1, 3])

with season_col:
    season = st.selectbox(
        "Season",
        seasons,
        key="team_points_season",
    )

calendar = tables["races"].loc[
    tables["races"]["year"].eq(season)
].sort_values("round")

season_standings = tables["team_standings"].loc[
    tables["team_standings"]["year"].eq(season)
]

available_rounds = sorted(
    season_standings["round"].unique(),
    reverse=True,
)

race_names = (
    calendar.set_index("round")["grandPrixId"]
    .map(tables["grands_prix"])
)

with race_col:
    selected_round = st.selectbox(
        "After race",
        available_rounds,
        format_func=lambda value: f"R{value:02d} · {race_names.loc[value]}",
        key=f"team_points_round_{season}",
    )

# use only standings and participants known at the selected round
history = season_standings.loc[
    season_standings["round"].le(selected_round)
]

team_ids = tables["results"].loc[
    tables["results"]["year"].eq(season)
    & tables["results"]["round"].le(selected_round),
    "constructorId",
].unique()

season_colors = TEAM_COLORS.get(int(season), {})

team_colors = {
    tables["teams"].get(team_id, team_id): season_colors.get(
        team_id, "#999999"
    )
    for team_id in team_ids
}

# create one column per team and carry existing points forward
points = (
    history.pivot(index="round", columns="constructorId", values="points")
    .reindex(columns=team_ids)
    .sort_index()
    .ffill()
    .fillna(0)
    .rename(columns=tables["teams"].to_dict())
)

# start every team's line at zero points before the first race
points.loc[0] = 0
points = points.sort_index()

season_end = int(calendar["round"].max())

title_col, forecast_col = st.columns([4, 1])
title_col.subheader("Team Points Evolution")

show_forecast = forecast_col.toggle(
    "Forecast",
    value=False,
    disabled=selected_round >= season_end,
    key=f"team_points_forecast_{season}_{selected_round}",
)

fig = px.line(
    points,
    markers=True,
    color_discrete_map=team_colors,
    labels={
        "round": "Round",
        "value": "Championship points",
        "constructorId": "Team",
    },
)

if show_forecast:
    # read the saved expected season-end points for the selected starting point
    timeline = pd.DataFrame(dd.constructor_timeline(tables, season))

    if not timeline.empty:
        current = timeline.loc[timeline["round"].eq(selected_round)]
    else:
        current = pd.DataFrame()

    if current.empty:
        st.info("No forecast saved for this starting point.")
    else:
        for _, team in current.iterrows():
            name = team["name"]

            fig.add_scatter(
                x=[selected_round, season_end],
                y=[
                    points.loc[selected_round, name],
                    team["average_final_points"],
                ],
                mode="lines+markers",
                name=f"{name} forecast",
                legendgroup=name,
                showlegend=False,
                line=dict(color=team_colors[name], dash="dash"),
            )

        st.caption(
            "Dashed lines connect current points to predicted season-end totals. "
            "Intermediate rounds are not individually forecast."
        )

fig.update_xaxes(
    dtick=1,
    range=[0, season_end if show_forecast else selected_round],
)
fig.update_yaxes(rangemode="tozero")
fig.update_layout(legend=dict(groupclick="togglegroup"))

st.plotly_chart(
    fig,
    width="stretch",
    config={"displayModeBar": False},
)