"""CLI skibot : `skibot collect`, `skibot status`."""

from __future__ import annotations

from datetime import UTC, datetime

import click

from . import db
from .collector import collect as collect_mod
from .config import ConfigError, load_config, update_env_value
from .riot.client import RiotApiError, RiotAuthError, RiotClient


@click.group()
def main() -> None:
    """Outils du projet skibot (Road to Master)."""


@main.command()
@click.option("--max-games", type=int, default=None, help="Limite le nombre de games sur ce run.")
def collect(max_games: int | None) -> None:
    """Récupère les nouvelles games ranked (match + timeline) et met à jour la base."""
    try:
        cfg = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))
    conn = db.connect(cfg.db_path)
    client = RiotClient(cfg.riot_api_key, cfg.platform, cfg.regional)
    try:
        summary = collect_mod.collect(conn, client, cfg, log=click.echo, max_games=max_games)
    except RiotAuthError as e:
        raise click.ClickException(str(e))
    except RiotApiError as e:
        raise click.ClickException(f"Erreur API Riot : {e}")
    click.echo(
        f"\n{summary['new_games']} game(s) ajoutée(s)"
        f" ({summary['no_timeline']} sans timeline), {summary['sessions']} session(s) en base."
    )
    if summary.get("skipped"):
        click.echo(f"{summary['skipped']} game(s) ignorée(s) : payload invalide côté Riot.")
    if summary["rank"]:
        click.echo(f"Rang actuel : {summary['rank']}")


@main.command()
@click.option("--rebuild", is_flag=True, help="Recalcule toutes les games (apres une evolution de l'extracteur).")
def features(rebuild):
    """Extrait les features d'analyse (une ligne par game) depuis la base."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    from .features import extract
    s = extract.run(conn, rebuild=rebuild, log=click.echo)
    click.echo(f"\n{s['extracted']} game(s) extraite(s), {s['total']} au total.")
    click.echo(
        "Couverture : challenges {}/{}, gold@15 {}/{}, remakes exclus : {}.".format(
            s["with_challenges"], s["total"], s["with_gold15"], s["total"], s["remakes"]
        )
    )


@main.command()
@click.option("--era-start", default=None, help="Debut de l'ere courante (defaut : voir analysis/run.py).")
def analyze(era_start):
    """Screening exploration + confirmation independante, rapport dans reports/."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    from .analysis import run as analysis_run
    kwargs = {"era_start": era_start} if era_start else {}
    s = analysis_run.analyze(conn, log=click.echo, **kwargs)
    click.echo(
        "{} variables testees, {} candidates au screening, {} confirmees.".format(
            s["tested"], s["retained"], s["confirmed"]
        )
    )
    click.echo("Rapport : {}".format(s["report"]))


@main.command()
@click.option("--port", default=5000, help="Port d'ecoute (defaut 5000).")
@click.option("--host", default="127.0.0.1", help="Interface (127.0.0.1 = local uniquement).")
def dashboard(port, host):
    """Lance le dashboard Flask (vue publique / et vue interne /interne)."""
    from .dashboard.app import create_app
    app = create_app()
    click.echo(f"Dashboard : http://{host}:{port}  (Ctrl+C pour arreter)")
    app.run(host=host, port=port, debug=False)


@main.command()
@click.option("--limit", default=3, help="Nombre maximum de games a auditer sur ce run.")
@click.option("--since-days", default=7, help="Fenetre en jours (defaut 7).")
@click.option("--all", "all_games", is_flag=True, help="Ignorer la fenetre (tout l'historique).")
@click.option("--match", "match_id", default=None, help="Auditer une game precise (match_id).")
def audit(limit, since_days, all_games, match_id):
    """Genere les verdicts LLM post-game (dossier de faits + verification des citations)."""
    import os
    cfg = load_config(require_key=False)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise click.ClickException(
            "ANTHROPIC_API_KEY absente du .env. Cree ta cle sur https://console.anthropic.com "
            "(API Keys -> Create Key) puis lance `skibot set-anthropic-key`."
        )
    conn = db.connect(cfg.db_path)
    from .auditor import audit as auditor_mod
    try:
        if match_id:
            res = auditor_mod.audit_match(conn, match_id, log=click.echo)
            click.echo("\n" + res["markdown"])
            s = {"audited": 1, "cost_usd": res["cost_usd"]}
        else:
            last = conn.execute("SELECT MAX(game_start) ts FROM matches").fetchone()["ts"]
            if last:
                dt = datetime.fromtimestamp(last / 1000, tz=UTC).astimezone()
                click.echo(
                    f"Derniere game en base : {dt:%d/%m %H:%M} - si ta toute derniere "
                    "game manque, lance `skibot collect` d'abord.\n"
                )
            s = auditor_mod.run(conn, limit=limit,
                                since_days=None if all_games else since_days,
                                log=click.echo)
            if s["audited"] == 0:
                click.echo("Rien a auditer : toutes les games de la fenetre ont deja "
                           "leur verdict (une game n'est jamais auditee deux fois).")
    except (auditor_mod.AuditError, ValueError) as e:
        raise click.ClickException(str(e))
    click.echo("\n{} game(s) auditee(s), cout total {:.3f} $.".format(s["audited"], s["cost_usd"]))


