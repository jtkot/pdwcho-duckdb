COPY (
    WITH episode_metrics AS (
        SELECT 
            season_num,
            episode_num,
            aired_date,
            cnt_downed_redshirts AS redshirts_lost,
            cnt_kirk_hookups AS kirk_romances,
            highest_warp_speed_issued AS max_warp,
            (cnt_damn_it_jim_quote + cnt_im_givin_her_all_shes_got_quote + cnt_highly_illogical_quote) AS classic_catchphrases,
            
            -- Wskaźnik Zagrożenia Misji (Severity Score)
            (
                (cnt_downed_redshirts * 3) +
                (bool_aliens_almost_took_over_enterprise::INT * 10) +
                (bool_aliens_almost_took_over_planet::INT * 5) +
                (bool_ship_photon_torpedos_fired::INT * 4) +
                (bool_hand_phasers_fired::INT * 2)
            ) AS mission_hazard_score,
            
            bool_enterprise_saved_the_day AS mission_success
        FROM 'https://blobs.duckdb.org/data/Star_Trek-Season_1.csv'
    )
    SELECT 
        episode_num,
        aired_date,
        mission_hazard_score,
        DENSE_RANK() OVER (ORDER BY mission_hazard_score DESC) AS hazard_rank,
        redshirts_lost,
        kirk_romances,
        max_warp,
        classic_catchphrases,
        
        -- Średnia krocząca ofiar (okno: poprzedni, bieżący i następny odcinek)
        ROUND(AVG(redshirts_lost) OVER (
            ORDER BY episode_num 
            ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
        ), 2) AS rolling_avg_redshirts_lost,
        
        -- Skumulowana liczba poległych członków załogi w trakcie sezonu
        SUM(redshirts_lost) OVER (ORDER BY episode_num) AS cumulative_redshirts_lost,
        
        mission_success
    FROM episode_metrics
    ORDER BY hazard_rank ASC
) TO 'star_trek_s1_danger_index.parquet' (FORMAT PARQUET, COMPRESSION ZSTD);
