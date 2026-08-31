# 02 — Boucle macro (hebdomadaire)

Chaque semaine, un créneau fixe (recommandé : dimanche soir), 20-30 minutes,
documenté en stream quand c'est possible.

## Déroulé

1. **Mettre à jour la donnée** :

   ```
   .venv\Scripts\skibot collect
   .venv\Scripts\skibot features
   .venv\Scripts\skibot status
   ```

2. **Suivre la consigne active** (voir [consigne-active.md](consigne-active.md)) :
   - le **X** : le comportement visé a-t-il bougé sur les games de la semaine ?
     (comparer la médiane de la métrique aux valeurs baseline W/L du rapport) ;
   - le **Y** : WR et LP sur la fenêtre — à lire sans conclure avant le terme ;
   - le compteur : combien de games prospectives accumulées / cible.
3. **Journal hebdo** : 3 lignes dans `protocol/journal.md` (date, games jouées,
   état de la consigne, observation éventuelle). Committé.
4. **Rien changer d'autre.** Pas de nouveau champion pool, pas de nouvelle
   routine en parallèle — une seule variable à la fois (règle fixe n°12).

## Cycle de vie d'une consigne

```
candidate (levier confirmé par l'analyse)
   → ACTIVE (formulée + critères figés AVANT le départ)
   → verdict au terme : ADOPTÉE | REJETÉE | PROLONGÉE (une seule fois)
```

### Formulation (à figer avant la première game de la fenêtre)

- **Hypothèse** : « augmenter X (levier confirmé) améliore Y ».
- **Comportement** : une instruction concrète, exécutable en jeu, formulée en
  une phrase.
- **Manipulation check (X)** : la métrique mesurable qui prouve que le
  comportement a changé, et le seuil visé (ex. : médiane scuttle ≥ 4).
- **Fenêtre** : nombre de games prospectives (minimum 40) ET durée minimale
  (2 semaines) — le verdict tombe quand les deux sont atteints.
- **Critère de succès (Y)** : défini à l'avance. Ordre de grandeur honnête :
  sur 40 games, seul un effet fort est détectable (±8-10 pts de WR). En dessous,
  le verdict sera « non concluant » — c'est prévu et acceptable, la consigne
  peut être prolongée une fois (40 games de plus) si le X a bien bougé.

### Verdicts

- **X n'a pas bougé** → consigne mal conçue ou inapplicable : REJETÉE (quel que
  soit le Y), reformuler.
- **X a bougé, Y favorable au-delà du critère** → ADOPTÉE : devient une
  habitude (plus une consigne), une nouvelle consigne peut démarrer.
- **X a bougé, Y plat au terme de la prolongation** → REJETÉE : le levier était
  corrélationnel sans être causal. C'est une découverte, elle se publie.

## Priorité des candidates

Leviers confirmés par l'analyse du 2026-08-31, du moins exposé au plus exposé à
la causalité inverse :

1. `scuttle_crabs` / `vision_advantage_vs_ejgl` — comportements de début de
   partie, largement sous ton contrôle.
2. `pings_total` / `on_my_way_pings` — communication : contrôlable, mais le
   volume de pings dépend aussi du déroulé de la game (prudence).
