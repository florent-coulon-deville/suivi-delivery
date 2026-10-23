# Keycloak : les comptes et la connexion

Keycloak garde les comptes et les mots de passe, affiche la page de connexion et fabrique les jetons de l'outil. Guide complet : [docs/keycloak.md](../docs/keycloak.md).

| Fichier | Rôle |
| --- | --- |
| `start.sh` | le démarrage : Keycloak, puis l'adresse de sa console d'administration (`KC_HOSTNAME_ADMIN`) donnée au domaine `master` |
| `Dockerfile` | l'image `suivi-delivery-keycloak-local` : Keycloak 26.7.4 (Docker Hardened Image, `dhi.io`), préparé pour PostgreSQL et l'adresse `/auth`, avec notre thème et notre domaine |
| `import/suivi-delivery.json` | le domaine « suivi-delivery » : rôles (VIEWER < EDITOR < ADMIN), clients (interface, outils, api), compte `admin`, durées, règles des mots de passe. **Importé au premier démarrage seulement** ; les `${…}` y sont remplacés par les variables d'environnement du même nom |
| `themes/suivi-delivery/login/` | le thème des pages de connexion, à l'allure de l'outil : `template.ftl` (le cadre), `login.ftl` et `login-update-password.ftl` (réécrites), `resources/css/suivi-delivery.css` (les couleurs de l'interface), `messages/messages_fr.properties` (les textes) |
| `docker.example.env` | modèle des réglages : sa base, son adresse publique, sa console, ce qu'il importe |

## Lancer

La base doit tourner (module [`postgres/`](../postgres/README.md)), préparée avec l'utilisateur et le schéma de Keycloak :

```bash
./deployment/docker-deploy.zsh keycloak
```

Le premier démarrage prend une à deux minutes (tables de Keycloak, import du domaine). Ses pages de connexion passent ensuite par l'interface : <http://localhost:8080/auth/…>. Sa console d'administration, sur ce poste seulement : <http://localhost:8081/auth/admin> (`KC_BOOTSTRAP_ADMIN_*` de `deployment/docker.env`).

## Modifier

- **Le thème** (allure des pages) : modifier les fichiers de `themes/`, puis `./deployment/docker-deploy.zsh keycloak`. Garder les couleurs de `resources/css/suivi-delivery.css` d'accord avec `frontend/app/styles.css`.
- **Le domaine** (rôles, clients, durées) : modifier `import/suivi-delivery.json`. Il n'est importé que dans une base neuve : sur le poste, `./deployment/docker-deploy.zsh --reset` ; sur un cluster déjà installé, faire le même changement dans la console de Keycloak.