@main.command("set-anthropic-key")
def set_anthropic_key():
    """Enregistre la cle API Anthropic dans .env (pour l'auditor) et la verifie."""
    key = click.prompt("Colle ta cle Anthropic (sk-ant-...)", hide_input=True).strip()
    if not key.startswith("sk-ant-"):
        click.confirm("La cle ne commence pas par sk-ant- ; continuer quand meme ?", abort=True)
    path = update_env_value("ANTHROPIC_API_KEY", key)
    click.echo(f"Cle enregistree dans {path}")
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    try:
        client.messages.count_tokens(
            model="claude-opus-5", messages=[{"role": "user", "content": "ping"}]
        )
    except anthropic.AuthenticationError:
        raise click.ClickException("Cette cle est refusee par l'API Anthropic (mal copiee ?).")
    click.echo("Cle valide - l'auditor est pret (`skibot audit`).")


@main.command("bench-collect")
@click.option("--max-players", default=60, help="Joueurs Diamant echantillonnes.")
@click.option("--games-per-player", default=5, help="Games recentes par joueur.")
def bench_collect(max_players, games_per_player):
    """Crawle un echantillon de junglers Diamant (benchmark, table bench_games)."""
    try:
        cfg = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))
    conn = db.connect(cfg.db_path)
    client = RiotClient(cfg.riot_api_key, cfg.platform, cfg.regional)
    from .benchmark import collect as bench_mod
    try:
        s = bench_mod.collect(conn, client, max_players=max_players,
                              games_per_player=games_per_player, log=click.echo)
    except RiotAuthError as e:
        raise click.ClickException(str(e))
    except RiotApiError as e:
        raise click.ClickException(f"Erreur API Riot : {e}")
    n_tl = bench_mod.backfill_timelines(conn, client, log=click.echo)
    click.echo("\n{} nouvelle(s) game(s), {} lignes jungler ajoutees ({} au total), "
               "{} game(s) enrichie(s) en timeline.".format(
        s["new_games"], s["new_junglers"], s["total_junglers"], n_tl))


@main.command()
def bench():
    """Compare mes distributions (ere courante) aux junglers Diamant crawles."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    from .benchmark import compare as compare_mod
    result = compare_mod.compare(conn)
    if not result["metrics"]:
        raise click.ClickException(
            "Pas assez de donnees de benchmark - lance d'abord `skibot bench-collect`."
        )
    path = compare_mod.write_latest(result)
    click.echo("Moi ({} games depuis {}) vs junglers {} ({} lignes) :\n".format(
        result["n_me"], result["era_start"], result["bench_tier"],
        result["n_bench_junglers"]))
    click.echo(f"{'Metrique':<44} {'Moi (med)':>10} {'Eux (med)':>10} {'Ma position':>12}")
    for r in result["metrics"]:
        click.echo("{:<44} {:>10g} {:>10g} {:>10.0f} %".format(
            r["label"][:43], round(r["my_median"], 2), round(r["bench_median"], 2),
            r["my_percentile_in_bench"]))
    click.echo("\n'Ma position' = ou tombe ma mediane dans LEUR distribution "
               "(50 % = identique a eux).")
    click.echo(f"Export : {path}")


@main.command("set-key")
def set_key() -> None:
    """Enregistre ta clé Riot dans .env et vérifie qu'elle fonctionne."""
    key = click.prompt("Colle ta clé Riot (RGAPI-...)", hide_input=True).strip()
    if not key.startswith("RGAPI-"):
        click.confirm("La clé ne commence pas par RGAPI- ; continuer quand même ?", abort=True)
    path = update_env_value("RIOT_API_KEY", key)
    click.echo(f"Clé enregistrée dans {path}")
    try:
        cfg = load_config()
    except ConfigError:
        click.echo(
            "Riot ID pas encore renseigné dans .env — impossible de tester la clé maintenant, "
            "elle sera vérifiée au premier `skibot collect`."
        )
        return
    client = RiotClient(cfg.riot_api_key, cfg.platform, cfg.regional)
    try:
        account = client.account_by_riot_id(cfg.game_name, cfg.tag_line)
    except RiotAuthError:
        raise click.ClickException(
            "Cette clé est refusée par l'API Riot (mal copiée ou déjà expirée ?)."
        )
    click.echo(f"Clé valide — compte résolu : {account.get('gameName')}#{account.get('tagLine')}")


@main.command()
def status() -> None:
    """Affiche l'état de la base : games, sessions, dernier rang connu."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    n_matches = conn.execute("SELECT COUNT(*) AS c FROM matches").fetchone()["c"]
    n_timeline = conn.execute(
        "SELECT COUNT(*) AS c FROM matches WHERE has_timeline = 1"
    ).fetchone()["c"]
    n_sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
    last_start = conn.execute("SELECT MAX(game_start) AS ts FROM matches").fetchone()["ts"]
    rank = conn.execute(
        "SELECT * FROM rank_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()

    click.echo(f"Base : {cfg.db_path}")
    click.echo(f"Games : {n_matches} ({n_timeline} avec timeline)")
    click.echo(f"Sessions : {n_sessions}")
    if last_start is not None:
        dt = datetime.fromtimestamp(last_start / 1000, tz=UTC).astimezone()
        click.echo(f"Dernière game : {dt:%Y-%m-%d %H:%M}")
    if rank is not None:
        click.echo(
            f"Dernier rang connu : {rank['tier']} {rank['division']} — {rank['lp']} LP "
            f"({rank['wins']}W/{rank['losses']}L, snapshot {rank['taken_at']})"
        )


if __name__ == "__main__":
    main()
