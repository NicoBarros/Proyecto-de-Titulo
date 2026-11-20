# LEICA Inventario
Sistema de gestión de inventario y préstamo de equipos del laboratorio LEICA, INACAP Sede Valdivia.
Proyecto de título.

Permite administrar equipos e insumos, solicitar préstamos (kits), aprobarlos, entregarlos y
registrar su devolución equipo por equipo, sancionar atrasos, avisar por correo, gestionar
mantenimientos con la regla del 70 %, generar reportes, importar y exportar el inventario en Excel,
registrar el historial de cambios de cada equipo, generar códigos QR que abren la ficha del equipo
y buscar equipos en lenguaje natural con IA mediante una arquitectura RAG híbrida (recuperación local y
respuesta redactada por Google Gemini).

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.14 + Django 6.1 |
| Frontend | Plantillas de Django (HTML, CSS y JavaScript sin frameworks) |
| Base de datos | PostgreSQL (probado con la versión 18) |
| IA | RAG híbrido: recuperación densa con EmbeddingGemma (`fastembed`, ONNX Runtime, solo CPU) y léxica con BM25, fusionadas con RRF; generación con Google Gemini (`google-genai`) |
| Producción | Gunicorn + WhiteNoise para archivos estáticos |

## Instalación local

Requisitos: Python 3.14 y PostgreSQL instalados. Los comandos son para PowerShell en Windows.

**1. Entorno virtual y dependencias**

```powershell
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**2. Base de datos**

Crea un usuario y una base de datos para la aplicación. Abre `psql` como superusuario:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost
```

y ejecuta:

```sql
CREATE ROLE leica WITH LOGIN PASSWORD 'una-clave-segura' CREATEDB;
CREATE DATABASE leica_inventario OWNER leica ENCODING 'UTF8' TEMPLATE template0;
```

El permiso `CREATEDB` es necesario para que Django pueda crear la base temporal de los tests.

**3. Variables de entorno**

Copia `.env.example` como `.env` y completa los valores:

```powershell
copy .env.example .env
```

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Obligatoria. Genera una con `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DEBUG` | `True` en desarrollo. Por defecto es `False` |
| `ALLOWED_HOSTS` | Dominios permitidos, separados por coma |
| `DATABASE_URL` | `postgres://leica:una-clave-segura@localhost:5432/leica_inventario` |
| `DOMINIO_INSTITUCIONAL` | Dominio de correo aceptado al crear usuarios (`inacapmail.cl`) |
| `BUSQUEDA_SEMANTICA` | `True` activa la búsqueda semántica local. Necesita unos 1,5 GB de RAM por proceso; en Azure App Service B1 déjala en `False`. Por defecto `False` |
| `MODELOS_DIR` | Carpeta donde se descarga el modelo de búsqueda (~1,2 GB, una sola vez). Por defecto `modelos/` |
| `GEMINI_API_KEY` | Opcional. Sin clave, la búsqueda muestra los equipos recuperados sin la respuesta redactada |
| `GEMINI_MODELO` / `GEMINI_MODELO_RESPALDO` | Opcionales. Modelo principal y de respaldo (por defecto `gemini-3.5-flash-lite` y `gemini-3.1-flash-lite`) |
| `POSTGRES_BIN` | Opcional. Carpeta de `pg_dump` y `pg_restore` si no están en el PATH |
| `RESPALDOS_DIR` | Carpeta de los respaldos. Por defecto `respaldos/` |
| `RESPALDO_AUTOMATICO` | `True` genera un respaldo con las tareas programadas cada `RESPALDO_HORAS` (por defecto `24`) y conserva los últimos `RESPALDO_CONSERVAR` (por defecto `14`). Si falla, avisa por correo a los administradores. En Azure déjalo en `False`: la base ya tiene respaldos automáticos y App Service no incluye `pg_dump`. Por defecto `False` |
| `SESION_MINUTOS` | Minutos de inactividad antes de cerrar la sesión. Por defecto `30` |
| `SLA_REVISION_HORAS` | Plazo para revisar una solicitud pendiente. Al vencer, las tareas programadas avisan por correo a quienes aprueban. Por defecto `24` |
| `SLA_BAJA_DIAS` | Plazo para validar un equipo pendiente de baja. Por defecto `5` |
| `PRIVACIDAD_CONTACTO` | Correo de contacto del responsable que muestra el aviso de privacidad. Opcional |
| `PLAZO_DERECHOS_DIAS` | Plazo para responder solicitudes de derechos sobre datos personales. Por defecto `30` |
| `RETENCION_BUSQUEDAS_DIAS` / `RETENCION_EVENTOS_DIAS` | Días que las búsquedas quedan asociadas a su autor y que se conservan los eventos de seguridad. Por defecto `365` |
| `EVALUACION_BUSQUEDA_DIAS` | Cada cuántos días las tareas programadas evalúan la búsqueda con las consultas de referencia. `0` la desactiva. Por defecto `30` |
| `IA_CONSULTAS_POR_HORA` | Respuestas generadas con Gemini por usuario y hora; al superarlas solo se muestran los equipos recuperados. Por defecto `20` |
| `URL_SITIO` | URL pública usada en los correos y en los códigos QR. En Azure se toma de `WEBSITE_HOSTNAME` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | Servidor SMTP para los avisos. Sin `EMAIL_HOST`, los correos se muestran en la consola |
| `DEFAULT_FROM_EMAIL` | Remitente de los correos |
| `HORAS_RECORDATORIO` | Horas antes del vencimiento en que se envía el recordatorio de devolución. Por defecto `24` |
| `TAREAS_TOKEN` | Token que autoriza `POST /tareas/` (tareas programadas). Vacío deshabilita el endpoint |

