# Telemetry visualization functions copied from the notebook

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import tif1

def telemetry_viz_2drivers_messages(year, circuit, driver1, driver2, fps=20):

    # F1 DESIGN (AI-generated)
    BACKGROUND = "#101014"
    GRID = "#303038"
    WHITE = "#FFFFFF"
    MUTED = "#AAAAAA"
    RED = "#E5484D"
    BLUE = "#36A3FF"

    # 1. Load data
    session = tif1.get_session(year, circuit, "Race")
    track = session.get_circuit_info().track
    corners = session.get_circuit_info().corners

    # 2. Calculate lap distance and section boundaries
    distance = session.get_driver(driver1).get_fastest_lap_tel()[["Distance", "RelativeDistance"]].dropna()

    lap_distance = np.median(distance["Distance"] / distance["RelativeDistance"])

    corner_distances = corners.sort_values("Distance")["Distance"].to_numpy()
    section_bounds = np.concatenate(([0], corner_distances, [lap_distance]))

    # 3. Create sections DataFrame
    n_sections = len(section_bounds) - 1
    section_names = (["Start → T1"] + [f"T{i} → T{i+1}" for i in range(1, n_sections - 1)] + [f"T{n_sections - 1} → Finish"])

    sections = pd.DataFrame({"Section": section_names, "StartDistance": section_bounds[:-1], "EndDistance": section_bounds[1:]})

    # 4. Load driver telemetry
    telemetry1 = (session.get_driver(driver1).get_fastest_lap_tel()[["Time", "X", "Y", "Distance", "RelativeDistance", "Speed"]].dropna().sort_values("Distance")).drop_duplicates("Distance")
    telemetry2 = (session.get_driver(driver2).get_fastest_lap_tel()[["Time", "X", "Y", "Distance", "RelativeDistance", "Speed"]].dropna().sort_values("Distance")).drop_duplicates("Distance")

    telemetry1["TimeSeconds"] = telemetry1["Time"].dt.total_seconds()
    telemetry2["TimeSeconds"] = telemetry2["Time"].dt.total_seconds()

    telemetry1["TimeSeconds"] -= telemetry1["TimeSeconds"].min()
    telemetry2["TimeSeconds"] -= telemetry2["TimeSeconds"].min()

    # 5. Match corners spatially
    def corner_times(telemetry, corners, lap_distance):
        times = []

        for _, corner in corners.sort_values("Distance").iterrows():

            # Expected relative distance
            expected = corner["Distance"] / lap_distance

            # Only consider telemetry within +- 1%
            nearby = telemetry[(telemetry["RelativeDistance"] > expected - 0.01) & (telemetry["RelativeDistance"] < expected + 0.01)]

            distances = ((nearby["X"] - corner["X"])**2 + (nearby["Y"] - corner["Y"])**2)

            closest = distances.idxmin()
            times.append(nearby.loc[closest, "TimeSeconds"])

        return np.array(times)

    time1_corners = corner_times(telemetry1, corners, lap_distance)
    time2_corners = corner_times(telemetry2, corners, lap_distance)

    # 6. Calculate section times
    time1 = np.concatenate(([0], time1_corners, [telemetry1["TimeSeconds"].max()]))
    time2 = np.concatenate(([0], time2_corners, [telemetry2["TimeSeconds"].max()]))

    sections["Time1"] = np.diff(time1)
    sections["Time2"] = np.diff(time2)
    sections["Delta"] = sections["Time1"] - sections["Time2"]
    sections["Winner"] = np.where(sections["Delta"] > 0, driver2, driver1)

    # 7. Create section messages
    sections["Message"] = (sections["Winner"] + " gained " + sections["Delta"].abs().round(3).astype(str) + "s in " + sections["Section"])

    message_times = np.maximum(time1[1:], time2[1:])

    # 8. Prepare animation telemetry
    drivers = [driver1, driver2]
    colors = [RED, BLUE]
    telemetry_data = {}

    for driver in drivers:
        telemetry = (session.get_driver(driver).get_fastest_lap_tel()[["Time", "X", "Y"]].dropna().sort_values("Time").drop_duplicates("Time"))

        time = telemetry["Time"].dt.total_seconds().to_numpy()
        time = time - time[0]

        telemetry_data[driver] = {"time": time, "X": telemetry["X"].to_numpy(), "Y": telemetry["Y"].to_numpy()}

    # 9. Interpolate both drivers onto common time grid
    max_time = max(telemetry_data[d]["time"][-1] for d in drivers)
    time_interp = np.arange(0, max_time + 1 / fps, 1 / fps)

    for driver in drivers:
        data = telemetry_data[driver]
        data["x"] = np.interp(time_interp, data["time"], data["X"])
        data["y"] = np.interp(time_interp, data["time"], data["Y"])

    # 10. Match messages to animation frames
    messages = []

    for t in time_interp:
        completed = np.searchsorted(message_times, t, side="right")

        if completed > 0:
            message = sections["Message"].iloc[completed - 1]
        else:
            message = ""

        messages.append(message)

    # 11. Section endpoint coordinates
    section_x = np.concatenate((corners.sort_values("Distance")["X"].to_numpy(), [track["X"].iloc[0]]))
    section_y = np.concatenate((corners.sort_values("Distance")["Y"].to_numpy(), [track["Y"].iloc[0]]))

    # 12. Create figure
    fig = go.Figure()

    fig.add_trace(go.Scatter(x=track["X"], y=track["Y"], mode="lines", name="Circuit", line=dict(color="#666674", width=5), hoverinfo="skip"))

    for driver, color in zip(drivers, colors):
        fig.add_trace(go.Scatter(x=[telemetry_data[driver]["x"][0]], y=[telemetry_data[driver]["y"][0]], mode="markers", name=driver, marker=dict(color=color, size=13, line=dict(color=WHITE, width=2)), hoverinfo="skip"))

    # F1 styling (AI-generated)
    fig.update_layout(
        title=dict(
            text=f"<b>F1 / LAP TELEMETRY</b><br><span style='font-size:14px;color:{MUTED}'>{year} {circuit} | <span style='color:{RED}'>{driver1}</span> vs <span style='color:{BLUE}'>{driver2}</span> | Fastest Lap</span>",
            font=dict(size=23, color=WHITE),
            x=0.04, y=0.97, xanchor="left", yanchor="top"
        ),
        template="plotly_dark",
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font=dict(family="Arial", color=WHITE, size=13),
        width=750, height=580,
        margin=dict(l=20, r=20, t=90, b=65),
        showlegend=False,
        hovermode=False
    )

    # Leave some room for the message boxes
    padding = 0.25

    x_pad = (track["X"].max() - track["X"].min()) * padding
    y_pad = (track["Y"].max() - track["Y"].min()) * padding

    fig.update_xaxes(visible=False, range=[track["X"].min() - x_pad, track["X"].max() + x_pad])
    fig.update_yaxes(visible=False, range=[track["Y"].min() - y_pad, track["Y"].max() + y_pad], scaleanchor="x", scaleratio=1)

    # 13. Animation
    frames = []

    for i in range(len(time_interp)):
        positions = []

        for driver in drivers:
            scatter = go.Scatter(x=[telemetry_data[driver]["x"][i]], y=[telemetry_data[driver]["y"][i]])
            positions.append(scatter)

        completed = np.searchsorted(message_times, time_interp[i], side="right")
        annotations = []

        if completed > 0:
            j = completed - 1

            # Find closest circuit point
            distance = (track["X"] - section_x[j])**2 + (track["Y"] - section_y[j])**2
            k = distance.argmin()

            # Calculate local circuit direction
            before = (k - 1) % len(track)
            after = (k + 1) % len(track)

            dx = track["X"].iloc[after] - track["X"].iloc[before]
            dy = track["Y"].iloc[after] - track["Y"].iloc[before]

            # Perpendicular annotation offset
            length = np.sqrt(dx**2 + dy**2)

            if length > 0:
                ax = -dy / length * 150
                ay = -dx / length * 150
            else:
                ax, ay = 120, -90

            # Color corresponds to the faster driver
            winner = sections["Winner"].iloc[j]
            color = RED if winner == driver1 else BLUE

            # Message box
            text = f"<span style='font-size:10px;color:{MUTED}'>SECTION {j+1:02d}</span><br><b>{messages[i]}</b>"

            annotations.append(dict(
                x=section_x[j], y=section_y[j],
                text=text,
                showarrow=True,
                arrowhead=2,
                arrowwidth=2,
                arrowcolor=color,
                ax=ax, ay=ay,
                bgcolor="#202027",
                bordercolor=color,
                borderwidth=1.5,
                borderpad=8,
                font=dict(size=12, color=WHITE)
            ))

        frame = go.Frame(data=positions, traces=[1, 2], layout=go.Layout(annotations=annotations))
        frames.append(frame)

    fig.frames = frames

    # 14. Playback controls (AI generated)
    fig.update_layout(updatemenus=[dict(
        type="buttons", direction="left", showactive=False,
        x=0.5, xanchor="center", y=-0.05, yanchor="top",
        bgcolor="#202027", bordercolor=GRID, font=dict(color=WHITE, size=13),
        buttons=[
            dict(label="▶ Play", method="animate", args=[None, {"frame": {"duration": 1000 / fps, "redraw": True}, "transition": {"duration": 0}, "fromcurrent": True}]),
            dict(label="Ⅱ Pause", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": True}, "transition": {"duration": 0}, "mode": "immediate"}])
        ]
    )])

    return fig
