# Consigne active

**Statut : aucune — phase d'observation jusqu'au 1er décembre 2026 : je joue normalement, la donnée s'accumule.**

Décision du 2026-08-31 : accumulation de games prospectives à l'elo actuel
jusqu'à la **revue de décembre 2026**, sans consigne. Motif : la baseline
(14 mois) mélange plusieurs ères de process (elo, meta) ; le contrôle de
robustesse a montré qu'au moins un levier (`scuttle_crabs`) était porté par
l'ère ancienne. On choisira la consigne n°1 sur un screening propre de l'ère
courante, enrichi de ~100-150 games nouvelles.

D'ici là : jouer normalement (règle fixe n°14). La collecte et l'extraction
tournent automatiquement.

## Candidates au 2026-08-31 (leviers confirmés + stabilité temporelle)

| Levier | Baseline (méd. W vs L) | Ère courante (≥ 2026-03-01) | Éligibilité |
|---|---|---|---|
| `on_my_way_pings` | 9 vs 6 | δ=+0,31, p=5e-8 — **stable** | ✅ candidate n°1 |
| `vision_advantage_vs_ejgl` | ~0 vs négatif | δ=+0,13, p=0,02 — stable | ✅ candidate |
| `pings_total` | 44 vs 40 | δ=+0,13, p=0,02 — stable | ✅ candidate |
| `scuttle_crabs` | 4 vs 3 | δ=+0,12, méd. 4 vs 4 — **affaibli** | ❌ non éligible (règle n°11) |

---

## Gabarit (à remplir à l'activation)

- **Consigne n°** : 1
- **Date d'activation** :
- **Hypothèse** :
- **Comportement (une phrase)** :
- **Manipulation check (X)** : métrique + seuil
- **Fenêtre** : ≥ 40 games prospectives ET ≥ 2 semaines
- **Critère de succès (Y)** : figé avant le départ
- **Verdict** : (à la date prévue, pas avant, pas après)

## Historique des consignes

| n° | Consigne | Fenêtre | X bougé ? | Y | Verdict |
|---|---|---|---|---|---|
| — | — | — | — | — | — |