**4. Tablas, datos de prueba y servidor**

```powershell
python manage.py migrate
python manage.py createcachetable
python manage.py seed
python manage.py runserver
```

La aplicación queda en http://127.0.0.1:8000.

## Usuarios de prueba

El comando `seed` crea estos usuarios, todos con la contraseña `Leica2026!`. Con `DEBUG=True`, la
pantalla de login también los muestra.

| Rol | Correo |
|---|---|
| Encargado de Laboratorio (superusuario) | encargado.leica@inacapmail.cl |
| Control de Calidad | calidad@inacapmail.cl |
| Director de Carrera | dcarrera@inacapmail.cl |
| Docente | docente1@inacapmail.cl |
| Estudiante | estudiante1@inacapmail.cl, estudiante2@inacapmail.cl |

No ejecutes `seed` en producción: crea un superusuario con una contraseña pública.

## Roles y permisos

Los permisos se validan en el servidor según el rol del usuario, no solo en la interfaz.

| Función | Estudiante | Docente | Director | Encargado | Control Calidad | Comité |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Ver inventario y buscar equipos | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Crear solicitudes | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Solicitar en representación de un estudiante | | ✓ | ✓ | ✓ | ✓ | |
| Ver todas las solicitudes (el resto ve solo las propias) | | | ✓ | ✓ | ✓ | |
| Aprobar, entregar y recibir devoluciones | | | ✓ | ✓ | ✓ | |
| Mantenimiento | | | ✓ | ✓ | ✓ | |
| Reportes y KPIs | | | ✓ | ✓ | ✓ | ✓ |
| Editar inventario, exportar a Excel, QR e historial de equipos | | | | ✓ | ✓ | |

El **Panel Admin** es para usuarios staff. Un staff que no es superusuario solo gestiona cuentas
comunes: no puede modificar a otros administradores ni asignar roles con permisos de aprobación.

## Reglas de negocio principales

- **Préstamos:** una solicitud pasa por pendiente → aprobada → entregada → devuelta. Solo se puede
  rechazar mientras está pendiente o aprobada. Al aprobar se verifica que el equipo no esté reservado
  en un horario que se cruce.
- **Atrasos:** un préstamo entregado cuyo plazo venció pasa automáticamente a "Atrasada" y aparece
  como alerta en el dashboard de quienes aprueban. Si se devuelve tarde queda como "Devuelta con
  atraso". El comando `python manage.py marcar_atrasadas` permite programar esta revisión.
- **Representación:** docentes, directores, encargados y Control de Calidad pueden pedir un préstamo
  a nombre de un estudiante; en ese caso la sanción por atraso se aplica al estudiante.
