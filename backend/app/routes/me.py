"""Routes /api/me : la personne (ou le programme) connectée, d'après son jeton Keycloak.

  GET   /api/me   200  qui suis-je (identifiant, nom, sorte, rôle) et mes préférences (thème)
  PATCH /api/me   200  mes préférences : { "theme": "AUTO" | "LIGHT" | "DARK" } | 422 valeur inconnue
  DELETE /api/me/offline-access   204  ferme mes accès par script : mes jetons hors ligne ne marchent
                                          plus (PERSON) | 422 programme | 503 Keycloak injoignable

Le mot de passe se change sur la page de Keycloak (à l'allure de l'outil), où l'interface envoie
la personne depuis « Mon compte » : l'API n'en voit jamais aucun.

Les préférences sont gardées dans notre base (table « preferences »), repérées par l'identifiant
Keycloak de la personne (« sub ») : il ne change jamais, même si l'identifiant de connexion change.
"""

from fastapi import APIRouter, HTTPException, Request, status

from app.access import IdentityDep
from app.routes import StorageDep
from app.routes.accounts import KeycloakErrors, directory_of
from app.schemas import AccountKind, Me, MyPreferences, Theme
from app.security import Identity
from app.storage import Storage

router = APIRouter(prefix="/me", tags=["Mon compte"])


def _me(identity: Identity, storage: Storage) -> dict:
    preferences = storage.preferences.find(subject=identity.subject)
    return {
        "identifier": identity.identifier,
        "name": identity.name,
        "kind": identity.kind,
        "role": identity.role,
        "theme": preferences["theme"] if preferences else Theme.AUTO,
    }


@router.get("", response_model=Me, summary="Mon compte")
def me(identity: IdentityDep, storage: StorageDep):
    return _me(identity, storage)


@router.patch(
    "",
    response_model=Me,
    summary="Changer mes préférences",
    description="Seuls les champs envoyés sont modifiés. Aujourd'hui : le thème de couleurs de l'interface.",
)
def change_preferences(data: MyPreferences, identity: IdentityDep, storage: StorageDep):
    changes = data.model_dump(exclude_unset=True)
    if changes:
        preferences = storage.preferences.find(subject=identity.subject)
        if preferences is None:
            storage.preferences.add({"subject": identity.subject, "theme": Theme.AUTO, **changes})
        else:
            storage.preferences.update(preferences["id"], changes)
    return _me(identity, storage)


@router.delete(
    "/offline-access",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Fermer mes accès par script",
    description="Mes jetons hors ligne (scripts) ne marchent plus : chaque script devra se reconnecter. "
    "Ma connexion à l'interface n'est pas touchée.",
)
def close_offline_access(request: Request, identity: IdentityDep) -> None:
    if identity.kind != AccountKind.PERSON:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Un PROGRAM n'a pas de jeton hors ligne")
    with KeycloakErrors():
        directory_of(request).close_offline_access(identity.subject)
