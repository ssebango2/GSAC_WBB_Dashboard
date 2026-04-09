# R dependencies for the UCSB WBB data pipeline
#
# Run once to install all required packages:
#   Rscript requirements/r.R

required_packages <- c(
  "wehoop",   # SportsDataverse WBB play-by-play loader
  "dplyr",    # data manipulation
  "readr"     # CSV export (write_csv)
)

for (pkg in required_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    install.packages(pkg, repos = "https://cloud.r-project.org")
  } else {
    message(paste(pkg, "already installed"))
  }
}

message("All R packages ready.")
