
from skibot.collector import ingest, sessions
from skibot.features import extract

MY_PUUID = "puuid-me"
HOUR = 3_600_000  # ms
T0 = 1_756_000_000_000  # 2025-08-24, timestamp moderne (Windows refuse ~1970)

# champion_id -> meta Data Dragon factice
FAKE_META = {
    64: {"tags": ["Fighter"], "ranged": False, "ap_ratio": 0.3},    # LeeSin (moi)
    103: {"tags": ["Mage"], "ranged": True, "ap_ratio": 0.9},       # Ahri (allié)
    121: {"tags": ["Assassin"], "ranged": False, "ap_ratio": 0.2},  # Khazix (ejgl)
    54: {"tags": ["Tank"], "ranged": False, "ap_ratio": 0.5},       # Malphite (ennemi)
}


def participant(pid, puuid, team, win, champ_id, champ_name, position, **extra):
    base = {
        "participantId": pid, "puuid": puuid, "teamId": team, "win": win,
        "championId": champ_id, "championName": champ_name, "teamPosition": position,
        "kills": 0, "deaths": 0, "assists": 0, "goldEarned": 10000,
        "totalMinionsKilled": 50, "neutralMinionsKilled": 100,
        "visionScore": 20, "totalDamageDealtToChampions": 10000,
    }
    base.update(extra)
    return base


def make_match(match_id="EUW1_1", start_ms=T0, win=True, duration_s=1800, my_extra=None):
    me = participant(
        1, MY_PUUID, 100, win, 64, "LeeSin", "JUNGLE",
        kills=5, assists=3, totalDamageDealtToChampions=18000,
        onMyWayPings=3, dangerPings=2,
        gameEndedInEarlySurrender=False, gameEndedInSurrender=True,
        challenges={
            "jungleCsBefore10Minutes": 55.5,
            "moreEnemyJungleThanOpponent": -10.5,
            "scuttleCrabKills": 2,
            "initialCrabCount": 1,
            "killsOnLanersEarlyJungleAsJungler": 1,
            "junglerKillsEarlyJungle": 0,
            "soloKills": 1,
            "epicMonsterSteals": 0,
            "visionScoreAdvantageLaneOpponent": 0.25,
        },
    )
    if my_extra:
        me.update(my_extra)
    return {
        "metadata": {"matchId": match_id},
        "info": {
            "queueId": 420, "platformId": "EUW1", "gameVersion": "15.17.700.1234",
            "gameCreation": start_ms, "gameStartTimestamp": start_ms,
            "gameEndTimestamp": start_ms + duration_s * 1000, "gameDuration": duration_s,
            "participants": [
                me,
                participant(2, "p-ally", 100, win, 103, "Ahri", "MIDDLE",
                            kills=5, totalDamageDealtToChampions=12000),
                participant(6, "p-ejgl", 200, not win, 121, "Khazix", "JUNGLE"),
                participant(7, "p-enemy", 200, not win, 54, "Malphite", "TOP"),
            ],
        },
    }


def gold(pid, idx):
    rate = {1: 400, 6: 300}.get(pid, 350)
    return 1000 + idx * rate


