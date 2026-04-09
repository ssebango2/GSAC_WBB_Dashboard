# GSAC WBB Dashboard

UCSB Women's Basketball 2025-26 analytics dashboard built with Streamlit.

## Setup

**Python** (dashboard + data fetching):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/python.txt
```

**R** (data fetching via wehoop):

```bash
Rscript requirements/r.R
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
