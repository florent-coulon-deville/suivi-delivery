"""Route /api/enumerations : les valeurs possibles des listes fermées (types de module, de version…).
Les zones réseau ne sont pas une liste fermée : ce sont des données (/api/network-zones).

L'interface s'en sert pour ses listes déroulantes : si une liste change ici (schemas.py),
l'interface suit sans modification. Indépendante de Swagger : elle marche aussi avec APP_DOCS=non.

  GET /api/enumerations   200  { "ModuleType": [...], "VersionType": [...], ... }
"""

from enum import StrEnum

from fastapi import APIRouter

from app.schemas import ConditionType, ModuleType, ParameterType, VersionType

router = APIRouter(prefix="/enumerations", tags=["Énumérations"])

# Les listes fermées des données métier (pas celles de la sécurité).
ENUMERATIONS: list[type[StrEnum]] = [ModuleType, VersionType, ParameterType, ConditionType]


@router.get("", response_model=dict[str, list[str]], summary="Valeurs des listes fermées")
def list_all():
    return {enumeration.__name__: [value.value for value in enumeration] for enumeration in ENUMERATIONS}
