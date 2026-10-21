#!/usr/bin/env bash
set -o errexit
set -o nounset

: "${APP_NAME:?Define APP_NAME, por ejemplo: export APP_NAME=leica-inventario}"
: "${ADMIN_EMAIL:?Define ADMIN_EMAIL}"
: "${ADMIN_PASSWORD:?Define ADMIN_PASSWORD}"

RESOURCE_GROUP="${RESOURCE_GROUP:-rg-leica-inventario}"
LOCATION="${LOCATION:-brazilsouth}"
PLAN_NAME="${PLAN_NAME:-plan-leica-inventario}"
PLAN_SKU="${PLAN_SKU:-B1}"
PYTHON_VERSION="${PYTHON_VERSION:-3.14}"
PG_SERVER="${PG_SERVER:-${APP_NAME}-db}"
PG_VERSION="${PG_VERSION:-17}"
PG_SKU="${PG_SKU:-Standard_B1ms}"
PG_ADMIN="${PG_ADMIN:-leicaadmin}"
PG_DATABASE="leica_inventario"
PG_PASSWORD="${PG_PASSWORD:-$(openssl rand -hex 24)}"
SECRET_KEY="${SECRET_KEY:-$(openssl rand -base64 48 | tr -d '\n=+/')}"

for proveedor in Microsoft.DBforPostgreSQL Microsoft.Web; do
  if [ "$(az provider show --namespace "${proveedor}" --query registrationState --output tsv 2>/dev/null)" != "Registered" ]; then
    echo "Registrando el proveedor ${proveedor} en la suscripción..."
    az provider register --namespace "${proveedor}" --wait --output none
  fi
done

echo "Grupo de recursos: ${RESOURCE_GROUP} (${LOCATION})"
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" --output none

echo "PostgreSQL Flexible Server: ${PG_SERVER}"
if az postgres flexible-server show --resource-group "${RESOURCE_GROUP}" --name "${PG_SERVER}" --output none 2>/dev/null; then
  echo "El servidor ya existe: se actualiza la clave del administrador."
  az postgres flexible-server update \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${PG_SERVER}" \
    --admin-password "${PG_PASSWORD}" \
    --output none
else
az postgres flexible-server create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${PG_SERVER}" \
  --location "${LOCATION}" \
  --version "${PG_VERSION}" \
  --tier Burstable \
  --sku-name "${PG_SKU}" \
  --storage-size 32 \
  --backup-retention 7 \
  --admin-user "${PG_ADMIN}" \
  --admin-password "${PG_PASSWORD}" \
  --public-access 0.0.0.0 \
  --yes \
  --output none
fi

az postgres flexible-server db create \
  --resource-group "${RESOURCE_GROUP}" \
  --server-name "${PG_SERVER}" \
  --name "${PG_DATABASE}" \
  --output none

echo "App Service: ${APP_NAME} (plan ${PLAN_SKU}, Python ${PYTHON_VERSION})"
az appservice plan create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${PLAN_NAME}" \
  --location "${LOCATION}" \
  --sku "${PLAN_SKU}" \
  --is-linux \
  --output none

az webapp create \
  --resource-group "${RESOURCE_GROUP}" \
  --plan "${PLAN_NAME}" \
  --name "${APP_NAME}" \
  --runtime "PYTHON:${PYTHON_VERSION}" \
  --output none

DATABASE_URL="postgres://${PG_ADMIN}:${PG_PASSWORD}@${PG_SERVER}.postgres.database.azure.com:5432/${PG_DATABASE}?sslmode=require"

az webapp config appsettings set \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${APP_NAME}" \
  --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    DEBUG=False \
    SECRET_KEY="${SECRET_KEY}" \
    DATABASE_URL="${DATABASE_URL}" \
    DOMINIO_INSTITUCIONAL=inacapmail.cl \
    ADMIN_EMAIL="${ADMIN_EMAIL}" \
    ADMIN_PASSWORD="${ADMIN_PASSWORD}" \
    GEMINI_API_KEY="${GEMINI_API_KEY:-}" \
  --output none

az webapp config set \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${APP_NAME}" \
  --startup-file "bash startup.sh" \
  --always-on "$([ "${PLAN_SKU}" = "F1" ] && echo false || echo true)" \
  --http20-enabled true \
  --min-tls-version 1.2 \
  --ftps-state Disabled \
  --generic-configurations '{"healthCheckPath": "/salud/"}' \
  --output none

az webapp update --resource-group "${RESOURCE_GROUP}" --name "${APP_NAME}" --https-only true --output none
az resource update \
  --resource-group "${RESOURCE_GROUP}" \
  --namespace Microsoft.Web \
  --resource-type basicPublishingCredentialsPolicies \
  --parent "sites/${APP_NAME}" \
  --name scm \
  --set properties.allow=true \
  --output none
az webapp log config --resource-group "${RESOURCE_GROUP}" --name "${APP_NAME}" \
  --docker-container-logging filesystem --output none

echo
echo "Infraestructura lista."
echo "  Aplicación:       https://${APP_NAME}.azurewebsites.net"
echo "  Servidor de base: ${PG_SERVER}.postgres.database.azure.com"
echo "  Usuario de base:  ${PG_ADMIN}"
echo "  Clave de base:    ${PG_PASSWORD}"
echo
echo "Guarda la clave de la base en un lugar seguro: no se vuelve a mostrar."
echo
echo "Perfil de publicación para GitHub Actions (secreto AZURE_WEBAPP_PUBLISH_PROFILE):"
az webapp deployment list-publishing-profiles \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${APP_NAME}" \
  --xml
