# Telemetry visualization functions copied from the notebook

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import tif1


def get_overtake_highlights(year, circuit, limit=8):

    session = tif1.get_session(year, circuit, "Race")
    laps = session.laps.copy()

    # Prepare position data
    positions = laps[["Driver", "LapNumber", "Position"]].copy()
    positions = positions.dropna().sort_values(["Driver", "LapNumber"])

    # Add starting grid as lap 0
    grid = session.results[["Abbreviation", "GridPosition"]].copy()

    grid = grid.rename(columns={
        "Abbreviation": "Driver",
        "GridPosition": "Position"
    })

    grid["LapNumber"] = 0

    positions = pd.concat([positions, grid], ignore_index=True)
    positions = positions[positions["Position"] > 0]
    positions = positions.sort_values(["Driver", "LapNumber"])

    # Position table
    pos = positions.pivot_table(
        index="LapNumber", columns="Driver", values="Position"
    )

    # Identify pit-stop laps
    pit = laps["PitInTime"].notna() | laps["PitOutTime"].notna()
    pit_laps = laps[pit]
    pit_set = set(zip(pit_laps["Driver"], pit_laps["LapNumber"]))

    # Identify potential overtakes
    events = []

    for lap in pos.index[1:]:
        if lap - 1 not in pos.index:
            continue

        before = pos.loc[lap - 1]
        after = pos.loc[lap]

        for i, a in enumerate(pos.columns):
            for b in pos.columns[i + 1:]:

                if pd.isna(before[a]) or pd.isna(before[b]) or pd.isna(after[a]) or pd.isna(after[b]):
                    continue

                if before[a] > before[b] and after[a] < after[b]:
                    winner, loser = a, b

                elif before[b] > before[a] and after[b] < after[a]:
                    winner, loser = b, a

                else:
                    continue

                if (winner, lap) in pit_set or (loser, lap) in pit_set:
                    continue

                events.append({
                    "LapNumber": int(lap),
                    "GainedAhead": winner,
                    "FellBehind": loser,
                    "NewPosition": int(after[winner])
                })

    # Select the most interesting events
    highlights = pd.DataFrame(
        events,
        columns=["LapNumber", "GainedAhead", "FellBehind", "NewPosition"]
    )

    highlights = highlights.sort_values(
        ["NewPosition", "LapNumber"],
        ascending=[True, False]
    ).head(limit).copy()

    # Generate headlines
    def headline(row):
        a = row["GainedAhead"]
        b = row["FellBehind"]

        if row["NewPosition"] == 1:
            return f"Lead change! {a} moves ahead of {b}"
        elif row["NewPosition"] <= 3:
            return f"Podium battle! {a} moves ahead of {b}"
        else:
            return f"{a} moves ahead of {b}"

    highlights["Headline"] = highlights.apply(headline, axis=1)

    return highlights.reset_index(drop=True)