- **Devolución:** se registra el estado de cada equipo del kit; los que vuelven dañados o inservibles
  pasan a mantenimiento y el resto queda disponible.
- **Cancelación:** quien creó una solicitud puede cancelarla mientras esté pendiente o aprobada.
- **Insumos:** los renovables vuelven al stock al devolverse; los perecibles se consumen.
- **Rechazo:** quien rechaza una solicitud debe indicar el motivo; se guarda y se envía al solicitante.
- **Sanciones (RF-09):** una devolución atrasada bloquea por 7 días al estudiante y a su sección. Al
  quitar la sanción desde el panel de administración también se libera la sección.
- **Edición concurrente:** si otra persona guardó cambios en un equipo o insumo mientras se editaba,
  el sistema avisa y no sobrescribe hasta que se recargue o se confirme guardando de nuevo.
- **Mantenimiento (RF-10):** si el costo de reparación es igual o mayor al 70 % del valor de
  adquisición, el sistema sugiere dar el equipo de baja.
- **Historial:** un equipo, insumo o usuario con préstamos o mantenimientos registrados no se puede
  eliminar. Para retirar un equipo se marca como "Fuera de servicio".
- **Auditoría:** cada creación, edición, cambio de estado o eliminación de un equipo queda registrada
  con usuario, fecha, valores anteriores y nuevos, y origen (inventario, préstamo, mantenimiento,
  panel o admin). Se consulta con el botón "Historial" de cada equipo.

## Seguridad

- **Inicio de sesión:** después de 5 intentos fallidos con un mismo correo desde un mismo equipo, el acceso
  se bloquea por 15 minutos (`django-axes`). Un inicio exitoso reinicia el contador.
- **Sesiones:** expiran tras 60 minutos sin actividad y al cerrar el navegador.
- **Registro de seguridad:** inicios y cierres de sesión, intentos fallidos, bloqueos y accesos denegados
  quedan registrados con fecha, usuario, IP y ruta. Se consultan en `/admin/` → **Eventos de seguridad**
  (solo lectura) y también se escriben en el log de la aplicación.
- **Transporte:** HTTPS obligatorio, HSTS de un año, cookies seguras y TLS 1.2 como mínimo.
- **Recursos externos:** Bootstrap y Bootstrap Icons se cargan con verificación de integridad (SRI).
- **Política de seguridad de contenido (CSP):** el navegador solo ejecuta scripts del propio sitio y del CDN
  de Bootstrap; no hay JavaScript inline en ninguna plantilla, lo que bloquea la inyección de scripts (XSS).
  Tampoco se permite incrustar la aplicación en otros sitios (`frame-ancestors 'none'`).
- **Base de datos:** en Azure, el firewall solo acepta conexiones desde las IP de salida de la aplicación.
- **Búsqueda con IA:** la recuperación se ejecuta en el propio servidor. Gemini recibe solo los fragmentos
  del catálogo recuperados y la consulta, nunca datos personales. Cada usuario tiene un máximo de respuestas
  generadas por hora (`IA_CONSULTAS_POR_HORA`).
- **Dependencias:** cada push ejecuta `pip-audit` contra la base de vulnerabilidades conocidas, y Dependabot
  propone actualizaciones semanales.

## Avisos por correo

- Al aprobar o rechazar una solicitud se avisa al solicitante y, si corresponde, al estudiante representado.
- Las tareas programadas envían un recordatorio antes del vencimiento (`HORAS_RECORDATORIO`) y un aviso
  cuando el préstamo pasa a atrasado. Cada aviso se envía una sola vez; si el servidor de correo falla,
  se reintenta en la siguiente ejecución.

## Ficha de equipo y códigos QR

Cada equipo tiene una ficha en `/inventario/equipo/<id>/` con su estado, ubicación, especificaciones y
próximas reservas, y un botón para solicitarlo si está disponible. Quienes aprueban ven además sus
mantenimientos y devoluciones; el encargado y Control de Calidad, su historial y su código QR. El QR
contiene la URL de la ficha, así que al escanearlo con el celular se abre directamente.

