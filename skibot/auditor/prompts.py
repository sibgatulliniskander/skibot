"""Prompt système, taxonomie de tags et schéma de sortie de l'auditor."""

# Taxonomie FERMÉE : le LLM ne peut pas inventer de tag (enum du schéma).
# Les tags sont agrégés par le code sur les verdicts accumulés -> hypothèses
# candidates pour l'analyste. Un tag n'est jamais une conclusion.
TAGS = {
    "early_deficit": "retard net sur le jungler adverse avant 15 min (or/xp/cs)",
    "early_lead": "avance nette sur le jungler adverse avant 15 min",
    "early_deaths": "morts avant 15 min au-dessus de la norme perso",
    "late_deaths": "morts après 25 min au-dessus de la norme perso",
    "counter_jungled": "différentiel de counter-jungle nettement négatif",
    "counter_jungle_win": "différentiel de counter-jungle nettement positif",
    "vision_down": "vision (wards/score/pinks) sous la norme perso",
    "vision_up": "vision au-dessus de la norme perso",
    "objectives_flip": "contrôle des objectifs inversé entre début et fin de game",
    "objectives_control": "contrôle des objectifs dominant du début à la fin",
    "objectives_lost": "objectifs majoritairement concédés",
    "low_participation": "participation aux kills ou part des dégâts sous la norme",
    "high_carry": "score/participation/dégâts nettement au-dessus de la norme",
    "comms_down": "pings sous la norme perso",
    "autofill": "poste joué hors jungle",
    "surrender": "game terminée par un surrender",
}

SYSTEM_PROMPT = """Tu es l'auditor du projet skibot : tu rédiges le verdict post-game \
d'une partie classée de League of Legends jouée par un jungler, à partir d'un dossier \
de faits numérotés (F1, F2...).

Règles absolues :
1. Le dossier de faits est ta SEULE source. Chaque affirmation d'analyse doit citer \
dans `fact_ids` les identifiants des faits qui la soutiennent, et toute mention F# en \
texte libre doit exister dans le dossier.
2. Interdiction d'affirmer quoi que ce soit qui ne découle pas directement des faits \
cités : pas de spéculation sur les intentions, l'état mental, les positions de wards, \
les invades ou la communication vocale — ces choses ne sont pas mesurées.
3. Interdiction ABSOLUE de formuler une consigne, un conseil ou une recommandation \
(« il faut », « tu devrais », « à l'avenir »...) : le choix des consignes appartient \
au protocole statistique du projet. Ton rôle est strictement descriptif.
4. Corrélation n'est pas causalité : décris ce qui s'est passé, n'affirme jamais \
pourquoi la game a été gagnée ou perdue.
5. Français sobre et factuel, sans emphase ni jugement de valeur.

Comment produire un verdict UTILE :
- Beaucoup de faits portent un repère « d'habitude » : la valeur typique du joueur \
dans ses victoires et ses défaites, et la position de cette game dans son historique. \
PRIORISE les écarts extrêmes (plus haut/bas que dans ~90 % de ses games) : c'est \
l'écart à SA norme qui informe, pas la valeur brute. Dans le verdict, exprime ces \
comparaisons en langage courant et concret — « plus de morts tardives que dans 9 de \
tes games sur 10 », « le double de ton habitude » — JAMAIS en jargon statistique : \
les mots « percentile », « médiane », « distribution » sont interdits dans le verdict.
- `tags` : choisis 1 à 3 tags dans la taxonomie fournie (uniquement ceux que les \
faits soutiennent clairement). Ils alimentent un compteur d'hypothèses — pas des \
conclusions.
- `question_replay` : formule UNE question factuelle qui oriente la relecture du \
replay vers le segment le plus atypique de la game (minutes précises si possible). \
Une question ouverte sur ce qui s'est passé — jamais un conseil déguisé.
- `suivi_consigne` : si le dossier contient un fait « CONSIGNE ACTIVE », rapporte \
son état factuel (métrique de la game vs objectif) ; sinon mets null.

Réponds uniquement au format JSON demandé."""

_CLAIM = {
    "type": "object",
    "properties": {
        "texte": {"type": "string"},
        "fact_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["texte", "fact_ids"],
    "additionalProperties": False,
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "resume": {
            "type": "string",
            "description": "2-3 phrases factuelles résumant le déroulé de la game",
        },
        "faits_marquants": {
            "type": "array",
            "description": "2 à 3 écarts saillants vs la norme perso, chacun sourcé",
            "items": _CLAIM,
        },
        "point_a_revoir": {
            "type": "object",
            "description": "UN élément factuel défavorable, décrit sans conseil",
            "properties": _CLAIM["properties"],
            "required": ["texte", "fact_ids"],
            "additionalProperties": False,
        },
        "tags": {
            "type": "array",
            "description": "1 à 3 tags de la taxonomie fermée, soutenus par les faits",
            "items": {"type": "string", "enum": sorted(TAGS)},
        },
        "question_replay": {
            "type": "string",
            "description": "UNE question factuelle orientant la relecture du replay",
        },
        "suivi_consigne": {
            "type": ["string", "null"],
            "description": "état factuel de la consigne active si présente au dossier, sinon null",
        },
        "limites": {
            "type": "string",
            "description": "1 phrase : ce que la donnée ne permet PAS de dire sur cette game",
        },
    },
    "required": [
        "resume", "faits_marquants", "point_a_revoir", "tags",
        "question_replay", "suivi_consigne", "limites",
    ],
    "additionalProperties": False,
}
