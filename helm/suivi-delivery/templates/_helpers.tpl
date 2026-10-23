{{/*
Fonctions communes aux modèles du chart (noms, étiquettes, images).
*/}}

{{/* Nom de base des objets : le nom de l'installation (ex. « suivi-delivery »), 63 caractères au plus. */}}
{{- define "sd.name" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Étiquettes communes à tous les objets. */}}
{{- define "sd.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/part-of: suivi-delivery
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Étiquettes qui désignent les pods d'une partie (backend ou frontend) : ne changent jamais. */}}
{{- define "sd.selector" -}}
app.kubernetes.io/name: {{ .context.Chart.Name }}
app.kubernetes.io/instance: {{ .context.Release.Name }}
app.kubernetes.io/component: {{ .part }}
{{- end -}}

{{/* Image d'une partie : [registre/]dépôt + étiquette (par défaut, la version du chart). */}}
{{- define "sd.image" -}}
{{- $image := index .context.Values.images .part -}}
{{- $repository := $image.repository -}}
{{- with .context.Values.images.registry }}{{ $repository = printf "%s/%s" (trimSuffix "/" .) $repository }}{{ end -}}
{{- printf "%s:%s" $repository (default .context.Chart.AppVersion $image.tag) -}}
{{- end -}}

{{/* Nom du Secret d'accès au registre ; vide s'il n'y en a pas. */}}
{{- define "sd.registrySecret" -}}
{{- if .Values.registry.existingSecret -}}
{{- .Values.registry.existingSecret -}}
{{- else if .Values.registry.server -}}
{{- printf "%s-registry" (include "sd.name" .) -}}
{{- end -}}
{{- end -}}

{{/* Bloc imagePullSecrets, s'il y a un Secret d'accès au registre. */}}
{{- define "sd.imagePullSecrets" -}}
{{- with include "sd.registrySecret" . }}
imagePullSecrets:
  - name: {{ . }}
{{- end }}
{{- end -}}

{{/* Adresse de la base : le Service de la base intégrée, ou celle fournie (database.host). */}}
{{- define "sd.databaseHost" -}}
{{- if .Values.database.internal -}}
{{- printf "%s-postgresql" (include "sd.name" .) -}}
{{- else -}}
{{- required "database.host est obligatoire avec une base fournie (database.internal: false)" .Values.database.host -}}
{{- end -}}
{{- end -}}

{{/* Adresse publique de l'interface (APP_FRONTEND_URL), sans « / » final : celle que tape le navigateur.
     Les pages de connexion de Keycloak y sont servies (sous /auth), et l'interface y reçoit les
     retours de connexion.
     application.frontendUrl, sinon l'hôte de la Route (HTTPS) ou de l'Ingress, sinon
     http://localhost:8080 (kind, avec « kubectl port-forward »). */}}
{{- define "sd.frontendUrl" -}}
{{- if .Values.application.frontendUrl -}}
{{- trimSuffix "/" .Values.application.frontendUrl -}}
{{- else if and .Values.route.enabled .Values.route.host -}}
{{- printf "https://%s" .Values.route.host -}}
{{- else if and .Values.ingress.enabled .Values.ingress.host -}}
{{- printf "%s://%s" (ternary "https" "http" (not (empty .Values.ingress.tlsSecret))) .Values.ingress.host -}}
{{- else -}}
http://localhost:8080
{{- end -}}
{{- end -}}

{{/* Adresse INTERNE de Keycloak (son Service, avec /auth) : l'API et l'interface y parlent à Keycloak. */}}
{{- define "sd.keycloakUrl" -}}
{{- printf "http://%s-keycloak:8080/auth" (include "sd.name" .) -}}
{{- end -}}

{{/* Nom du Secret de l'application (APP_ADMIN_PASSWORD, APP_DB_PASSWORD, APP_KEYCLOAK_CLIENT_SECRET,
     KC_DB_PASSWORD, KC_BOOTSTRAP_ADMIN_PASSWORD). */}}
{{- define "sd.applicationSecret" -}}
{{- default (printf "%s-application" (include "sd.name" .)) .Values.application.existingSecret -}}
{{- end -}}

{{/* Utilisateur des conteneurs de l'image PostgreSQL : sur OpenShift, rien (un utilisateur au
     hasard est imposé, que l'image déclare elle-même au démarrage) ; ailleurs, « postgres » (70,
     l'utilisateur de l'image durcie). */}}
{{- define "sd.postgresUser" -}}
{{- if not (.Capabilities.APIVersions.Has "security.openshift.io/v1") -}}
runAsUser: 70
runAsGroup: 70
{{- end -}}
{{- end -}}

{{/* Réglages de sécurité des conteneurs, compatibles avec la politique « restricted » d'OpenShift
     et les Pod Security Standards de Kubernetes. Aucun numéro d'utilisateur n'est fixé :
     OpenShift en choisit un, ailleurs c'est celui de l'image (1001). */}}
{{- define "sd.containerSecurity" -}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
{{- end -}}
