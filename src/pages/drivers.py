import streamlit as st
import pandas as pd
import plotly.express as px

from data import dashboard_data as dd
from visualizations.theme import TEAM_COLORS

st.title("Drivers")
st.caption("Full driver standings: coming soon.")

#----------------------------------------------------------------#
### FEEL FREE TO MOVE THIS GRAFIC WHERE YOU THINK IT FITS BEST ###
#----------------------------------------------------------------#


@st.cache_data
def load_driver_tables():
    return dd.load_tables()


tables = load_driver_tables()
seasons = [int(year) for year in dd.seasons(tables) if year >= 2020]
season_col, race_col = st.columns([1, 3])

with season_col:
    season = st.selectbox(
        "Season",
        seasons,
        key="driver_points_season",
    )

calendar = tables["races"].loc[
    tables["races"]["year"].eq(season)
].sort_values("round")

season_standings = tables["driver_standings"].loc[
    tables["driver_standings"]["year"].eq(season)
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
        key=f"driver_points_round_{season}",
    )

# use only results and standings available at the selected round
history = season_standings.loc[
    season_standings["round"].le(selected_round)
]

results = tables["results"].loc[
    tables["results"]["year"].eq(season)
    & tables["results"]["round"].le(selected_round)
]

driver_teams = (
    results.sort_values("round")
    .drop_duplicates("driverId", keep="last")
    .set_index("driverId")["constructorId"]
)

season_colors = TEAM_COLORS.get(int(season), {})

driver_colors = {
    tables["drivers"].get(driver_id, driver_id): season_colors.get(
        team, "#999999"
    )
    for driver_id, team in driver_teams.items()
}

# create one column per driver and carry existing points forward
points = (
    history.pivot(index="round", columns="driverId", values="points")
    .reindex(columns=driver_teams.index)
    .sort_index()
    .ffill()
    .fillna(0)
    .rename(columns=tables["drivers"].to_dict())
)

# start every driver's line at zero points before the first race
points.loc[0] = 0
points = points.sort_index()

season_end = int(calendar["round"].max())

title_col, forecast_col = st.columns([4, 1])
title_col.subheader("Driver Points Evolution")

show_forecast = forecast_col.toggle(
    "Forecast",
    value=False,
    disabled=selected_round >= season_end,
    key=f"driver_points_forecast_{season}_{selected_round}",
)

fig = px.line(
    points,
    markers=True,
    color_discrete_map=driver_colors,
    labels={
        "round": "Round",
        "value": "Championship points",
        "driverId": "Driver",
    },
)

if show_forecast:
    # read the saved expected season-end points for the selected starting point
    timeline = pd.DataFrame(dd.championship_timeline(tables, season))

    if not timeline.empty:
        current = timeline.loc[timeline["round"].eq(selected_round)]
    else:
        current = pd.DataFrame()

    if current.empty:
        st.info("No forecast saved for this starting point.")
    else:
        for _, driver in current.iterrows():
            name = driver["name"]

            fig.add_scatter(
                x=[selected_round, season_end],
                y=[
                    points.loc[selected_round, name],
                    driver["average_final_points"],
                ],
                mode="lines+markers",
                name=f"{name} forecast",
                legendgroup=name,
                showlegend=False,
                line=dict(color=driver_colors[name], dash="dash"),
            )

        st.caption(
            "Dashed lines connect current points to predicted season-end totals. "
            "Intermediate rounds are not individually forecast."
        )

fig.update_xaxes(dtick=1, range=[0, season_end if show_forecast else selected_round])
fig.update_yaxes(rangemode="tozero")
fig.update_layout(legend=dict(groupclick="togglegroup"))

st.plotly_chart(
    fig,
    width="stretch",
    config={"displayModeBar": False},
)