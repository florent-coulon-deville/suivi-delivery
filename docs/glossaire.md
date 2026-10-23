# Glossaire : les mots métier et leur nom dans le code

Le code est **en anglais** : noms de variables, de fonctions, de classes, de fichiers, adresses de l'API, champs JSON, tables et colonnes de la base, clés du chart Helm, options des scripts. Les **commentaires**, la documentation et tous les textes affichés (écrans, messages d'erreur, onglets du fichier Excel) restent **en français**.

Ce tableau donne, pour chaque mot métier, le nom utilisé dans le code.

## Les objets

| Mot métier | Dans le code | Exemples |
| --- | --- | --- |
| environnement (libellé, prod, ordre de promotion) | `environment` (`label`, `is_prod`, `promotion_order`) | table `environments`, `/api/environments` |
| cluster | `cluster` | `/api/clusters` |
| zone réseau | `network_zone` | table `network_zones`, `/api/network-zones` |
| application (identifiant, nom, trigramme) | `application` (`identifier`, `name`, `trigram`) | `/api/applications` |
| namespace (suffixe) | `namespace` (`suffix`) | `/api/namespaces`, `/api/namespaces/batch` (création groupée) |
| module : capacité, projet métier | `module` : `CAPABILITY`, `BUSINESS_PROJECT` | `/api/modules` |
| dépendance (« dépend de ») | `dependency` (`depends_on_id`) | table `dependencies` |
| version de module (numéro) | `module_version` (`number`) | table `module_versions`, `/api/module-versions` |
| compatibilité (module requis ; exacte, à partir de, entre) | `compatibility` (`required_module_id` ; `EXACT`, `AT_LEAST`, `BETWEEN`) | table `compatibilities` |
| paramètre technique, applicatif (rang) | `parameter` : `TECHNICAL`, `APPLICATION` (`position`) | tables `parameters`, `parameter_namespaces` |
| emplacement (nom de release) | `slot` (`release_name`) | table `slots`, `/api/slots` |
| installation | `installation` (`slot_id`, `technical_parameter_id`, `application_parameter_id`) | `/api/installations` |
| journal des actions (auteur, sorte, objet, avant, après) | `audit_log` (`author`, `author_kind`, `object`, `before`, `after`) | `/api/audit-log`, écran `/audit-log` |
| création, modification, suppression | `CREATE`, `UPDATE`, `DELETE` | |
| personne, programme | `PERSON`, `PROGRAM` | |
| compte, mon compte | `account`, `me` | `/api/accounts`, `/api/me` |
| thème : automatique, clair, sombre | `theme` : `AUTO`, `LIGHT`, `DARK` | table `preferences` (`subject`) |
| rôles : consultation < saisie < administration | `VIEWER` < `EDITOR` < `ADMIN` | rôles du domaine Keycloak |
| aperçu d'un import | `dry_run` | `PATCH /api/configuration?dry_run=true` |

## Les briques techniques

| Mot | Dans le code |
| --- | --- |
| stockage (en mémoire, PostgreSQL) | `storage` (`MemoryStorage`, `PostgresStorage`) |
| réglages | `settings` (`app/settings.py`, `lib/settings.ts`) |
| sécurité, accès | `security`, `access` |
| annuaire (les comptes dans Keycloak) | `directory` |
| cohérence d'ensemble | `consistency` (`app/consistency.py`) |
| santé (probes) | `health` (`/health` pour l'interface) |
| saisie (l'espace de saisie de l'interface) | `edit` (page `/edit`) |
| connexion | `login` (pages `/login`, `/login/callback`, `/login/end`…) |
| écran « Ce qui tourne » | `view` (`components/view/`) |
| clients Keycloak : interface, outils | `suivi-delivery-frontend`, `suivi-delivery-tools` |

## Le poste, la CI et le chart

| Avant | Maintenant |
| --- | --- |
| dossier `deploiement/` | `deployment/` |
| options `--contexte`, `--espace`, `--valeurs`, `--registre`, `--oui`, `--reinitialiser`, `--aide` | `--context`, `--namespace`, `--values`, `--registry`, `--yes`, `--reset`, `--help` |
| chart : `images.registre`, `base.*`, `exemplaires`, `ressources`, `nomInstance`… | `images.registry`, `database.*`, `replicas`, `resources`, `instanceName`… (voir `values.yaml`) |
| modèles `*.exemple.env`, `values-*.exemple.yaml` | `*.example.env`, `values-*.example.yaml` |
