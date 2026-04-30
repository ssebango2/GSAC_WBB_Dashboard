import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="UCSB WBB · Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ──────────────────────────────────────────────────────────────────

UCSB_TEAM_ID = 2540
DATA_PATH = "data/ucsb_wbb_2026_pbp.csv"

# Big West Conference opponents 2025-26.
# TODO: Update if schedule changes or team names differ in your CSV.
BIG_WEST_TEAMS = {
    "UC Davis", "UC Riverside", "UC Irvine", "Cal Poly",
    "Long Beach State", "Cal State Fullerton", "Cal State Northridge",
    "Cal State Bakersfield", "UC San Diego", "Hawai'i",
}

# Play type constants — these must match the `type_text` column exactly.
# TODO: If your CSV uses different strings, update these sets.
MADE_FG_TYPES    = {"JumpShot", "LayUpShot", "TipShot"}
TURNOVER_TYPES   = {"Lost Ball Turnover"}
DEF_REBOUND_TYPE = "Defensive Rebound"
OFF_REBOUND_TYPE = "Offensive Rebound"
FREE_THROW_TYPE  = "MadeFreeThrow"

# Chart colors
UCSB_NAVY = "#003660"
UCSB_GOLD = "#FEB81C"
OPP_COLOR = "#8B9BB0"

# Offensive efficiency threshold for insight generation.
PPP_WIN_THRESHOLD = 1.00



# Offensive efficiency threshold for insight generation.
PPP_WIN_THRESHOLD = 1.00


# ── Data loading ───────────────────────────────────────────────────────────────

@st.cache_data
def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, low_memory=False)
    df["game_date"]        = pd.to_datetime(df["game_date"]).dt.date
    df["team_id"]          = pd.to_numeric(df["team_id"],          errors="coerce")
    df["home_team_id"]     = pd.to_numeric(df["home_team_id"],     errors="coerce")
    df["away_team_id"]     = pd.to_numeric(df["away_team_id"],     errors="coerce")
    df["score_value"]      = pd.to_numeric(df["score_value"],      errors="coerce").fillna(0)
    df["points_attempted"] = pd.to_numeric(df["points_attempted"], errors="coerce").fillna(0)
    df["scoring_play"]     = df["scoring_play"].astype(str).str.upper() == "TRUE"
    df["shooting_play"]    = df["shooting_play"].astype(str).str.upper() == "TRUE"
    return df

def load_player_performance():
    try:
        df = pd.read_csv("data/ucsb_wbb_2026_box.csv")
        name_col = 'athlete_display_name'

        avgs = df.groupby(name_col)['points'].mean().reset_index()
        avgs.rename(columns = {'points': 'avg_pts'}, inplace=True)

        merged = pd.merge(df, avgs, on=name_col)
        merged['points_diff'] = merged['points'] - merged['avg_pts']

        return merged
    
    except FileNotFoundError:
        return pd.DataFrame

@st.cache_data
def load_player_lookup() -> pd.DataFrame:
    try:
        box = pd.read_csv("data/ucsb_wbb_2026_box.csv", low_memory=False)
    except FileNotFoundError:
        return pd.DataFrame(columns=["athlete_id", "athlete_display_name"])

    box["team_id"] = pd.to_numeric(box["team_id"], errors="coerce")
    box["athlete_id"] = pd.to_numeric(box["athlete_id"], errors="coerce")
    lookup = (
        box[box["team_id"] == UCSB_TEAM_ID][["athlete_id", "athlete_display_name"]]
        .dropna(subset=["athlete_id"])
        .drop_duplicates(subset=["athlete_id"])
    )
    return lookup

def compute_players_game_stats(df: pd.DataFrame) -> pd.DataFrame:
    ucsb_plays = df[df['team_id'] == UCSB_TEAM_ID].copy()

    points = ucsb_plays[ucsb_plays['scoring_play']].groupby(['game_id', 'athlete_id_1', 'athlete_id_1_name'])['score_value'].sum().reset_index()
    points.columns = ['game_id', 'player_id', 'player_name', 'pts']

    rebs = ucsb_plays[ucsb_plays['type_text'].str.contains("Rebound", na=False)].groupby(['game_id', 'athlete_id_1'])['type_text'].count().reset_index()
    rebs.columns = ['game_id', 'player_id', 'reb']

    player_stats = pd.merge(points, rebs, on=['game_id', 'player_id'], how='outer').fillna(0)

    return player_stats

def get_performance_indicator(player_df: pd.DataFrame):
    season_avgs = player_df.groupby('player_name')[['pts','reb']].mean().reset_index()
    season_avgs.columns = ['player_name', 'avg_points', 'avg_rebounds']

    merged = pd.merge(player_df, season_avgs, on='player_name')

    merged['points_diff'] = merged['pts'] - merged['avg_points']
    merged['rebounds_diff'] = merged['reb'] - merged['avg_rebounds']

    return merged

# ── Possession counting ────────────────────────────────────────────────────────


# ── Possession counting ────────────────────────────────────────────────────────

def count_possessions(game_sorted: pd.DataFrame, team_id: int) -> int:
    """
    Estimate possessions for one team in one game using the standard PBP heuristic.
    A possession ends on:
      1. A made field goal
      2. A turnover (Lost Ball Turnover attributed to this team)
      3. An opponent defensive rebound (missed shot/FT secured by defense)
      4. The last made FT of a trip (next event is not a free throw)
    Offensive rebounds do NOT end a possession.
    """
    team_plays = game_sorted[game_sorted["team_id"] == team_id]
    possessions = 0

    # 1 & 2
    made_fg   = team_plays["type_text"].isin(MADE_FG_TYPES) & team_plays["scoring_play"]
    turnovers = team_plays["type_text"].isin(TURNOVER_TYPES)
    possessions += int(made_fg.sum()) + int(turnovers.sum())

    # 3: opponent defensive rebounds
    opp_ids = game_sorted.loc[game_sorted["team_id"] != team_id, "team_id"].dropna().unique()
    if len(opp_ids) > 0:
        opp_def_reb = (
            (game_sorted["team_id"] == opp_ids[0]) &
            (game_sorted["type_text"] == DEF_REBOUND_TYPE)
        )
        possessions += int(opp_def_reb.sum())

    # 4: last made FT of a trip
    team_made_ft = team_plays[
        (team_plays["type_text"] == FREE_THROW_TYPE) & team_plays["scoring_play"]
    ]
    for idx in team_made_ft.index:
        next_idx = idx + 1
        if next_idx not in game_sorted.index or \
                game_sorted.loc[next_idx, "type_text"] != FREE_THROW_TYPE:
            possessions += 1

    return max(possessions, 1)


# ── Four Factors (possession-level efficiency drivers) ─────────────────────────

