import json
from types import SimpleNamespace

import pytest

from skibot.auditor import audit, dossier

T0 = 1_756_000_000_000


def insert_game(conn, match_id="EUW1_1", win=True):
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, started_at, ended_at, n_games)"
        " VALUES (1, ?, ?, 1)",
        (T0, T0 + 1800_000),
    )
    conn.execute(
        "INSERT INTO matches (match_id, queue_id, platform_id, game_version, patch,"
        " game_creation, game_start, game_end, game_duration_s, session_id, fetched_at,"
        " has_timeline, raw_match_json) VALUES (?, 420, 'EUW1', 'v', '16.9', ?, ?, ?, 1920,"
        " 1, 'now', 1, '{}')",
        (match_id, T0, T0, T0 + 1920_000),
    )
    conn.execute(
        "INSERT INTO participants (match_id, participant_id, puuid, is_me, team_id, win,"
        " champion_id, champion_name, team_position, kills, deaths, assists, gold_earned,"
        " cs_total, vision_score, damage_to_champions, raw_json)"
        " VALUES (?, 1, 'me', 1, 100, ?, 64, 'Viego', 'JUNGLE', 5, 3, 7, 12000, 180, 25,"
        " 18000, '{}')",
        (match_id, int(win)),
    )
    # deux morts : minute 7 et minute 27
    for ts in (7 * 60_000, 27 * 60_000):
        conn.execute(
            "INSERT INTO timeline_events (match_id, timestamp_ms, type, killer_id,"
            " victim_id) VALUES (?, ?, 'CHAMPION_KILL', 6, 1)",
            (match_id, ts),
        )
    conn.execute(
        "INSERT INTO features (match_id, computed_at, extractor_version, y_win, is_remake,"
        " my_champion, enemy_jungler_champion, side, session_game_index, deaths_pre15,"
        " deaths_post25, kills_pre15, assists_pre15, scuttle_crabs, counter_jungle_diff,"
        " gold_diff_ejgl_10, on_my_way_pings, pings_total, wards_placed, wards_killed,"
        " kill_participation, i_am_autofilled, ended_in_surrender)"
        " VALUES (?, 'now', 1, ?, 0, 'Viego', 'Khazix', 'blue', 1, 1, 1, 2, 1, 4, -12.0,"
        " 350, 6, 40, 3, 1, 0.5, 0, 0)",
        (match_id, int(win)),
    )


def make_verdict(fact_ids):
    return {
        "resume": "Game serrée décidée en fin de partie.",
        "faits_marquants": [
            {"texte": "Avance d'or sur le jungler adverse à 10 min.", "fact_ids": [fact_ids[0]]},
            {"texte": "Quatre scuttles prises.", "fact_ids": [fact_ids[1]]},
        ],
        "point_a_revoir": {"texte": "Une mort après 25 min.", "fact_ids": [fact_ids[2]]},
        "tags": ["late_deaths"],
        "question_replay": "Que s'est-il passé à la minute 27 ?",
        "suivi_consigne": None,
        "limites": "Les positions de wards et les invades ne sont pas mesurés.",
    }


class FakeClient:
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=self._payloads.pop(0))],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
        )


def test_dossier_facts_have_ids_and_provenance(conn):
    insert_game(conn)
    d = dossier.build(conn, "EUW1_1")
    ids = [f["id"] for f in d["facts"]]
    assert len(ids) == len(set(ids))
    assert all(f["prov"] for f in d["facts"])
    assert d["header"]["result"] == "VICTOIRE"
    text = dossier.render(d)
    assert "DOSSIER DE FAITS" in text
    assert "None" not in text
    # les morts portent leurs minutes, prouvées par la timeline
    assert "aux minutes 7" in text
    assert "aux minutes 27" in text


def test_dossier_requires_features(conn):
    with pytest.raises(ValueError):
        dossier.build(conn, "INCONNUE")


