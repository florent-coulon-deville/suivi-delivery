-- Version 1 de la structure de la base SQLite : les tables du suivi de la delivery.
--
-- Ce fichier est appliqué par l'API elle-même, au premier démarrage sur une base neuve
-- (app/storage_sqlite.py) : il n'y a pas d'outil à part (comme Liquibase) à lancer avant.
--
-- Règles, pour faire évoluer la structure plus tard :
--   - on AJOUTE un fichier numéroté (002-….sql, 003-….sql…) : l'API applique, dans l'ordre, ceux
--     que la base n'a pas encore ;
--   - on ne MODIFIE JAMAIS un fichier déjà appliqué sur une base qui sert : il ne serait pas rejoué.
-- La base retient le numéro du dernier fichier appliqué (PRAGMA user_version).
--
-- Chaque fichier est appliqué dans une transaction : entièrement, ou pas du tout.
--
-- Contraintes nommées (pk_, uq_, ck_, fk_) : la base refuse elle-même ce qui serait faux, en
-- filet de sécurité derrière l'API (qui vérifie la même chose avant, avec un message en
-- français). Les règles d'ensemble (versions compatibles, pas de snapshot en prod…) restent
-- dans l'API (app/consistency.py).
--
-- Types : SQLite range tout en texte, nombre entier ou réel. Les booléens sont des entiers 0 / 1,
-- les dates du texte ISO 8601 en UTC (ex. 2026-10-09T08:30:00+00:00), l'avant / après du
-- journal du texte JSON. app/storage_sqlite.py les convertit à la lecture.
--
-- Identifiants : « integer primary key autoincrement » = numérotés par la base (1, 2, 3…),
-- jamais réutilisés après une suppression.


-- ===== Listes gérées dans l'outil ============================================

-- Environnements (int, rec, prod...), avec leur ordre de promotion facultatif.
create table environments (
    id              integer      not null constraint pk_environments primary key autoincrement,
    code            varchar(30)  not null constraint uq_environments_code unique,
    label           varchar(100) not null,
    is_prod         boolean      not null default 0,
    promotion_order integer,
    constraint ck_environments_code_lowercase  check (code = lower(code)),
    constraint ck_environments_promotion_order check (promotion_order >= 1)
);

-- Clusters OpenShift, de prod ou de hors prod.
create table clusters (
    id      integer      not null constraint pk_clusters primary key autoincrement,
    code    varchar(30)  not null constraint uq_clusters_code unique,
    label   varchar(100) not null,
    is_prod boolean      not null default 0,
    constraint ck_clusters_code_lowercase check (code = lower(code))
);

-- Zones réseau des namespaces (dmz, interne...).
create table network_zones (
    id    integer      not null constraint pk_network_zones primary key autoincrement,
    code  varchar(30)  not null constraint uq_network_zones_code unique,
    label varchar(100) not null,
    constraint ck_network_zones_code_lowercase check (code = lower(code))
);


-- ===== Commande des ressources ===============================================

-- Applications : identifiant unique partout, trigramme partageable (3 lettres ou chiffres minuscules).
create table applications (
    id         integer      not null constraint pk_applications primary key autoincrement,
    identifier varchar(30)  not null constraint uq_applications_identifier unique,
    name       varchar(100) not null,
    trigram    char(3)      not null,
    constraint ck_applications_identifier_lowercase check (identifier = lower(identifier)),
    constraint ck_applications_trigram check (length(trigram) = 3 and trigram not glob '*[^a-z0-9]*')
);

-- Namespaces OpenShift d'une application, par environnement et cluster. Le nom est calculé par l'API.
create table namespaces (
    id              integer     not null constraint pk_namespaces primary key autoincrement,
    application_id  integer     not null constraint fk_namespaces_application references applications (id),
    environment_id  integer     not null constraint fk_namespaces_environment references environments (id),
    cluster_id      integer     not null constraint fk_namespaces_cluster references clusters (id),
    suffix          varchar(30) not null,
    network_zone_id integer     not null constraint fk_namespaces_network_zone references network_zones (id),
    constraint uq_namespaces_application_environment_cluster_suffix
        unique (application_id, environment_id, cluster_id, suffix),
    constraint ck_namespaces_suffix_lowercase check (suffix = lower(suffix))
);

-- Modules (programmes) d'une application : CAPABILITY (socle) ou BUSINESS_PROJECT.
create table modules (
    id             integer      not null constraint pk_modules primary key autoincrement,
    application_id integer      not null constraint fk_modules_application references applications (id),
    code           varchar(30)  not null,
    name           varchar(100) not null,
    type           varchar(20)  not null,
    constraint uq_modules_application_code unique (application_id, code),
    constraint ck_modules_code_lowercase check (code = lower(code)),
    constraint ck_modules_type check (type in ('CAPABILITY', 'BUSINESS_PROJECT'))
);

-- Le module A (module_id) a besoin du module B (depends_on_id), y compris entre applications.
create table dependencies (
    id            integer not null constraint pk_dependencies primary key autoincrement,
    module_id     integer not null constraint fk_dependencies_module references modules (id),
    depends_on_id integer not null constraint fk_dependencies_depends_on references modules (id),
    constraint uq_dependencies_module_depends_on unique (module_id, depends_on_id),
    constraint ck_dependencies_not_self check (module_id <> depends_on_id)
);


-- ===== Déploiement ===========================================================

