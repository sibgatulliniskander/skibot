import sqlite3

import pytest

from skibot import db
from skibot.dashboard import queries
from skibot.dashboard.app import create_app

T0 = 1_756_000_000_000
HOUR = 3_600_000


def test_lp_absolute():
    assert queries.lp_absolute("IRON", "IV", 0) == 0
    assert queries.lp_absolute("PLATINUM", "III", 49) == 4 * 400 + 100 + 49
    assert queries.lp_absolute("EMERALD", "I", 0) == 5 * 400 + 300
    assert queries.lp_absolute("MASTER", "I", 120) == 7 * 400 + 120


@pytest.fixture
def app(tmp_path):
    path = tmp_path / "dash.db"
    conn = db.connect(path)
    with conn:
        conn.execute(
            "INSERT INTO rank_snapshots (taken_at, queue_type, tier, division, lp, wins,"
            " losses) VALUES ('2026-08-31T10:00:00+00:00', 'RANKED_SOLO_5x5', 'PLATINUM',"
            " 'III', 49, 100, 98)"
        )
        conn.execute(
            "INSERT INTO sessions (session_id, started_at, ended_at, n_games)"
            " VALUES (1, ?, ?, 1)", (T0, T0 + HOUR)
        )
        conn.execute(
            "INSERT INTO matches (match_id, queue_id, platform_id, game_version, patch,"
            " game_creation, game_start, game_end, game_duration_s, session_id, fetched_at,"
            " has_timeline, raw_match_json) VALUES ('M1', 420, 'EUW1', 'v', '16.9', ?, ?, ?,"
            " 1800, 1, 'now', 1, '{}')", (T0, T0, T0 + 1800_000)
        )
        conn.execute(
            "INSERT INTO features (match_id, computed_at, extractor_version, y_win,"
            " is_remake, my_champion, on_my_way_pings, session_game_index)"
            " VALUES ('M1', 'now', 1, 1, 0, 'Viego', 7, 1)"
        )
    conn.close()
    return create_app(db_path=path)


def test_public_page(app):
    r = app.test_client().get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Platinum III — 49 LP" in html
    assert "Consigne active" in html


def test_internal_page(app):
    r = app.test_client().get("/interne")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Viego" in html
    assert "on_my_way_pings" in html


def test_summary_counts(app):
    conn = sqlite3.connect(app.config["DB_PATH"])
    conn.row_factory = sqlite3.Row
    s = queries.summary(conn)
    assert s["games_total"] == 1
    assert s["prospective"] == 1  # M1 n'est dans aucun split
    conn.close()
