# ADR-003 · GitOps push con manifiestos de Cloud Run; Argo CD como alternativa on-premise

**Estado:** aceptada

## Contexto
En la Fase II el despliegue a Cloud Run fue manual (`gcloud run deploy`), sin registro de qué
versión estaba en cada ambiente.

## Decisión
- El estado deseado vive en `deploy/cloudrun/staging.yaml` y `produccion.yaml` (manifiestos
  Knative con la etiqueta de imagen fijada).
- `cd.yml` los aplica con `gcloud run services replace` cuando cambian en `main`: staging en
  automático, producción con aprobación manual (environment de GitHub), prueba de humo y
  regreso automático a la revisión previa si falla.
- Para un clúster propio (OpenShift/Kubernetes) se dejan `deploy/k8s` (Kustomize) y
  `deploy/argocd/application.yaml` (GitOps tipo *pull*, con `selfHeal`).

## Razones
Cloud Run no tiene un agente que lea Git, así que el modelo *push* desde Actions es el estándar.
Lo que hace que sea GitOps es que nadie despliega con la consola: cualquier cambio de versión
pasa por un pull request y queda en el historial.
