from skibot.config import update_env_value


def test_update_existing_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# commentaire\nRIOT_API_KEY=vieille-cle\nRIOT_PLATFORM=euw1\n", encoding="utf-8")
    update_env_value("RIOT_API_KEY", "RGAPI-nouvelle", env_path=env)
    content = env.read_text(encoding="utf-8")
    assert "RIOT_API_KEY=RGAPI-nouvelle" in content
    assert "vieille-cle" not in content
    assert "RIOT_PLATFORM=euw1" in content  # les autres lignes sont préservées


def test_append_missing_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text("RIOT_PLATFORM=euw1\n", encoding="utf-8")
    update_env_value("RIOT_GAME_NAME", "Toto", env_path=env)
    assert "RIOT_GAME_NAME=Toto" in env.read_text(encoding="utf-8")


def test_analysis_accounts_and_filter(monkeypatch):
    from skibot import config as cfg_mod
    monkeypatch.delenv("RIOT_ANALYSIS_ACCOUNTS", raising=False)
    assert cfg_mod.analysis_accounts() == ()
    assert cfg_mod.account_filter() == ("1=1", ())
    monkeypatch.setenv("RIOT_ANALYSIS_ACCOUNTS", "Main#EUW; Smurf#666 ")
    assert cfg_mod.analysis_accounts() == ("Main#EUW", "Smurf#666")
    cond, params = cfg_mod.account_filter("f.account")
    assert "f.account IS NULL" in cond
    assert params == ("Main#EUW", "Smurf#666")
