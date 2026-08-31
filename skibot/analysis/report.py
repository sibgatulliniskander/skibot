"""Génération du rapport markdown daté (reports/analyse_YYYY-MM-DD.md)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .stats import LEVIER


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out.extend("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return out


def _result_row(r: dict, with_confirm: bool) -> list[str]:
    row = [
        f"`{r['feature']}`", r["category"], r["tag"], str(r["n"]),
        r["effect_label"], f"{r['p']:.2g}", f"{r['q']:.2g}",
    ]
    if with_confirm:
        c = r.get("confirm")
        row.append(c["effect_label"] if c else "—")
        row.append(f"{c['p']:.2g}" if c else "—")
        row.append(r.get("era_label", "—"))
    return row


def write(out_dir: Path, results: list[dict], meta: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    path = out_dir / f"analyse_{today}.md"

    confirmed = [r for r in results if r.get("verdict") == "confirmé"]
    not_replicated = [r for r in results if r["retained"] and r.get("verdict") != "confirmé"]
    confirmed.sort(key=lambda r: (r["tag"] != LEVIER, -r["effect_abs"]))
    not_replicated.sort(key=lambda r: -r["effect_abs"])

    lines: list[str] = []
    add = lines.append
    add(f"# Screening wins/losses — {today}")
    add("")
    add("## Méthode")
    add(
        f"- Échantillons : **{meta['n_explore']}** games exploration / "
        f"**{meta['n_confirm']}** confirmation — split aléatoire **par session**, "
        f"figé en base (seed 42), jamais re-tiré. "
        f"{meta['n_prospective']} game(s) prospective(s) hors split."
    )
    add(
        f"- Screening (exploration) : Mann-Whitney / Fisher / χ² selon le type, "
        f"correction Benjamini-Hochberg, retenue si q ≤ {meta['fdr_q']}."
    )
    add(
        f"- Confirmation : re-test des seules candidates sur l'échantillon "
        f"indépendant, α = {meta['alpha']}, même direction exigée."
    )
    add(
        f"- Stabilité temporelle : effet recalculé sur l'ère courante "
        f"(games depuis {meta['era_start']}, n = {meta['n_era']}) — descriptif ; "
        f"une candidate instable dans l'ère courante ne peut pas devenir une consigne."
    )
    add("- Remakes exclus. NULL = non mesuré, jamais imputé.")
    add(
        "- **Tag** : *levier* = actionnable par une consigne ; *mécanisme* = décrit "
        "comment la game se gagne, ne peut PAS fonder une consigne directement."
    )
    add("")

    add(f"## Effets CONFIRMÉS ({len(confirmed)}) — screening + réplication indépendante")
    add("")
    if confirmed:
        lines += _table(
            ["Variable", "Cat", "Tag", "n", "Effet (exploration)", "p", "q",
             "Effet (confirmation)", "p conf.", "Ère courante"],
            [_result_row(r, with_confirm=True) for r in confirmed],
        )
    else:
        add("Aucun effet confirmé à ce stade.")
    add("")

    add(f"## Candidats NON répliqués ({len(not_replicated)}) — [exploratoire], à revoir avec plus de données")
    add("")
    if not_replicated:
        lines += _table(
            ["Variable", "Cat", "Tag", "n", "Effet (exploration)", "p", "q",
             "Effet (confirmation)", "p conf.", "Ère courante"],
            [_result_row(r, with_confirm=True) for r in not_replicated],
        )
    else:
        add("Aucun.")
    add("")

    add("## Annexe — screening complet (exploration uniquement, ne rien conclure ici)")
    add("")
    lines += _table(
        ["Variable", "Type", "Tag", "n", "Effet", "p", "q", "Retenue"],
        [
            [
                f"`{r['feature']}`", r["kind"], r["tag"], str(r["n"]),
                r["effect_label"], f"{r['p']:.2g}", f"{r['q']:.2g}",
                "oui" if r["retained"] else "non",
            ]
            for r in sorted(results, key=lambda x: x["q"])
        ],
    )
    add("")

    cat_retained = [r for r in results if r["retained"] and "levels" in r]
    if cat_retained:
        add("## Détail des variables catégorielles retenues (exploration)")
        add("")
        for r in cat_retained:
            add(f"### `{r['feature']}`")
            add("")
            lines += _table(
                ["Niveau", "n", "WR %"],
                [[lv["level"], str(lv["n"]), f"{lv['wr']:.0f}"] for lv in r["levels"]],
            )
            add("")

    noted = [r for r in results if r["note"] and r["retained"]]
    if noted:
        add("## Mises en garde spécifiques")
        add("")
        for r in noted:
            add(f"- `{r['feature']}` : {r['note']}")
        add("")

    add("---")
    add(
        "*Clause d'honnêteté : chaque valeur ci-dessus est calculée depuis les "
        "données Riot collectées (rien d'inféré sans étiquette). Un effet "
        "« confirmé » reste corrélationnel — la causalité ne sera établie que par "
        "l'expérimentation prospective (consignes) sur les games futures.*"
    )
    add("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