def compute_four_factors(team_plays: pd.DataFrame) -> dict:
    """
    Compute the Four Factors for one team in one game.

    Schema assumptions:
      - `type_text`: identifies shot type (MADE_FG_TYPES = 2pt/3pt FGA, made or missed),
        free throws (FREE_THROW_TYPE, made or missed), rebounds, and turnovers.
      - `score_value`: the point value of the play. For shots, this equals the
        attempt value (2 or 3) regardless of whether the shot was made — this is used
        to distinguish 2pt from 3pt attempts reliably across all games.
      - `scoring_play`: True if the play resulted in points being scored.
      - `points_attempted` is NOT used here because one game in the dataset
        (Chattanooga, 401831301) has all-zero values for that column. `score_value`
        is populated correctly in all games.

    TODO: "Lost Ball Turnover" may not capture all live-ball turnover types if the
    source data encodes other turnover subtypes differently (e.g. bad pass, out of
    bounds). Verify against box-score TO totals when possible.
    """
    # Field goal attempts: type_text identifies the shot; score_value tells us 2pt vs 3pt
    shot_mask = team_plays["type_text"].isin(MADE_FG_TYPES)
    fga      = int(shot_mask.sum())
    fgm      = int((shot_mask & team_plays["scoring_play"]).sum())
    three_pa = int((shot_mask & (team_plays["score_value"] == 3)).sum())
    three_pm = int((shot_mask & team_plays["scoring_play"] & (team_plays["score_value"] == 3)).sum())

    # Free throws: type_text == FREE_THROW_TYPE covers both made and missed FTs
    ft_mask  = team_plays["type_text"] == FREE_THROW_TYPE
    fta      = int(ft_mask.sum())
    ftm      = int((ft_mask & team_plays["scoring_play"]).sum())

    tov      = int(team_plays["type_text"].isin(TURNOVER_TYPES).sum())
    oreb     = int((team_plays["type_text"] == OFF_REBOUND_TYPE).sum())
    dreb     = int((team_plays["type_text"] == DEF_REBOUND_TYPE).sum())

    # eFG% = (FGM + 0.5 × 3PM) / FGA  — rewards 3-pt makes at 1.5× weight
    efg = (fgm + 0.5 * three_pm) / max(fga, 1)

    # TO% = turnovers per possession estimate (Hollinger formula)
    tov_pct = tov / max(fga + 0.44 * fta + tov, 1)

    # FT Rate = FTA / FGA  (how often do they get to the line?)
    ftr = fta / max(fga, 1)

    return {
        "fga": fga, "fgm": fgm, "three_pa": three_pa, "three_pm": three_pm,
        "fta": fta, "ftm": ftm, "tov": tov, "oreb": oreb, "dreb": dreb,
        "efg": efg, "tov_pct": tov_pct, "ftr": ftr,
    }


    # eFG% = (FGM + 0.5 × 3PM) / FGA  — rewards 3-pt makes at 1.5× weight
    efg = (fgm + 0.5 * three_pm) / max(fga, 1)

    # TO% = turnovers per possession estimate (Hollinger formula)
    tov_pct = tov / max(fga + 0.44 * fta + tov, 1)

    # FT Rate = FTA / FGA  (how often do they get to the line?)
    ftr = fta / max(fga, 1)

    return {
        "fga": fga, "fgm": fgm, "three_pa": three_pa, "three_pm": three_pm,
        "fta": fta, "ftm": ftm, "tov": tov, "oreb": oreb, "dreb": dreb,
        "efg": efg, "tov_pct": tov_pct, "ftr": ftr,
    }


# ── Game-level stat computation ────────────────────────────────────────────────

