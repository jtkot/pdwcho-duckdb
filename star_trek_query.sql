SELECT 
    hazard_rank,
    episode_num,
    mission_hazard_score,
    redshirts_lost,
    cumulative_redshirts_lost,
    kirk_romances,
    classic_catchphrases
FROM 'star_trek_s1_danger_index.parquet'
LIMIT 5;
