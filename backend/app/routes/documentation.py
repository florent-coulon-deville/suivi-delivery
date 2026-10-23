"""Documentation de l'API : Swagger et sa description OpenAPI (masquées si APP_DOCS=non).

  GET /api/docs                   la page Swagger (essayer les appels, bouton « Authorize »)
  GET /api/docs/oauth2-redirect   page de retour de Swagger après une connexion
  GET /api/openapi.json           la description OpenAPI, lue par Swagger, Bruno, Postman…

Ces routes remplacent celles que FastAPI crée tout seul, pour deux retouches de la description,
qui permettent à Bruno (ou Postman) de régler la connexion tout seul à l'import :
  1. la connexion est déclarée UNE fois, pour toute l'API (« security » à la racine) : l'outil la
     règle sur la collection, et chaque requête en hérite. Les routes sans jeton (probes…) sont
     marquées « security: [] » ;
  2. les adresses de Keycloak sont complètes : la page de connexion (authorization code + PKCE,
     pour une personne) et l'adresse des jetons (aussi pour un programme, client credentials),
     telles que les voit le navigateur (<APP_FRONTEND_URL>/auth/realms/suivi-delivery/…).
Swagger se présente avec le client « suivi-delivery-tools » de Keycloak (public, PKCE).
"""

import copy

from fastapi import APIRouter, Request
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse, JSONResponse

OPENAPI = "/api/openapi.json"
DOCS = "/api/docs"
CALLBACK = "/api/docs/oauth2-redirect"
CLIENT_TOOLS = "suivi-delivery-tools"  # client Keycloak des outils (keycloak/import/suivi-delivery.json)

router = APIRouter(include_in_schema=False)


@router.get(OPENAPI)
def description(request: Request) -> JSONResponse:
    return JSONResponse(describe_login(request.app.openapi(), request.app.state.security.issuer))


@router.get(DOCS)
def swagger(request: Request) -> HTMLResponse:
    init_oauth = {"clientId": CLIENT_TOOLS, "usePkceWithAuthorizationCodeGrant": True, "scopes": "openid"}
    return get_swagger_ui_html(
        openapi_url=OPENAPI, title=f"{request.app.title} - Swagger", oauth2_redirect_url=CALLBACK, init_oauth=init_oauth
    )


@router.get(CALLBACK)
def swagger_callback() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()


def describe_login(schema: dict, issuer: str) -> dict:
    """La description OpenAPI, avec la connexion déclarée pour toute l'API et les adresses de Keycloak
    complètes (emetteur : le domaine de l'outil, vu du navigateur)."""
    schema = copy.deepcopy(schema)  # celle de FastAPI est gardée en cache : on n'y touche pas
    login_schemes = schema["components"]["securitySchemes"]
    connection = [{name: []} for name in login_schemes]
    schema["security"] = connection
    for operations in schema["paths"].values():
        for operation in operations.values():
            if "security" not in operation:
                operation["security"] = []  # route ouverte sans jeton
            elif _names(operation["security"]) == _names(connection):
                del operation["security"]  # même connexion que toute l'API : héritée
    oidc = f"{issuer}/protocol/openid-connect"
    flow = login_schemes["Connexion"]["flows"]
    # La page de connexion en premier : c'est le mode que Bruno (ou Postman) choisit à l'import.
    flow = login_schemes["Connexion"]["flows"] = dict(sorted(flow.items(), key=lambda f: f[0] != "authorizationCode"))
    for name, detail in flow.items():
        if name == "authorizationCode":
            detail["authorizationUrl"] = f"{oidc}/auth"
        detail["tokenUrl"] = detail["refreshUrl"] = f"{oidc}/token"
    return schema


def _names(security: list[dict]) -> set[str]:
    return {name for requirement in security for name in requirement}
