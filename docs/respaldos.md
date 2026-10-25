# Respaldos y restauración

Procedimientos de respaldo y recuperación de la base de datos de LEICA Inventario en producción
(Azure Database for PostgreSQL – Flexible Server `leica-inventario-db`, grupo `rg-leica-inventario`).

## Política de respaldos

| Capa | Qué se respalda | Frecuencia | Retención | Ubicación |
|---|---|---|---|---|
| Automática (Azure) | Snapshot completo + registro de transacciones (WAL) | Snapshot diario, WAL continuo | 7 días | Azure, región Chile Central |
| Lógica (`respaldar`) | Volcado completo con `pg_dump`, formato comprimido, con huella SHA-256 | Semanal y antes de cada despliegue con migraciones | Últimos 14 respaldos | Fuera de Azure: equipo del encargado y OneDrive institucional |
| Prueba de restauración | Restaurar el último respaldo lógico en una base temporal y comparar | Mensual | Registro en la bitácora de este documento | Equipo del encargado |

Objetivos de recuperación:

| Escenario | RPO (datos que se pueden perder) | RTO (tiempo para volver a operar) |
|---|---|---|
| Restauración a un punto en el tiempo (Azure) | ≤ 5 minutos | ≤ 30 minutos |
| Restauración desde respaldo lógico | Hasta el último respaldo (≤ 7 días) | ≤ 60 minutos |

Las dos capas se complementan: la automática cubre errores recientes con mínima pérdida de datos, y la
lógica sobrevive a la eliminación del servidor o de la suscripción, porque se guarda fuera de Azure.

## Herramientas

Requieren el cliente de PostgreSQL 17 o superior (`pg_dump`, `pg_restore`). En Windows se instala con
PostgreSQL; si no está en el PATH, se indica su carpeta en `.env`:

```
POSTGRES_BIN=C:\Program Files\PostgreSQL\18\bin
```

| Comando | Función |
|---|---|
| `python manage.py respaldar` | Genera `respaldos/leica_AAAAMMDD_HHMMSS.dump` y su `.sha256`, verifica que el archivo sea legible y elimina los más antiguos que excedan la retención (`--conservar 14`, `0` conserva todos). `--directorio` cambia la carpeta de destino. |
| `python manage.py restaurar ARCHIVO` | Verifica la huella SHA-256, pide escribir el nombre de la base como confirmación y reemplaza todos los datos en una sola transacción: si algo falla, la base queda como estaba. Al terminar muestra la cantidad de usuarios, equipos, insumos, solicitudes, mantenimientos e historial. |

Ambos comandos operan sobre la base definida en `DATABASE_URL`. La clave se entrega a PostgreSQL por
variable de entorno, nunca en la línea de comandos.

## Procedimientos proactivos

### P1. Respaldo lógico de producción (semanal)

1. Obtener la IP pública del equipo (PowerShell):

   ```powershell
   Invoke-RestMethod https://api.ipify.org
   ```

2. En Azure Cloud Shell, permitir temporalmente esa IP en el firewall del servidor:

   ```bash
   az postgres flexible-server firewall-rule create \
     --resource-group rg-leica-inventario --name leica-inventario-db \
     --rule-name respaldo-local --start-ip-address MI_IP --end-ip-address MI_IP
   ```

3. En el equipo local, desde la carpeta del proyecto con el entorno virtual activo:

   ```powershell
   $env:DATABASE_URL = "postgres://leicaadmin:CLAVE@leica-inventario-db.postgres.database.azure.com:5432/leica_inventario?sslmode=require"
   python manage.py respaldar --directorio respaldos\produccion
   Remove-Item Env:DATABASE_URL
   ```

   Cerrar la variable al terminar evita que un comando posterior (por ejemplo `restaurar`) se ejecute
   contra producción por error.

4. Copiar el `.dump` y su `.sha256` a OneDrive institucional.

5. Quitar la regla del firewall:

   ```bash
   az postgres flexible-server firewall-rule delete \
     --resource-group rg-leica-inventario --name leica-inventario-db \
     --rule-name respaldo-local --yes
   ```

### P2. Respaldo previo a un despliegue con migraciones

Antes de hacer push a `main` de un cambio que incluya archivos nuevos en `inventario/migrations/`,
ejecutar P1. Ese respaldo es el punto de retorno si la migración falla (procedimiento R2).

### P3. Verificación de los respaldos automáticos (mensual)

```bash
az postgres flexible-server backup list \
  --resource-group rg-leica-inventario --name leica-inventario-db --output table
az postgres flexible-server show \
  --resource-group rg-leica-inventario --name leica-inventario-db \
  --query "backup.{retencion_dias: backupRetentionDays, restaurable_desde: earliestRestoreDate}"
```

Debe existir un respaldo de cada uno de los últimos 7 días y `restaurable_desde` no puede tener más de
7 días de antigüedad.

