-- Une ligne par game (mon point de vue), entièrement recalculable depuis le JSON brut.
-- NULL = non mesurable pour cette game (jamais de valeur inventée).
CREATE TABLE features (
    match_id              TEXT PRIMARY KEY REFERENCES matches(match_id) ON DELETE CASCADE,
    computed_at           TEXT NOT NULL,
    extractor_version     INTEGER NOT NULL,
    -- cibles
    y_win                 INTEGER NOT NULL,
    y2_team_gold_diff_15  INTEGER,
    -- flags (is_remake = critère d'exclusion des analyses)
    is_remake             INTEGER NOT NULL DEFAULT 0,
    ended_in_surrender    INTEGER,
    -- A. contexte de session
    session_game_index    INTEGER,
    games_played_today    INTEGER,
    minutes_since_prev_game REAL,
    prev_game_result      TEXT,     -- 'W' / 'L' / NULL (première game connue)
    current_streak        INTEGER,  -- série entrante signée (+2 = 2 wins, -3 = 3 losses)
    hour_of_day           INTEGER,  -- heure locale
    day_of_week           INTEGER,  -- 0 = lundi
    session_length_so_far_min REAL,
    -- B. draft & compo
    my_champion           TEXT,
    my_champ_recent_games INTEGER,  -- fenêtre 30 jours avant la game
    my_champ_recent_wr    REAL,     -- ATTENTION au screening : bruit si peu de games, corrèle avec les streaks
    enemy_jungler_champion TEXT,
    side                  TEXT,     -- 'blue' / 'red'
    i_am_autofilled       INTEGER,
    ally_tank_count       INTEGER,  -- compo via Data Dragon (tags)
    enemy_tank_count      INTEGER,
    ally_ranged_count     INTEGER,
    enemy_ranged_count    INTEGER,
    ally_ap_ratio         REAL,     -- approximation DDragon info.magic/attack (inféré)
    enemy_ap_ratio        REAL,
    -- C. early game (< 15 min), diffs vs jungler adverse
    gold_diff_ejgl_5      INTEGER,
    gold_diff_ejgl_10     INTEGER,
    gold_diff_ejgl_15     INTEGER,
    xp_diff_ejgl_10       INTEGER,
    cs_diff_ejgl_10       INTEGER,
    kills_pre15           INTEGER,
    deaths_pre15          INTEGER,
    assists_pre15         INTEGER,
    deaths_pre8           INTEGER,
    first_blood_team      INTEGER,
    first_dragon_team     INTEGER,
    grubs_team            INTEGER,
    herald_team           INTEGER,
    plates_diff           INTEGER,
    -- D. mid/late & objectifs
    dragons_diff          INTEGER,
    soul_team             INTEGER,  -- 1 = mon équipe, 0 = adverse, NULL = pas d'âme
    barons_diff           INTEGER,
    atakhan_team          INTEGER,
    towers_diff           INTEGER,
    deaths_post25         INTEGER,
    kill_participation    REAL,
    damage_share          REAL,
    -- E. vision & économie (comptages seuls : les positions de wards n'existent pas)
    wards_placed          INTEGER,
    wards_killed          INTEGER,
    control_wards_bought  INTEGER,
    -- F. challenges Riot (précalculés par game ; NULL si absents du payload)
    jungle_cs_before_10   REAL,
    counter_jungle_diff   REAL,     -- moreEnemyJungleThanOpponent
    scuttle_crabs         INTEGER,
    initial_crab_secured  INTEGER,
    early_gank_kills      INTEGER,  -- killsOnLanersEarlyJungleAsJungler
    early_jungle_duel_kills INTEGER,
    solo_kills            INTEGER,
    epic_monster_steals   INTEGER,
    vision_advantage_vs_ejgl REAL,
    pings_total           INTEGER,
    on_my_way_pings       INTEGER
);
CREATE INDEX idx_features_win ON features(y_win);
