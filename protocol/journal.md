# Journal hebdomadaire

Trois lignes par semaine, pas plus. Format : date — games jouées — état de la
consigne — observation éventuelle.

## 2026-08-31
Baseline établie : 828 games valides, Platine III 49 LP. Screening + confirmation
livrés (19 effets confirmés dont 4 leviers). Aucune consigne active — choix en cours.

## 2026-08-31 (suite)
Contrôle de robustesse par ère : scuttle_crabs porté par l'ère ancienne (affaibli
depuis mars 2026), on_my_way_pings stable dans les deux ères. Décision : AUCUNE
consigne avant la revue de décembre 2026 — collecte prospective à l'elo actuel,
outillage préparé en parallèle. Règle fixe n°11 (éligibilité ère courante) ajoutée ;
`skibot analyze` intègre désormais la stabilité temporelle (stable/affaibli/instable).

## 2026-09-01
Smurf skibimid#666 branché (144 games collectées) — découvert SILVER I, pas
Platine : ses games sont exclues des analyses de décision (règle n°11 étendue
aux comptes) jusqu'à ce que son rang rejoigne l'ère courante. Benchmark Diamant
en production (894 junglers, 18 métriques) : écart n°1 = pings on-my-way (5 vs
15) ; morts post-25 confirmées par la 3e source (76e percentile chez eux).

## 2026-09-01 (suite)
Champion pool gravé (protocol/pool.md) : Viego titulaire + Kha'Zix en backup en
ranked, slot AP carry vacant — Ekko et Karthus en test sur le labo-smurf,
décision ~21/09. Fin de la roulette (18 champions en carrière). Meta Diamant du
benchmark utilisée comme meta révélée (Nasus/Amumu absents des picks Diamant).

## 2026-09-14 — reprise après ~2 semaines
La machine a tourné seule : 1085 games en base, features à jour, zéro rattrapage.
ÉMERAUDE IV atteint sur le main (jalon « Émeraude fin 2026 » rempli avec 3 mois
et demi d'avance) — 44 games depuis le 02/09 à 64 % de WR, dont 38 Viego à 68 %.
Fait notable [prouvé] : pings on-my-way à ~11 de moyenne sur la période (médiane
historique : 5) — le comportement du levier n°1 a bougé spontanément, sans
consigne active ; à discuter à la revue de décembre (X déjà déplacé → la
consigne éventuelle serait « maintenir », et le lien X→Y reste non causal :
pas de contrôle). Pool : discipline à 86 % (6 games hors pool en ranked, une
par champion). Labo-smurf : test Ekko/Karthus NON réalisé (8 games seulement,
Zyra/Talon/Brand) — échéance du slot AP du 21/09 à recalibrer.