def make_timeline(match_id="EUW1_1"):
    frames = []
    for idx in range(16):
        pf = {}
        for pid in (1, 2, 6, 7):
            pf[str(pid)] = {
                "totalGold": gold(pid, idx), "currentGold": 100,
                "xp": idx * (500 if pid == 1 else 450), "level": min(1 + idx, 18),
                "minionsKilled": 0 if pid in (1, 6) else idx * 6,
                "jungleMinionsKilled": idx * (4 if pid == 1 else 3) if pid in (1, 6) else 0,
                "position": {"x": 100, "y": 100},
                "damageStats": {"totalDamageDoneToChampions": 0, "totalDamageTaken": 0},
            }
        frames.append({"timestamp": idx * 60000, "participantFrames": pf, "events": []})
    m = 60000
    frames[15]["events"] = [
        {"timestamp": 3 * m, "type": "CHAMPION_SPECIAL_KILL", "killType": "KILL_FIRST_BLOOD",
         "killerId": 6},
        {"timestamp": 6 * m, "type": "CHAMPION_KILL", "killerId": 1, "victimId": 6,
         "position": {"x": 1, "y": 1}},
        {"timestamp": 7 * m, "type": "CHAMPION_KILL", "killerId": 6, "victimId": 1,
         "position": {"x": 1, "y": 1}},
        {"timestamp": 12 * m, "type": "CHAMPION_KILL", "killerId": 2, "victimId": 7,
         "assistingParticipantIds": [1], "position": {"x": 1, "y": 1}},
        {"timestamp": 26 * m, "type": "CHAMPION_KILL", "killerId": 7, "victimId": 2,
         "position": {"x": 1, "y": 1}},
        {"timestamp": 8 * m, "type": "ELITE_MONSTER_KILL", "killerId": 1,
         "monsterType": "DRAGON", "monsterSubType": "FIRE_DRAGON", "killerTeamId": 100},
        {"timestamp": 14 * m, "type": "ELITE_MONSTER_KILL", "killerId": 6,
         "monsterType": "DRAGON", "monsterSubType": "AIR_DRAGON", "killerTeamId": 200},
        {"timestamp": 9 * m, "type": "ELITE_MONSTER_KILL", "killerId": 1,
         "monsterType": "HORDE", "killerTeamId": 100},
        {"timestamp": 10 * m, "type": "ELITE_MONSTER_KILL", "killerId": 1,
         "monsterType": "HORDE", "killerTeamId": 100},
        {"timestamp": 16 * m, "type": "ELITE_MONSTER_KILL", "killerId": 6,
         "monsterType": "RIFTHERALD", "killerTeamId": 200},
        {"timestamp": 25 * m, "type": "ELITE_MONSTER_KILL", "killerId": 1,
         "monsterType": "BARON_NASHOR", "killerTeamId": 100},
        {"timestamp": 27 * m, "type": "ELITE_MONSTER_KILL", "killerId": 1,
         "monsterType": "ATAKHAN", "killerTeamId": 100},
        # annonce du type d'âme (teamId 0) AVANT l'attribution réelle : à ignorer
        {"timestamp": 20 * m, "type": "DRAGON_SOUL_GIVEN", "teamId": 0, "name": "Air"},
        {"timestamp": 28 * m, "type": "DRAGON_SOUL_GIVEN", "teamId": 200, "name": "Air"},
        {"timestamp": 18 * m, "type": "BUILDING_KILL", "killerId": 1, "teamId": 200,
         "buildingType": "TOWER_BUILDING", "towerType": "OUTER_TURRET", "laneType": "MID_LANE"},
        {"timestamp": 19 * m, "type": "BUILDING_KILL", "killerId": 2, "teamId": 200,
         "buildingType": "TOWER_BUILDING", "towerType": "INNER_TURRET", "laneType": "MID_LANE"},
        {"timestamp": 20 * m, "type": "BUILDING_KILL", "killerId": 6, "teamId": 100,
         "buildingType": "TOWER_BUILDING", "towerType": "OUTER_TURRET", "laneType": "TOP_LANE"},
        {"timestamp": 11 * m, "type": "TURRET_PLATE_DESTROYED", "killerId": 2, "teamId": 200,
         "laneType": "MID_LANE"},
        {"timestamp": 11 * m, "type": "TURRET_PLATE_DESTROYED", "killerId": 2, "teamId": 200,
         "laneType": "MID_LANE"},
        {"timestamp": 11 * m, "type": "TURRET_PLATE_DESTROYED", "killerId": 2, "teamId": 200,
         "laneType": "MID_LANE"},
        {"timestamp": 12 * m, "type": "TURRET_PLATE_DESTROYED", "killerId": 7, "teamId": 100,
         "laneType": "TOP_LANE"},
        {"timestamp": 2 * m, "type": "WARD_PLACED", "creatorId": 1, "wardType": "YELLOW_TRINKET"},
        {"timestamp": 21 * m, "type": "WARD_PLACED", "creatorId": 1, "wardType": "CONTROL_WARD"},
        {"timestamp": 22 * m, "type": "WARD_PLACED", "creatorId": 6, "wardType": "YELLOW_TRINKET"},
        {"timestamp": 23 * m, "type": "WARD_KILL", "killerId": 1, "wardType": "YELLOW_TRINKET"},
        {"timestamp": 20 * m, "type": "ITEM_PURCHASED", "participantId": 1, "itemId": 2055},
        {"timestamp": 20 * m, "type": "ITEM_PURCHASED", "participantId": 1, "itemId": 1001},
    ]
    return {"metadata": {"matchId": match_id}, "info": {"frames": frames}}


def setup_two_games(conn):
    """Game 1 (win, timeline complète) puis game 2 (loss, sans timeline) 2 h plus tard."""
    ingest.ingest_match(conn, make_match(), make_timeline(), MY_PUUID)
    ingest.ingest_match(
        conn, make_match(match_id="EUW1_2", start_ms=T0 + 2 * HOUR, win=False), None, MY_PUUID
    )
    sessions.rebuild_sessions(conn, 60)
    return extract.run(conn, meta_provider=lambda patch: FAKE_META, log=lambda s: None)


def row(conn, match_id):
    return conn.execute("SELECT * FROM features WHERE match_id = ?", (match_id,)).fetchone()


def test_targets_and_flags(conn):
    s = setup_two_games(conn)
    assert s["extracted"] == 2
    f = row(conn, "EUW1_1")
    assert f["y_win"] == 1
    # gold@15 : moi 7000, allié 6250 vs ejgl 5500, ennemi 6250
    assert f["y2_team_gold_diff_15"] == (7000 + 6250) - (5500 + 6250)
    assert f["is_remake"] == 0
    assert f["ended_in_surrender"] == 1