@st.cache_data
def compute_game_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per game with PPP, Four Factors, and metadata."""
    records = []
    for game_id, game_df in df.groupby("game_id"):
        game_df   = game_df.sort_values("sequence_number").reset_index(drop=True)
        row0      = game_df.iloc[0]

        is_home   = row0["home_team_id"] == UCSB_TEAM_ID
        opponent  = row0["away_team_name"] if is_home else row0["home_team_name"]
        home_away = "Home" if is_home else "Away"
        is_conf   = opponent in BIG_WEST_TEAMS
        opp_id    = int(row0["away_team_id"] if is_home else row0["home_team_id"])

        ucsb_pts = game_df.loc[
            (game_df["team_id"] == UCSB_TEAM_ID) & game_df["scoring_play"], "score_value"
        ].sum()
        opp_pts = game_df.loc[
            (game_df["team_id"] == opp_id) & game_df["scoring_play"], "score_value"
        ].sum()

        ucsb_poss = count_possessions(game_df, UCSB_TEAM_ID)
        opp_poss  = count_possessions(game_df, opp_id)

        ucsb_ff = compute_four_factors(game_df[game_df["team_id"] == UCSB_TEAM_ID])
        opp_ff  = compute_four_factors(game_df[game_df["team_id"] == opp_id])

        # OREB% = team OREBs / (team OREBs + opponent DREBs)
        ucsb_oreb_pct = ucsb_ff["oreb"] / max(ucsb_ff["oreb"] + opp_ff["dreb"], 1)
        opp_oreb_pct  = opp_ff["oreb"]  / max(opp_ff["oreb"]  + ucsb_ff["dreb"], 1)

        records.append({
            "game_id":          game_id,
            "game_date":        row0["game_date"],
            "opponent":         opponent,
            "home_away":        home_away,
            "is_conference":    is_conf,
            "ucsb_points":      int(ucsb_pts),
            "opp_points":       int(opp_pts),
            "ucsb_possessions": ucsb_poss,
            "opp_possessions":  opp_poss,
            "ucsb_ppp":         round(ucsb_pts / ucsb_poss, 3),
            "opp_ppp":          round(opp_pts  / opp_poss,  3),
            "result":           "W" if ucsb_pts > opp_pts else "L",
            # UCSB Four Factors
            "ucsb_efg":         round(ucsb_ff["efg"],       3),
            "ucsb_tov_pct":     round(ucsb_ff["tov_pct"],   3),
            "ucsb_oreb_pct":    round(ucsb_oreb_pct,        3),
            "ucsb_ftr":         round(ucsb_ff["ftr"],        3),
            "ucsb_fga":         ucsb_ff["fga"],
            "ucsb_3pa":         ucsb_ff["three_pa"],
            "ucsb_3pm":         ucsb_ff["three_pm"],
            "ucsb_fta":         ucsb_ff["fta"],
            "ucsb_ftm":         ucsb_ff["ftm"],
            "ucsb_tov":         ucsb_ff["tov"],
            # Opponent Four Factors
            "opp_efg":          round(opp_ff["efg"],        3),
            "opp_tov_pct":      round(opp_ff["tov_pct"],    3),
            "opp_oreb_pct":     round(opp_oreb_pct,         3),
            "opp_ftr":          round(opp_ff["ftr"],         3),
        })

    return pd.DataFrame(records).sort_values("game_date").reset_index(drop=True)


# ── Key Insights generator ─────────────────────────────────────────────────────

def generate_insights(gdf: pd.DataFrame) -> list[tuple[str, str]]:
    """
    Return up to 4 (level, text) pairs.
    level is one of: 'success' | 'warning' | 'info'
    """
    if len(gdf) == 0:
        return [("info", "No games match the current filters.")]

    wins   = gdf[gdf["result"] == "W"]
    losses = gdf[gdf["result"] == "L"]
    n_w, n_l = len(wins), len(losses)
    insights: list[tuple[str, str]] = []

    # 1. PPP threshold and win rate
    above = gdf[gdf["ucsb_ppp"] >= PPP_WIN_THRESHOLD]
    below = gdf[gdf["ucsb_ppp"] <  PPP_WIN_THRESHOLD]
    if len(above) > 0:
        a_wins = int((above["result"] == "W").sum())
        b_wins = int((below["result"] == "W").sum())
        level  = "success" if len(above) > 0 and a_wins / len(above) >= 0.70 else "info"
        insights.append((level,
            f"**Scoring efficiency & wins:** UCSB reaches ≥{PPP_WIN_THRESHOLD:.2f} pts/possession "
            f"in {len(above)} of {len(gdf)} game(s), going **{a_wins}–{len(above) - a_wins}** in those. "
            f"Below that mark: {b_wins}–{len(below) - b_wins}."
        ))

    # 2. Offense vs defense as the swing factor in losses
    if n_w >= 1 and n_l >= 1:
        avg_off_w = wins["ucsb_ppp"].mean()
        avg_off_l = losses["ucsb_ppp"].mean()
        avg_def_w = wins["opp_ppp"].mean()
        avg_def_l = losses["opp_ppp"].mean()
        off_drop  = avg_off_w - avg_off_l   # positive = offense drops in losses
        def_rise  = avg_def_l - avg_def_w   # positive = defense worsens in losses
        if off_drop > def_rise:
            insights.append(("warning",
                f"**Offense is the bigger swing factor:** UCSB scores {avg_off_l:.3f} PPP in losses "
                f"vs {avg_off_w:.3f} in wins (−{off_drop:.3f}). "
                f"Opponents improve only {def_rise:.3f} PPP in losses by comparison."
            ))
        else:
            insights.append(("warning",
                f"**Defense is the bigger swing factor:** Opponents average {avg_def_l:.3f} PPP "
                f"in losses vs {avg_def_w:.3f} in wins (+{def_rise:.3f}). "
                f"UCSB's own offense drops {off_drop:.3f} in losses — less of a factor."
            ))

    # 3. Home vs away split
    home_g = gdf[gdf["home_away"] == "Home"]
    away_g = gdf[gdf["home_away"] == "Away"]
    if len(home_g) >= 2 and len(away_g) >= 2:
        h_ppp = home_g["ucsb_ppp"].mean()
        a_ppp = away_g["ucsb_ppp"].mean()
        diff  = h_ppp - a_ppp
        h_rec = f"{int((home_g['result']=='W').sum())}–{int((home_g['result']=='L').sum())}"
        a_rec = f"{int((away_g['result']=='W').sum())}–{int((away_g['result']=='L').sum())}"
        if abs(diff) > 0.03:
            better = "at home" if diff > 0 else "on the road"
            insights.append(("info",
                f"**Location split:** UCSB scores {abs(diff):.3f} more PPP {better}. "
                f"Home: {h_ppp:.3f} PPP ({h_rec}) | Away: {a_ppp:.3f} PPP ({a_rec})."
            ))
        else:
            insights.append(("info",
                f"**Consistent across locations:** Home {h_ppp:.3f} PPP ({h_rec}) vs "
                f"Away {a_ppp:.3f} PPP ({a_rec}) — minimal location effect."
            ))

    # 4. Recent form: last 5 games vs earlier
    if len(gdf) >= 6:
        recent  = gdf.tail(5)
        earlier = gdf.iloc[:-5]
        r_off = recent["ucsb_ppp"].mean()
        e_off = earlier["ucsb_ppp"].mean()
        r_def = recent["opp_ppp"].mean()
        e_def = earlier["opp_ppp"].mean()
        off_arrow = "↑" if r_off > e_off else "↓"
        def_arrow = "↑" if r_def < e_def else "↓"  # lower opp PPP = better defense
        off_word  = "improving" if r_off > e_off else "declining"
        def_word  = "tightening" if r_def < e_def else "weakening"
        level = "success" if r_off > e_off else "warning"
        insights.append((level,
            f"**Recent form (last 5 games):** Offense {off_arrow} {off_word} "
            f"({r_off:.3f} vs {e_off:.3f} PPP earlier). "
            f"Defense {def_arrow} {def_word} (allowing {r_def:.3f} vs {e_def:.3f} PPP earlier)."
        ))
    elif len(gdf) >= 3:
        r_avg = gdf.tail(3)["ucsb_ppp"].mean()
        s_avg = gdf["ucsb_ppp"].mean()
        direction = "↑ trending up" if r_avg > s_avg else "↓ trending down"
        level = "success" if r_avg > s_avg else "warning"
        insights.append((level,
            f"**Recent offense (last 3):** {direction} — "
            f"{r_avg:.3f} PPP vs {s_avg:.3f} season average."
        ))

    return insights[:4]


# ── Highlight games ────────────────────────────────────────────────────────────

def get_highlights(gdf: pd.DataFrame) -> dict:
    if len(gdf) == 0:
        return {}
    gdf = gdf.copy()
    gdf["ppp_margin"] = gdf["ucsb_ppp"] - gdf["opp_ppp"]
    wins   = gdf[gdf["result"] == "W"]
    losses = gdf[gdf["result"] == "L"]
    return {
        "best_off":    gdf.loc[gdf["ucsb_ppp"].idxmax()],
        "worst_off":   gdf.loc[gdf["ucsb_ppp"].idxmin()],
        "best_def":    gdf.loc[gdf["opp_ppp"].idxmin()],
        "worst_def":   gdf.loc[gdf["opp_ppp"].idxmax()],
        "biggest_win": wins.loc[wins["ppp_margin"].idxmax()]  if len(wins)   > 0 else None,
        "worst_loss":  losses.loc[losses["ppp_margin"].idxmin()] if len(losses) > 0 else None,
    }


def hl_label(row: pd.Series) -> str:
    d = row["game_date"]
    date_str = d.strftime("%b %d") if hasattr(d, "strftime") else str(d)
    return f"{date_str} vs {row['opponent']} ({row['result']})"


# ── Sidebar ────────────────────────────────────────────────────────────────────

raw_df  = load_data()
full_df = compute_game_stats(raw_df)
full_df["game_date"] = pd.to_datetime(full_df["game_date"])

with st.sidebar:
    st.title("UCSB WBB 2025–26")
    st.markdown("### Filters")
    st.markdown("---")

    min_d = full_df["game_date"].min().date()
    max_d = full_df["game_date"].max().date()
    date_range = st.date_input(
        "Date range",
        value=(min_d, max_d),
        min_value=min_d,
        max_value=max_d,
    )

    all_opps = sorted(full_df["opponent"].unique().tolist())
    sel_opps = st.multiselect("Opponent", all_opps, default=[])

    location_filter = st.radio("Location", ["All", "Home", "Away"], horizontal=True)
    result_filter   = st.radio("Result",   ["All", "Wins", "Losses"], horizontal=True)
    conf_filter     = st.radio(
        "Game type",
        ["All", "Conference", "Non-Conference"],
        horizontal=True,
        help="Conference = Big West. Non-conference teams are inferred by name.",
    )

    st.markdown("---")
    roll_window = st.slider("Rolling avg window (games)", min_value=3, max_value=8, value=5,
                            help="Number of games for the rolling average trend line.")


# ── Apply filters ──────────────────────────────────────────────────────────────

filtered = full_df.copy()

if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    d0 = pd.Timestamp(date_range[0])
    d1 = pd.Timestamp(date_range[1])
    filtered = filtered[(filtered["game_date"] >= d0) & (filtered["game_date"] <= d1)]

if sel_opps:
    filtered = filtered[filtered["opponent"].isin(sel_opps)]

if location_filter != "All":
    filtered = filtered[filtered["home_away"] == location_filter]

if result_filter == "Wins":
    filtered = filtered[filtered["result"] == "W"]
elif result_filter == "Losses":
    filtered = filtered[filtered["result"] == "L"]

if conf_filter == "Conference":
    filtered = filtered[filtered["is_conference"]]
elif conf_filter == "Non-Conference":
    filtered = filtered[~filtered["is_conference"]]

filtered = filtered.sort_values("game_date").reset_index(drop=True)


# ── Header ─────────────────────────────────────────────────────────────────────

st.title("UCSB Women's Basketball · 2025–26")
st.caption("Coaching Analytics · Points Per Possession & Possession Drivers")

n_filtered = len(filtered)
n_total    = len(full_df)
if n_filtered < n_total:
    st.info(f"Showing **{n_filtered} of {n_total}** games based on current filters.", icon="🔎")


# ══════════════════════════════════════════════════════════════════════════════
# 1 · KEY INSIGHTS
# ══════════════════════════════════════════════════════════════════════════════

st.header("Key Insights")
insights = generate_insights(filtered)

# Display in a 2-column grid (or single column if only 1 insight)
if len(insights) >= 2:
    left_col, right_col = st.columns(2)
    buckets = [left_col, right_col, left_col, right_col]
    for col, (level, text) in zip(buckets, insights):
        with col:
            if level == "success":
                st.success(text)
            elif level == "warning":
                st.warning(text)
            else:
                st.info(text)
else:
    for level, text in insights:
        if level == "success":
            st.success(text)
        elif level == "warning":
            st.warning(text)
        else:
            st.info(text)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 2 · SEASON METRICS
# ══════════════════════════════════════════════════════════════════════════════

wins_n   = int((filtered["result"] == "W").sum())
losses_n = int((filtered["result"] == "L").sum())
avg_off  = filtered["ucsb_ppp"].mean() if n_filtered else 0.0
avg_def  = filtered["opp_ppp"].mean()  if n_filtered else 0.0
margin   = avg_off - avg_def

full_avg_off = full_df["ucsb_ppp"].mean()
full_avg_def = full_df["opp_ppp"].mean()

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Record",       f"{wins_n}–{losses_n}")
m2.metric("Games",        n_filtered)
m3.metric(
    "UCSB Avg PPP", f"{avg_off:.3f}",
    delta=f"{avg_off - full_avg_off:+.3f} vs full season" if n_filtered < n_total else None,
    help="Average points per possession for UCSB across filtered games.",
)
m4.metric(
    "Opp Avg PPP", f"{avg_def:.3f}",
    delta=f"{avg_def - full_avg_def:+.3f} vs full season" if n_filtered < n_total else None,
    delta_color="inverse",
    help="Average points per possession allowed by UCSB across filtered games.",
)
m5.metric(
    "PPP Margin", f"{margin:+.3f}",
    help="UCSB avg PPP minus opponent avg PPP. Positive = net efficiency advantage.",
)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 3 · POSSESSION DRIVERS (FOUR FACTORS)
# ══════════════════════════════════════════════════════════════════════════════

st.header("Possession Drivers — Why Is PPP High or Low?")
st.caption(
    "**eFG%** = effective FG% (3-pointers weighted 1.5×)  ·  "
    "**TO%** = turnover rate (lower is better)  ·  "
    "**OREB%** = offensive rebound rate  ·  "
    "**FT Rate** = FT attempts per FGA (getting to the line)"
)

if n_filtered > 0:
    wins_sub   = filtered[filtered["result"] == "W"]
    losses_sub = filtered[filtered["result"] == "L"]

    def _mean_ff(sub: pd.DataFrame) -> dict:
        cols = ["ucsb_efg", "ucsb_tov_pct", "ucsb_oreb_pct", "ucsb_ftr",
                "opp_efg",  "opp_tov_pct",  "opp_oreb_pct",  "opp_ftr"]
        if len(sub) == 0:
            return {c: np.nan for c in cols}
        return sub[cols].mean().to_dict()

    ov  = _mean_ff(filtered)
    inn = _mean_ff(wins_sub)
    inl = _mean_ff(losses_sub)

    # ── Top row: UCSB vs Opponent (overall) ──────────────────────────────────
    st.markdown("**UCSB vs Opponent — overall (filtered games)**")
    fa1, fa2, fa3, fa4 = st.columns(4)
    fa1.metric(
        "eFG%  (UCSB / Opp)",
        f"{ov['ucsb_efg']:.1%}  /  {ov['opp_efg']:.1%}",
        delta=f"UCSB advantage: {ov['ucsb_efg'] - ov['opp_efg']:+.1%}",
        help="Higher eFG% = more efficient shooting. Delta = UCSB minus Opponent.",
    )
    fa2.metric(
        "TO%  (UCSB / Opp)",
        f"{ov['ucsb_tov_pct']:.1%}  /  {ov['opp_tov_pct']:.1%}",
        delta=f"Opp advantage: {ov['opp_tov_pct'] - ov['ucsb_tov_pct']:+.1%}",
        delta_color="inverse",
        help="Lower TO% is better. Delta here shows how much fewer turnovers the opponent commits (positive = opp turns it over less).",
    )
    fa3.metric(
        "OREB%  (UCSB / Opp)",
        f"{ov['ucsb_oreb_pct']:.1%}  /  {ov['opp_oreb_pct']:.1%}",
        delta=f"UCSB advantage: {ov['ucsb_oreb_pct'] - ov['opp_oreb_pct']:+.1%}",
        help="Share of available offensive rebounds secured. Higher = more second-chance opportunities.",
    )
    fa4.metric(
        "FT Rate  (UCSB / Opp)",
        f"{ov['ucsb_ftr']:.2f}  /  {ov['opp_ftr']:.2f}",
        delta=f"UCSB advantage: {ov['ucsb_ftr'] - ov['opp_ftr']:+.2f}",
        help="FT attempts per FG attempt. Higher = getting to the free-throw line more often.",
    )

    # ── Wins vs Losses breakdown ───────────────────────────────────────────────
    if len(wins_sub) > 0 and len(losses_sub) > 0:
        st.markdown("**UCSB Four Factors — Wins vs Losses**")

        ff_table = pd.DataFrame({
            "Factor": ["eFG%", "Turnover Rate", "Off. Reb %", "FT Rate"],
            "In Wins":   [
                f"{inn['ucsb_efg']:.1%}",
                f"{inn['ucsb_tov_pct']:.1%}",
                f"{inn['ucsb_oreb_pct']:.1%}",
                f"{inn['ucsb_ftr']:.2f}",
            ],
            "In Losses": [
                f"{inl['ucsb_efg']:.1%}",
                f"{inl['ucsb_tov_pct']:.1%}",
                f"{inl['ucsb_oreb_pct']:.1%}",
                f"{inl['ucsb_ftr']:.2f}",
            ],
            "Direction": ["Higher = better", "Lower = better", "Higher = better", "Higher = better"],
        })
        st.dataframe(ff_table, use_container_width=True, hide_index=True)

        # Bar chart comparing wins vs losses for each factor
        cats    = ["eFG%", "TO%\n(lower=better)", "OREB%", "FT Rate"]
        w_vals  = [inn["ucsb_efg"], inn["ucsb_tov_pct"], inn["ucsb_oreb_pct"], inn["ucsb_ftr"]]
        l_vals  = [inl["ucsb_efg"], inl["ucsb_tov_pct"], inl["ucsb_oreb_pct"], inl["ucsb_ftr"]]

        if not any(np.isnan(v) for v in w_vals + l_vals):
            fig_ff = go.Figure()
            fig_ff.add_trace(go.Bar(
                name="Wins",   x=cats, y=w_vals,
                marker_color=UCSB_NAVY,
                text=[f"{v:.1%}" if i < 3 else f"{v:.2f}" for i, v in enumerate(w_vals)],
                textposition="outside",
            ))
            fig_ff.add_trace(go.Bar(
                name="Losses", x=cats, y=l_vals,
                marker_color=UCSB_GOLD,
                text=[f"{v:.1%}" if i < 3 else f"{v:.2f}" for i, v in enumerate(l_vals)],
                textposition="outside",
            ))
            fig_ff.update_layout(
                barmode="group",
                height=340,
                margin=dict(t=30, b=60),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(gridcolor="rgba(128,128,128,0.2)", tickformat=".1%"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_ff, use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 4 · HIGHLIGHT GAMES
# ══════════════════════════════════════════════════════════════════════════════

st.header("Highlight Games")
highlights = get_highlights(filtered)

if highlights:
    hc1, hc2, hc3 = st.columns(3)
    hc4, hc5, hc6 = st.columns(3)

    if highlights.get("best_off") is not None:
        r = highlights["best_off"]
        hc1.metric("Best Offense", f"{r['ucsb_ppp']:.3f} PPP", hl_label(r), delta_color="off")

    if highlights.get("worst_off") is not None:
        r = highlights["worst_off"]
        hc2.metric("Worst Offense", f"{r['ucsb_ppp']:.3f} PPP", hl_label(r), delta_color="off")

    if highlights.get("biggest_win") is not None:
        r = highlights["biggest_win"]
        hc3.metric("Biggest Win (PPP margin)", f"{r['ppp_margin']:+.3f}", hl_label(r), delta_color="off")

    if highlights.get("best_def") is not None:
        r = highlights["best_def"]
        hc4.metric("Best Defense", f"{r['opp_ppp']:.3f} opp PPP", hl_label(r), delta_color="off")

    if highlights.get("worst_def") is not None:
        r = highlights["worst_def"]
        hc5.metric("Worst Defense", f"{r['opp_ppp']:.3f} opp PPP", hl_label(r), delta_color="off")

    if highlights.get("worst_loss") is not None:
        r = highlights["worst_loss"]
        hc6.metric("Worst Loss (PPP margin)", f"{r['ppp_margin']:+.3f}", hl_label(r), delta_color="off")

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 5 · PLAYER OVERPERFORMANCE/UNDERPERFORMANCE
# ══════════════════════════════════════════════════════════════════════════════

st.header("Player Performance")

st.caption("Select a player to see their scoring trend over the last 10 games vs. their season average.")

def load_player_trends(box_path, games_df):
    try:
        box =pd.read_csv(box_path)

        meta = games_df[['game_id', 'game_date', 'opponent', 'result']].copy()
        df = pd.merge(box, meta, on='game_id')

        avgs = df.groupby('athlete_display_name')['points'].mean().reset_index()

        avgs.rename(columns={'points': 'avg_points'}, inplace=True)

        return pd.merge(df, avgs, on='athlete_display_name')
    except Exception:
        return pd.DataFrame()
    
player_trends_df = load_player_trends("data/ucsb_wbb_2026_box.csv", full_df)
if not player_trends_df.empty:

    col_sel, col_met = st.columns([1,1])

    with col_sel:
        player_sorting = player_trends_df[['athlete_display_name', 'avg_points']].drop_duplicates()
        player_sorting = player_sorting.sort_values('avg_points', ascending=False)
        all_players = player_sorting['athlete_display_name'].tolist()
        selected_player = st.selectbox("Select a Player", all_players)


    with col_met:

        metric_map = {
            'Points': 'points',
            'Rebounds': 'rebounds',
            'Assists': 'assists',
            'Steals': 'steals',
            'Blocks': 'blocks'
        }
        selected_label = st.radio('Metric', list(metric_map.keys()), horizontal=True)
        active_metric =metric_map[selected_label]

    p_full_data = player_trends_df[player_trends_df['athlete_display_name'] == selected_player].copy()
    p_full_data['game_date_x'] = pd.to_datetime(p_full_data['game_date_x'])
    p_full_data = p_full_data.sort_values('game_date_x', ascending=False)

    p_last_10 = p_full_data.head(10).iloc[::-1]
    season_avg = p_full_data[active_metric].mean()
    last_10_avg = p_last_10[active_metric].mean()

    img_col, stats_col = st.columns([1,4])

    with img_col:
        if 'athlete_headshot_href' in p_full_data.columns and pd.notnull(p_full_data['athlete_headshot_href'].iloc[0]):
            st.image(p_full_data['athlete_headshot_href'].iloc[0], width=120)
        else:
            st.write("No Image")

    with stats_col:
        m1,m2,m3 = st.columns(3)
        m1.metric("Season Average", f'{season_avg:.1f}')
        m2.metric("Last 10 Average", f'{last_10_avg:.1f}',
                  delta=f'{last_10_avg-season_avg:+.1f}',
                  help="Comparing last 10 games with season average")
        m3.metric("Max (Season)", f'{p_full_data[active_metric].max():.0f}')

    p_last_10['game_label'] = p_last_10.apply(
        lambda r: f"{r['game_date_x'].strftime('%b %d')}<br>vs {r['opponent']}", axis=1
    )

    fig_spot = go.Figure()

    fig_spot.add_trace(go.Bar(
        x=p_last_10['game_label'],
        y=p_last_10[active_metric],
        marker_color = [UCSB_NAVY if val >= season_avg else UCSB_GOLD for val in p_last_10[active_metric]],
        text=p_last_10[active_metric],
        textposition='outside',
        name=selected_label,
        hovertemplate="<b>%{x}</b><br>" + f'{selected_label}: ' + "%{y}<extra></extra>",
    ))

    fig_spot.add_hline(
        y=season_avg,
        line_dash='dash',
        line_color= "#FF4B4B",
        annotation_text=f'Season Average: {season_avg:.1f}',
        annotation_position='top left'
    )

    fig_spot.update_layout(
        title=f'Last 10 games: {selected_player} ({selected_label})',
        yaxis_title=selected_label,
        xaxis_title="",
        height=400,
        margin=dict(t=60, b=20),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False
    )

    st.plotly_chart(fig_spot, use_container_width=True)

    with st.expander(f"View {selected_player}'s Full Season Game Log"):
        display_cols = ['game_date_x', 'opponent', 'minutes', 'points', 'rebounds', 'assists', 'steals', 'blocks']
        st.dataframe(p_full_data[display_cols].rename(columns={'game_date_x': 'Date'}), use_container_width=True, hide_index=True)
    
else:
    st.warning("Player boxscore data not found")


st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 6 · PER-GAME CHARTS
# 5 · PER-GAME CHARTS
# ══════════════════════════════════════════════════════════════════════════════

st.header("Per-Game Performance")

if n_filtered == 0:
    st.warning("No games match the current filters.")
else:
    filtered = filtered.copy()
    filtered["short_label"] = filtered.apply(
        lambda r: (
            f"{r['game_date'].strftime('%b %d')} "
            f"{'vs' if r['home_away'] == 'Home' else '@'} "
            f"{r['opponent'][:14]} ({r['result']})"
        ),
        axis=1,
    )

    tab_bar, tab_trend = st.tabs(["PPP Bar Chart", "Rolling Average Trend"])

    # ── Tab 1: Grouped bar chart ─────────────────────────────────────────────
    with tab_bar:
        bar_colors = [UCSB_NAVY if r == "W" else UCSB_GOLD for r in filtered["result"]]
        fig_bar = go.Figure()
        fig_bar.add_trace(go.Bar(
            name="UCSB PPP",
            x=filtered["short_label"],
            y=filtered["ucsb_ppp"],
            marker_color=bar_colors,
            text=filtered["ucsb_ppp"].apply(lambda x: f"{x:.3f}"),
            textposition="outside",
        ))
        fig_bar.add_trace(go.Bar(
            name="Opponent PPP",
            x=filtered["short_label"],
            y=filtered["opp_ppp"],
            marker_color=OPP_COLOR,
            text=filtered["opp_ppp"].apply(lambda x: f"{x:.3f}"),
            textposition="outside",
        ))
        fig_bar.update_layout(
            barmode="group",
            xaxis_tickangle=-35,
            yaxis_title="Points Per Possession",
            xaxis_title="",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=480,
            margin=dict(t=40, b=160),
            yaxis=dict(gridcolor="rgba(128,128,128,0.2)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_bar, use_container_width=True)
        st.caption("Navy bar = Win · Gold bar = Loss · Grey bar = Opponent PPP")

    # ── Tab 2: Rolling average trend ─────────────────────────────────────────
    with tab_trend:
        if n_filtered < roll_window:
            st.info(
                f"Need at least {roll_window} games for a rolling average. "
                "Reduce the window in the sidebar or adjust your filters."
            )
        else:
            roll_off = filtered["ucsb_ppp"].rolling(roll_window, min_periods=roll_window).mean()
            roll_def = filtered["opp_ppp"].rolling(roll_window, min_periods=roll_window).mean()

            fig_trend = go.Figure()

            # Faint per-game scatter
            fig_trend.add_trace(go.Scatter(
                x=filtered["game_date"], y=filtered["ucsb_ppp"],
                mode="markers",
                name="UCSB PPP (per game)",
                marker=dict(color=UCSB_NAVY, size=8, opacity=0.35),
                hovertemplate="%{text}<br>UCSB: %{y:.3f} PPP<extra></extra>",
                text=filtered["short_label"],
            ))
            fig_trend.add_trace(go.Scatter(
                x=filtered["game_date"], y=filtered["opp_ppp"],
                mode="markers",
                name="Opp PPP (per game)",
                marker=dict(color=OPP_COLOR, size=8, opacity=0.35),
                hovertemplate="%{text}<br>Opp: %{y:.3f} PPP<extra></extra>",
                text=filtered["short_label"],
            ))

            # Rolling average lines
            fig_trend.add_trace(go.Scatter(
                x=filtered["game_date"], y=roll_off,
                mode="lines",
                name=f"UCSB {roll_window}-game rolling avg",
                line=dict(color=UCSB_NAVY, width=3),
                hovertemplate="UCSB rolling: %{y:.3f}<extra></extra>",
            ))
            fig_trend.add_trace(go.Scatter(
                x=filtered["game_date"], y=roll_def,
                mode="lines",
                name=f"Opp {roll_window}-game rolling avg",
                line=dict(color=UCSB_GOLD, width=3, dash="dash"),
                hovertemplate="Opp rolling: %{y:.3f}<extra></extra>",
            ))

            fig_trend.update_layout(
                yaxis_title="Points Per Possession",
                xaxis_title="",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                height=420,
                margin=dict(t=30, b=40),
                yaxis=dict(gridcolor="rgba(128,128,128,0.2)"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig_trend, use_container_width=True)
            st.caption(
                f"Solid navy = UCSB {roll_window}-game rolling avg  ·  "
                f"Dashed gold = Opponent {roll_window}-game rolling avg  ·  "
                "Faint dots = per-game values"
            )

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 7 · SHOT MAP
# ══════════════════════════════════════════════════════════════════════════════

st.header("UCSB Shot Map")
st.caption("Made shots = red circles · Missed shots = blue Xs")

shot_game_options = filtered[["game_id", "game_date", "home_away", "opponent", "result"]].drop_duplicates()
shot_game_options = shot_game_options.sort_values("game_date").reset_index(drop=True)
shot_game_options["game_label"] = shot_game_options.apply(
    lambda r: (
        f"{r['game_date'].strftime('%Y-%m-%d')} "
        f"{'vs' if r['home_away'] == 'Home' else '@'} {r['opponent']} ({r['result']})"
    ),
    axis=1,
)

shot_label_to_id = dict(zip(shot_game_options["game_label"], shot_game_options["game_id"]))
selected_shot_game = st.selectbox(
    "Shot chart game",
    options=["All filtered games"] + shot_game_options["game_label"].tolist(),
    index=0,
)

if selected_shot_game == "All filtered games":
    shot_games = set(filtered["game_id"].tolist()) if n_filtered > 0 else set()
else:
    shot_games = {shot_label_to_id[selected_shot_game]}

shot_df = raw_df[
    (raw_df["team_id"] == UCSB_TEAM_ID)
    & (raw_df["game_id"].isin(shot_games))
    & (raw_df["type_text"].isin(MADE_FG_TYPES))
].copy()

if shot_df.empty:
    st.info("No UCSB shot attempts available for the selected filters.")
else:
    shot_df["athlete_id_1"] = pd.to_numeric(shot_df["athlete_id_1"], errors="coerce")
    player_lookup = load_player_lookup()
    shot_df = shot_df.merge(
        player_lookup,
        left_on="athlete_id_1",
        right_on="athlete_id",
        how="left",
    )
    shot_df["shooter_label"] = shot_df["athlete_display_name"].fillna(
        shot_df["athlete_id_1"].apply(
            lambda x: f"Player ID {int(x)}" if pd.notna(x) else "Unknown"
        )
    )

    player_options = sorted(shot_df["shooter_label"].dropna().unique().tolist())
    selected_shooter = st.selectbox(
        "Shot chart player",
        options=["All players"] + player_options,
        index=0,
    )
    if selected_shooter != "All players":
        shot_df = shot_df[shot_df["shooter_label"] == selected_shooter]

    shot_df["coordinate_x"] = pd.to_numeric(shot_df["coordinate_x"], errors="coerce")
    shot_df["coordinate_y"] = pd.to_numeric(shot_df["coordinate_y"], errors="coerce")

    # Drop missing and sentinel/out-of-bounds values from provider feed.
    shot_df = shot_df[
        shot_df["coordinate_x"].notna()
        & shot_df["coordinate_y"].notna()
        & shot_df["coordinate_x"].between(-50, 50)
        & shot_df["coordinate_y"].between(-30, 30)
    ]

    if shot_df.empty:
        st.info("No valid shot coordinates available for the selected filters.")
    else:
        # Normalize both basket directions to a single hoop view.
        # Original feed places hoops on left/right (x near +/- 41.75).
        # After transform: hoop is at (0, 0), all shots shown on one half court.
        hoop_x = 41.75
        shot_df["plot_x"] = shot_df["coordinate_y"]
        shot_df["plot_y"] = hoop_x - shot_df["coordinate_x"].abs()
        shot_df["shot_distance_ft"] = np.sqrt(shot_df["plot_x"] ** 2 + shot_df["plot_y"] ** 2)
        shot_df["shot_result"] = np.where(shot_df["scoring_play"], "Made", "Missed")
        shot_df["shot_type"] = np.where(
            pd.to_numeric(shot_df["score_value"], errors="coerce") == 3,
            "3PT attempt",
            "2PT attempt",
        )

        shot_meta = (
            filtered[["game_id", "game_date", "opponent", "home_away"]]
            .drop_duplicates()
            .rename(columns={"game_date": "game_date_meta"})
        )
        shot_df = shot_df.merge(shot_meta, on="game_id", how="left")
        shot_df["game_context"] = shot_df.apply(
            lambda r: (
                f"{pd.Timestamp(r['game_date_meta']).strftime('%Y-%m-%d')} "
                f"{'vs' if r['home_away'] == 'Home' else '@'} {r['opponent']}"
            )
            if pd.notna(r["game_date_meta"]) and pd.notna(r["opponent"]) and pd.notna(r["home_away"])
            else "Game context unavailable",
            axis=1,
        )

        made_shots = shot_df[shot_df["scoring_play"]]
        missed_shots = shot_df[~shot_df["scoring_play"]]

        court_color = "rgba(25, 70, 145, 0.9)"
        # NCAA women's 3PT line (2021-22 onward): 22' 1.75" top, 21' 8" corners.
        three_radius = 22 + (1.75 / 12)  # 22.145833...
        corner_three_x = 21 + (8 / 12)    # 21.666667...
        baseline_y = -4.0
        paint_top_y = baseline_y + 19.0  # top of key is 19 ft from baseline
        # Arc/line intersection so corner segments connect seamlessly to the arc.
        break_y = np.sqrt(max(three_radius**2 - corner_three_x**2, 0.0))
        angle_at_break = np.arcsin(np.clip(break_y / three_radius, -1.0, 1.0))
        theta = np.linspace(angle_at_break, np.pi - angle_at_break, 180)
        three_arc_x = three_radius * np.cos(theta)
        three_arc_y = three_radius * np.sin(theta)
        ft_theta = np.linspace(0, np.pi, 120)
        ft_arc_x = 6 * np.cos(ft_theta)
        ft_arc_y = paint_top_y - 6 * np.sin(ft_theta)

        is_three = pd.to_numeric(shot_df["score_value"], errors="coerce") == 3
        is_paint = (
            shot_df["plot_x"].abs().le(6)
            & shot_df["plot_y"].ge(baseline_y)
            & shot_df["plot_y"].le(paint_top_y)
        )
        is_mid_range = (~is_three) & (~is_paint) & (shot_df["shot_distance_ft"] < three_radius)

        def fg_stat(mask: pd.Series) -> tuple[str, str]:
            attempts = int(mask.sum())
            if attempts == 0:
                return "N/A", "0/0"
            makes = int((shot_df.loc[mask, "scoring_play"]).sum())
            return f"{(makes / attempts):.1%}", f"{makes}/{attempts}"

        total_pct, total_raw = fg_stat(pd.Series(True, index=shot_df.index))
        paint_pct, paint_raw = fg_stat(is_paint)
        mid_pct, mid_raw = fg_stat(is_mid_range)
        three_pct, three_raw = fg_stat(is_three)

        fig_shot = go.Figure()
        # Half-court markings with hoop at top center.
        fig_shot.add_shape(type="rect", x0=-25, y0=-4, x1=25, y1=47, line=dict(color=court_color, width=2))
        # Paint drawn to match zone logic: |x| <= 6 and baseline_y <= y <= paint_top_y.
        fig_shot.add_shape(type="rect", x0=-6, y0=baseline_y, x1=6, y1=paint_top_y, line=dict(color=court_color, width=2))
        fig_shot.add_shape(type="circle", x0=-0.75, y0=-0.75, x1=0.75, y1=0.75, line=dict(color=court_color, width=3))
        fig_shot.add_shape(type="line", x0=-3, y0=-1.5, x1=3, y1=-1.5, line=dict(color=court_color, width=2))
        fig_shot.add_shape(
            type="line",
            x0=-corner_three_x,
            y0=-4,
            x1=-corner_three_x,
            y1=break_y,
            line=dict(color=court_color, width=2),
        )
        fig_shot.add_shape(
            type="line",
            x0=corner_three_x,
            y0=-4,
            x1=corner_three_x,
            y1=break_y,
            line=dict(color=court_color, width=2),
        )
        fig_shot.add_trace(go.Scatter(
            x=ft_arc_x,
            y=ft_arc_y,
            mode="lines",
            line=dict(color=court_color, width=2),
            hoverinfo="skip",
            showlegend=False,
        ))
        fig_shot.add_trace(go.Scatter(
            x=three_arc_x,
            y=three_arc_y,
            mode="lines",
            name="3PT Arc",
            line=dict(color=court_color, width=2),
            hoverinfo="skip",
            showlegend=False,
        ))

        fig_shot.add_trace(go.Scatter(
            x=made_shots["plot_x"],
            y=made_shots["plot_y"],
            mode="markers",
            name="Made",
            marker=dict(color="red", symbol="circle", size=8, opacity=0.8),
            customdata=np.stack(
                [
                    made_shots["shooter_label"].to_numpy(),
                    made_shots["shot_distance_ft"].round(1).to_numpy(),
                    made_shots["shot_type"].to_numpy(),
                    made_shots["shot_result"].to_numpy(),
                    made_shots["game_context"].to_numpy(),
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[2]} %{customdata[3]}<br>"
                "Distance: %{customdata[1]} ft<br>"
                "%{customdata[4]}<extra></extra>"
            ),
        ))
        fig_shot.add_trace(go.Scatter(
            x=missed_shots["plot_x"],
            y=missed_shots["plot_y"],
            mode="markers",
            name="Missed",
            marker=dict(color="blue", symbol="x", size=8, opacity=0.8),
            customdata=np.stack(
                [
                    missed_shots["shooter_label"].to_numpy(),
                    missed_shots["shot_distance_ft"].round(1).to_numpy(),
                    missed_shots["shot_type"].to_numpy(),
                    missed_shots["shot_result"].to_numpy(),
                    missed_shots["game_context"].to_numpy(),
                ],
                axis=-1,
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "%{customdata[2]} %{customdata[3]}<br>"
                "Distance: %{customdata[1]} ft<br>"
                "%{customdata[4]}<extra></extra>"
            ),
        ))

        fig_shot.update_layout(
            xaxis_title="",
            yaxis_title="",
            height=520,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(range=[-25, 25], showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(range=[47, -5], showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", scaleratio=1),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(t=30, b=30),
        )
        plot_col, metric_col = st.columns([4, 1])
        with plot_col:
            st.plotly_chart(fig_shot, use_container_width=True)
        with metric_col:
            st.metric("Total FG%", total_pct, delta=total_raw, delta_color="off")
            st.metric("Paint FG%", paint_pct, delta=paint_raw, delta_color="off")
            st.metric("Mid-Range FG%", mid_pct, delta=mid_raw, delta_color="off")
            st.metric("3P FG%", three_pct, delta=three_raw, delta_color="off")

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# 7 · GAME LOG
# 6 · GAME LOG
# ══════════════════════════════════════════════════════════════════════════════

st.header("Game Log")

if n_filtered == 0:
    st.warning("No games match the current filters.")
else:
    log_cols = {
        "game_date":        "Date",
        "home_away":        "H/A",
        "opponent":         "Opponent",
        "result":           "Result",
        "ucsb_points":      "UCSB Pts",
        "opp_points":       "Opp Pts",
        "ucsb_possessions": "UCSB Poss",
        "opp_possessions":  "Opp Poss",
        "ucsb_ppp":         "UCSB PPP",
        "opp_ppp":          "Opp PPP",
        "ucsb_efg":         "eFG%",
        "ucsb_tov_pct":     "TO%",
        "ucsb_oreb_pct":    "OREB%",
        "ucsb_ftr":         "FT Rate",
    }

    log_df = filtered[list(log_cols.keys())].rename(columns=log_cols).copy()
    log_df["Date"] = log_df["Date"].dt.strftime("%Y-%m-%d")

    st.dataframe(
        log_df.style
              .format({
                  "UCSB PPP": "{:.3f}", "Opp PPP": "{:.3f}",
                  "eFG%": "{:.1%}", "TO%": "{:.1%}", "OREB%": "{:.1%}",
                  "FT Rate": "{:.2f}",
              })
              .background_gradient(subset=["UCSB PPP"], cmap="Blues")
              .background_gradient(subset=["Opp PPP"],  cmap="Reds_r"),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("Column definitions"):
        st.markdown("""
| Column | Definition |
|--------|-----------|
| **H/A** | Home or Away |
| **UCSB / Opp Poss** | Estimated possessions per team (see possession logic in code) |
| **UCSB PPP** | UCSB points ÷ estimated UCSB possessions |
| **Opp PPP** | Opponent points ÷ estimated opponent possessions |
| **eFG%** | Effective field goal % — `(FGM + 0.5 × 3PM) / FGA` — weights 3-pointers at 1.5× |
| **TO%** | Turnover rate — `TOV / (FGA + 0.44 × FTA + TOV)` — lower is better |
| **OREB%** | Offensive rebound rate — `UCSB OREB / (UCSB OREB + Opp DREB)` |
| **FT Rate** | Free throw rate — `FTA / FGA` — how often UCSB gets to the line |
        """)
