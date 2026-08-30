{{- define "bist.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "bist.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else if contains .Chart.Name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "bist.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "bist.labels" -}}
app.kubernetes.io/name: {{ include "bist.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: bist-mini
{{- end }}

{{- define "bist.selectorLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: bist-mini
{{- end }}

{{- define "bist.image" -}}
{{- printf "%s:%s" .repository .tag }}
{{- end }}

{{- define "bist.redisUrl" -}}
{{- if .Values.redis.url -}}
{{ .Values.redis.url }}
{{- else -}}
{{ printf "redis://%s-redis:6379/0" (include "bist.fullname" .) }}
{{- end -}}
{{- end }}
