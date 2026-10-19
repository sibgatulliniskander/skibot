from skibot.collector import ingest, sessions
from skibot.collector.collect import sync_account_name
from skibot.features import extract
from tests.test_features import FAKE_META, HOUR, MY_PUUID, T0, make_match


def riot_id(name, tag):
    return {"riotIdGameName": name, "riotIdTagline": tag}


def features_accounts(conn):
    return {r["match_id"]: r["account"] for r in conn.execute("SELECT match_id, account FROM features")}


def test_rename_reattaches_history(conn):
    ingest.ingest_match(conn, make_match(my_extra=riot_id("oldname", "666")), None, MY_PUUID)
    sessions.rebuild_sessions(conn, 60)
    extract.run(conn, meta_provider=lambda p: FAKE_META, log=lambda s: None)
    conn.execute(
        "INSERT INTO rank_snapshots (taken_at, queue_type, tier, division, lp, wins, losses, riot_id)"
        " VALUES ('2026-09-01', 'RANKED_SOLO_5x5', 'EMERALD', 'IV', 10, 1, 0, 'oldname#666')"
    )

    assert sync_account_name(conn, MY_PUUID, "Isko#6677") == ["oldname#666"]
    assert features_accounts(conn) == {"EUW1_1": "Isko#6677"}
    assert conn.execute("SELECT riot_id FROM rank_snapshots").fetchone()["riot_id"] == "Isko#6677"
    # idempotent : rien de nouveau au run suivant
    assert sync_account_name(conn, MY_PUUID, "Isko#6677") == []

    # une game sous le nouveau nom, puis rebuild : l'ancienne reste rattachée
    ingest.ingest_match(
        conn, make_match(match_id="EUW1_2", start_ms=T0 + 2 * HOUR,
                         my_extra=riot_id("Isko", "6677")), None, MY_PUUID)
    sessions.rebuild_sessions(conn, 60)
    extract.run(conn, rebuild=True, meta_provider=lambda p: FAKE_META, log=lambda s: None)
    assert features_accounts(conn) == {"EUW1_1": "Isko#6677", "EUW1_2": "Isko#6677"}


def test_chained_rename(conn):
    ingest.ingest_match(conn, make_match(my_extra=riot_id("a", "1")), None, MY_PUUID)
    sync_account_name(conn, MY_PUUID, "b#2")
    sync_account_name(conn, MY_PUUID, "c#3")
    aliases = dict(conn.execute("SELECT alias, canonical FROM account_aliases").fetchall())
    assert aliases == {"a#1": "c#3", "b#2": "c#3", "c#3": "c#3"}