### P4. Prueba de restauración (mensual)

1. Crear una base temporal en el PostgreSQL local:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U leica -h localhost -d postgres -c "CREATE DATABASE leica_restauracion"
   ```

2. Restaurar el último respaldo de producción en ella:

   ```powershell
   $env:DATABASE_URL = "postgres://leica:CLAVE@localhost:5432/leica_restauracion"
   python manage.py restaurar respaldos\produccion\leica_AAAAMMDD_HHMMSS.dump --noinput
   Remove-Item Env:DATABASE_URL
   ```

3. Comparar los conteos que muestra el comando con los de producción (pantalla Reportes o
   `/admin/`). Deben coincidir con el estado al momento del respaldo.

4. Eliminar la base temporal y registrar el resultado en la bitácora:

   ```powershell
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U leica -h localhost -d postgres -c "DROP DATABASE leica_restauracion"
   ```

## Procedimientos reactivos

### R1. Datos borrados o modificados por error

Ejemplo: se eliminó un insumo o se cambió masivamente el estado de los equipos.

1. Identificar la hora del incidente (por ejemplo, en el **Historial** del equipo afectado) y elegir un
   momento inmediatamente anterior, en UTC (Chile continental = UTC−3 en horario de verano, UTC−4 en invierno).
2. Restaurar el servidor a ese momento. Azure crea un servidor **nuevo**; el original no se modifica:

   ```bash
   az postgres flexible-server restore \
     --resource-group rg-leica-inventario \
     --name leica-inventario-db-rest \
     --source-server leica-inventario-db \
     --restore-time "2026-10-21T13:00:00Z"
   ```

3. Validar el servidor restaurado conectándose con DBeaver o `psql` (mismo usuario y clave que el original).
4. Elegir según el alcance del daño:
   - **Daño amplio:** apuntar la aplicación al servidor restaurado.

     ```bash
     az webapp config appsettings set --resource-group rg-leica-inventario --name leica-inventario \
       --settings DATABASE_URL="postgres://leicaadmin:CLAVE@leica-inventario-db-rest.postgres.database.azure.com:5432/leica_inventario?sslmode=require"
     ```

     Los datos registrados después del momento elegido se pierden; deben volver a ingresarse.
   - **Daño puntual:** copiar solo los registros afectados desde el servidor restaurado al original.
5. Comprobar `https://leica-inventario.azurewebsites.net/salud/` y el inicio de sesión.
6. Tras una semana sin incidencias, eliminar el servidor que ya no se usa para no pagar dos servidores.

### R2. Migración o despliegue fallido

1. Revertir el código: `git revert <commit>` y push a `main`. GitHub Actions vuelve a desplegar la versión anterior.
2. Si la migración alcanzó a modificar datos, restaurar el respaldo tomado en P2 contra producción
   (abriendo el firewall como en P1):

   ```powershell
   $env:DATABASE_URL = "postgres://leicaadmin:CLAVE@leica-inventario-db.postgres.database.azure.com:5432/leica_inventario?sslmode=require"
   python manage.py restaurar respaldos\produccion\leica_AAAAMMDD_HHMMSS.dump
   Remove-Item Env:DATABASE_URL
   ```

3. Reiniciar la aplicación (`az webapp restart --resource-group rg-leica-inventario --name leica-inventario`)
   y comprobar `/salud/`.

### R3. Pérdida del servidor o del grupo de recursos

Si el servidor se elimina, sus respaldos automáticos se eliminan con él. La recuperación usa el último
respaldo lógico guardado fuera de Azure.

1. Volver a crear la infraestructura con `azure/crear_infraestructura.sh` (ver README) y guardar la nueva
   clave de la base.
2. Actualizar el secreto `AZURE_WEBAPP_PUBLISH_PROFILE` en GitHub y desplegar (**Actions → CI/CD → Run workflow**).
   El primer arranque crea las tablas vacías.
3. Abrir el firewall como en P1 y restaurar el último respaldo lógico contra el servidor nuevo con `restaurar`.
4. Comprobar `/salud/`, el inicio de sesión y los conteos.

### R4. Respaldo dañado

`restaurar` se detiene con *"El respaldo está dañado: su SHA-256 no coincide"* sin tocar la base.
Usar el respaldo anterior o la copia de OneDrive.

## Bitácora de pruebas de restauración

| Fecha | Respaldo | Base de destino | Resultado |
|---|---|---|---|
| 2026-10-21 | `leica_20261021_035255.dump` (68,9 KB, 19 tablas) | `leica_restauracion_prueba` (local) | Correcto: 19 de 19 tablas y 182 de 182 filas idénticas al origen. Una segunda restauración sobre la base ya poblada también fue correcta, y un respaldo alterado a propósito fue rechazado por la verificación SHA-256. |