def test_verify_citations():
    valid = {"F1", "F2", "F3"}
    ok = make_verdict(["F1", "F2", "F3"])
    assert audit.verify_citations(ok, valid) == []
    bad = make_verdict(["F1", "F99", "F3"])
    assert any("F99" in p for p in audit.verify_citations(bad, valid))
    no_cite = make_verdict(["F1", "F2", "F3"])
    no_cite["point_a_revoir"]["fact_ids"] = []
    assert any("sans citation" in p for p in audit.verify_citations(no_cite, valid))


def test_audit_persists_conform_verdict(conn):
    insert_game(conn)
    d = dossier.build(conn, "EUW1_1")
    ids = [f["id"] for f in d["facts"]]
    client = FakeClient([json.dumps(make_verdict(ids[:3]))])
    res = audit.audit_match(conn, "EUW1_1", client=client, log=lambda m: None)
    row = conn.execute("SELECT * FROM audits WHERE match_id = 'EUW1_1'").fetchone()
    assert row is not None
    assert row["model"] == audit.MODEL
    assert row["cost_usd"] > 0
    assert "Faits cités" in res["markdown"]
    # le système impose le dossier comme seul contenu utilisateur
    assert "DOSSIER DE FAITS" in client.calls[0]["messages"][0]["content"]


def test_audit_retries_then_fails_on_bad_citations(conn):
    insert_game(conn)
    bad = json.dumps(make_verdict(["F997", "F998", "F999"]))
    client = FakeClient([bad, bad])
    with pytest.raises(audit.AuditError):
        audit.audit_match(conn, "EUW1_1", client=client, log=lambda m: None)
    assert len(client.calls) == 2  # une regénération a bien été tentée
    assert conn.execute("SELECT COUNT(*) c FROM audits").fetchone()["c"] == 0


def test_run_skips_already_audited(conn):
    insert_game(conn)
    d = dossier.build(conn, "EUW1_1")
    ids = [f["id"] for f in d["facts"]]
    client = FakeClient([json.dumps(make_verdict(ids[:3]))])
    s = audit.run(conn, client=client, log=lambda m: None)
    assert s["audited"] == 1
    s2 = audit.run(conn, client=FakeClient([]), log=lambda m: None)
    assert s2["audited"] == 0


def test_free_text_citations_are_verified():
    valid = {"F1", "F2", "F3"}
    v = make_verdict(["F1", "F2", "F3"])
    v["resume"] = "Game marquée par un early déficitaire (F1, F42)."
    problems = audit.verify_citations(v, valid)
    assert any("F42" in p for p in problems)
    v["resume"] = "Game marquée par un early déficitaire (F1, F2)."
    assert audit.verify_citations(v, valid) == []


def test_verifier_rejects_prescriptive_language():
    valid = {"F1", "F2", "F3"}
    v = make_verdict(["F1", "F2", "F3"])
    v["question_replay"] = "Il faudrait ganker plus tôt, non ?"
    assert any("prescriptive" in p for p in audit.verify_citations(v, valid))


def test_verifier_rejects_bad_tags():
    valid = {"F1", "F2", "F3"}
    v = make_verdict(["F1", "F2", "F3"])
    v["tags"] = ["tag_invente"]
    assert any("taxonomie" in p for p in audit.verify_citations(v, valid))
    v["tags"] = []
    assert any("nombre de tags" in p for p in audit.verify_citations(v, valid))


def test_dossier_baselines_and_consigne(conn):
    # 40 games pour dépasser MIN_BASELINE_N, puis un dossier avec repères + consigne
    for i in range(40):
        insert_game(conn, match_id=f"EUW1_B{i}", win=i % 2 == 0)
    baselines = dossier.compute_baselines(conn)
    assert "scuttle_crabs" in baselines
    consigne = {"numero": 1, "comportement": "test", "metric": "on_my_way_pings",
                "operator": ">=", "target": 8}
    d = dossier.build(conn, "EUW1_B0", baselines=baselines, consigne=consigne)
    text = dossier.render(d)
    assert "repère perso" in text
    assert "percentile" in text
    assert "CONSIGNE ACTIVE n°1" in text
    assert "objectif >= 8" in text
