-- Échantillon de junglers Diamant+ (benchmark). Une ligne par jungler et par game.
-- Payload match uniquement (pas de timeline) ; jamais mélangé aux données du joueur.
CREATE TABLE bench_games (
    match_id          TEXT NOT NULL,
    participant_id    INTEGER NOT NULL,
    puuid             TEXT NOT NULL,
    tier              TEXT NOT NULL,      -- tier du joueur échantillonné au moment du crawl
    champion_id       INTEGER NOT NULL,
    champion_name     TEXT NOT NULL,
    patch             TEXT NOT NULL,
    game_start        INTEGER NOT NULL,   -- epoch ms
    game_duration_s   INTEGER NOT NULL,
    win               INTEGER NOT NULL,
    -- métriques comparables aux features (mêmes compteurs Riot)
    jungle_cs_before_10      REAL,
    counter_jungle_diff      REAL,
    scuttle_crabs            INTEGER,
    initial_crab_secured     INTEGER,
    early_gank_kills         INTEGER,
    early_jungle_duel_kills  INTEGER,
    solo_kills               INTEGER,
    epic_monster_steals      INTEGER,
    vision_advantage_vs_ejgl REAL,
    kill_participation       REAL,
    damage_share             REAL,
    pings_total              INTEGER,
    on_my_way_pings          INTEGER,
    -- extras stockés pour le build advisor (étage 2)
    kills INTEGER, deaths INTEGER, assists INTEGER,
    wards_placed INTEGER, wards_killed INTEGER, control_wards_bought INTEGER,
    ally_ap_ratio REAL, enemy_ap_ratio REAL, enemy_tank_count INTEGER,
    item0 INTEGER, item1 INTEGER, item2 INTEGER,
    item3 INTEGER, item4 INTEGER, item5 INTEGER,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (match_id, participant_id)
);
CREATE INDEX idx_bench_champion ON bench_games(champion_name);
CREATE INDEX idx_bench_patch ON bench_games(patch);