## Importar inventario desde Excel

En **Inventario → Importar desde Excel** se sube un `.xlsx` con hojas «Equipos» y/o «Insumos». Sirve la
plantilla descargable o el mismo archivo que genera la exportación. Los equipos se identifican por su
código y los insumos por su nombre: si existen se actualizan (sin tocar las columnas ausentes ni el
estado de equipos ya registrados) y si no, se crean. Las filas con errores se informan con su número y
el resto se importa. Cada importación queda registrada con su resultado.

## Exportar inventario a Excel

El botón "Exportar Inventario Excel" de la pantalla Inventario descarga `inventario_leica_AAAAMMDD.xlsx`
con tres hojas con formato: **Resumen** (equipos por estado, valor total e insumos con stock bajo),
**Equipos** e **Insumos**, con colores por estado y filtros en cada columna.

En Reportes, "Exportar Excel" descarga `reportes_leica_AAAAMMDD.xlsx` con los indicadores del período
elegido, los equipos más solicitados, los préstamos vencidos, los equipos sin movimiento, las brechas de
la búsqueda y el detalle de la última evaluación de la búsqueda.

## Datos personales (Ley N.° 21.719)

- **Aviso de privacidad** (`/privacidad/`), enlazado en el inicio de sesión y en el pie de página: datos,
  finalidad, base de licitud, conservación, proveedores, seguridad y derechos.
- **Mis datos** (ícono de tarjeta en la barra superior): perfil, resumen de lo registrado y descarga de
  todos los datos personales en JSON (acceso y portabilidad).
- **Solicitudes de derechos:** rectificación, supresión, oposición y bloqueo se piden desde Mis datos,
  llegan por correo a los superusuarios y se resuelven en el panel de administración con una respuesta
  al titular. Aceptar una supresión anonimiza la cuenta conservando los préstamos sin datos
  identificables; aceptar un bloqueo suspende la cuenta.
- **Conservación limitada:** las tareas programadas desvinculan las búsquedas antiguas de su autor y
  eliminan los eventos de seguridad vencidos.

El registro de actividades de tratamiento y el cifrado en reposo están en [docs/privacidad.md](docs/privacidad.md).

## Supervisión humana y calidad de la IA

Reportes muestra, para el período elegido:

- **Supervisión humana (SLA):** solicitudes revisadas dentro de `SLA_REVISION_HORAS`, solicitudes
  pendientes fuera de plazo, equipos pendientes de baja sin validar en `SLA_BAJA_DIAS` y tasa de
  aprobación directa (revisadas que no se rechazaron). Cuando una solicitud supera el plazo sin revisión,
  las tareas programadas envían un aviso único a Encargado, Control de Calidad y Dirección de Carrera.
- **Calidad de la IA y adopción:** fidelidad de las respuestas (generadas que pasaron la verificación de
  citas), búsquedas calificadas como útiles, tasa de escalado (búsquedas sin resultado o calificadas
  como no útiles, que requieren intervención humana) y adopción (usuarios activos con búsquedas o
  solicitudes en el período).
- **Brechas de la búsqueda:** consultas sin resultados o calificadas como no útiles, agrupadas y
  ordenadas por frecuencia. Indican equipos que se necesitan y no están en el inventario o que la
  búsqueda no encuentra.

## Búsqueda en lenguaje natural (RAG híbrido)

La búsqueda sigue el esquema recuperar → generar → verificar (`inventario/rag.py`):

1. **Indexación:** cada modelo de equipo es un fragmento (nombre, modelo y especificaciones) con su vector
   de EmbeddingGemma, guardado en `VectorEquipo` y actualizado por las tareas programadas.
2. **Recuperación híbrida:** sobre los equipos disponibles, combina la similitud de vectores (que además
   divide la consulta cuando pide varias cosas) con BM25 sobre los términos, que encuentra códigos y
   modelos exactos. Las dos listas se fusionan con *Reciprocal Rank Fusion* y se toman los 5 primeros.
3. **Generación:** Gemini recibe solo esos 5 fragmentos, numerados `[E1]`…`[E5]`, con instrucciones de
   sistema separadas de la consulta, temperatura 0,2 y salida JSON. Redacta una recomendación de una a
   tres oraciones citando cada equipo. La consulta va delimitada y se trata como dato, no como instrucción.
