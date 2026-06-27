{{- define "wanderbot.labels" -}}
app.kubernetes.io/name: wanderbot
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "wanderbot.apiImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.apiRepository }}:{{ .Values.image.tag }}
{{- end -}}

{{- define "wanderbot.mcpImage" -}}
{{ .Values.image.registry }}/{{ .Values.image.mcpRepository }}:{{ .Values.image.tag }}
{{- end -}}
