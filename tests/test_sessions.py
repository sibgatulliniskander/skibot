from skibot.collector import sessions

HOUR = 3_600_000  # ms


def insert_match(conn, match_id, start_ms, duration_s=1800):
    conn.execute(
        "INSERT INTO matches (match_id, queue_id, platform_id, game_version, patch,"
        " game_creation, game_start, game_end, game_duration_s, fetched_at, has_timeline,"
        " raw_match_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (match_id, 420, "EUW1", "15.17.1", "15.17", start_ms, start_ms,
         start_ms + duration_s * 1000, duration_s, "2026-08-31T00:00:00+00:00", 0, "{}"),
    )


def test_grouping(conn):
    insert_match(conn, "M1", 0)          # finit à 0:30
    insert_match(conn, "M2", HOUR)       # écart 30 min -> même session
    insert_match(conn, "M3", 4 * HOUR)   # écart 2h30 -> nouvelle session
    n = sessions.rebuild_sessions(conn, 60)
    assert n == 2
    sid = {
        r["match_id"]: r["session_id"]
        for r in conn.execute("SELECT match_id, session_id FROM matches")
    }
    assert sid["M1"] == sid["M2"]
    assert sid["M2"] != sid["M3"]
    s = conn.execute("SELECT * FROM sessions ORDER BY started_at").fetchall()
    assert s[0]["n_games"] == 2
    assert s[1]["n_games"] == 1


def test_rebuild_is_deterministic_and_preserves_notes(conn):
    insert_match(conn, "M1", 0)
    sessions.rebuild_sessions(conn, 60)
    conn.execute("UPDATE sessions SET note = 'fatigué'")
    insert_match(conn, "M2", 10 * HOUR)
    sessions.rebuild_sessions(conn, 60)
    notes = [r["note"] for r in conn.execute("SELECT note FROM sessions ORDER BY started_at")]
    assert notes == ["fatigué", None]
