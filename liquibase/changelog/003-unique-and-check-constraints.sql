--liquibase formatted sql

-- Unicités et contrôles : la base refuse elle-même ce qui serait faux, en filet de sécurité
-- derrière l'API (qui vérifie la même chose avant, avec un message en français).
--   uq_<table>_<colonnes>   unicité : deux lignes ne peuvent pas avoir ces mêmes valeurs ;
--   ck_<table>_<règle>      contrôle : une condition toujours vraie pour chaque ligne.
-- Les règles d'ensemble (versions compatibles, pas de snapshot en prod…) restent dans l'API
-- (backend/app/consistency.py).

--changeset suivi-delivery:003-01-environments
--comment: Environnements : code unique, en minuscules ; ordre de promotion à partir de 1.
alter table environments add constraint uq_environments_code            unique (code);
alter table environments add constraint ck_environments_code_lowercase  check (code = lower(code));
alter table environments add constraint ck_environments_promotion_order check (promotion_order >= 1);
--rollback alter table environments drop constraint ck_environments_promotion_order;
--rollback alter table environments drop constraint ck_environments_code_lowercase;
--rollback alter table environments drop constraint uq_environments_code;

--changeset suivi-delivery:003-02-clusters
--comment: Clusters : code unique, en minuscules.
alter table clusters add constraint uq_clusters_code           unique (code);
alter table clusters add constraint ck_clusters_code_lowercase check (code = lower(code));
--rollback alter table clusters drop constraint ck_clusters_code_lowercase;
--rollback alter table clusters drop constraint uq_clusters_code;

