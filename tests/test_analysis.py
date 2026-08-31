from skibot.analysis import run, split, stats

T0 = 1_756_000_000_000
HOUR = 3_600_000


def add_game(conn, i, session_id, win, deaths_pre15=None):
    start = T0 + i * HOUR
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, started_at, ended_at, n_games) "
        "VALUES (?, ?, ?, 0)",
        (session_id, start, start + 1800_000),
    )
    conn.execute(
        "INSERT INTO matches (match_id, queue_id, platform_id, game_version, patch,"
        " game_creation, game_start, game_end, game_duration_s, session_id, fetched_at,"
        " has_timeline, raw_match_json) VALUES (?, 420, 'EUW1', 'v', '15.17', ?, ?, ?,"
        " 1800, ?, 'now', 1, '{}')",
        (f"M{i}", start, start, start + 1800_000, session_id),
    )
    conn.execute(
        "INSERT INTO features (match_id, computed_at, extractor_version, y_win,"
        " is_remake, deaths_pre15) VALUES (?, 'now', 1, ?, 0, ?)",
        (f"M{i}", int(win), deaths_pre15),
    )


def make_dataset(conn, n=64, per_session=8):
    # wins/losses alternées ; signal fort : deaths_pre15 = 1 si win, 5 si loss
    for i in range(n):
        win = i % 2 == 0
        add_game(conn, i, session_id=1 + i // per_session, win=win,
                 deaths_pre15=1 if win else 5)


def test_split_is_by_session_and_frozen(conn):
    make_dataset(conn)
    info = split.ensure_split(conn)
    assert not info["frozen"]
    assert info["explore"] + info["confirm"] == 64
    assert abs(info["explore"] - 38) <= 8  # ~60 %, granularité session

    # toutes les games d'une session sont du même côté
    rows = conn.execute(
        """SELECT m.session_id, COUNT(DISTINCT s.split) k
           FROM analysis_split s JOIN matches m USING (match_id)
           GROUP BY m.session_id"""
    ).fetchall()
    assert all(r["k"] == 1 for r in rows)

    # deuxième appel : figé, aucune réassignation
    info2 = split.ensure_split(conn, seed=999)
    assert info2["frozen"]
    assert info2["explore"] == info["explore"]


def test_benjamini_hochberg():
    assert stats.benjamini_hochberg([0.01, 0.02, 0.03, 0.04]) == [0.04, 0.04, 0.04, 0.04]
    q = stats.benjamini_hochberg([0.001, 0.5, 0.04])
    assert q[0] == 0.003
    assert q[2] == 0.06
    assert q[1] == 0.5


def test_continuous_detects_signal(conn):
    import pandas as pd
    df = pd.DataFrame({
        "deaths_pre15": [1] * 20 + [5] * 20,
        "y_win": [1] * 20 + [0] * 20,
    })
    spec = next(s for s in stats.FEATURES if s.name == "deaths_pre15")
    r = stats.test_feature(df, spec)
    assert r["p"] < 0.001
    assert r["direction"] == -1  # plus de morts chez les losses
    assert r["effect_abs"] == 1.0  # séparation parfaite


def test_insufficient_n_returns_none():
    import pandas as pd
    df = pd.DataFrame({"deaths_pre15": [1, 2, 3], "y_win": [1, 0, 1]})
    spec = next(s for s in stats.FEATURES if s.name == "deaths_pre15")
    assert stats.test_feature(df, spec) is None


def test_end_to_end_confirms_signal(conn, tmp_path):
    make_dataset(conn)
    s = run.analyze(conn, out_dir=tmp_path, log=lambda m: None)
    assert s["tested"] == 1  # seule deaths_pre15 est renseignée
    assert s["retained"] == 1
    assert s["confirmed"] == 1
    r = s["results"][0]
    assert r["feature"] == "deaths_pre15"
    assert r["verdict"] == "confirmé"
    content = s["report"].read_text(encoding="utf-8")
    assert "Effets CONFIRMÉS (1)" in content
    assert "deaths_pre15" in content
