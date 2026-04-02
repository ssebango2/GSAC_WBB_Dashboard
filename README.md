# GSAC WBB Dashboard

UCSB Women's Basketball 2025-26 analytics dashboard built with Streamlit.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install setuptools==70.3.0
pip install "xgboost<3.1"
pip install streamlit plotly pandas sportsdataverse
```

## Refresh Data

Run the R script to pull the latest season PBP data from wehoop:

```bash
Rscript ucsb_wbb_data.R
```

Or use the Python script (requires the venv above):

```bash
python3 ucsb_wbb_data.py
```

## Run the Dashboard

```bash
source .venv/bin/activate
streamlit run app.py
```

## Data Source

Play-by-play data via [wehoop](https://github.com/sportsdataverse/wehoop) (R) / [sportsdataverse](https://github.com/sportsdataverse/sportsdataverse-py) (Python).
