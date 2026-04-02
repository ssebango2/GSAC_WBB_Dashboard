import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="UCSB WBB · Points Per Possession", layout="wide")

UCSB_TEAM_ID = 2540
DATA_PATH = "data/ucsb_wbb_2026_pbp.csv"

# ── Possession-ending play types ───────────────────────────────────────────────
# A possession ends when:
#   - A field goal is made (JumpShot, LayUpShot, TipShot)
#   - A turnover occurs (Lost Ball Turnover)
#   - A defensive rebound gives the ball to the other team
#   - A made free throw that is the last of the sequence (MadeFreeThrow)
MADE_FG_TYPES = {"JumpShot", "LayUpShot", "TipShot"}
TURNOVER_TYPES = {"Lost Ball Turnover"}
DEF_REBOUND_TYPE = "Defensive Rebound"
FREE_THROW_TYPE = "MadeFreeThrow"


@st.cache_data
def load_data():
    df = pd.read_csv(DATA_PATH, low_memory=False)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")
    df["home_team_id"] = pd.to_numeric(df["home_team_id"], errors="coerce")
    df["away_team_id"] = pd.to_numeric(df["away_team_id"], errors="coerce")
    df["score_value"] = pd.to_numeric(df["score_value"], errors="coerce").fillna(0)
    return df


def get_opponent(row):
    if row["home_team_id"] == UCSB_TEAM_ID:
        return row["away_team_name"]
    return row["home_team_name"]


def count_possessions(game_df, team_id):
    """
    Estimate possessions for one team in one game using the standard
    play-by-play heuristic: possession ends on a made FG, turnover,
    defensive rebound (by the other team), or the last free throw attempt.
    """
    team_plays = game_df[game_df["team_id"] == team_id].copy()
    possessions = 0

    made_fg = team_plays["type_text"].isin(MADE_FG_TYPES)
    turnovers = team_plays["type_text"].isin(TURNOVER_TYPES)

    # Defensive rebounds credited to the opponent end our possession
    opp_id = game_df.loc[
        game_df["team_id"] != team_id, "team_id"
    ].dropna().unique()
    if len(opp_id) > 0:
        opp_def_reb = game_df[
            (game_df["team_id"] == opp_id[0]) &
            (game_df["type_text"] == DEF_REBOUND_TYPE)
        ]
        possessions += len(opp_def_reb)

    possessions += made_fg.sum() + turnovers.sum()
    return max(possessions, 1)  # avoid division by zero


def compute_ppp(df):
    results = []
    for game_id, game_df in df.groupby("game_id"):
        game_df = game_df.sort_values("sequence_number")
        row0 = game_df.iloc[0]
        game_date = row0["game_date"]
        opponent = get_opponent(row0)
        home_away = "Home" if row0["home_team_id"] == UCSB_TEAM_ID else "Away"

        # UCSB points = sum of score_value on UCSB plays
        ucsb_points = game_df.loc[
            game_df["team_id"] == UCSB_TEAM_ID, "score_value"
        ].sum()

        opp_team_id = (
            row0["away_team_id"]
            if row0["home_team_id"] == UCSB_TEAM_ID
            else row0["home_team_id"]
        )
        opp_points = game_df.loc[
            game_df["team_id"] == opp_team_id, "score_value"
        ].sum()

        ucsb_poss = count_possessions(game_df, UCSB_TEAM_ID)
        opp_poss = count_possessions(game_df, opp_team_id)

        ucsb_ppp = ucsb_points / ucsb_poss
        opp_ppp = opp_points / opp_poss

        results.append({
            "game_id": game_id,
            "game_date": game_date,
            "opponent": opponent,
            "home_away": home_away,
            "ucsb_points": int(ucsb_points),
            "opp_points": int(opp_points),
            "ucsb_possessions": ucsb_poss,
            "opp_possessions": opp_poss,
            "ucsb_ppp": round(ucsb_ppp, 3),
            "opp_ppp": round(opp_ppp, 3),
            "result": "W" if ucsb_points > opp_points else "L",
        })

    return pd.DataFrame(results).sort_values("game_date")


# ── Load & compute ─────────────────────────────────────────────────────────────
df = load_data()
ppp_df = compute_ppp(df)
ppp_df["game_label"] = ppp_df.apply(
    lambda r: f"{r['game_date']}  {r['home_away']} vs {r['opponent']}  ({r['result']})",
    axis=1,
)

# ── Sidebar filter ─────────────────────────────────────────────────────────────
st.sidebar.title("Filters")
all_label = "All Games"
game_options = [all_label] + ppp_df["game_label"].tolist()
selected = st.sidebar.selectbox("Select Game Date", game_options)

if selected == all_label:
    view = ppp_df
else:
    view = ppp_df[ppp_df["game_label"] == selected]

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("UCSB Women's Basketball · 2025-26")
st.subheader("Points Per Possession")

# ── Season-average metrics (always shown) ─────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Season Avg UCSB PPP",  f"{ppp_df['ucsb_ppp'].mean():.3f}")
col2.metric("Season Avg Opp PPP",   f"{ppp_df['opp_ppp'].mean():.3f}")
col3.metric("Record",
    f"{(ppp_df['result']=='W').sum()}-{(ppp_df['result']=='L').sum()}")
col4.metric("Games Played", len(ppp_df))

st.divider()

# ── Bar chart ──────────────────────────────────────────────────────────────────
fig = go.Figure()

fig.add_trace(go.Bar(
    name="UCSB PPP",
    x=view["game_label"],
    y=view["ucsb_ppp"],
    marker_color="#003660",
    text=view["ucsb_ppp"].apply(lambda x: f"{x:.3f}"),
    textposition="outside",
))

fig.add_trace(go.Bar(
    name="Opponent PPP",
    x=view["game_label"],
    y=view["opp_ppp"],
    marker_color="#DCE1E7",
    text=view["opp_ppp"].apply(lambda x: f"{x:.3f}"),
    textposition="outside",
))

fig.update_layout(
    barmode="group",
    xaxis_tickangle=-35,
    yaxis_title="Points Per Possession",
    xaxis_title="",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    plot_bgcolor="white",
    height=480,
    margin=dict(t=40, b=160),
    yaxis=dict(gridcolor="#f0f0f0"),
)

st.plotly_chart(fig, use_container_width=True)

# ── Data table ─────────────────────────────────────────────────────────────────
st.subheader("Game Log")

display_cols = {
    "game_date": "Date",
    "home_away": "H/A",
    "opponent": "Opponent",
    "result": "Result",
    "ucsb_points": "UCSB Pts",
    "opp_points": "Opp Pts",
    "ucsb_possessions": "UCSB Poss",
    "opp_possessions": "Opp Poss",
    "ucsb_ppp": "UCSB PPP",
    "opp_ppp": "Opp PPP",
}

table = view[list(display_cols.keys())].rename(columns=display_cols)

st.dataframe(
    table.style.format({"UCSB PPP": "{:.3f}", "Opp PPP": "{:.3f}"})
         .background_gradient(subset=["UCSB PPP"], cmap="Blues")
         .background_gradient(subset=["Opp PPP"], cmap="Reds"),
    use_container_width=True,
    hide_index=True,
)
