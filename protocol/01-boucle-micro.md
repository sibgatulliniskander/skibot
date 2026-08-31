# 01 — Boucle micro (par session de jeu)

Objectif : zéro friction. La boucle micro doit tenir en moins de 2 minutes,
sinon elle sautera.

## Avant la session (30 s)

1. Relire [consigne-active.md](consigne-active.md) — une phrase, un comportement.
2. C'est tout. Pas de revue de stats avant de jouer (biais d'amorçage, tilt
   préventif).

## Pendant

- Jouer. Aucune consultation d'outil (règle fixe n°1).
- La consigne active est le seul « extra » mental autorisé.

## Après la session (1-2 min)

1. La collecte tourne toute seule (tâche planifiée, 1×/h). Pour forcer tout de
   suite :

   ```
   .venv\Scripts\skibot collect
   .venv\Scripts\skibot features
   ```

2. Optionnel mais précieux : une note de contexte sur la session (fatigue,
   humeur, interruptions) dans `sessions.note` — elle sera exploitable plus
   tard comme variable. (CLI dédiée à venir avec l'auditor.)
3. **Interdit** : tirer une conclusion d'une session. Une session = 2 à 5
   games = du bruit. Les conclusions appartiennent à la boucle macro.

## Règle anti-tilt par défaut

En l'absence de signal de tilt confirmé dans les données (état au 2026-08-31 :
aucun), la règle de bon sens reste : **stop après 3 défaites consécutives dans
la session**. Ce n'est pas une consigne expérimentale, c'est de l'hygiène — elle
ne compte pas comme « la » consigne active.
