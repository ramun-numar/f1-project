# just copied the function from the .ipynb-file

import numpy as np
import plotly.graph_objects as go
import tif1

def telemetry_viz(year, circuit, driver, fps=20):

    # F1 DESIGN (AI-generated)
    BACKGROUND = "#101014"
    GRID = "#303038"
    WHITE = "#FFFFFF"
    MUTED = "#AAAAAA"
    RED = "#E5484D"

    # 1. Load data
    session = tif1.get_session(year, circuit, "Race")
    track = session.get_circuit_info().track

    telemetry = (session.get_driver(driver).get_fastest_lap_tel()[["Time", "X", "Y"]].dropna().sort_values("Time").drop_duplicates("Time"))

    # 2. Prepare time for interpolation
    time = telemetry["Time"].dt.total_seconds().to_numpy()
    time = time - time[0]

    # 3. Interpolate
    time_interp = np.arange(0, time[-1], 1 / fps)
    x_interp = np.interp(time_interp, time, telemetry["X"])
    y_interp = np.interp(time_interp, time, telemetry["Y"])

    # 4. Create figure
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=track["X"], y=track["Y"], mode="lines", name="Circuit", line=dict(color="#666674", width=5), hoverinfo="skip"))

    fig.add_trace(go.Scatter(x=[x_interp[0]], y=[y_interp[0]], mode="markers", name=driver, marker=dict(color=RED, size=13, line=dict(color=WHITE, width=2)), hoverinfo="skip"))

    # F1 styling  (AI-generated)
    fig.update_layout(
        title=dict(
            text=f"<b>F1 / LAP TELEMETRY</b><br><span style='font-size:14px;color:{MUTED}'>{year} {circuit} | {driver} | Fastest Lap</span>",
            font=dict(size=23, color=WHITE),
            x=0.04, y=0.97, xanchor="left", yanchor="top"
        ),
        template="plotly_dark",
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font=dict(family="Arial", color=WHITE, size=13),
        width=750, height=750,
        margin=dict(l=40, r=40, t=110, b=100),
        showlegend=False,
        hovermode=False
    )

    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)

    # 5. Animation
    driver_trace = len(fig.data) - 1

    fig.frames = [go.Frame(data=[go.Scatter(x=[x], y=[y])], traces=[driver_trace]) for x, y in zip(x_interp, y_interp)]

    # 6. Playback controls (AI generated)
    fig.update_layout(updatemenus=[dict(
        type="buttons", direction="left", showactive=False,
        x=0.5, xanchor="center", y=-0.05, yanchor="top",
        bgcolor="#202027", bordercolor=GRID, font=dict(color=WHITE, size=13),
        buttons=[
            dict(label="▶ Play", method="animate", args=[None, {"frame": {"duration": 1000 / fps, "redraw": False}, "transition": {"duration": 0}, "fromcurrent": True}]),
            dict(label="Ⅱ Pause", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "transition": {"duration": 0}, "mode": "immediate"}])
        ]
    )])

    return fig