-- Versions d'un module : SNAPSHOT (par défaut) ou RELEASE.
create table module_versions (
    id        integer     not null constraint pk_module_versions primary key autoincrement,
    module_id integer     not null constraint fk_module_versions_module references modules (id),
    number    varchar(50) not null,
    type      varchar(20) not null default 'SNAPSHOT',
    constraint uq_module_versions_module_number unique (module_id, number),
    constraint ck_module_versions_type check (type in ('RELEASE', 'SNAPSHOT'))
);

-- Versions des modules requis compatibles avec une version de module (bornes comprises).
create table compatibilities (
    id                 integer     not null constraint pk_compatibilities primary key autoincrement,
    module_version_id  integer     not null
        constraint fk_compatibilities_module_version references module_versions (id),
    required_module_id integer     not null constraint fk_compatibilities_required_module references modules (id),
    condition          varchar(20) not null,
    version            varchar(50) not null,
    version_max        varchar(50),
    constraint uq_compatibilities_module_version_required_module unique (module_version_id, required_module_id),
    constraint ck_compatibilities_condition check (condition in ('EXACT', 'AT_LEAST', 'BETWEEN')),
    constraint ck_compatibilities_version_max check ((condition = 'BETWEEN') = (version_max is not null))
);

-- Paramètres TECHNICAL ou APPLICATION d'un module : un nom libre (souvent une version).
create table parameters (
    id        integer     not null constraint pk_parameters primary key autoincrement,
    module_id integer     not null constraint fk_parameters_module references modules (id),
    name      varchar(50) not null,
    type      varchar(20) not null,
    constraint uq_parameters_module_type_name unique (module_id, type, name),
    constraint ck_parameters_name_lowercase check (name = lower(name)),
    constraint ck_parameters_type check (type in ('TECHNICAL', 'APPLICATION'))
);

-- Namespaces auxquels un paramètre est affecté (plusieurs pour plusieurs) ; position : ordre de la liste.
-- Ses lignes partent avec le paramètre (« on delete cascade »).
create table parameter_namespaces (
    parameter_id integer not null
        constraint fk_parameter_namespaces_parameter references parameters (id) on delete cascade,
    namespace_id integer not null constraint fk_parameter_namespaces_namespace references namespaces (id),
    position     integer not null,
    constraint pk_parameter_namespaces primary key (parameter_id, namespace_id)
);

-- Emplacements d'un namespace, réservés à un module, nommés par leur release Helm.
create table slots (
    id           integer     not null constraint pk_slots primary key autoincrement,
    namespace_id integer     not null constraint fk_slots_namespace references namespaces (id),
    module_id    integer     not null constraint fk_slots_module references modules (id),
    release_name varchar(30) not null,
    constraint uq_slots_namespace_release_name unique (namespace_id, release_name),
    constraint ck_slots_release_name_lowercase check (release_name = lower(release_name))
);

-- Historique : quelle version, avec quels paramètres, sur quel emplacement, à quelle date (texte ISO, UTC).
create table installations (
    id                       integer not null constraint pk_installations primary key autoincrement,
    slot_id                  integer not null constraint fk_installations_slot references slots (id),
    module_version_id        integer not null
        constraint fk_installations_module_version references module_versions (id),
    technical_parameter_id   integer not null
        constraint fk_installations_technical_parameter references parameters (id),
    application_parameter_id integer not null
        constraint fk_installations_application_parameter references parameters (id),
    date                     text    not null
);


-- ===== Journal des actions (app/audit_log.py) ==================================

-- Journal : quoi a été créé, modifié ou supprimé, et quand. Jamais modifié ni effacé.
-- Pas d'auteur : cette version de l'outil n'a pas de comptes.
create table audit_log (
    id        integer     not null constraint pk_audit_log primary key autoincrement,
    date      text        not null,
    object    varchar(50) not null,
    object_id varchar(64) not null,
    action    varchar(20) not null,
    before    text,
    after     text,
    constraint ck_audit_log_action check (action in ('CREATE', 'UPDATE', 'DELETE')),
    constraint ck_audit_log_before_after check (before is not null or after is not null)
);


-- ===== Index =================================================================
-- Des « sommaires » qui accélèrent les recherches. Nom : ix_<table>_<colonnes>.
-- Une contrainte d'unicité ou une clé primaire a déjà le sien ; on en ajoute un pour chaque
-- lien qui n'est pas déjà en tête d'une unicité, et pour les recherches du journal.

create index ix_namespaces_environment              on namespaces (environment_id);
create index ix_namespaces_cluster                  on namespaces (cluster_id);
create index ix_namespaces_network_zone             on namespaces (network_zone_id);
create index ix_dependencies_depends_on             on dependencies (depends_on_id);
create index ix_compatibilities_required_module     on compatibilities (required_module_id);
create index ix_parameters_module                   on parameters (module_id);
create index ix_parameter_namespaces_namespace      on parameter_namespaces (namespace_id);
create index ix_slots_module                        on slots (module_id);
create index ix_installations_slot_date             on installations (slot_id, date);
create index ix_installations_module_version        on installations (module_version_id);
create index ix_installations_technical_parameter   on installations (technical_parameter_id);
create index ix_installations_application_parameter on installations (application_parameter_id);
create index ix_audit_log_date                      on audit_log (date);
create index ix_audit_log_object                    on audit_log (object, object_id);
