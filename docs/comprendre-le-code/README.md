# Comprendre le code du backend

Ce dossier explique **comment le code de l'API est découpé, et pourquoi**. Il se lit dans l'ordre : chaque page s'appuie sur la précédente. Les extraits de code viennent des vrais fichiers de `backend/app/`.

| # | Page | Fichier(s) expliqué(s) | Ce que tu y apprends |
| --- | --- | --- | --- |
| 1 | [Le découpage en modules](01-decoupage.md) | tout `backend/` | la carte des fichiers, qui utilise qui, et pourquoi c'est découpé ainsi |
| 2 | [Le démarrage](02-demarrage.md) | `main.py` | comment l'application est assemblée au lancement |
| 3 | [Le stockage](03-stockage.md) | `storage.py`, `storage_postgres.py`, `transactions.py`, `audit_log.py` | où vivent les données (mémoire ou PostgreSQL), comment on les lit et les écrit, une transaction par requête, le journal des actions |
| 4 | [Les schémas](04-schemas.md) | `schemas.py` | comment les données reçues sont vérifiées avant d'entrer dans le code |
| 5 | [Les routes : le modèle commun](05-routes.md) | `routes/__init__.py`, `routes/clusters.py` | l'anatomie d'une ressource : lire, créer, modifier, supprimer |
| 6 | [Les routes plus riches](06-routes-riches.md) | `routes/namespaces.py`, `installations.py`, `dependencies.py`, `configuration.py`, `import_configuration.py` | les vérifications métier propres à un objet ; l'export et l'import Excel |
| 7 | [La cohérence d'ensemble](07-coherence.md) | `consistency.py`, `versions.py` | les règles qui croisent plusieurs objets, et l'essai sur une copie |
| 8 | [Les règles HTTP](08-http.md) | `http.py` | HEAD, OPTIONS, l'en-tête Allow, et le choix entre 400, 404, 415 et 422 |
| 9 | [Les tests](09-tests.md) | `tests/` | comment le comportement est vérifié automatiquement |
| 10 | [Recette : ajouter une ressource](10-ajouter-une-ressource.md) | — | la marche à suivre, étape par étape |
| 11 | [La sécurité](11-securite.md) | `security.py`, `access.py`, `directory.py` | les jetons de Keycloak vérifiés à chaque appel, les droits, et les comptes gérés dans Keycloak |
| — | [Les notions Python utilisées](notions-python.md) | — | un aide-mémoire : dictionnaire, décorateur, `lambda`, `raise`… |

Si tu bloques sur une écriture Python (`**criteria`, `@router.get`, `lambda`…), regarde l'[aide-mémoire](notions-python.md).

Pour le **pourquoi** global (choix techniques, limites), voir aussi [../architecture.md](../architecture.md).