def telemetry_viz_2drivers_2modes(year, circuit, driver1, driver2, fps=20, lap_number=None):
    # F1 styling
    BACKGROUND = "#101014"
    GRID = "#303038"
    WHITE = "#FFFFFF"
    MUTED = "#AAAAAA"
    RED = "#E5484D"
    BLUE = "#36A3FF"

    # 1. Load circuit and telemetry
    session = tif1.get_session(year, circuit, "Race")
    track = session.get_circuit_info().track
    drivers = [driver1, driver2]
    colors = [RED, BLUE]
    telemetry_data = {}

    # column name differs for fastest lap vs. overtake animation
    time_col = "Time" if lap_number is None else "SessionTime"

    for driver in drivers:
        if lap_number is None:
            telemetry = session.get_driver(driver).get_fastest_lap_tel()
        else:
            # for the overtake the telemetry of the specific lap is imported from tif1
            telemetry = session.get_driver(driver).get_lap(lap_number).telemetry

        telemetry = telemetry.dropna(subset=[time_col, "X", "Y"]).sort_values(time_col).drop_duplicates(time_col).copy()
        if len(telemetry) < 2:
            raise ValueError(f"Not enough telemetry for {driver} on the requested lap.")

        time = telemetry[time_col].dt.total_seconds().to_numpy()
        # adjusting drivers to the same time grid is not used for overtakes
        if lap_number is None:
            time = time - time[0]

        telemetry["TimeSeconds"] = time
        telemetry_data[driver] = {"telemetry": telemetry, "time": time}

    # 2. Shared time axis only for fastest lap animation
    if lap_number is None:
        start = 0
        end = max(telemetry_data[d]["time"][-1] for d in drivers)
    else:
        # find the time interval where both drivers have telemetry
        start = max(telemetry_data[d]["time"][0] for d in drivers)
        end = min(telemetry_data[d]["time"][-1] for d in drivers)

    if end <= start:
        raise ValueError("The selected laps do not overlap in race time.")

    # NEW: Find overtaking time
    if lap_number is not None:

        time_check = np.arange(start, end, 0.1)

        d1 = telemetry_data[driver1]
        d2 = telemetry_data[driver2]

        p1 = np.interp(time_check, d1["time"], d1["telemetry"]["RelativeDistance"])
        p2 = np.interp(time_check, d2["time"], d2["telemetry"]["RelativeDistance"])

        difference = p1 - p2

        if difference[0] < 0 and (difference >= 0).any():
            overtake_time = time_check[np.where(difference >= 0)[0][0]]

            start = max(start, overtake_time - 10)
            end = min(end, overtake_time + 10)

        else:
            print("No overtake detected. Showing the full lap.")

    time_interp = np.arange(start, end, 1 / fps)

    for driver in drivers:
        data = telemetry_data[driver]
        telemetry = data["telemetry"]
        data["x"] = np.interp(time_interp, data["time"], telemetry["X"])
        data["y"] = np.interp(time_interp, data["time"], telemetry["Y"])

    # 3. Section messages only for fastest-lap animation
    if lap_number is None:
        corners = session.get_circuit_info().corners.sort_values("Distance")
        reference = telemetry_data[driver1]["telemetry"][ ["Distance", "RelativeDistance"] ].dropna()
        reference = reference[reference["RelativeDistance"] > 0.01]
        lap_distance = np.median(reference["Distance"] / reference["RelativeDistance"])

        section_bounds = np.concatenate(([0], corners["Distance"].to_numpy(), [lap_distance]))
        n_sections = len(section_bounds) - 1
        section_names = (["Start → T1"] + [f"T{i} → T{i+1}" for i in range(1, n_sections - 1)] + [f"T{n_sections - 1} → Finish"])
        sections = pd.DataFrame({"Section": section_names})

        def corner_times(telemetry):
            times = []
            for _, corner in corners.iterrows():
                expected = corner["Distance"] / lap_distance
                nearby = telemetry[telemetry["RelativeDistance"].between(expected - 0.01, expected + 0.01)]
                if nearby.empty:
                    raise ValueError("A corner could not be matched to telemetry.")
                distances = (nearby["X"] - corner["X"])**2 + (nearby["Y"] - corner["Y"])**2
                times.append(nearby.loc[distances.idxmin(), "TimeSeconds"])
            return np.array(times)

        t1 = telemetry_data[driver1]["telemetry"]
        t2 = telemetry_data[driver2]["telemetry"]
        time1 = np.concatenate(([0], corner_times(t1), [t1["TimeSeconds"].max()]))
        time2 = np.concatenate(([0], corner_times(t2), [t2["TimeSeconds"].max()]))

        sections["Delta"] = np.diff(time1) - np.diff(time2)
        sections["Winner"] = np.where(sections["Delta"] > 0, driver2, driver1)
        sections["Message"] = (sections["Winner"] + " gained " + sections["Delta"].abs().round(3).astype(str) + "s in " + sections["Section"])
        message_times = np.maximum(time1[1:], time2[1:])
        section_x = np.concatenate((corners["X"].to_numpy(), [track["X"].iloc[0]]))
        section_y = np.concatenate((corners["Y"].to_numpy(), [track["Y"].iloc[0]]))

    # 4. Plot the circuit and cars
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=track["X"], y=track["Y"], mode="lines", name="Circuit",
        line=dict(color="#666674", width=5), hoverinfo="skip"
    ))

    for driver, marker in zip(drivers, [dict(symbol="diamond", color=RED, size=14),
                                        dict(symbol="circle", color=BLUE, size=11)]):
        fig.add_trace(go.Scatter(
            x=[telemetry_data[driver]["x"][0]], y=[telemetry_data[driver]["y"][0]],
            mode="markers", name=driver, marker=marker, hoverinfo="skip"
        ))

    # figure title depends on "mode"
    mode = "Fastest Lap" if lap_number is None else f"Lap {lap_number} / Race Replay"
    fig.update_layout(
        title=dict(
            text=f"<b>F1 / LAP TELEMETRY</b><br><span style='font-size:14px;color:{MUTED}'>{year} {circuit} | <span style='color:{RED}'>{driver1}</span> vs <span style='color:{BLUE}'>{driver2}</span> | {mode}</span>",
            font=dict(size=23, color=WHITE), x=0.04, y=0.97, xanchor="left", yanchor="top"
        ),
        template="plotly_dark", paper_bgcolor=BACKGROUND, plot_bgcolor=BACKGROUND,
        font=dict(family="Arial", color=WHITE, size=13),
        width=750, height=670, margin=dict(l=70, r=40, t=110, b=95),
        showlegend=False, hovermode=False
    )

    x_pad = (track["X"].max() - track["X"].min()) * 0.30
    y_pad = (track["Y"].max() - track["Y"].min()) * 0.30
    fig.update_xaxes(visible=False, range=[track["X"].min() - x_pad, track["X"].max() + x_pad])
    fig.update_yaxes(visible=False, range=[track["Y"].min() - y_pad, track["Y"].max() + y_pad], scaleanchor="x", scaleratio=1)

    # 5. Prepare section annotations once (fastest-lap mode only)
    section_annotations = []
    if lap_number is None:
        for j in range(len(sections)):
            distance = (track["X"] - section_x[j])**2 + (track["Y"] - section_y[j])**2
            k = distance.argmin()
            before, after = (k - 1) % len(track), (k + 1) % len(track)
            dx = track["X"].iloc[after] - track["X"].iloc[before]
            dy = track["Y"].iloc[after] - track["Y"].iloc[before]
            length = np.sqrt(dx**2 + dy**2)
            ax, ay = (-dy / length * 150, -dx / length * 150) if length > 0 else (120, -90)
            color = RED if sections["Winner"].iloc[j] == driver1 else BLUE
            text = f"<span style='font-size:10px;color:{MUTED}'>SECTION {j+1:02d}</span><br><b>{sections['Message'].iloc[j]}</b>"
            section_annotations.append(dict(
                x=section_x[j], y=section_y[j], text=text, showarrow=True,
                arrowhead=2, arrowwidth=2, arrowcolor=color, ax=ax, ay=ay,
                bgcolor="#202027", bordercolor=color, borderwidth=1.5,
                borderpad=8, font=dict(size=12, color=WHITE)
            ))

    # 6. Animation
    frames = []
    for i, t in enumerate(time_interp):
        positions = [go.Scatter(x=[telemetry_data[d]["x"][i]], y=[telemetry_data[d]["y"][i]]) for d in drivers]
        annotations = []
        if lap_number is None:
            completed = np.searchsorted(message_times, t, side="right")
            if completed > 0:
                annotations = [section_annotations[completed - 1]]

        frames.append(go.Frame(data=positions, traces=[1, 2], layout=go.Layout(annotations=annotations)))

    fig.frames = frames
    fig.update_layout(updatemenus=[dict(
        type="buttons", direction="left", showactive=False,
        x=0.5, xanchor="center", y=-0.08, yanchor="top",
        bgcolor="#202027", bordercolor=GRID, font=dict(color=WHITE, size=13),
        buttons=[
            dict(label="▶ Play", method="animate", args=[None, {"frame": {"duration": 1000 / fps, "redraw": True}, "transition": {"duration": 0}, "fromcurrent": True}]),
            dict(label="Ⅱ Pause", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": True}, "transition": {"duration": 0}, "mode": "immediate"}])
        ]
    )])
    return fig
