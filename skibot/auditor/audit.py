"""Appel LLM, vérification mécanique des citations et persistance des verdicts.

L'honnêteté n'est pas une promesse du prompt : le vérificateur rejette tout
verdict citant un fait inexistant ou toute affirmation sans citation, et fait
regénérer. Deux échecs = AuditError, jamais de verdict non conforme en base.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from ..config import PROJECT_ROOT, account_filter
from . import dossier
from .prompts import SYSTEM_PROMPT, TAGS, VERDICT_SCHEMA

CONSIGNE_FILE = PROJECT_ROOT / "protocol" / "consigne.json"

# Marqueurs prescriptifs : leur présence dans un texte = verdict rejeté
PRESCRIPTIVE_MARKERS = [
    "il faut", "il faudrait", "tu devrais", "vous devriez", "à l'avenir",
    "essaie de", "essaye de", "pense à", "veille à", "il est recommandé",
]


def load_consigne() -> dict | None:
    """Consigne active au format machine (créée à l'activation, cf. protocole)."""
    if not CONSIGNE_FILE.exists():
        return None
    try:
        return json.loads(CONSIGNE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

MODEL = "claude-opus-5"
PRICE_PER_MTOK = {"claude-opus-5": (5.00, 25.00)}  # (input, output) en USD
MAX_ATTEMPTS = 2


class AuditError(RuntimeError):
    pass


def verify_citations(verdict: dict, valid_ids: set[str]) -> list[str]:
    """Renvoie la liste des problèmes (vide = verdict conforme)."""
    problems: list[str] = []
    claims = list(verdict.get("faits_marquants") or [])
    if verdict.get("point_a_revoir"):
        claims.append(verdict["point_a_revoir"])
    if not claims:
        problems.append("aucune affirmation produite")
    for c in claims:
        ids = c.get("fact_ids") or []
        if not ids:
            problems.append(f"affirmation sans citation : « {c.get('texte', '')[:60]} »")
        problems.extend(f"citation inexistante : {i}" for i in ids if i not in valid_ids)
    # les citations en texte libre (résumé, limites, textes) sont vérifiées aussi
    free_text = " ".join(
        [verdict.get("resume", ""), verdict.get("limites", ""),
         verdict.get("question_replay", ""), verdict.get("suivi_consigne") or ""]
        + [c.get("texte", "") for c in claims]
    )
    problems.extend(
        f"citation inexistante dans le texte : {i}"
        for i in sorted(set(re.findall(r"F\d+", free_text)))
        if i not in valid_ids
    )
    # tags : 1 à 3, uniquement dans la taxonomie fermée
    tags = verdict.get("tags") or []
    if not 1 <= len(tags) <= 3:
        problems.append(f"nombre de tags invalide : {len(tags)} (attendu 1 à 3)")
    problems.extend(f"tag hors taxonomie : {t}" for t in tags if t not in TAGS)
    # aucune formulation prescriptive, nulle part
    lowered = free_text.lower()
    problems.extend(
        f"formulation prescriptive interdite : « {mk} »"
        for mk in PRESCRIPTIVE_MARKERS
        if mk in lowered
    )
    return problems


def audit_match(
    conn: sqlite3.Connection,
    match_id: str,
    *,
    client=None,
    model: str = MODEL,
    baselines: dict | None = None,
    consigne: dict | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    if baselines is None:
        baselines = dossier.compute_baselines(conn)
    if consigne is None:
        consigne = load_consigne()
    d = dossier.build(conn, match_id, baselines=baselines, consigne=consigne)
    valid_ids = {f["id"] for f in d["facts"]}
    if client is None:
        import anthropic

        client = anthropic.Anthropic()

    messages = [{"role": "user", "content": dossier.render(d)}]
    in_tok = out_tok = 0
    problems: list[str] = []
    for _attempt in range(MAX_ATTEMPTS):
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=messages,
            output_config={"format": {"type": "json_schema", "schema": VERDICT_SCHEMA}},
        )
        in_tok += response.usage.input_tokens
        out_tok += response.usage.output_tokens
        if response.stop_reason == "refusal":
            raise AuditError(f"{match_id} : le modèle a refusé la requête (stop_reason=refusal)")
        text = next(b.text for b in response.content if b.type == "text")
        verdict = json.loads(text)
        problems = verify_citations(verdict, valid_ids)
        if not problems:
            break
        log(f"  verdict non conforme ({' ; '.join(problems)}), regénération...")
        messages += [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": "Verdict rejeté par le vérificateur : " + " ; ".join(problems)
                + ". Corrige en citant uniquement des faits existants du dossier.",
            },
        ]
    else:
        raise AuditError(
            f"{match_id} : verdict non conforme après {MAX_ATTEMPTS} tentatives "
            f"({' ; '.join(problems)})"
        )

    price_in, price_out = PRICE_PER_MTOK.get(model, (0.0, 0.0))
    cost = in_tok * price_in / 1e6 + out_tok * price_out / 1e6
    md = render_markdown(d, verdict)
    with conn:
        conn.execute(
            """INSERT OR REPLACE INTO audits
               (match_id, created_at, model, verdict_json, verdict_md,
                input_tokens, output_tokens, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                match_id,
                datetime.now(UTC).isoformat(timespec="seconds"),
                model,
                json.dumps(verdict, ensure_ascii=False),
                md,
                in_tok,
                out_tok,
                round(cost, 5),
            ),
        )
    return {"match_id": match_id, "verdict": verdict, "markdown": md, "cost_usd": cost}


def render_markdown(d: dict, verdict: dict) -> str:
    facts_by_id = {f["id"]: f for f in d["facts"]}
    h = d["header"]

    def cite(ids: list[str]) -> str:
        return " ".join(f"[{i}]" for i in ids)

    lines = [
        (
            f"### {h['result']} — {h['champion']} vs {h['vs']} · {h['date']} "
            f"({h['duration_min']} min)"
        ),
        "",
    ]
    if verdict.get("suivi_consigne"):
        lines += [f"**Consigne** : {verdict['suivi_consigne']}", ""]
    lines += [verdict["resume"], "", "**Faits marquants**"]
    used: set[str] = set()
    for fm in verdict["faits_marquants"]:
        lines.append(f"- {fm['texte']} {cite(fm['fact_ids'])}")
        used.update(fm["fact_ids"])
    par = verdict["point_a_revoir"]
    used.update(par["fact_ids"])
    # les faits cités en texte libre (ex. dans le résumé) figurent aussi en annexe
    used.update(
        i for i in re.findall(r"F\d+", verdict.get("resume", "")) if i in facts_by_id
    )
    lines += [
        "",
        f"**À revoir** : {par['texte']} {cite(par['fact_ids'])}",
        "",
        f"**Question de replay** : {verdict.get('question_replay', '—')}",
        "",
        "Tags : " + ", ".join(f"`{t}`" for t in verdict.get("tags", [])),
        "",
        f"*Limites : {verdict['limites']}*",
        "",
        "Faits cités :",
    ]
    for i in sorted(used, key=lambda x: int(x[1:])):
        f = facts_by_id[i]
        lines.append(f"- {i} : {f['text']} [{f['prov']}]")
    return "\n".join(lines)


def run(
    conn: sqlite3.Connection,
    *,
    limit: int = 3,
    since_days: int | None = 7,
    client=None,
    model: str = MODEL,
    baselines: dict | None = None,
    consigne: dict | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Audite les games récentes sans verdict (hors remakes), de la plus récente.

    since_days borne la fenêtre (7 jours par défaut) : sans elle, --limit
    finirait par remonter tout l'historique, verdict par verdict payant.
    """
    min_start = 0
    if since_days is not None:
        min_start = int((datetime.now(UTC).timestamp() - since_days * 86_400) * 1000)
    # même frontière que les analyses (règle n°11) : les games du smurf ne
    # nourrissent ni verdicts par défaut ni compteur d'hypothèses.
    # Échappatoire : `skibot audit --match <id>` audite n'importe quelle game.
    acond, aparams = account_filter("f.account")
    todo = conn.execute(
        f"""SELECT f.match_id FROM features f
           JOIN matches m USING (match_id)
           LEFT JOIN audits a USING (match_id)
           WHERE a.match_id IS NULL AND f.is_remake = 0 AND m.game_start >= ?
             AND {acond}
           ORDER BY m.game_start DESC LIMIT ?""",
        (min_start, *aparams, limit),
    ).fetchall()
    results = []
    baselines = dossier.compute_baselines(conn)
    consigne = load_consigne()
    for r in todo:
        log(f"Audit de {r['match_id']}...")
        res = audit_match(conn, r["match_id"], client=client, model=model,
                          baselines=baselines, consigne=consigne, log=log)
        log(f"  ok — {res['cost_usd'] * 100:.1f} centime(s)")
        results.append(res)
    return {"audited": len(results), "cost_usd": sum(x["cost_usd"] for x in results)}
