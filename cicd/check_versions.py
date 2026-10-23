"""Vérifie que toute l'application a UN SEUL numéro de version, partout le même :

    backend/pyproject.toml          [project] version
    backend/uv.lock                 version du paquet du projet (suivi-delivery-backend)
    frontend/package.json           "version"
    frontend/package-lock.json      "version" (racine et paquet du projet)
    helm/suivi-delivery/Chart.yaml  version et appVersion (le chart suit la version de l'application)

Usage, depuis la racine du projet (Python 3.11 ou plus, rien à installer ; sur Mac, le Python
du système est trop ancien : prendre celui du projet) :
    backend/.venv/bin/python cicd/check_versions.py
Sort en erreur (code 1), avec la liste des numéros trouvés, s'ils ne sont pas tous égaux.
Lancé par la CI (.github/workflows/ci-version.yml). Les numéros sont changés ensemble par
release-please (release-please-config.json, voir docs/ci.md § 5).
"""

import json
import re
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent


def chart_version(field: str) -> str:
    """Lit « version » ou « appVersion » de Chart.yaml (sans bibliothèque YAML : une ligne simple)."""
    text = (ROOT / "helm" / "suivi-delivery" / "Chart.yaml").read_text()
    found = re.search(rf"^{field}:\s*[\"']?([^\"'\s#]+)", text, re.MULTILINE)
    return found.group(1) if found else "(absent)"


def backend_lock_version() -> str:
    """Lit dans uv.lock la version du paquet du projet (recopiée de pyproject.toml par uv lock)."""
    lock = tomllib.loads((ROOT / "backend" / "uv.lock").read_text())
    found = [package["version"] for package in lock["package"] if package["name"] == "suivi-delivery-backend"]
    return found[0] if found else "(absent)"


def main() -> int:
    package = json.loads((ROOT / "frontend" / "package.json").read_text())
    lock = json.loads((ROOT / "frontend" / "package-lock.json").read_text())
    versions = {
        "backend/pyproject.toml": tomllib.loads(
            (ROOT / "backend" / "pyproject.toml").read_text()
        )["project"]["version"],
        "backend/uv.lock": backend_lock_version(),
        "frontend/package.json": package["version"],
        "frontend/package-lock.json": lock["version"],
        "frontend/package-lock.json (paquet)": lock["packages"][""]["version"],
        "helm/suivi-delivery/Chart.yaml version": chart_version("version"),
        "helm/suivi-delivery/Chart.yaml appVersion": chart_version("appVersion"),
    }
    for file, version in versions.items():
        print(f"  {version:<12} {file}")
    if len(set(versions.values())) != 1:
        print(
            "Les numéros de version ne sont pas tous égaux : release-please les change ensemble (voir docs/ci.md § 5)."
        )
        return 1
    print(f"Version unique : {next(iter(versions.values()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
