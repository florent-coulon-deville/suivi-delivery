"""Charge un jeu de données de démonstration dans une API déjà démarrée.

L'API démarre vide (base neuve, ou données en mémoire) : ce script la remplit, pour avoir
quelque chose à regarder dans l'interface web. Il passe par les routes normales de l'API :
toutes les règles s'appliquent (une donnée incohérente ferait échouer le script).

Usage, depuis backend/, l'API étant démarrée (uv run python -m app --reload) :
    uv run python scripts/load_demo.py
    uv run python scripts/load_demo.py http://autre-adresse:8000
    API_URL=http://autre-adresse:8000 uv run python scripts/load_demo.py

Adresse de l'API : le paramètre s'il est donné, sinon la variable API_URL (la même que
celle du frontend), sinon http://127.0.0.1:8000.

Pas de connexion : cette version de l'outil n'a pas de comptes.
"""

import json
import os
import sys
import urllib.error
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("API_URL") or "http://127.0.0.1:8000"
API = URL.rstrip("/") + "/api"


def check() -> None:
    """Vérifie que l'API répond, avant de commencer (GET /api/environments)."""
    try:
        with urllib.request.urlopen(f"{API}/environments"):
            pass
    except urllib.error.URLError:
        sys.exit(f"API injoignable sur {API} : démarre-la d'abord (uv run python -m app --reload).")


def create(resource: str, **fields) -> dict:
    """POST /api/<ressource> ; arrête le script avec le message de l'API en cas de refus."""
    request = urllib.request.Request(
        f"{API}/{resource}",
        data=json.dumps(fields).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"Refus de l'API sur {resource} {fields} : {error.code} {error.read().decode()}")
    except urllib.error.URLError:
        sys.exit(f"API injoignable sur {API} : démarre-la d'abord (uv run python -m app --reload).")


# Version de travail du batch de paie : citée par une compatibilité et une installation.
BATCH_PAIE_SNAPSHOT = "2.4.0-SNAPSHOT"

MODULE_APPLICATION = {
    "auth": "socle",
    "journal": "socle",
    "batch-paie": "paiement",
    "web-paie": "paiement",
    "web-facture": "facture",
}


def main() -> None:
    check()
    applications = create_applications()
    namespaces = create_namespaces(applications, create_environments())
    modules = create_modules(applications)
    parameters_by_module = create_parameters(modules, namespaces)
    versions = create_versions(modules)
    create_compatibilities(modules, versions)
    install_all(Installer(namespaces, modules, versions, parameters_by_module))

    # Un emplacement réservé mais encore vide.
    create(
        "slots",
        namespace_id=namespaces["facture", "rec"]["id"],
        module_id=modules["web-facture"]["id"],
        release_name="web-facture",
    )

    print(f"Données de démonstration chargées dans {API}.")


# --- Listes ---


def create_environments() -> dict[str, dict]:
    return {
        "int": create("environments", code="int", label="Intégration", promotion_order=1),
        "rec": create("environments", code="rec", label="Recette", promotion_order=2),
        "preprod": create("environments", code="preprod", label="Pré-production", promotion_order=3),
        "prod": create("environments", code="prod", label="Production", is_prod=True, promotion_order=4),
    }


def create_network_zones() -> dict[str, dict]:
    """Des zones réseau d'exemple (code en minuscules ; l'interface l'affiche en majuscules)."""
    names = ["DMZ", "INTERNE", "PARTENAIRES", "ADMIN", "DEVOPS"]
    return {name.lower(): create("network-zones", code=name.lower(), label=name) for name in names}


# --- Applications, namespaces, paramètres, modules ---


def create_applications() -> dict[str, dict]:
    return {
        "socle": create("applications", identifier="socle", name="Socle commun", trigram="soc"),
        "paiement": create("applications", identifier="paiement", name="Paiement", trigram="pai"),
        "facture": create("applications", identifier="facture", name="Facturation", trigram="fac"),
    }