def test_early_game_diffs(conn):
    setup_two_games(conn)
    f = row(conn, "EUW1_1")
    assert f["gold_diff_ejgl_10"] == (1000 + 4000) - (1000 + 3000)
    assert f["gold_diff_ejgl_15"] == 6000 - 4500 - 0  # 400*15 - 300*15
    assert f["xp_diff_ejgl_10"] == 10 * 50
    assert f["cs_diff_ejgl_10"] == 10 * (4 - 3)
    assert f["kills_pre15"] == 1
    assert f["deaths_pre15"] == 1
    assert f["deaths_pre8"] == 1
    assert f["assists_pre15"] == 1
    assert f["deaths_post25"] == 0


def test_objectives(conn):
    setup_two_games(conn)
    f = row(conn, "EUW1_1")
    assert f["first_blood_team"] == 0     # FB par le pid 6 (ennemi)
    assert f["first_dragon_team"] == 1
    assert f["dragons_diff"] == 0         # 1 - 1
    assert f["grubs_team"] == 2
    assert f["herald_team"] == 0
    assert f["barons_diff"] == 1
    assert f["atakhan_team"] == 1
    assert f["soul_team"] == 0            # âme donnée à la team 200
    assert f["towers_diff"] == 1          # 2 prises - 1 perdue
    assert f["plates_diff"] == 2          # 3 - 1


def test_vision_and_shares(conn):
    setup_two_games(conn)
    f = row(conn, "EUW1_1")
    assert f["wards_placed"] == 2
    assert f["wards_killed"] == 1
    assert f["control_wards_bought"] == 1
    assert f["kill_participation"] == (5 + 3) / 10
    assert f["damage_share"] == 18000 / 30000


def test_challenges_and_pings(conn):
    setup_two_games(conn)
    f = row(conn, "EUW1_1")
    assert f["jungle_cs_before_10"] == 55.5
    assert f["counter_jungle_diff"] == -10.5
    assert f["scuttle_crabs"] == 2
    assert f["early_gank_kills"] == 1
    assert f["vision_advantage_vs_ejgl"] == 0.25
    assert f["pings_total"] == 5
    assert f["on_my_way_pings"] == 3


def test_draft_and_compo(conn):
    setup_two_games(conn)
    f = row(conn, "EUW1_1")
    assert f["my_champion"] == "LeeSin"
    assert f["enemy_jungler_champion"] == "Khazix"
    assert f["side"] == "blue"
    assert f["i_am_autofilled"] == 0
    assert f["ally_tank_count"] == 0
    assert f["enemy_tank_count"] == 1
    assert f["ally_ranged_count"] == 1
    assert f["ally_ap_ratio"] == (0.3 + 0.9) / 2


def test_session_context(conn):
    setup_two_games(conn)
    f1, f2 = row(conn, "EUW1_1"), row(conn, "EUW1_2")
    assert f1["session_game_index"] == 1
    assert f1["prev_game_result"] is None
    assert f1["current_streak"] == 0
    assert f1["my_champ_recent_games"] == 0
    # game 2 : 2 h après la fin de la game 1 -> nouvelle session
    assert f2["session_game_index"] == 1
    assert f2["games_played_today"] == 1
    assert f2["prev_game_result"] == "W"
    assert f2["current_streak"] == 1
    assert f2["minutes_since_prev_game"] == 90.0
    assert f2["my_champ_recent_games"] == 1
    assert f2["my_champ_recent_wr"] == 100.0


def test_no_timeline_gives_nulls_not_zeros(conn):
    setup_two_games(conn)
    f2 = row(conn, "EUW1_2")
    assert f2["gold_diff_ejgl_10"] is None
    assert f2["y2_team_gold_diff_15"] is None
    assert f2["wards_placed"] is None
    assert f2["kill_participation"] is not None  # dispo depuis le DTO même sans timeline


def test_incremental_and_rebuild(conn):
    setup_two_games(conn)
    s = extract.run(conn, meta_provider=lambda p: FAKE_META, log=lambda s: None)
    assert s["extracted"] == 0  # rien à refaire
    s = extract.run(conn, rebuild=True, meta_provider=lambda p: FAKE_META, log=lambda s: None)
    assert s["extracted"] == 2


def test_remake_flag(conn):
    ingest.ingest_match(
        conn,
        make_match(match_id="EUW1_3", start_ms=T0, duration_s=180,
                   my_extra={"gameEndedInEarlySurrender": True}),
        None, MY_PUUID,
    )
    sessions.rebuild_sessions(conn, 60)
    extract.run(conn, meta_provider=lambda p: FAKE_META, log=lambda s: None)
    assert row(conn, "EUW1_3")["is_remake"] == 1
