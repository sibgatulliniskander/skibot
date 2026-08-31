# 03 — Revues trimestrielles

Une fois par trimestre (cibles : début décembre 2026, mars, juin, septembre,
décembre 2027). C'est le seul moment où le protocole lui-même peut changer.

## Ordre du jour

1. **Trajectoire elo** : courbe LP (`rank_snapshots`) vs jalons indicatifs
   (Émeraude fin 2026 → Diamant mi-2027 → Master fin 2027). Réviser les jalons
   si nécessaire — en le disant publiquement, jamais en silence.
2. **Bilan des consignes** du trimestre : adoptées / rejetées / non concluantes,
   et ce qu'on en apprend sur la méthode elle-même (les fenêtres sont-elles
   assez longues ? les X bien choisis ?).
3. **Re-screening autorisé** : c'est ici — et seulement ici — qu'un nouveau
   split peut être tiré pour intégrer les games accumulées depuis le dernier :
   - nouveau tirage par session, nouveau seed, documenté (date, seed, effectifs)
     dans le rapport de revue et committé ;
   - les games jouées SOUS une consigne active sont marquées comme telles : un
     effet « découvert » sur ces games peut être un artefact de la consigne ;
   - l'ancien rapport n'est pas supprimé — l'historique des analyses fait
     partie du projet public.
4. **Dette technique et évolutions** : extracteur (bump `EXTRACTOR_VERSION` +
   `skibot features --rebuild`), nouvelles features candidates, migration
   Postgres si la volumétrie l'exige, évolutions du dashboard.
5. **Audit d'honnêteté** : relire un échantillon de sorties publiques
   (dashboard, stream, auditor) et vérifier l'étiquetage [prouvé]/[inféré].
   Toute affirmation non sourcée trouvée = corrigée + notée dans le rapport de
   revue.

## Livrable

Un rapport `protocol/revues/AAAA-TT.md` committé, avec les décisions et leurs
justifications. Les décisions non écrites n'existent pas.
