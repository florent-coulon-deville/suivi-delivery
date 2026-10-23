#!/bin/bash
# Démarre Keycloak (kc.sh, avec les arguments reçus), puis rend sa console d'administration
# utilisable à son adresse à elle (KC_HOSTNAME_ADMIN).
#
# Pourquoi : les pages de Keycloak sont servies par l'interface, sous <APP_FRONTEND_URL>/auth, qui
# ne relaie QUE le domaine de l'outil (jamais l'administration). Or la console se connecte par le
# domaine d'administration (« master »), qui annonce par défaut l'adresse publique (KC_HOSTNAME) :
# elle restait blanche. On donne donc au domaine « master » l'adresse de la console
# (http://localhost:8081/auth sur le poste, ou par « kubectl port-forward » sur un cluster).
#
# Le réglage est fait à chaque démarrage (sans effet s'il est déjà bon), avec l'administrateur
# provisoire de Keycloak (KC_BOOTSTRAP_ADMIN_*). Sans KC_HOSTNAME_ADMIN, ou si cet administrateur
# n'existe plus, rien n'est fait : Keycloak tourne normalement, la console n'est simplement pas réglée.
set -u

/opt/keycloak/bin/kc.sh "$@" &
keycloak=$!
# Arrêt demandé (docker stop, Kubernetes) : transmis à Keycloak, qui s'arrête proprement.
trap 'kill -TERM "$keycloak" 2>/dev/null' TERM INT

configure_console() {
    local kcadm=/opt/keycloak/bin/kcadm.sh config=/tmp/kcadm.config
    # Attendre que Keycloak réponde (10 minutes au plus : premier démarrage, import du domaine).
    for _ in $(seq 1 120); do
        if "$kcadm" config credentials --config "$config" --server http://localhost:8080/auth --realm master \
            --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD" >/dev/null 2>&1; then
            if "$kcadm" update realms/master --config "$config" -s "attributes.frontendUrl=$KC_HOSTNAME_ADMIN" >/dev/null 2>&1; then
                echo "Console d'administration : $KC_HOSTNAME_ADMIN/admin"
            else
                echo "Console d'administration : réglage de son adresse impossible" >&2
            fi
            rm -f "$config"
            return
        fi
        sleep 5
    done
    echo "Console d'administration : non réglée (Keycloak ne répond pas, ou administrateur provisoire absent)" >&2
}

if [[ -n "${KC_HOSTNAME_ADMIN:-}" && -n "${KC_BOOTSTRAP_ADMIN_USERNAME:-}" && -n "${KC_BOOTSTRAP_ADMIN_PASSWORD:-}" ]]; then
    configure_console &
fi

# Attendre la fin de Keycloak, et rendre son code de sortie (« wait » est interrompu par un signal :
# on attend alors la vraie fin).
wait "$keycloak"
code=$?
while kill -0 "$keycloak" 2>/dev/null; do
    wait "$keycloak"
    code=$?
done
exit "$code"