def create_namespaces(applications: dict[str, dict], env: dict[str, dict]) -> dict[tuple[str, str], dict]:
    """Un namespace par application et par environnement, sur le cluster du bon type."""
    non_prod = create("clusters", code="cb01", label="Cluster hors prod")
    prod = create("clusters", code="cb02", label="Cluster prod", is_prod=True)
    zones = create_network_zones()
    namespaces: dict[tuple[str, str], dict] = {}
    for app_name, application in applications.items():
        for code_env, environment in env.items():
            cluster = prod if environment["is_prod"] else non_prod
            namespaces[app_name, code_env] = create(
                "namespaces",
                application_id=application["id"],
                environment_id=environment["id"],
                cluster_id=cluster["id"],
                suffix="app",
                network_zone_id=zones["interne" if app_name == "socle" else "partenaires"]["id"],
            )
    return namespaces


def create_parameters(
    modules: dict[str, dict], namespaces: dict[tuple[str, str], dict]
) -> dict[tuple[str, str], list[dict]]:
    """Par module : deux paramètres techniques et deux applicatifs, nommés « 1 » et « 2 » (des
    versions), affectés à tous les namespaces de son application."""
    parameters: dict[tuple[str, str], list[dict]] = {}
    for code_module, module in modules.items():
        app_name = MODULE_APPLICATION[code_module]
        ids = [n["id"] for (app, _), n in namespaces.items() if app == app_name]
        for parameter_type in ("TECHNICAL", "APPLICATION"):
            parameters[code_module, parameter_type] = [
                create("parameters", module_id=module["id"], name=name, type=parameter_type, namespace_ids=ids)
                for name in ("1", "2")
            ]
    return parameters


def create_modules(applications: dict[str, dict]) -> dict[str, dict]:
    def module(code: str, name: str, module_type: str) -> dict:
        application_id = applications[MODULE_APPLICATION[code]]["id"]
        return create("modules", application_id=application_id, code=code, name=name, type=module_type)

    return {
        "auth": module("auth", "Authentification", "CAPABILITY"),
        "journal": module("journal", "Journalisation", "CAPABILITY"),
        "batch-paie": module("batch-paie", "Batch de paie", "BUSINESS_PROJECT"),
        "web-paie": module("web-paie", "Portail de paie", "BUSINESS_PROJECT"),
        "web-facture": module("web-facture", "Portail de facturation", "BUSINESS_PROJECT"),
    }


# --- Dépendances et versions ---


def create_versions(modules: dict[str, dict]) -> dict[tuple[str, str], dict]:
    """Les dépendances entre modules, puis les versions de chaque module."""
    for module, required in [
        ("batch-paie", "auth"),
        ("batch-paie", "journal"),
        ("web-paie", "auth"),
        ("web-facture", "auth"),
    ]:
        create("dependencies", module_id=modules[module]["id"], depends_on_id=modules[required]["id"])

    versions: dict[tuple[str, str], dict] = {}
    for module, numbers in {
        "auth": ["1.2.0", "1.4.0", "2.0.0", "2.1.0-SNAPSHOT"],
        "journal": ["3.0.0", "3.1.0"],
        "batch-paie": ["2.2.0", "2.3.0", BATCH_PAIE_SNAPSHOT],
        "web-paie": ["1.0.0", "1.1.0-SNAPSHOT"],
        "web-facture": ["0.9.0", "1.0.0"],
    }.items():
        for number in numbers:
            version_type = "SNAPSHOT" if number.endswith("SNAPSHOT") else "RELEASE"
            versions[module, number] = create(
                "module-versions", module_id=modules[module]["id"], number=number, type=version_type
            )
    return versions


