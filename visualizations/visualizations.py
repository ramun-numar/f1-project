import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Designed by AI
# Coded by Human :)
# Copied from the Jupyter Notebook


# F1 DESIGN
BACKGROUND = "#101014"
GRID = "#303038"
WHITE = "#FFFFFF"
MUTED = "#AAAAAA"
GREEN = "#19B99B"
RED = "#E5484D"
BLUE = "#5695E8"


def f1_style(fig, title, subtitle, height=600):
    """Apply consistent F1 styling to all plots."""

    fig.update_layout(
        title=dict(
            text=(
                f"<b>F1 / {title}</b>"
                f"<br><span style='font-size:14px;color:{MUTED}'>"
                f"{subtitle}</span>"
            ),
            font=dict(size=23, color=WHITE),
            x=0.04,
            y=0.97,
            xanchor="left",
            yanchor="top"
        ),
        template="plotly_dark",
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        font=dict(family="Arial", color=WHITE, size=13),
        height=height,
        margin=dict(l=180, r=70, t=120, b=70),
        showlegend=False
    )

    fig.update_xaxes(
        gridcolor=GRID,
        zeroline=False,
        tickfont=dict(color=MUTED)
    )

    fig.update_yaxes(
        showgrid=False,
        tickfont=dict(color=WHITE, size=13)
    )

    return fig


def feature_group(name):
    """Group model features into readable categories."""

    name = str(name).split("__", 1)[-1]

    if name in ("gridPositionNumber", "grid_fraction", "grid_street", "pit_lane"):
        return "Starting grid"
    if name.startswith(("qualifying", "qualification", "quali", "q1", "q2", "q3")):
        return "Qualifying"
    if name.startswith("driverId_"):
        return "Driver identity"
    if name.startswith("constructorId_"):
        return "Constructor"
    if name.startswith("driver_"):
        return "Driver history"
    if name.startswith("team_"):
        return "Team performance"
    if name.startswith(("circuit", "course", "turns", "scheduledLaps", "street")):
        return "Circuit characteristics"

    return "Other features"


# GRAPH 1: PREDICTED RACE RESULTS

def plot_race_results(prediction_data):

    data = prediction_data.sort_values("predicted_position").copy()
    driver_order = data["driverId"].tolist()

    fig = px.bar(
        data,
        x="predicted_position",
        y="driverId",
        color="constructorId",
        orientation="h",
        hover_data=["predicted_score", "gridPositionNumber"],
        category_orders={"driverId": driver_order[::-1]}
    )

    fig = f1_style(
        fig,
        title="PREDICTED RACE RESULTS",
        subtitle="Ridge Regression | Predicted Finishing Order",
        height=850
    )

    fig.update_layout(bargap=0.3)

    fig.update_xaxes(
        title="Predicted finishing position",
        dtick=2
    )

    fig.update_yaxes(title=None)

    fig.update_traces(
        marker_line_width=0,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Predicted position: %{x}<br>"
            "Predicted score: %{customdata[0]:.3f}<br>"
            "Grid position: %{customdata[1]}"
            "<extra></extra>"
        )
    )

    return fig


# GRAPH 2: PREDICTION BREAKDOWN

def plot_prediction_breakdown(driver, race_model):

    if len(driver) != 1:
        raise ValueError("driver must contain exactly one row")

    # Get fitted model components
    preprocessor = race_model.named_steps["preprocessor"]
    ridge = race_model.named_steps["regression"]

    # Transform selected driver's features
    feature_columns = list(preprocessor.feature_names_in_)
    transformed = preprocessor.transform(driver[feature_columns])

    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()

    values = np.asarray(transformed).ravel()
    names = preprocessor.get_feature_names_out()
    coefficients = np.asarray(ridge.coef_).ravel()

    if len(values) != len(coefficients):
        raise ValueError("Feature count does not match coefficients")

    # Calculate and group contributions
    contributions = pd.DataFrame({
        "feature": names,
        "contribution": values * coefficients
    })

    contributions["group"] = contributions["feature"].map(feature_group)

    grouped = (
        contributions.groupby("group")["contribution"]
        .sum()
        .sort_values()
    )

    intercept = float(np.asarray(ridge.intercept_).item())
    predicted_score = intercept + grouped.sum()
    driver_id = str(driver["driverId"].iloc[0])

    # Create waterfall chart
    fig = go.Figure(go.Waterfall(
        orientation="h",
        y=["Intercept", *grouped.index, "Prediction"],
        x=[intercept, *grouped.values, 0],
        measure=["absolute"] + ["relative"] * len(grouped) + ["total"],

        decreasing={"marker": {"color": GREEN}},
        increasing={"marker": {"color": RED}},
        totals={"marker": {"color": BLUE}},

        connector={"line": {
            "color": "#555560",
            "width": 1,
            "dash": "dot"
        }},

        textposition="outside",
        text=(
            [f"{intercept:.3f}"]
            + [f"{v:+.3f}" for v in grouped]
            + [f"{predicted_score:.3f}"]
        ),
        textfont=dict(color=WHITE, size=13)
    ))

    fig = f1_style(
        fig,
        title="PREDICTION BREAKDOWN",
        subtitle=f"Driver: {driver_id} | Ridge Regression Feature Contributions",
        height=600
    )

    fig.update_layout(waterfallgap=0.35)

    fig.update_xaxes(
        title="Predicted finish fraction",
        zeroline=True,
        zerolinecolor="#666666"
    )

    fig.update_yaxes(autorange="reversed")

    return fig