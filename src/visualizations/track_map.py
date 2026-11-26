"""
Track outline maps, drawn from tif1 circuit data.

For an upcoming race there is no session data yet, so the map uses the most
recent past race held at the same circuit (layouts rarely change).
"""
import numpy as np
import plotly.graph_objects as go
import tif1

TIF1_FIRST_YEAR = 2018  # tif1 has no sessions before this


def tif1_event_name(year, rnd):
    """tif1 identifies races by EventName ("Qatar Grand Prix"); f1db by round."""
    events = tif1.get_events(year)
    match = events.loc[events["RoundNumber"].eq(rnd), "EventName"]
    return match.iloc[0] if len(match) else None


def latest_session_at(tables, circuit_id, before_race_id=None):
    """(year, event name) of the most recent finished race at this circuit."""
    races = tables["races"]
    past = races.loc[
        races["circuitId"].eq(circuit_id)
        & races["id"].isin(tables["results"]["raceId"])
        & races["year"].ge(TIF1_FIRST_YEAR)
    ]
    if before_race_id is not None:
        past = past.loc[past["id"].le(before_race_id)]
    if past.empty:
        return None
    race = past.sort_values("start").iloc[-1]
    name = tif1_event_name(int(race["year"]), int(race["round"]))
    return (int(race["year"]), name) if name else None


def _rotate(x, y, degrees):
    """Rotate points so the map has the familiar orientation (as on TV graphics)."""
    a = np.deg2rad(degrees)
    return x * np.cos(a) - y * np.sin(a), x * np.sin(a) + y * np.cos(a)


def track_map_fig(year, event_name, height=260, show_corners=True, color="#E10600"):
    info = tif1.get_session(year, event_name, "Race").get_circuit_info()
    x, y = _rotate(info.track["X"].to_numpy(), info.track["Y"].to_numpy(), info.rotation)
    fig = go.Figure(go.Scatter(x=np.append(x, x[0]), y=np.append(y, y[0]), mode="lines",
                               line=dict(color=color, width=5), hoverinfo="skip"))
    corners = info.corners
    if show_corners and corners is not None and len(corners):
        cx, cy = _rotate(corners["X"].to_numpy(), corners["Y"].to_numpy(), info.rotation)
        fig.add_trace(go.Scatter(x=cx, y=cy, mode="text", text=corners["Number"].astype(str),
                                 textfont=dict(color="#AAAAAA", size=10), hoverinfo="skip"))
    fig.update_layout(
        height=height, showlegend=False, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False, scaleanchor="x"),  # equal aspect ratio
    )
    return fig