--changeset suivi-delivery:003-03-network-zones
--comment: Zones réseau : code unique, en minuscules (affiché en majuscules par l'interface).
alter table network_zones add constraint uq_network_zones_code           unique (code);
alter table network_zones add constraint ck_network_zones_code_lowercase check (code = lower(code));
--rollback alter table network_zones drop constraint ck_network_zones_code_lowercase;
--rollback alter table network_zones drop constraint uq_network_zones_code;

--changeset suivi-delivery:003-04-applications
--comment: Applications : identifiant unique partout, en minuscules ; trigramme de 3 lettres ou chiffres minuscules.
alter table applications add constraint uq_applications_identifier           unique (identifier);
alter table applications add constraint ck_applications_identifier_lowercase check (identifier = lower(identifier));
alter table applications add constraint ck_applications_trigram              check (trigram ~ '^[a-z0-9]{3}$');
--rollback alter table applications drop constraint ck_applications_trigram;
--rollback alter table applications drop constraint ck_applications_identifier_lowercase;
--rollback alter table applications drop constraint uq_applications_identifier;

--changeset suivi-delivery:003-05-namespaces
--comment: Namespaces : un seul par application, environnement, cluster et suffixe ; suffixe en minuscules.
alter table namespaces add constraint uq_namespaces_application_environment_cluster_suffix
    unique (application_id, environment_id, cluster_id, suffix);
alter table namespaces add constraint ck_namespaces_suffix_lowercase check (suffix = lower(suffix));
--rollback alter table namespaces drop constraint ck_namespaces_suffix_lowercase;
--rollback alter table namespaces drop constraint uq_namespaces_application_environment_cluster_suffix;

--changeset suivi-delivery:003-06-modules
--comment: Modules : code unique dans l'application, en minuscules ; type CAPABILITY ou BUSINESS_PROJECT.
alter table modules add constraint uq_modules_application_code unique (application_id, code);
alter table modules add constraint ck_modules_code_lowercase   check (code = lower(code));
alter table modules add constraint ck_modules_type             check (type in ('CAPABILITY', 'BUSINESS_PROJECT'));
--rollback alter table modules drop constraint ck_modules_type;
--rollback alter table modules drop constraint ck_modules_code_lowercase;
--rollback alter table modules drop constraint uq_modules_application_code;

--changeset suivi-delivery:003-07-dependencies
--comment: Dépendances : une seule fois chaque couple ; un module ne dépend pas de lui-même.
alter table dependencies add constraint uq_dependencies_module_depends_on unique (module_id, depends_on_id);
alter table dependencies add constraint ck_dependencies_not_self          check (module_id <> depends_on_id);
--rollback alter table dependencies drop constraint ck_dependencies_not_self;
--rollback alter table dependencies drop constraint uq_dependencies_module_depends_on;

--changeset suivi-delivery:003-08-module-versions
--comment: Versions de module : numéro unique pour le module ; type RELEASE ou SNAPSHOT.
alter table module_versions add constraint uq_module_versions_module_number unique (module_id, number);
alter table module_versions add constraint ck_module_versions_type          check (type in ('RELEASE', 'SNAPSHOT'));
--rollback alter table module_versions drop constraint ck_module_versions_type;
--rollback alter table module_versions drop constraint uq_module_versions_module_number;

--changeset suivi-delivery:003-09-compatibilities
--comment: Compatibilités : une seule par version et module requis ; condition connue ; borne haute seulement pour BETWEEN.
alter table compatibilities add constraint uq_compatibilities_module_version_required_module unique (module_version_id, required_module_id);
alter table compatibilities add constraint ck_compatibilities_condition                      check (condition in ('EXACT', 'AT_LEAST', 'BETWEEN'));
alter table compatibilities add constraint ck_compatibilities_version_max                    check ((condition = 'BETWEEN') = (version_max is not null));
--rollback alter table compatibilities drop constraint ck_compatibilities_version_max;
--rollback alter table compatibilities drop constraint ck_compatibilities_condition;
--rollback alter table compatibilities drop constraint uq_compatibilities_module_version_required_module;

--changeset suivi-delivery:003-10-parameters
--comment: Paramètres : nom unique par module et type, en minuscules ; type TECHNICAL ou APPLICATION.
alter table parameters add constraint uq_parameters_module_type_name unique (module_id, type, name);
alter table parameters add constraint ck_parameters_name_lowercase   check (name = lower(name));
alter table parameters add constraint ck_parameters_type             check (type in ('TECHNICAL', 'APPLICATION'));
--rollback alter table parameters drop constraint ck_parameters_type;
--rollback alter table parameters drop constraint ck_parameters_name_lowercase;
--rollback alter table parameters drop constraint uq_parameters_module_type_name;

--changeset suivi-delivery:003-11-slots
--comment: Emplacements : nom de release unique dans le namespace, en minuscules.
alter table slots add constraint uq_slots_namespace_release_name unique (namespace_id, release_name);
alter table slots add constraint ck_slots_release_name_lowercase check (release_name = lower(release_name));
--rollback alter table slots drop constraint ck_slots_release_name_lowercase;
--rollback alter table slots drop constraint uq_slots_namespace_release_name;

--changeset suivi-delivery:003-12-preferences
--comment: Préférences : une seule ligne par personne ; thème connu.
alter table preferences add constraint uq_preferences_subject unique (subject);
alter table preferences add constraint ck_preferences_theme   check (theme in ('AUTO', 'LIGHT', 'DARK'));
--rollback alter table preferences drop constraint ck_preferences_theme;
--rollback alter table preferences drop constraint uq_preferences_subject;

--changeset suivi-delivery:003-13-audit-log
--comment: Journal : action et sorte d'auteur connues ; toujours un « avant » ou un « après ».
alter table audit_log add constraint ck_audit_log_action       check (action in ('CREATE', 'UPDATE', 'DELETE'));
alter table audit_log add constraint ck_audit_log_author_kind  check (author_kind in ('PERSON', 'PROGRAM'));
alter table audit_log add constraint ck_audit_log_before_after check (before is not null or after is not null);
--rollback alter table audit_log drop constraint ck_audit_log_before_after;
--rollback alter table audit_log drop constraint ck_audit_log_author_kind;
--rollback alter table audit_log drop constraint ck_audit_log_action;