4. **Verificación:** se descarta la respuesta si cita un fragmento que no recibió, si contiene un correo
   o si no tiene el formato esperado; si nombra un equipo recuperado sin citarlo, se agrega la cita.
5. **Supervisión humana:** los equipos aparecen al instante y la respuesta llega después, sin bloquear.
   Quien busca puede calificar si le sirvió. Cada búsqueda guarda la consulta, los equipos recuperados,
   la respuesta, las citas, el resultado de la verificación, los tiempos, el equipo elegido y la
   calificación.

Si Gemini no está configurado, falla o se agota el cupo, se muestran los equipos recuperados igual. Si el
modelo principal no responde, se usa el de respaldo.

## Evaluación de la búsqueda (RNF-11)

`inventario/datos/consultas_referencia.json` contiene 30 consultas en lenguaje natural con el equipo
esperado para cada una. La evaluación ejecuta la búsqueda local (semántica o por palabras clave, sin
Gemini) sobre todo el catálogo vigente y cuenta una consulta como acertada si el equipo esperado
aparece entre los 5 primeros resultados. La meta es 80 %.

- Las tareas programadas la ejecutan una vez al mes (`EVALUACION_BUSQUEDA_DIAS`).
- El Encargado o Control de Calidad puede ejecutarla con "Evaluar ahora" en Reportes, donde se ve el
  porcentaje y las consultas sin acierto.
- Por consola: `python manage.py evaluar_busqueda` (acepta `--consultas otro_archivo.json`).

## Tests y calidad del código

Las herramientas de desarrollo están en `requirements-dev.txt` (incluye las de producción):

```powershell
pip install -r requirements-dev.txt
python manage.py test inventario       # suite completa
coverage run manage.py test inventario # suite con medición de cobertura
coverage report                        # falla si la cobertura baja del 90 %
ruff check .                           # estilo y errores comunes
```

La suite está en `inventario/tests/` y cubre permisos por rol, inventario, el flujo de préstamos,
mantenimiento, importación y exportación a Excel, correos, tareas programadas, códigos QR, auditoría,
búsqueda con IA (modelo semántico y Gemini simulados, nunca descargan modelos ni llaman a la API real), la política de seguridad de contenido y
el panel de administración. El CI ejecuta `ruff`, las migraciones pendientes, `check --deploy`, la suite
con cobertura y `pip-audit` en cada push.

## Despliegue en Azure

Arquitectura de producción:

| Componente | Servicio de Azure |
|---|---|
| Aplicación (Django + Gunicorn) | App Service en Linux, plan B1 |
| Base de datos | Azure Database for PostgreSQL – Flexible Server (Burstable B1ms, respaldos de 7 días) |
| Archivos estáticos | WhiteNoise, servidos por la misma aplicación |
| Integración y entrega continua | GitHub Actions (`.github/workflows/ci-cd.yml`) |
| Monitoreo de disponibilidad | Health check de App Service sobre `/salud/` |

### 1. Crear la infraestructura

Abre **Azure Cloud Shell** (ícono `>_` en el portal de Azure, modo Bash), clona el repositorio y ejecuta:

```bash
git clone https://github.com/NicoBarros/Proyecto-de-Titulo.git
cd Proyecto-de-Titulo
export APP_NAME=leica-inventario
export ADMIN_EMAIL=encargado@inacapmail.cl
export ADMIN_PASSWORD='una-clave-segura'
bash azure/crear_infraestructura.sh
```

`APP_NAME` define la URL (`https://APP_NAME.azurewebsites.net`) y debe ser única en Azure. El script crea
el grupo de recursos, el servidor PostgreSQL con su base, el plan y la aplicación, y configura las
variables de entorno, el comando de inicio, HTTPS obligatorio, TLS 1.2 y el health check. Al terminar
muestra la clave de la base de datos y el perfil de publicación.

Variables opcionales:

