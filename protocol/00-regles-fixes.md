# 00 — Règles fixes

Ces règles ne changent jamais, quel que soit le résultat du moment.

## Conformité Riot

1. **Aucune assistance in-game.** Tout l'outillage travaille post-game, ou en
   champ select au plus tard. Pas d'overlay, pas de coaching temps réel, pas de
   script. Si un doute existe sur un usage : il est interdit jusqu'à preuve du
   contraire.
2. La clé API vit dans `.env` (gitignoré) et nulle part ailleurs — ni dans le
   chat, ni dans le code, ni dans un commit, ni à l'écran en stream.

## Clause d'honnêteté

3. Toute affirmation produite par l'outillage (analyses, auditor, dashboard,
   stream) est étiquetée :
   - **[prouvé par X]** — la donnée le contient directement (event, frame,
     challenge Riot) ;
   - **[inféré de Y]** — déduit, avec la source et la limite explicites ;
   - **NULL / non mesurable** — jamais remplacé par une estimation silencieuse.
4. Non-mesurables connus, à ne jamais affirmer : positions de wards (la
   timeline ne les contient pas), invades (inférables au mieux par positions),
   état mental, qualité réseau, contenu du chat vocal/écrit.
5. Les résultats négatifs se publient comme les positifs (ex. : aucun signal de
   tilt détecté sur la baseline — c'est un résultat, pas un échec).

## Discipline statistique

6. **Jamais de conclusion sur l'échantillon d'exploration.** Un effet est
   *exploratoire* tant qu'il n'a pas répliqué sur l'échantillon de confirmation,
   et *corrélationnel* tant qu'il n'a pas été validé prospectivement.
7. Le split exploration/confirmation est figé en base (`analysis_split`, par
   session, seed 42). Il n'est re-tiré qu'en revue trimestrielle, versionné et
   documenté. Re-tirer un split pour obtenir un résultat = fraude.
8. Screening toujours corrigé pour les comparaisons multiples
   (Benjamini-Hochberg, q ≤ 0,10). Confirmation à α = 0,05, même direction.
9. Une variable taguée **mécanisme** (towers_diff, baron_diff…) ne fonde jamais
   une consigne : « prendre des tours fait gagner » n'est pas une découverte.
10. Les remakes (`is_remake = 1`) sont exclus de toute analyse.
11. **Éligibilité des games** : une décision (choix de consigne) ne s'appuie que
    sur l'« ère courante » — la fenêtre la plus récente où le process est
    homogène (elo, meta), définie en revue trimestrielle (actuelle : depuis le
    2026-03-01). L'historique complet sert aux tendances, au contexte et aux
    tests de stabilité temporelle — jamais seul à choisir une consigne. Un
    levier dont l'effet est instable ou affaibli dans l'ère courante n'est pas
    éligible comme consigne. [Décision du 2026-08-31 — le rang par game n'étant
    pas fourni par Riot, l'ère est un proxy temporel : inféré, pas prouvé.]

## Conduite de l'expérimentation

12. **Une seule consigne active à la fois.** Jamais deux changements simultanés :
    sinon l'effet mesuré n'est attribuable à rien.
13. Une consigne se juge d'abord sur le **X** (le comportement a-t-il changé ?)
    puis sur le **Y** (le résultat a-t-il bougé ?). Un Y qui bouge sans X qui
    bouge ne valide rien.
14. Pendant la collecte d'une baseline ou d'une fenêtre de mesure : on joue
    normalement, on ne « joue pas pour la stat ».
15. Le verdict d'une consigne tombe à la date/volume prévu à l'avance — pas
    avant (même si ça a l'air génial), pas après (même si « encore quelques
    games »).
