library(wehoop)
library(dplyr)
library(readr)

# ── Fetch Player Box Scores ──────────────────────────────────────────────────
message("Fetching 2025-26 Player Box Scores...")
# This call provides the official points and minutes for the Over/Under chart
box_raw <- wehoop::load_wbb_player_box(seasons = 2026)
# ── Fetch ─────────────────────────────────────────────────────────────────────
message("Fetching 2025-26 Women's College Basketball PBP data...")
pbp <- wehoop::load_wbb_pbp(seasons = 2026)

# ── Filter ────────────────────────────────────────────────────────────────────
ucsb_pbp <- pbp |>
  filter(
    home_team_name == "UC Santa Barbara" |
    away_team_name == "UC Santa Barbara"
  )

# ── Filter for UCSB ──────────────────────────────────────────────────────────
# Using grepl is safer because box scores often use "UC Santa Barbara Gauchos"
ucsb_box <- box_raw |>
  filter(grepl("Santa Barbara", team_display_name, ignore.case = TRUE))

# ── Export ────────────────────────────────────────────────────────────────────
if (!dir.exists("data")) dir.create("data")

write_csv(ucsb_box, "data/ucsb_wbb_2026_box.csv")

# ── Summary ───────────────────────────────────────────────────────────────────
message(sprintf(
  "Success! Exported %d rows of player data to 'data/ucsb_wbb_2026_box.csv'.",
  nrow(ucsb_box)
))