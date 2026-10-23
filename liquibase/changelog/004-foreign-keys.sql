--liquibase formatted sql

-- Clés étrangères : un lien vers une autre table doit désigner une ligne qui existe, et une
-- ligne encore désignée ne peut pas être supprimée. Nom : fk_<table>_<lien>.
-- « on delete cascade » seulement pour la table de liaison des paramètres : ses lignes partent
-- avec le paramètre.

--changeset suivi-delivery:004-01-namespaces
--comment: Un namespace appartient à une application, un environnement, un cluster et une zone réseau.
alter table namespaces add constraint fk_namespaces_application  foreign key (application_id)   references applications (id);
alter table namespaces add constraint fk_namespaces_environment  foreign key (environment_id) references environments (id);
alter table namespaces add constraint fk_namespaces_cluster      foreign key (cluster_id)       references clusters (id);
alter table namespaces add constraint fk_namespaces_network_zone foreign key (network_zone_id)   references network_zones (id);
--rollback alter table namespaces drop constraint fk_namespaces_network_zone;
--rollback alter table namespaces drop constraint fk_namespaces_cluster;
--rollback alter table namespaces drop constraint fk_namespaces_environment;
--rollback alter table namespaces drop constraint fk_namespaces_application;

--changeset suivi-delivery:004-02-modules
--comment: Un module appartient à une application.
alter table modules add constraint fk_modules_application foreign key (application_id) references applications (id);
--rollback alter table modules drop constraint fk_modules_application;

--changeset suivi-delivery:004-03-dependencies
--comment: Une dépendance relie deux modules.
alter table dependencies add constraint fk_dependencies_module     foreign key (module_id)    references modules (id);
alter table dependencies add constraint fk_dependencies_depends_on foreign key (depends_on_id) references modules (id);
--rollback alter table dependencies drop constraint fk_dependencies_depends_on;
--rollback alter table dependencies drop constraint fk_dependencies_module;

--changeset suivi-delivery:004-04-module-versions
--comment: Une version appartient à un module.
alter table module_versions add constraint fk_module_versions_module foreign key (module_id) references modules (id);
--rollback alter table module_versions drop constraint fk_module_versions_module;

--changeset suivi-delivery:004-05-compatibilities
--comment: Une compatibilité relie une version de module à un module requis.
alter table compatibilities add constraint fk_compatibilities_module_version  foreign key (module_version_id) references module_versions (id);
alter table compatibilities add constraint fk_compatibilities_required_module foreign key (required_module_id)  references modules (id);
--rollback alter table compatibilities drop constraint fk_compatibilities_required_module;
--rollback alter table compatibilities drop constraint fk_compatibilities_module_version;

--changeset suivi-delivery:004-06-parameters
--comment: Un paramètre appartient à un module, et est affecté à des namespaces.
alter table parameters           add constraint fk_parameters_module              foreign key (module_id) references modules (id);
alter table parameter_namespaces add constraint fk_parameter_namespaces_parameter
    foreign key (parameter_id) references parameters (id) on delete cascade;
alter table parameter_namespaces add constraint fk_parameter_namespaces_namespace
    foreign key (namespace_id) references namespaces (id);
--rollback alter table parameter_namespaces drop constraint fk_parameter_namespaces_namespace;
--rollback alter table parameter_namespaces drop constraint fk_parameter_namespaces_parameter;
--rollback alter table parameters drop constraint fk_parameters_module;

--changeset suivi-delivery:004-07-slots
--comment: Un emplacement est dans un namespace, et réservé à un module.
alter table slots add constraint fk_slots_namespace foreign key (namespace_id) references namespaces (id);
alter table slots add constraint fk_slots_module    foreign key (module_id)    references modules (id);
--rollback alter table slots drop constraint fk_slots_module;
--rollback alter table slots drop constraint fk_slots_namespace;

--changeset suivi-delivery:004-08-installations
--comment: Une installation : un emplacement, une version de module, un paramètre technique et un applicatif.
alter table installations add constraint fk_installations_slot                  foreign key (slot_id)          references slots (id);
alter table installations add constraint fk_installations_module_version        foreign key (module_version_id)       references module_versions (id);
alter table installations add constraint fk_installations_technical_parameter   foreign key (technical_parameter_id)  references parameters (id);
alter table installations add constraint fk_installations_application_parameter foreign key (application_parameter_id) references parameters (id);
--rollback alter table installations drop constraint fk_installations_application_parameter;
--rollback alter table installations drop constraint fk_installations_technical_parameter;
--rollback alter table installations drop constraint fk_installations_module_version;
--rollback alter table installations drop constraint fk_installations_slot;
