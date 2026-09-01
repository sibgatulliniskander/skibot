import json

from skibot.collector import ingest

MY_PUUID = "puuid-me"


def make_match():
    return {
        "metadata": {"matchId": "EUW1_1"},
        "info": {
            "queueId": 420,
            "platformId": "EUW1",
            "gameVersion": "15.17.700.1234",
            "gameCreation": 1_756_000_000_000,
            "gameStartTimestamp": 1_756_000_000_500,
            "gameEndTimestamp": 1_756_001_000_500,
            "gameDuration": 1000,
            "participants": [
                {
                    "participantId": 1, "puuid": MY_PUUID,
                    "riotIdGameName": "Me", "riotIdTagline": "EUW",
                    "teamId": 100, "win": True,
                    "championId": 64, "championName": "LeeSin", "teamPosition": "JUNGLE",
                    "kills": 5, "deaths": 2, "assists": 7, "goldEarned": 12000,
                    "totalMinionsKilled": 30, "neutralMinionsKilled": 150,
                    "visionScore": 25, "totalDamageDealtToChampions": 18000,
                },
                {
                    "participantId": 6, "puuid": "puuid-them",
                    "teamId": 200, "win": False,
                    "championId": 121, "championName": "Khazix", "teamPosition": "JUNGLE",
                    "kills": 2, "deaths": 5, "assists": 3, "goldEarned": 9000,
                    "totalMinionsKilled": 20, "neutralMinionsKilled": 140,
                    "visionScore": 18, "totalDamageDealtToChampions": 11000,
                },
            ],
        },
    }


def make_timeline():
    frame1 = {
        "timestamp": 0,
        "participantFrames": {
            "1": {
                "totalGold": 500, "currentGold": 500, "xp": 0, "level": 1,
                "minionsKilled": 0, "jungleMinionsKilled": 0,
                "position": {"x": 100, "y": 200},
                "damageStats": {"totalDamageDoneToChampions": 0, "totalDamageTaken": 0},
            },
        },
        "events": [
            # WARD_PLACED : creatorId, pas de position dans la timeline Riot
            {"timestamp": 1000, "type": "WARD_PLACED", "creatorId": 1,
             "wardType": "YELLOW_TRINKET"},
        ],
    }
    frame2 = {
        "timestamp": 60000,
        "participantFrames": {
            "1": {
                "totalGold": 900, "currentGold": 400, "xp": 400, "level": 2,
                "minionsKilled": 0, "jungleMinionsKilled": 8,
                "position": {"x": 3000, "y": 7000},
                "damageStats": {"totalDamageDoneToChampions": 250, "totalDamageTaken": 300},
            },
        },
        "events": [
            {"timestamp": 61000, "type": "CHAMPION_KILL", "killerId": 1, "victimId": 6,
             "position": {"x": 5000, "y": 5000}, "assistingParticipantIds": [2, 3],
             "bounty": 300, "victimDamageReceived": [{"basic": True}]},
        ],
    }
    return {"metadata": {"matchId": "EUW1_1"}, "info": {"frames": [frame1, frame2]}}


def test_ingest_full(conn):
    ingest.ingest_match(conn, make_match(), make_timeline(), MY_PUUID)

    m = conn.execute("SELECT * FROM matches").fetchone()
    assert m["patch"] == "15.17"
    assert m["has_timeline"] == 1
    assert json.loads(m["raw_match_json"])["metadata"]["matchId"] == "EUW1_1"

    me = conn.execute("SELECT * FROM participants WHERE is_me = 1").fetchone()
    assert me["champion_name"] == "LeeSin"
    assert me["cs_total"] == 180
    assert me["riot_id"] == "Me#EUW"

    from skibot.features import extract as fx
    fx.run(conn, meta_provider=lambda p: None, log=lambda m: None)
    acc = conn.execute("SELECT account FROM features WHERE match_id = 'EUW1_1'").fetchone()
    assert acc["account"] == "Me#EUW"  # le compte est tracé pour la règle n°11

    ward = conn.execute("SELECT * FROM timeline_events WHERE type = 'WARD_PLACED'").fetchone()
    assert ward["participant_id"] == 1  # creatorId promu en participant_id
    assert ward["pos_x"] is None  # la timeline ne donne pas la position des wards

    kill = conn.execute("SELECT * FROM timeline_events WHERE type = 'CHAMPION_KILL'").fetchone()
    assert kill["killer_id"] == 1
    assert kill["victim_id"] == 6
    assert kill["pos_x"] == 5000
    assert json.loads(kill["assisting_ids"]) == [2, 3]
    extra = json.loads(kill["extra_json"])
    assert extra["bounty"] == 300
    assert "victimDamageReceived" not in extra  # volumineux, déjà dans raw_timeline_json

    n_frames = conn.execute("SELECT COUNT(*) AS c FROM timeline_frames").fetchone()["c"]
    assert n_frames == 2
    f2 = conn.execute(
        "SELECT * FROM timeline_frames WHERE frame_index = 1 AND participant_id = 1"
    ).fetchone()
    assert f2["jungle_minions_killed"] == 8
    assert f2["damage_taken"] == 300


def test_match_without_timeline(conn):
    assert not ingest.match_exists(conn, "EUW1_1")
    ingest.ingest_match(conn, make_match(), None, MY_PUUID)
    assert ingest.match_exists(conn, "EUW1_1")
    m = conn.execute("SELECT has_timeline, raw_timeline_json FROM matches").fetchone()
    assert m["has_timeline"] == 0
    assert m["raw_timeline_json"] is None


def test_timeline_with_null_frames(conn):
    # Régression : Riot renvoie parfois null au lieu de {} / [] dans les frames
    timeline = {
        "metadata": {"matchId": "EUW1_1"},
        "info": {"frames": [
            {"timestamp": 0, "participantFrames": None, "events": None},
            {"timestamp": 60000, "participantFrames": {
                "1": {"totalGold": 900, "currentGold": 400, "xp": 400, "level": 2,
                      "minionsKilled": 0, "jungleMinionsKilled": 8}},
             "events": [{"timestamp": 61000, "type": "LEVEL_UP", "participantId": 1}]},
        ]},
    }
    ingest.ingest_match(conn, make_match(), timeline, MY_PUUID)
    assert conn.execute("SELECT COUNT(*) AS c FROM timeline_frames").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) AS c FROM timeline_events").fetchone()["c"] == 1


def test_is_valid_match():
    assert ingest.is_valid_match(make_match())
    # Payload vide renvoyé par Riot sur de rares games
    assert not ingest.is_valid_match({"metadata": {"matchId": "EUW1_X"}, "info": {}})
    assert not ingest.is_valid_match(
        {"metadata": {"matchId": "EUW1_X"},
         "info": {"gameCreation": 0, "gameDuration": 0, "participants": []}}
    )
