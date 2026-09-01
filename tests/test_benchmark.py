from skibot.benchmark import collect as bench


def make_bench_match(match_id="EUW1_B1", duration=1800):
    def p(pid, team, position, champ_id, champ_name, win, kills=4):
        return {
            "participantId": pid, "puuid": f"p{pid}", "teamId": team,
            "teamPosition": position, "championId": champ_id, "championName": champ_name,
            "win": win, "kills": kills, "deaths": 3, "assists": 5,
            "totalDamageDealtToChampions": 10000, "wardsPlaced": 8, "wardsKilled": 3,
            "visionWardsBoughtInGame": 2, "onMyWayPings": 6, "dangerPings": 1,
            "item0": 6672, "item1": 3111, "item2": 6333, "item3": 0, "item4": 0, "item5": 0,
            "gameEndedInEarlySurrender": False,
            "challenges": {
                "jungleCsBefore10Minutes": 72.0, "moreEnemyJungleThanOpponent": 8.0,
                "scuttleCrabKills": 5, "initialCrabCount": 1,
                "killsOnLanersEarlyJungleAsJungler": 2, "junglerKillsEarlyJungle": 1,
                "soloKills": 1, "epicMonsterSteals": 0,
                "visionScoreAdvantageLaneOpponent": 0.3,
            },
        }
    parts = [
        p(1, 100, "JUNGLE", 64, "LeeSin", True),
        p(2, 100, "MIDDLE", 103, "Ahri", True),
        p(6, 200, "JUNGLE", 121, "Khazix", False),
        p(7, 200, "TOP", 54, "Malphite", False),
    ]
    return {
        "metadata": {"matchId": match_id},
        "info": {
            "queueId": 420, "gameVersion": "16.9.1.1", "gameCreation": 1_756_000_000_000,
            "gameStartTimestamp": 1_756_000_000_000, "gameDuration": duration,
            "participants": parts,
        },
    }


def test_extract_two_junglers_per_match():
    rows = bench.extract_junglers(make_bench_match(), "DIAMOND", meta_cache={"16.9": None})
    assert len(rows) == 2
    lee = next(r for r in rows if r["champion_name"] == "LeeSin")
    assert lee["jungle_cs_before_10"] == 72.0
    assert lee["scuttle_crabs"] == 5
    assert lee["kill_participation"] == (4 + 5) / 8
    assert lee["pings_total"] == 7
    assert lee["win"] == 1
    assert lee["item0"] == 6672
    # meta ddragon indisponible -> compo a NULL, jamais inventee
    assert lee["ally_ap_ratio"] is None


def test_remakes_excluded():
    assert bench.extract_junglers(make_bench_match(duration=200), "DIAMOND", {"16.9": None}) == []


def test_compare_positions_me_in_bench_distribution(conn):
    from skibot.benchmark import compare as cmp
    # 40 lignes bench (scuttles autour de 5) + 40 games a moi (scuttles autour de 3)
    for i in range(40):
        conn.execute(
            "INSERT INTO bench_games (match_id, participant_id, puuid, tier, champion_id,"
            " champion_name, patch, game_start, game_duration_s, win, scuttle_crabs,"
            " fetched_at) VALUES (?, 1, 'p', 'DIAMOND', 64, 'LeeSin', '16.9', ?, 1800, 1,"
            " ?, 'now')",
            (f"B{i}", 1_756_000_000_000 + i, 5 + (i % 3)),
        )
        conn.execute(
            "INSERT INTO sessions (session_id, started_at, ended_at, n_games)"
            " VALUES (?, ?, ?, 1)", (i + 1, i, i + 1),
        )
        conn.execute(
            "INSERT INTO matches (match_id, queue_id, platform_id, game_version, patch,"
            " game_creation, game_start, game_end, game_duration_s, session_id, fetched_at,"
            " has_timeline, raw_match_json) VALUES (?, 420, 'EUW1', 'v', '16.9', ?, ?, ?,"
            " 1800, ?, 'now', 1, '{}')",
            (f"M{i}", 1_756_000_000_000 + i, 1_756_000_000_000 + i,
             1_756_000_000_000 + i, i + 1),
        )
        conn.execute(
            "INSERT INTO features (match_id, computed_at, extractor_version, y_win,"
            " is_remake, scuttle_crabs) VALUES (?, 'now', 1, 1, 0, ?)",
            (f"M{i}", 3 + (i % 2)),
        )
    result = cmp.compare(conn, era_start="2025-01-01")
    assert result["n_bench_junglers"] == 40
    m = next(r for r in result["metrics"] if r["metric"] == "scuttle_crabs")
    assert m["my_median"] < m["bench_median"]
    assert m["my_percentile_in_bench"] < 50  # je suis sous leur mediane


def test_timeline_metrics_for_both_junglers():
    frames = []
    for idx in range(16):
        frames.append({
            "timestamp": idx * 60_000,
            "participantFrames": {
                "1": {"totalGold": 1000 + idx * 400, "xp": idx * 500,
                      "minionsKilled": 0, "jungleMinionsKilled": idx * 4},
                "6": {"totalGold": 1000 + idx * 300, "xp": idx * 450,
                      "minionsKilled": 0, "jungleMinionsKilled": idx * 3},
            },
            "events": [],
        })
    frames[15]["events"] = [
        {"type": "CHAMPION_KILL", "timestamp": 7 * 60_000, "victimId": 1},
        {"type": "CHAMPION_KILL", "timestamp": 27 * 60_000, "victimId": 1},
        {"type": "CHAMPION_KILL", "timestamp": 28 * 60_000, "victimId": 6},
    ]
    m = bench.timeline_metrics({"info": {"frames": frames}}, [1, 6])
    assert m[1]["deaths_pre15"] == 1
    assert m[1]["deaths_post25"] == 1
    assert m[6]["deaths_pre15"] == 0
    assert m[6]["deaths_post25"] == 1
    assert m[1]["gold_diff_ejgl_10"] == 1000
    assert m[6]["gold_diff_ejgl_10"] == -1000
    assert m[1]["cs_diff_ejgl_10"] == 10
