PRAGMA foreign_keys = ON;

CREATE TABLE sessions (
    session_id   INTEGER PRIMARY KEY,
    started_at   INTEGER NOT NULL,      -- epoch ms, début de la 1re game
    ended_at     INTEGER NOT NULL,      -- epoch ms, fin de la dernière game
    n_games      INTEGER NOT NULL,
    note         TEXT                   -- annotation manuelle (fatigue, contexte...)
);

CREATE TABLE matches (
    match_id          TEXT PRIMARY KEY,   -- "EUW1_7234567890"
    queue_id          INTEGER NOT NULL,   -- 420 = solo/duo
    platform_id       TEXT NOT NULL,      -- "EUW1"
    game_version      TEXT NOT NULL,      -- version complète Riot
    patch             TEXT NOT NULL,      -- "15.17" (dérivé, pour grouper par patch)
    game_creation     INTEGER NOT NULL,   -- epoch ms
    game_start        INTEGER NOT NULL,   -- epoch ms
    game_end          INTEGER,            -- epoch ms
    game_duration_s   INTEGER NOT NULL,
    session_id        INTEGER REFERENCES sessions(session_id),
    fetched_at        TEXT NOT NULL,      -- ISO 8601 UTC
    has_timeline      INTEGER NOT NULL DEFAULT 0,
    raw_match_json    TEXT NOT NULL,      -- payload Match-V5 complet
    raw_timeline_json TEXT                -- payload timeline complet
);
CREATE INDEX idx_matches_game_start ON matches(game_start);
CREATE INDEX idx_matches_session   ON matches(session_id);

CREATE TABLE participants (
    match_id            TEXT NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    participant_id      INTEGER NOT NULL,   -- 1..10, aligné avec les ids de la timeline
    puuid               TEXT NOT NULL,
    riot_id             TEXT,               -- "gameName#tagLine"
    is_me               INTEGER NOT NULL DEFAULT 0,
    team_id             INTEGER NOT NULL,   -- 100 / 200
    win                 INTEGER NOT NULL,
    champion_id         INTEGER NOT NULL,
    champion_name       TEXT NOT NULL,
    team_position       TEXT,               -- TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY
    kills               INTEGER NOT NULL,
    deaths              INTEGER NOT NULL,
    assists             INTEGER NOT NULL,
    gold_earned         INTEGER NOT NULL,
    cs_total            INTEGER NOT NULL,   -- minions + jungle
    vision_score        INTEGER NOT NULL,
    damage_to_champions INTEGER NOT NULL,
    raw_json            TEXT NOT NULL,      -- participant DTO complet
    PRIMARY KEY (match_id, participant_id)
);
CREATE INDEX idx_participants_puuid ON participants(puuid);
CREATE INDEX idx_participants_champ ON participants(champion_id);

CREATE TABLE timeline_frames (
    match_id              TEXT NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    frame_index           INTEGER NOT NULL,  -- ~1 frame / minute
    participant_id        INTEGER NOT NULL,
    timestamp_ms          INTEGER NOT NULL,
    total_gold            INTEGER NOT NULL,
    current_gold          INTEGER NOT NULL,
    xp                    INTEGER NOT NULL,
    level                 INTEGER NOT NULL,
    minions_killed        INTEGER NOT NULL,
    jungle_minions_killed INTEGER NOT NULL,
    pos_x                 INTEGER,
    pos_y                 INTEGER,
    damage_to_champions   INTEGER,
    damage_taken          INTEGER,
    PRIMARY KEY (match_id, frame_index, participant_id)
);

CREATE TABLE timeline_events (
    event_id         INTEGER PRIMARY KEY,
    match_id         TEXT NOT NULL REFERENCES matches(match_id) ON DELETE CASCADE,
    timestamp_ms     INTEGER NOT NULL,
    type             TEXT NOT NULL,       -- CHAMPION_KILL, WARD_PLACED, ELITE_MONSTER_KILL...
    participant_id   INTEGER,             -- acteur (participantId ou creatorId selon le type)
    killer_id        INTEGER,
    victim_id        INTEGER,
    assisting_ids    TEXT,                -- JSON array
    pos_x            INTEGER,             -- NULL si l'event n'a pas de position (ex: WARD_PLACED)
    pos_y            INTEGER,
    monster_type     TEXT,
    monster_sub_type TEXT,
    building_type    TEXT,
    tower_type       TEXT,
    lane_type        TEXT,
    ward_type        TEXT,
    item_id          INTEGER,
    skill_slot       INTEGER,
    extra_json       TEXT                 -- champs non promus en colonne
);
CREATE INDEX idx_events_match_type ON timeline_events(match_id, type);
CREATE INDEX idx_events_match_ts   ON timeline_events(match_id, timestamp_ms);

CREATE TABLE rank_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    taken_at    TEXT NOT NULL,           -- ISO 8601 UTC, une ligne par collecte
    queue_type  TEXT NOT NULL,           -- RANKED_SOLO_5x5
    tier        TEXT NOT NULL,
    division    TEXT NOT NULL,
    lp          INTEGER NOT NULL,
    wins        INTEGER NOT NULL,
    losses      INTEGER NOT NULL
);
