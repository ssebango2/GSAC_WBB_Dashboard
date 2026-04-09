# ── Dependencies ──────────────────────────────────────────────────────────────
required_packages <- c("wehoop", "dplyr", "readr")

for (pkg in required_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    install.packages(pkg, repos = "https://cloud.r-project.org")
  }
}

library(wehoop)
library(dplyr)
library(readr)

# ── Fetch ─────────────────────────────────────────────────────────────────────
message("Fetching 2025-26 Women's College Basketball PBP data...")
pbp <- wehoop::load_wbb_pbp(seasons = 2026)

# ── Filter ────────────────────────────────────────────────────────────────────
ucsb_pbp <- pbp |>
  filter(
    home_team_name == "UC Santa Barbara" |
    away_team_name == "UC Santa Barbara"
  )

# ── Clean ──────────────────────────────────────────────────────────────────────
ucsb_pbp <- ucsb_pbp |>
  mutate(game_date = as.Date(game_date)) |>
  arrange(game_date)

# ── Export ─────────────────────────────────────────────────────────────────────
dir.create("data", showWarnings = FALSE)
output_path <- file.path("data", "ucsb_wbb_2026_pbp.csv")
write_csv(ucsb_pbp, output_path)

# ── Summary ────────────────────────────────────────────────────────────────────
n_games <- n_distinct(ucsb_pbp$game_id)
n_rows  <- nrow(ucsb_pbp)

message(sprintf(
  "Done. Exported %d rows across %d UCSB game(s) to '%s'.",
  n_rows, n_games, output_path
))
