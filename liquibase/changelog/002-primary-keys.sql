--liquibase formatted sql

-- Clés primaires : ce qui identifie une ligne. Nom : pk_<table>.

--changeset suivi-delivery:002-01-keys-primaires
--comment: Une clé primaire par table : l'identifiant (ou le couple, pour la table de liaison).
alter table environments         add constraint pk_environments         primary key (id);
alter table clusters             add constraint pk_clusters             primary key (id);
alter table network_zones        add constraint pk_network_zones        primary key (id);
alter table applications         add constraint pk_applications         primary key (id);
alter table namespaces           add constraint pk_namespaces           primary key (id);
alter table modules              add constraint pk_modules              primary key (id);
alter table dependencies         add constraint pk_dependencies         primary key (id);
alter table module_versions      add constraint pk_module_versions      primary key (id);
alter table compatibilities      add constraint pk_compatibilities      primary key (id);
alter table parameters           add constraint pk_parameters           primary key (id);
alter table parameter_namespaces add constraint pk_parameter_namespaces primary key (parameter_id, namespace_id);
alter table slots                add constraint pk_slots                primary key (id);
alter table installations        add constraint pk_installations        primary key (id);
alter table preferences          add constraint pk_preferences          primary key (id);
alter table audit_log            add constraint pk_audit_log            primary key (id);
--rollback alter table audit_log               drop constraint pk_audit_log;
--rollback alter table preferences           drop constraint pk_preferences;
--rollback alter table installations         drop constraint pk_installations;
--rollback alter table slots          drop constraint pk_slots;
--rollback alter table parameter_namespaces drop constraint pk_parameter_namespaces;
--rollback alter table parameters            drop constraint pk_parameters;
--rollback alter table compatibilities        drop constraint pk_compatibilities;
--rollback alter table module_versions      drop constraint pk_module_versions;
--rollback alter table dependencies           drop constraint pk_dependencies;
--rollback alter table modules               drop constraint pk_modules;
--rollback alter table namespaces            drop constraint pk_namespaces;
--rollback alter table applications          drop constraint pk_applications;
--rollback alter table network_zones          drop constraint pk_network_zones;
--rollback alter table clusters              drop constraint pk_clusters;
--rollback alter table environments        drop constraint pk_environments;