def create_compatibilities(modules: dict[str, dict], versions: dict[tuple[str, str], dict]) -> None:
    """Le batch de paie 2.3 a besoin de l'authentification 1.4 ou plus, etc."""
    for (module, number), required, condition, version, version_max in [
        (("batch-paie", "2.3.0"), "auth", "AT_LEAST", "1.4.0", None),
        (("batch-paie", BATCH_PAIE_SNAPSHOT), "auth", "BETWEEN", "2.0.0", "2.9.9"),
        (("web-facture", "1.0.0"), "auth", "AT_LEAST", "1.4.0", None),
    ]:
        create(
            "compatibilities",
            module_version_id=versions[module, number]["id"],
            required_module_id=modules[required]["id"],
            condition=condition,
            version=version,
            version_max=version_max,
        )


# --- Emplacements et installations ---


class Installer:
    """Installe une version de module dans un environnement, en créant son emplacement la première fois."""

    def __init__(self, namespaces: dict, modules: dict, versions: dict, parameters_by_module: dict) -> None:
        self.namespaces = namespaces
        self.modules = modules
        self.versions = versions
        self.parameters_by_module = parameters_by_module
        self.slots: dict[tuple[str, str], dict] = {}

    def install(self, module: str, code_env: str, number: str, date: str, version_parameters: int = 0) -> None:
        app_name = MODULE_APPLICATION[module]
        if (module, code_env) not in self.slots:
            self.slots[module, code_env] = create(
                "slots",
                namespace_id=self.namespaces[app_name, code_env]["id"],
                module_id=self.modules[module]["id"],
                release_name=module,
            )
        create(
            "installations",
            slot_id=self.slots[module, code_env]["id"],
            module_version_id=self.versions[module, number]["id"],
            technical_parameter_id=self.parameters_by_module[module, "TECHNICAL"][version_parameters]["id"],
            application_parameter_id=self.parameters_by_module[module, "APPLICATION"][version_parameters]["id"],
            date=date,
        )


def install_all(installer: Installer) -> None:
    """Les installations, dans l'ordre : le socle d'abord."""
    install = installer.install

    # Production : releases uniquement.
    install("auth", "prod", "1.2.0", "2026-06-02T20:00:00Z")
    install("journal", "prod", "3.0.0", "2026-06-02T20:10:00Z")
    install("auth", "prod", "1.4.0", "2026-09-15T20:00:00Z", 1)
    install("batch-paie", "prod", "2.2.0", "2026-06-03T20:00:00Z")
    install("batch-paie", "prod", "2.3.0", "2026-09-16T20:00:00Z", 1)
    install("web-paie", "prod", "1.0.0", "2026-06-03T21:00:00Z")
    install("web-facture", "prod", "0.9.0", "2026-07-01T20:00:00Z")

    # Pré-production : la prochaine MEP.
    install("auth", "preprod", "2.0.0", "2026-10-01T09:00:00Z", 1)
    install("journal", "preprod", "3.1.0", "2026-10-01T09:30:00Z", 1)
    install("batch-paie", "preprod", "2.3.0", "2026-10-02T10:00:00Z", 1)
    install("web-facture", "preprod", "1.0.0", "2026-10-02T11:00:00Z", 1)

    # Recette et intégration : les versions de travail.
    install("auth", "rec", "2.0.0", "2026-09-20T09:00:00Z", 1)
    install("journal", "rec", "3.1.0", "2026-09-20T09:30:00Z", 1)
    install("web-paie", "rec", "1.0.0", "2026-09-21T10:00:00Z", 1)
    install("auth", "int", "2.1.0-SNAPSHOT", "2026-10-05T08:00:00Z", 1)
    install("journal", "int", "3.1.0", "2026-10-05T08:15:00Z", 1)
    install("batch-paie", "int", BATCH_PAIE_SNAPSHOT, "2026-10-06T08:00:00Z", 1)
    install("web-paie", "int", "1.1.0-SNAPSHOT", "2026-10-06T09:00:00Z", 1)


if __name__ == "__main__":
    main()
