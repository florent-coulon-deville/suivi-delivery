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
