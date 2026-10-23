"""Comparaison de numéros de version et conditions de compatibilité.

Les numéros sont comparés nombre par nombre, pas comme du texte :
  1.4 < 1.10 < 2.0        (en texte, « 1.10 » serait avant « 1.4 »)
  1.4 = 1.4.0             (les zéros de fin ne comptent pas)
  2.3.0-SNAPSHOT < 2.3.0  (une version avec suffixe précède la version finale)
"""

from app.schemas import ConditionType


def key(number: str) -> tuple:
    """Transforme un numéro (« 2.3.0-SNAPSHOT ») en valeur comparable."""
    main, _, suffix = number.partition("-")
    numbers = [int(n) for n in main.split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    # Sans suffixe (1) passe après avec suffixe (0) : 2.3.0-SNAPSHOT < 2.3.0.
    return tuple(numbers), 0 if suffix else 1, suffix


def satisfied(number: str, condition: ConditionType, version: str, version_max: str | None = None) -> bool:
    """Vrai si la version « numero » respecte la condition."""
    if condition == ConditionType.EXACT:
        return key(number) == key(version)
    if condition == ConditionType.AT_LEAST:
        return key(number) >= key(version)
    if version_max is None:  # BETWEEN sans borne haute : impossible à la saisie
        raise ValueError("La condition BETWEEN demande une version_max")
    return key(version) <= key(number) <= key(version_max)  # BETWEEN, bornes comprises


def describe(condition: ConditionType, version: str, version_max: str | None = None) -> str:
    """La condition en français, pour les messages d'erreur."""
    if condition == ConditionType.EXACT:
        return f"en {version}"
    if condition == ConditionType.AT_LEAST:
        return f"en {version} ou plus"
    return f"entre {version} et {version_max}"
