import sportsdataverse.wbb as wbb
import pandas as pd

def get_ucsb_data(season=2026):
    print(f"Fetching {season} Women's Basketball Play-by-Play data...")
    
    # Load the full season PBP
    # This pulls from the SportsDataverse GitHub/CDN
    df = wbb.load_wbb_pbp(seasons=[season])
    
    # Filter for UC Santa Barbara
    # We check both home and away to get all Gaucho games
    ucsb_df = df[(df['home_team_name'] == 'UC Santa Barbara') | 
                 (df['away_team_name'] == 'UC Santa Barbara')].copy()
    
    print(f"Successfully loaded {len(ucsb_df)} rows of data for UCSB.")
    return ucsb_df

if __name__ == "__main__":
    data = get_ucsb_data()
    
    # Quick look at the columns available for your metrics
    # Columns like 'shooting_play', 'foul_play', 'points_scored' are key for PPP
    print(data[['game_date', 'type_text', 'text', 'score_value']].head())
    
    # Export to CSV for your dashboard foundation
    data.to_csv("ucsb_wbb_2026_pbp.csv", index=False)