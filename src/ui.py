"""
Reusable UI pieces for the website pages.

A "component" here is just a function that calls st.* — call it inside a
column or container and it draws there.
"""
import pandas as pd
import streamlit as st

from data import site_data as sd

GREEN, RED, MUTED = "#19B99B", "#E5484D", "#8A8A95"


# ─────────────────────────────────────────────────────────────────────────────
# Data loading (cached once per server, shared by all pages)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading F1 data…")
def tables():
    return sd.load_site_tables()


@st.cache_data(show_spinner=False)
def track_map(year, event_name, height=260, show_corners=True):
    """Cached: the first load of a circuit downloads it with tif1 (can take ~30 s)."""
    from visualizations.track_map import track_map_fig
    return track_map_fig(year, event_name, height=height, show_corners=show_corners)


def draw_track_map(slot, tbl, race, height=260, before_race_id=None, show_corners=True):
    """Fill `slot` (an st.empty()) with the circuit outline.

    Pages create the slot where the map belongs, but call this at the *end*
    of the script. Streamlit draws elements as the script runs, so everything
    else is already visible while the (possibly slow) map downloads.
    """
    from visualizations.track_map import latest_session_at
    with slot.container():
        try:
            with st.spinner("Loading track map…"):
                source = latest_session_at(tbl, race["circuitId"], before_race_id)
                if source is None:
                    st.caption("No track data available for this circuit.")
                    return
                st.plotly_chart(track_map(*source, height=height, show_corners=show_corners),
                                width="stretch", config={"displayModeBar": False},
                                key=f"map_{race['id']}_{height}")
            if source[0] != race["year"]:
                st.caption(f"Layout from the {source[0]} {source[1]}")
        except Exception as error:  # network/tif1 problems shouldn't break the page
            st.caption(f"Track map unavailable ({error.__class__.__name__}).")


# ─────────────────────────────────────────────────────────────────────────────
# Text pieces
# ─────────────────────────────────────────────────────────────────────────────
def section_header(first_word, accent_word, link_page=None, link_label=None):
    """Two-tone heading ("Driver :red[Standings]") with an optional link on the right."""
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    left.subheader(f"{first_word} :red[{accent_word}]")
    if link_page:
        right.page_link(link_page, label=link_label, icon=":material/arrow_forward:")


