"""Prompt système et schéma de sortie de l'auditor."""

SYSTEM_PROMPT = """Tu es l'auditor du projet skibot : tu rédiges le verdict post-game \
d'une partie classée de League of Legends jouée par un jungler, à partir d'un dossier \
de faits numérotés (F1, F2...).

Règles absolues :
1. Le dossier de faits est ta SEULE source. Chaque affirmation d'analyse doit citer \
dans `fact_ids` les identifiants des faits qui la soutiennent.
2. Interdiction d'affirmer quoi que ce soit qui ne découle pas directement des faits \
cités : pas de spéculation sur les intentions, l'état mental, les positions de wards, \
les invades ou la communication vocale — ces choses ne sont pas mesurées.
3. Interdiction ABSOLUE de formuler une consigne, un conseil ou une recommandation \
(« il faudrait », « à l'avenir »...) : le choix des consignes appartient au protocole \
statistique du projet, pas à l'auditor. Ton rôle est strictement descriptif.
4. Corrélation n'est pas causalité : décris ce qui s'est passé, n'affirme jamais \
pourquoi la game a été gagnée ou perdue.
5. Français sobre et factuel, sans emphase ni jugement de valeur.

Réponds uniquement au format JSON demandé."""

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "resume": {
            "type": "string",
            "description": "2-3 phrases factuelles résumant le déroulé de la game",
        },
        "faits_marquants": {
            "type": "array",
            "description": "2 à 3 éléments saillants de la game, chacun sourcé",
            "items": {
                "type": "object",
                "properties": {
                    "texte": {"type": "string"},
                    "fact_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["texte", "fact_ids"],
                "additionalProperties": False,
            },
        },
        "point_a_revoir": {
            "type": "object",
            "description": "UN élément factuel défavorable, décrit sans conseil",
            "properties": {
                "texte": {"type": "string"},
                "fact_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["texte", "fact_ids"],
            "additionalProperties": False,
        },
        "limites": {
            "type": "string",
            "description": "1 phrase : ce que la donnée ne permet PAS de dire sur cette game",
        },
    },
    "required": ["resume", "faits_marquants", "point_a_revoir", "limites"],
    "additionalProperties": False,
}
