--liquibase formatted sql

-- Index : des « sommaires » qui accélèrent les recherches. Nom : ix_<table>_<colonnes>.
-- Une contrainte d'unicité ou une clé primaire a déjà le sien ; on en ajoute un pour chaque
-- lien (clé étrangère) qui n'est pas déjà en tête d'une unicité, et pour les recherches du journal.

--changeset suivi-delivery:005-01-index
--comment: Index des liens et des recherches courantes.
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
create index ix_audit_log_author                    on audit_log (author);
create index ix_audit_log_object                    on audit_log (object, object_id);
--rollback drop index ix_audit_log_object;
--rollback drop index ix_audit_log_author;
--rollback drop index ix_audit_log_date;
--rollback drop index ix_installations_application_parameter;
--rollback drop index ix_installations_technical_parameter;
--rollback drop index ix_installations_module_version;
--rollback drop index ix_installations_slot_date;
--rollback drop index ix_slots_module;
--rollback drop index ix_parameter_namespaces_namespace;
--rollback drop index ix_parameters_module;
--rollback drop index ix_compatibilities_required_module;
--rollback drop index ix_dependencies_depends_on;
--rollback drop index ix_namespaces_network_zone;
--rollback drop index ix_namespaces_cluster;
--rollback drop index ix_namespaces_environment;