@st.fragment(run_every="1s")
def countdown(target, label="until lights out"):
    """Live countdown.

    @st.fragment marks a piece of the page that can re-run on its own.
    run_every="1s" re-runs *only this function* every second, so the clock
    ticks without reloading the rest of the page.
    """
    left = target - pd.Timestamp.now(tz="UTC")
    if left.total_seconds() <= 0:
        st.markdown("### :red[● Live / finished]")
        return
    days, rest = divmod(int(left.total_seconds()), 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    st.markdown(f"### `{days:02d}`d `{hours:02d}`h `{minutes:02d}`m `{seconds:02d}`s")
    st.caption(label)


def banner(kind, name, detail):
    """Orange 'Winner / Favorite' box from the Standings sketches."""
    icon = ":material/emoji_events:" if kind == "Champion" else ":material/star:"
    with st.container(border=True):
        st.markdown(f"#### {icon} :orange[{kind}:] {name}")
        st.caption(detail)


# ─────────────────────────────────────────────────────────────────────────────
# Tables
# ─────────────────────────────────────────────────────────────────────────────
def _evo_text(value):
    if value > 0:
        return f"▲ {value}"
    if value < 0:
        return f"▼ {-value}"
    return "–"


def _evo_color(text):
    if text.startswith("▲"):
        return f"color: {GREEN}"
    if text.startswith("▼"):
        return f"color: {RED}"
    return f"color: {MUTED}"


def show_table(df, name_label="Driver", height=None, key=None):
    """Draw a standings-style table.

    st.dataframe accepts a pandas *Styler*, which lets us color cells
    (green/red Evo arrows) — column_config then sets labels and formats.
    """
    df = df.drop(columns=["id"], errors="ignore").rename(columns={"Name": name_label})
    if "Evo" in df:
        df["Evo"] = df["Evo"].map(_evo_text)
    styled = df.style.map(_evo_color, subset=["Evo"]) if "Evo" in df else df.style
    integer_points = "Points" in df and (df["Points"] % 1 == 0).all()
    st.dataframe(
        styled,
        hide_index=True,
        width="stretch",
        # fit all rows without an inner scrollbar (35 px per row + header)
        height=height or 35 * (len(df) + 1) + 3,
        key=key,
        column_config={
            "Pos": st.column_config.TextColumn("Pos.", width="small"),
            "Points": st.column_config.NumberColumn("Points", format="%d" if integer_points else "%.1f"),
            "Evo": st.column_config.TextColumn("Evo", width="small",
                                               help="Places gained (▲) or lost (▼)"),
            "Title %": st.column_config.ProgressColumn("Title %", format="%.0f%%", min_value=0, max_value=100),
        },
    )


def standings_card(tbl, season, rnd, kind="driver", key="", title=True, link_page=None, top_n=None,
                   forecast=None):
    """The 'Driver/Constructor Standings' box with its Forecast toggle.

    Toggle off: official standings, Evo = places gained in the last round.
    Toggle on:  championship-model forecast of the final standings,
                Evo = places the model expects them to gain by season end.
    Pass forecast=True/False to drive it from a page-level toggle instead.
    """
    first, label = ("Driver", "Driver") if kind == "driver" else ("Constructor", "Constructor")
    with st.container(border=True):
        head, toggle_col = st.columns([3, 1], vertical_alignment="center")
        if title:
            head.subheader(f"{first} :red[Standings]")
        if forecast is None:
            # st.toggle returns True/False; `key` must be unique per widget on a page
            forecast = toggle_col.toggle("Forecast", key=f"{key}{kind}_forecast_{season}_{rnd}")

        if forecast:
            df, start = sd.forecast_table(tbl, season, rnd, kind)
            if df.empty:
                st.info("No championship forecast saved for this season yet.")
                return
            st.caption(f"Projected final standings · simulated after round {start}")
        else:
            df = sd.standings_table(tbl, season, rnd, kind)
            if df.empty:
                st.info("No standings for this season.")
                return
            st.caption(f"After round {rnd}")

        show_table(df.head(top_n) if top_n else df, name_label=label, key=f"{key}{kind}_table_{forecast}")
        if link_page:
            st.page_link(link_page, label="Full standings & charts", icon=":material/arrow_forward:")


def title_probability_card(tbl, season, rnd):
    """'Title Probabilities' box: top 3 drivers | top 3 constructors + the rest."""
    with st.container(border=True):
        st.markdown("**Title Probabilities**")
        cols = st.columns(2)
        for col, kind, label in [(cols[0], "driver", "Driver"), (cols[1], "team", "Const.")]:
            probs = sd.title_probabilities(tbl, season, rnd, kind)
            with col:
                st.caption(label)
                if not probs:
                    st.write("No forecast saved.")
                    continue
                for i, (name, pct) in enumerate(probs["top"], start=1):
                    st.markdown(f"{i}. {name} — **{pct:.0f}%**")
                st.markdown(f":gray[Rest — {probs['rest']:.0f}%]")
        if probs:
            st.caption(f"Simulated after round {probs['after_round']}")


def model_error_card(tbl, race):
    """'MAE of pre & post quali model vs. baseline'."""
    errors = sd.model_errors(tbl, race)
    with st.container(border=True):
        st.markdown("**Model error** · average places off (MAE) vs. baseline")
        if not errors:
            st.caption("No saved predictions for this race, so there is nothing to compare.")
            return
        baseline = errors.get("Baseline (finish = grid)")
        for col, (label, value) in zip(st.columns(len(errors)), errors.items()):
            # delta_color="inverse": a *lower* error than the baseline shows green
            delta = None if baseline is None or label.startswith("Baseline") else f"{value - baseline:+.2f} vs baseline"
            col.metric(label, f"{value:.2f}", delta=delta, delta_color="inverse")
        st.caption("Baseline: predict that everyone finishes where they qualified.")
