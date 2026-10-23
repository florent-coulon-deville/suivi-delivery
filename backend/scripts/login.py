"""Connexion d'un script à l'API, par Keycloak (sans jamais envoyer le mot de passe d'une personne).

Trois façons, essayées dans cet ordre (variables d'environnement) :
  1. PROGRAM : API_CLIENT_ID et API_CLIENT_SECRET, son identifiant et sa clé (créés par
     l'administrateur dans l'écran Comptes) → « client credentials » ;
  2. PERSON, jeton hors ligne : API_OFFLINE_TOKEN, obtenu une fois avec ce script (voir plus
     bas) → échangé à chaque lancement contre un jeton d'accès, à son nom et avec ses droits ;
  3. PERSON, sans rien : le script affiche une adresse et un code ; on les ouvre dans le
     navigateur, on se connecte sur la page de l'outil, et le script continue (« connexion d'un
     appareil », OAuth 2.0 Device Authorization Grant).

Obtenir un jeton hors ligne (valable 30 jours sans servir, 1 an au plus ; « Mon compte » →
« Fermer mes accès par script » de l'interface les annule tous ; un compte désactivé ne peut plus
s'en servir) :
    uv run python -m scripts.login
puis le garder dans API_OFFLINE_TOKEN (jamais dans un fichier suivi par Git).

Adresse de Keycloak : KEYCLOAK_URL, celle que voit le navigateur, sous l'interface
(défaut : http://localhost:8080/auth) ; domaine : KEYCLOAK_REALM (défaut : suivi-delivery).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

KEYCLOAK = (os.environ.get("KEYCLOAK_URL") or "http://localhost:8080/auth").rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM") or "suivi-delivery"
OIDC = f"{KEYCLOAK}/realms/{REALM}/protocol/openid-connect"
CLIENT_TOOLS = "suivi-delivery-tools"  # client public de Keycloak pour les outils et scripts


def _send(url: str, fields: dict[str, str]) -> tuple[int, dict]:
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, method="POST")  # noqa: S310 (adresse de nos réglages)
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")
    except urllib.error.URLError as error:
        sys.exit(f"Keycloak injoignable sur {KEYCLOAK} ({error.reason}) : vérifier KEYCLOAK_URL")


def _tokens(fields: dict[str, str]) -> dict:
    status, content = _send(f"{OIDC}/token", fields)
    if status != 200:
        sys.exit(f"Connexion refusée par Keycloak : {content.get('error_description') or content.get('error')}")
    return content


def device_login(scope: str = "openid") -> dict:
    """Connexion d'une personne dans son navigateur : renvoie les jetons une fois la connexion faite."""
    status, device = _send(f"{OIDC}/auth/device", {"client_id": CLIENT_TOOLS, "scope": scope})
    if status != 200:
        sys.exit(f"Connexion d'un appareil refusée : {device.get('error_description') or device.get('error')}")
    print(f"Ouvrez {device['verification_uri_complete']}")
    print(f"(ou {device['verification_uri']} avec le code {device['user_code']}), puis connectez-vous.")
    pause = int(device.get("interval", 5))
    end = time.monotonic() + int(device.get("expires_in", 600))
    while time.monotonic() < end:
        time.sleep(pause)
        fields = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device["device_code"],
            "client_id": CLIENT_TOOLS,
        }
        status, content = _send(f"{OIDC}/token", fields)
        if status == 200:
            return content
        if content.get("error") == "slow_down":
            pause += 5
        elif content.get("error") != "authorization_pending":
            sys.exit(f"Connexion refusée : {content.get('error_description') or content.get('error')}")
    sys.exit("Connexion non faite à temps : recommencer")


def access_token() -> str:
    """Un jeton d'accès à l'API, selon les variables d'environnement (voir en tête du fichier)."""
    client_id, key = os.environ.get("API_CLIENT_ID"), os.environ.get("API_CLIENT_SECRET")
    if client_id and key:
        return _tokens({"grant_type": "client_credentials", "client_id": client_id, "client_secret": key})[
            "access_token"
        ]
    offline = os.environ.get("API_OFFLINE_TOKEN")
    if offline:
        fields = {"grant_type": "refresh_token", "refresh_token": offline.strip(), "client_id": CLIENT_TOOLS}
        return _tokens(fields)["access_token"]
    return device_login()["access_token"]


def main() -> None:
    """Affiche un jeton hors ligne, après une connexion dans le navigateur."""
    tokens = device_login(scope="openid offline_access")
    print("\nJeton hors ligne (à garder dans API_OFFLINE_TOKEN, comme un mot de passe) :\n")
    print(tokens["refresh_token"])


if __name__ == "__main__":
    main()