| Variable | Valor por defecto |
|---|---|
| `LOCATION` | `brazilsouth` (usa `chilecentral` si tu suscripción tiene esa región) |
| `RESOURCE_GROUP` | `rg-leica-inventario` |
| `PLAN_SKU` | `B1` (`F1` es gratuito, sin Always On y con 60 minutos de CPU al día) |
| `PYTHON_VERSION` | `3.14` (usa `3.13` si App Service aún no ofrece 3.14) |
| `PG_VERSION` | `17` |
| `GEMINI_API_KEY` | vacío |

### 2. Conectar GitHub Actions

En el repositorio de GitHub, **Settings → Secrets and variables → Actions**:

- **Secrets → New repository secret:** `AZURE_WEBAPP_PUBLISH_PROFILE`, con el XML completo que mostró el script.
- **Secrets → New repository secret:** `TAREAS_TOKEN`, con el token que mostró el script.
- **Variables → New repository variable:** `AZURE_WEBAPP_NAME`, con el valor de `APP_NAME`.

Desde ese momento, cada push a `main` ejecuta las pruebas contra PostgreSQL y, solo si todas pasan,
despliega en App Service. Los Pull Requests ejecutan las pruebas sin desplegar. Para el primer
despliegue, entra a **Actions → CI/CD → Run workflow**.

### 3. Operación

- En cada arranque, `startup.sh` aplica las migraciones, genera los archivos estáticos, crea el
  administrador (solo si no existe) e inicia Gunicorn.
- Los logs se ven en el portal, en **App Service → Log stream**.
- Cada 15 minutos, el workflow `.github/workflows/tareas.yml` llama a `POST /tareas/` con el token
  `TAREAS_TOKEN`: marca los préstamos vencidos como atrasados, envía los avisos pendientes, avisa de las
  solicitudes sin revisar fuera de plazo y una vez al mes evalúa la búsqueda. Localmente,
  lo mismo se ejecuta con `python manage.py tareas_programadas`.
- `GET /salud/` responde `{"estado": "ok", "base_de_datos": "ok"}` o un 503 si la base no está disponible.
- Azure respalda la base automáticamente (7 días, restauración a cualquier minuto). Además,
  `python manage.py respaldar` y `python manage.py restaurar` generan y restauran respaldos propios
  verificados con SHA-256. En un servidor propio, `RESPALDO_AUTOMATICO=True` hace que las tareas
  programadas generen un respaldo diario y avisen por correo a los administradores si falla. La política y los procedimientos están en [docs/respaldos.md](docs/respaldos.md).

## Estructura

```
leica_project/        Configuración de Django (settings, urls, wsgi)
inventario/
  models.py           Usuario, Equipo, Insumo, Solicitud, Movimiento, Bloqueo, Mantenimiento, Migracion
  servicios.py        Reglas de negocio: solicitudes, devoluciones, sanciones, mantenimiento, estados
  views/              Una vista por pantalla (inventario, solicitudes, mantenimiento, reportes, panel...)
  importar.py         Importación desde Excel
  exportar.py         Exportación a Excel y plantilla de importación
  notificaciones.py   Correos de aviso
  tareas.py           Tareas programadas (atrasos y avisos)
  seguridad.py        Registro de eventos de seguridad
  templates/          Plantillas HTML (correos en templates/inventario/correos/)
  static/             CSS, JavaScript e imágenes
  migrations/         Migraciones de la base de datos
  rag.py              Recuperación híbrida, generación con Gemini y verificación de citas
  privacidad.py       Exportación de datos personales, solicitudes de derechos, anonimización y conservación
  evaluacion_busqueda.py Evaluación mensual de la búsqueda con las consultas de referencia
  datos/              Consultas de referencia de la evaluación
  management/commands/ seed, respaldar, restaurar, marcar_atrasadas, tareas_programadas, crear_admin,
                      evaluar_busqueda, indexar_busqueda
  tests/              Suite de tests
azure/                Script de infraestructura
docs/respaldos.md     Política y procedimientos de respaldo
docs/privacidad.md    Registro de tratamiento de datos personales (Ley N.° 21.719)
```

Hubo un prototipo anterior en Node/Express. Ya no forma parte del proyecto y se conserva en la
etiqueta git `archivo/prototipo-node`.
